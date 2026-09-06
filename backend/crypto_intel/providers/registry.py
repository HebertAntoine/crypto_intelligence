"""Provider registry: capability -> ordered fallback chain.

Two jobs:
  1. Try providers in the configured order until one succeeds, so a dead source
     degrades the system instead of breaking it.
  2. In MOCK_MODE, replace every chain with the fixture provider, so the whole
     app runs offline.

Swapping a source is a `config/providers.yaml` edit. No business code changes.
"""

from __future__ import annotations

from typing import Any

from ..config_loader import providers_config
from ..core.enums import FetchStatus
from ..logging_setup import get_logger
from ..settings import get_settings
from .base import BaseProvider, FetchRequest, FetchResult, ProviderStatus

log = get_logger("providers.registry")


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}
        self._chains: dict[str, list[str]] = {}
        self._mock: BaseProvider | None = None
        self._built = False

    # --- construction -----------------------------------------------------

    def build(self) -> ProviderRegistry:
        if self._built:
            return self
        cfg = providers_config()
        self._chains = {k: list(v) for k, v in (cfg.get("capabilities") or {}).items()}
        provider_cfgs: dict[str, dict[str, Any]] = cfg.get("providers") or {}

        for name, cls in _provider_classes().items():
            try:
                self._providers[name] = cls(provider_cfgs.get(name, {}))
            except Exception as exc:  # a broken provider must not stop startup
                log.warning("provider_init_failed", provider=name, error=str(exc))

        from .fixtures import FixtureProvider

        self._mock = FixtureProvider()
        self._built = True
        return self

    # --- access -----------------------------------------------------------

    def get(self, name: str) -> BaseProvider | None:
        self.build()
        return self._providers.get(name)

    def chain(self, capability: str) -> list[BaseProvider]:
        """Providers for a capability, in priority order."""
        self.build()
        if get_settings().mock_mode:
            return [self._mock] if self._mock and self._mock.supports(capability) else []
        names = self._chains.get(capability, [])
        return [self._providers[n] for n in names if n in self._providers]

    def all_providers(self) -> list[BaseProvider]:
        self.build()
        return list(self._providers.values())

    async def statuses(self) -> list[ProviderStatus]:
        """Used by the /api/sources page - shows exactly what is and is not
        configured, so nothing is silently missing."""
        self.build()
        if get_settings().mock_mode and self._mock:
            return [ProviderStatus(name="fixtures", available=True, reason="MOCK_MODE active")]
        out = []
        for p in self._providers.values():
            try:
                out.append(await p.available())
            except Exception as exc:
                out.append(ProviderStatus(name=p.name, available=False, reason=str(exc)))
        return out

    # --- fetching ---------------------------------------------------------

    async def fetch(self, request: FetchRequest) -> FetchResult:
        """Walk the chain until something works.

        Returns the FIRST failure verbatim when the whole chain fails, because
        "Farside blocks automated access" is far more useful to the user than
        a generic "no data".
        """
        chain = self.chain(request.capability)
        if not chain:
            if get_settings().mock_mode:
                # Deliberate: some domains have NO fixture, because inventing
                # them would be exactly the fabrication this project forbids.
                # Whale flows in particular must never be synthesised.
                return FetchResult.failure(
                    FetchStatus.NOT_CONFIGURED, "registry",
                    f"UNAVAILABLE - '{request.capability}' has no mock fixture by design; "
                    "this domain requires a real provider and is never simulated",
                )
            return FetchResult.failure(
                FetchStatus.NOT_CONFIGURED,
                "registry",
                f"UNAVAILABLE - no provider registered for '{request.capability}'",
            )

        first_failure: FetchResult | None = None
        for provider in chain:
            status = await provider.available()
            if not status.available:
                if first_failure is None:
                    first_failure = FetchResult.failure(
                        FetchStatus.NOT_CONFIGURED, provider.name, status.reason
                    )
                continue
            try:
                result = await provider.fetch(request)
            except Exception as exc:
                # A provider bug must never take down a collection run.
                log.warning(
                    "provider_raised", provider=provider.name,
                    capability=request.capability, error=str(exc),
                )
                result = FetchResult.failure(FetchStatus.NETWORK_ERROR, provider.name, str(exc))

            if result.ok:
                return result
            if first_failure is None:
                first_failure = result
            log.info(
                "provider_fallback", capability=request.capability,
                provider=provider.name, status=result.status.value,
            )

        return first_failure or FetchResult.failure(
            FetchStatus.NO_DATA, "registry", f"No provider returned data for {request.capability}"
        )


def _provider_classes() -> dict[str, type[BaseProvider]]:
    """Imported lazily so a missing optional dependency cannot break startup."""
    from .defi.defillama import DefiLlamaProvider, DefiLlamaRWAProvider
    from .derivatives.binance_futures import BinanceFuturesProvider
    from .derivatives.coinglass import CoinglassProvider
    from .etf.coinglass_etf import CoinglassETFProvider, SoSoValueProvider
    from .etf.csv_import import ETFCSVProvider
    from .etf.farside import FarsideProvider
    from .macro.fred import FredProvider
    from .macro.stooq import StooqProvider
    from .macro.yahoo import YahooFinanceProvider
    from .market.binance import BinanceSpotProvider
    from .market.coinbase import CoinbaseSpotProvider
    from .market.coingecko import CoinGeckoProvider
    from .market.kraken import KrakenSpotProvider
    from .news.rss import RSSNewsProvider, RSSRegulationProvider
    from .onchain.blockchain_info import BlockchainInfoProvider
    from .onchain.blockchair import BlockchairBTCProvider, BlockchairETHProvider
    from .onchain.solana_rpc import SolanaRPCProvider
    from .stablecoins.defillama_stables import DefiLlamaStablecoinsProvider
    from .whales.optional_whales import (
        ArkhamProvider,
        CryptoQuantProvider,
        GlassnodeProvider,
        NansenProvider,
    )

    classes: list[type[BaseProvider]] = [
        BinanceSpotProvider, CoinbaseSpotProvider, KrakenSpotProvider, CoinGeckoProvider,
        BinanceFuturesProvider, CoinglassProvider,
        ETFCSVProvider, FarsideProvider, CoinglassETFProvider, SoSoValueProvider,
        BlockchainInfoProvider, BlockchairBTCProvider, BlockchairETHProvider, SolanaRPCProvider,
        DefiLlamaProvider, DefiLlamaRWAProvider, DefiLlamaStablecoinsProvider,
        FredProvider, YahooFinanceProvider, StooqProvider,
        RSSNewsProvider, RSSRegulationProvider,
        GlassnodeProvider, CryptoQuantProvider, NansenProvider, ArkhamProvider,
    ]
    return {c.name: c for c in classes}


_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry().build()
    return _registry


def reset_registry() -> None:
    """Tests toggling MOCK_MODE need a clean registry."""
    global _registry
    _registry = None
