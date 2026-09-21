"""Timestamped transcripts: reading them, finding numbers and cryptos in them.

Accepted inputs, as they come from the places a member can legitimately get
a transcript:

    [12:31] texte ...                 our own format
    12:31 texte ...                   one line per passage
    12:31                             YouTube « Afficher la transcription »,
    texte ...                         copied as is
    SRT / WebVTT                      subtitle files

Nothing here downloads or records anything.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_TS = r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:[.,]\d{1,3})?"
_BRACKETED = re.compile(rf"^\s*[\[(]\s*{_TS}\s*[\])]\s*(.*)$")
_LEADING = re.compile(rf"^\s*{_TS}\s+(\S.*)$")
_ALONE = re.compile(rf"^\s*{_TS}\s*$")
_CUE = re.compile(rf"^\s*{_TS}\s*-->\s*{_TS}")


@dataclass(slots=True)
class Segment:
    start_s: int
    text: str


def _seconds(h: str | None, m: str, s: str) -> int:
    return int(h or 0) * 3600 + int(m) * 60 + int(s)


def format_ts(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    h, rest = divmod(int(seconds), 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def clean(text: str) -> str:
    """Whitespace and subtitle markup only. Words are never changed."""

    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[(musique|music|applaudissements)\]", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def parse(raw: str) -> list[Segment]:
    segments: list[Segment] = []
    current: Segment | None = None

    def push(start: int, text: str) -> None:
        nonlocal current
        current = Segment(start, clean(text))
        segments.append(current)

    for line in raw.replace("\r", "").split("\n"):
        if (not line.strip() or line.strip().upper() == "WEBVTT" or line.strip().isdigit()
                or line.lstrip().startswith("#")):
            continue
        if m := _CUE.match(line):
            push(_seconds(*m.groups()[:3]), "")
        elif m := _BRACKETED.match(line):
            push(_seconds(*m.groups()[:3]), m.group(4))
        elif m := _ALONE.match(line):
            push(_seconds(*m.groups()), "")
        elif m := _LEADING.match(line):
            push(_seconds(*m.groups()[:3]), m.group(4))
        elif current is not None:
            current.text = clean(f"{current.text} {line}")
        else:
            push(0, line)
    # Text without a single timestamp is not a transcript we can cite.
    if not any(_CUE.match(x) or _BRACKETED.match(x) or _ALONE.match(x) or _LEADING.match(x)
               for x in raw.split("\n")):
        return []
    merged = [s for s in segments if s.text]
    merged.sort(key=lambda s: s.start_s)
    return merged


def render(segments: list[Segment]) -> str:
    return "\n".join(f"[{format_ts(s.start_s)}] {s.text}" for s in segments)


# --- numbers -----------------------------------------------------------------

# Thousands are grouped with spaces in French ("68 000"); "," or "." is the
# decimal mark ("2,4531" / "2.4531").
_NUMBER = re.compile(
    r"(?<![\w.,])(\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)(?:[,.](\d+))?(?:\s*(k|K)\b)?"
)


def numbers_in(text: str) -> list[float]:
    """Every figure written in a passage: 2,4531 / 2.4531 / 68 000 / 68k."""

    found: list[float] = []
    for m in _NUMBER.finditer(text):
        whole, decimals, thousand = m.groups()
        digits = re.sub(r"[ \u00a0\u202f]", "", whole)
        value = float(f"{digits}.{decimals}" if decimals else digits)
        found.append(value * 1000 if thousand else value)
    return found


def same_value(a: float, b: float) -> bool:
    return abs(a - b) <= max(abs(a), abs(b)) * 1e-6


def value_in(value: float, text: str) -> bool:
    return any(same_value(value, n) for n in numbers_in(text))


# --- cryptos -----------------------------------------------------------------

ASSET_ALIASES: dict[str, tuple[str, ...]] = {
    "BTC": ("btc", "bitcoin", "bitcoins"),
    "ETH": ("eth", "ether", "ethereum"),
    "SOL": ("sol", "solana"),
    "XRP": ("xrp", "ripple"),
    "BNB": ("bnb", "binance coin"),
    "ADA": ("ada", "cardano"),
    "DOGE": ("doge", "dogecoin"),
    "AVAX": ("avax", "avalanche"),
    "LINK": ("link", "chainlink"),
    "DOT": ("polkadot",),
    "SUI": ("sui",),
    "TRX": ("trx", "tron"),
    "TON": ("toncoin",),
    "LTC": ("ltc", "litecoin"),
    "HBAR": ("hbar", "hedera"),
    "PEPE": ("pepe",),
    "SHIB": ("shib", "shiba"),
    "NEAR": ("near protocol",),
    "APT": ("aptos",),
    "ARB": ("arbitrum",),
    "OP": ("optimism",),
    "INJ": ("injective",),
    "RNDR": ("render",),
    "FET": ("fetch.ai",),
    "TAO": ("bittensor",),
    "KAS": ("kaspa",),
    "ONDO": ("ondo",),
    "HYPE": ("hyperliquid",),
}
# Market-wide terms: mentions, never a crypto sheet.
MARKET_TERMS = ("dominance", "usdt.d", "btc.d", "total2", "total3")


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


_ALIAS_RE = {
    symbol: re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(a) for a in aliases) + r")(?![a-z0-9])")
    for symbol, aliases in ASSET_ALIASES.items()
}


def assets_in(text: str) -> list[str]:
    norm = _norm(text)
    hits = [(m.start(), symbol) for symbol, rx in _ALIAS_RE.items() for m in rx.finditer(norm)]
    # "dominance du bitcoin" is about the market, not a BTC analysis.
    hits = [(pos, s) for pos, s in hits
            if not (s == "BTC" and "dominance" in norm[max(0, pos - 25):pos + 25])]
    ordered: list[str] = []
    for _, symbol in sorted(hits):
        if symbol not in ordered:
            ordered.append(symbol)
    return ordered


def mentions(segments: list[Segment]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for seg in segments:
        for symbol in assets_in(seg.text):
            counts[symbol] = counts.get(symbol, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def topic_windows(segments: list[Segment]) -> dict[str, list[Segment]]:
    """The passages spoken while each crypto is the subject.

    The subject is the crypto last named. A passage naming a crypto belongs
    to it; the passages after it too, until another crypto is named. The
    passages before any crypto is named belong to no one (intro, macro).
    """

    windows: dict[str, list[Segment]] = {}
    topic: str | None = None
    for seg in segments:
        named = assets_in(seg.text)
        for symbol in named:
            if symbol != topic:
                windows.setdefault(symbol, [])
                if seg not in windows[symbol]:
                    windows[symbol].append(seg)
        if named:
            topic = named[-1]
        if topic is not None and seg not in windows.setdefault(topic, []):
            windows[topic].append(seg)
    return windows


def near(segments: list[Segment], timestamp_s: int | None, span_s: int = 45) -> list[Segment]:
    if timestamp_s is None:
        return []
    return [s for s in segments if abs(s.start_s - timestamp_s) <= span_s]


def quote_matches(quote: str, text: str) -> bool:
    """The quote is taken from the passage: most of its words are there, in order-free form."""

    q = [w for w in re.findall(r"[a-z0-9]+", _norm(quote)) if len(w) > 2]
    if not q:
        return False
    t = set(re.findall(r"[a-z0-9]+", _norm(text)))
    return sum(w in t for w in q) / len(q) >= 0.7
