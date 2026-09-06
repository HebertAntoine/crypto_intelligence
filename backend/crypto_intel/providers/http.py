"""Shared async HTTP client: caching, rate limiting, honest identification.

Three things this module deliberately does NOT do, because the project rules
forbid them: rotate User-Agents, use proxies to evade blocks, or retry past a
403/anti-bot response. A refusal from a source is final.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx

from ..core.enums import FetchStatus
from ..logging_setup import get_logger
from ..settings import get_settings

log = get_logger("providers.http")

# Responses that mean "this source refuses automated access". We stop; we do
# not attempt to look like a different client.
_BLOCKING_STATUSES = {401, 402, 403, 407, 451}
_BLOCK_MARKERS = ("cf-browser-verification", "captcha", "just a moment", "enable javascript")


class RateLimiter:
    """Simple per-provider spacing, enough for a single-user local tool."""

    def __init__(self, per_minute: int) -> None:
        self.min_interval = 60.0 / per_minute if per_minute > 0 else 0.0
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if self.min_interval <= 0:
            return
        async with self._lock:
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


class DiskCache:
    """TTL cache on disk. Keeps free-tier APIs (CoinGecko especially) usable
    and makes repeated analysis runs cheap."""

    def __init__(self, directory: Path) -> None:
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.dir / f"{hashlib.sha1(key.encode()).hexdigest()}.json"

    def get(self, key: str, ttl: int) -> Any | None:
        p = self._path(key)
        if not p.exists():
            return None
        try:
            if time.time() - p.stat().st_mtime > ttl:
                return None
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def set(self, key: str, value: Any) -> None:
        try:
            self._path(key).write_text(json.dumps(value), encoding="utf-8")
        except (OSError, TypeError) as exc:
            log.debug("cache_write_failed", error=str(exc))

    def clear(self) -> int:
        n = 0
        for f in self.dir.glob("*.json"):
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
        return n


class HTTPResult:
    __slots__ = ("data", "from_cache", "http_status", "message", "status")

    def __init__(
        self,
        status: FetchStatus,
        data: Any = None,
        message: str = "",
        from_cache: bool = False,
        http_status: int | None = None,
    ) -> None:
        self.status = status
        self.data = data
        self.message = message
        self.from_cache = from_cache
        self.http_status = http_status

    @property
    def ok(self) -> bool:
        return self.status is FetchStatus.OK


class HTTPClient:
    """One shared client for the whole process."""

    _instance: HTTPClient | None = None

    def __init__(self) -> None:
        s = get_settings()
        self._settings = s
        self._client: httpx.AsyncClient | None = None
        self._limiters: dict[str, RateLimiter] = {}
        self._cache = DiskCache(s.cache_dir)

    @classmethod
    def instance(cls) -> HTTPClient:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._settings.http_timeout),
                headers={
                    # Identifies the tool honestly. Never rotated to evade blocks.
                    "User-Agent": self._settings.http_user_agent,
                    "Accept": "application/json, text/plain, */*",
                },
                follow_redirects=True,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    def limiter(self, provider: str, per_minute: int) -> RateLimiter:
        if provider not in self._limiters:
            self._limiters[provider] = RateLimiter(per_minute)
        return self._limiters[provider]

    async def get_json(
        self,
        url: str,
        *,
        provider: str = "unknown",
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        cache_ttl: int = 300,
        rate_limit_per_min: int = 60,
        retries: int = 2,
    ) -> HTTPResult:
        return await self._request(
            url,
            provider=provider,
            params=params,
            headers=headers,
            cache_ttl=cache_ttl,
            rate_limit_per_min=rate_limit_per_min,
            retries=retries,
            expect="json",
        )

    async def get_text(
        self,
        url: str,
        *,
        provider: str = "unknown",
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        cache_ttl: int = 300,
        rate_limit_per_min: int = 60,
        retries: int = 1,
    ) -> HTTPResult:
        return await self._request(
            url,
            provider=provider,
            params=params,
            headers=headers,
            cache_ttl=cache_ttl,
            rate_limit_per_min=rate_limit_per_min,
            retries=retries,
            expect="text",
        )

    async def post_json(
        self,
        url: str,
        *,
        provider: str = "unknown",
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        cache_ttl: int = 0,
        rate_limit_per_min: int = 30,
    ) -> HTTPResult:
        """POST for JSON-RPC endpoints (Solana). Not cached by default."""
        cache_key = f"POST:{url}:{json.dumps(payload, sort_keys=True)}"
        if cache_ttl > 0 and self._settings.cache_enabled:
            cached = self._cache.get(cache_key, cache_ttl)
            if cached is not None:
                return HTTPResult(FetchStatus.OK, cached, from_cache=True)

        await self.limiter(provider, rate_limit_per_min).acquire()
        try:
            client = await self._get_client()
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in _BLOCKING_STATUSES:
                return HTTPResult(
                    FetchStatus.BLOCKED_BY_SOURCE,
                    message=f"HTTP {resp.status_code} - source refuses automated access",
                    http_status=resp.status_code,
                )
            if resp.status_code == 429:
                return HTTPResult(FetchStatus.RATE_LIMITED, message="HTTP 429", http_status=429)
            resp.raise_for_status()
            data = resp.json()
            if cache_ttl > 0 and self._settings.cache_enabled:
                self._cache.set(cache_key, data)
            return HTTPResult(FetchStatus.OK, data, http_status=resp.status_code)
        except httpx.HTTPError as exc:
            return HTTPResult(FetchStatus.NETWORK_ERROR, message=str(exc))
        except (json.JSONDecodeError, ValueError) as exc:
            return HTTPResult(FetchStatus.PARSE_ERROR, message=str(exc))

    async def _request(
        self,
        url: str,
        *,
        provider: str,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
        cache_ttl: int,
        rate_limit_per_min: int,
        retries: int,
        expect: str,
    ) -> HTTPResult:
        cache_key = f"{url}:{json.dumps(params or {}, sort_keys=True)}:{expect}"

        if cache_ttl > 0 and self._settings.cache_enabled:
            cached = self._cache.get(cache_key, cache_ttl)
            if cached is not None:
                return HTTPResult(FetchStatus.OK, cached, from_cache=True)

        limiter = self.limiter(provider, rate_limit_per_min)
        last_error = ""

        for attempt in range(retries + 1):
            await limiter.acquire()
            try:
                client = await self._get_client()
                resp = await client.get(url, params=params, headers=headers)

                # A source refusing automated access is a final answer.
                # We never retry it with different headers or via a proxy.
                if resp.status_code in _BLOCKING_STATUSES:
                    log.info(
                        "source_blocks_automated_access",
                        provider=provider,
                        status=resp.status_code,
                        url=url,
                    )
                    return HTTPResult(
                        FetchStatus.BLOCKED_BY_SOURCE,
                        message=(
                            f"HTTP {resp.status_code} - this source refuses automated access. "
                            "No bypass attempted (project policy)."
                        ),
                        http_status=resp.status_code,
                    )

                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", 2 ** attempt))
                    if attempt < retries:
                        await asyncio.sleep(min(retry_after, 10))
                        continue
                    return HTTPResult(
                        FetchStatus.RATE_LIMITED, message="HTTP 429 rate limited", http_status=429
                    )

                if resp.status_code >= 500:
                    last_error = f"HTTP {resp.status_code}"
                    if attempt < retries:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    return HTTPResult(
                        FetchStatus.NETWORK_ERROR, message=last_error, http_status=resp.status_code
                    )

                resp.raise_for_status()

                if expect == "json":
                    data = resp.json()
                else:
                    data = resp.text
                    low = data[:2000].lower()
                    # An HTML challenge page served with HTTP 200 is still a refusal.
                    if any(m in low for m in _BLOCK_MARKERS):
                        return HTTPResult(
                            FetchStatus.BLOCKED_BY_SOURCE,
                            message="Source returned an anti-bot challenge page. No bypass attempted.",
                            http_status=resp.status_code,
                        )

                if cache_ttl > 0 and self._settings.cache_enabled:
                    self._cache.set(cache_key, data)
                return HTTPResult(FetchStatus.OK, data, http_status=resp.status_code)

            except httpx.TimeoutException as exc:
                last_error = f"timeout: {exc}"
                if attempt < retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return HTTPResult(FetchStatus.NETWORK_ERROR, message=last_error)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                if attempt < retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return HTTPResult(FetchStatus.NETWORK_ERROR, message=last_error)
            except (json.JSONDecodeError, ValueError) as exc:
                return HTTPResult(FetchStatus.PARSE_ERROR, message=str(exc))

        return HTTPResult(FetchStatus.NETWORK_ERROR, message=last_error or "unknown error")

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None


def get_http() -> HTTPClient:
    return HTTPClient.instance()
