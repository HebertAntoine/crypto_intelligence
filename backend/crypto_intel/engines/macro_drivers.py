"""The fifteen macro engines watched permanently, and the five that matter now.

Not technical analysis: no RSI, no moving average, nothing about the shape of
the price. These are the monetary, fiscal, financial, regulatory and liquidity
forces crypto trades inside. The technical reading lives in its own family and
the two are never mixed.

    15 drivers watched  ->  importance recomputed  ->  the 5 that explain the
    current regime  ->  the other 10 one tap away

Three rules the module is built on:

  * **importance is not direction.** How much a driver deserves attention and
    which way it points are two scales with two vocabularies. A central bank
    decision due tomorrow is CRITICAL and UNKNOWN at the same time, and that
    is the honest reading, not a gap to fill;
  * **no macro shortcut.** « rate cut = crypto up », « CPI down = crypto up »
    and « weaker dollar = crypto up » are forbidden. A driver points somewhere
    only through a transmission channel that is written down, and when its own
    inputs disagree the answer is MIXED;
  * **a value is published, not refreshed.** Monthly data does not change every
    three hours. The importance of a driver may be recomputed at every cycle;
    the value itself keeps the date it was published, and the next publication
    is named.

Deterministic: every score here is arithmetic over measured series. No model
writes a state, a direction or a number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ..core.enums import Asset
from .factor_semantics import fr_number
from .market_radar import AttentionLevel, EventDirection, RadarCategory

# --- what a driver is ------------------------------------------------------------------------

FAVORABLE = EventDirection.FAVORABLE
UNFAVORABLE = EventDirection.UNFAVORABLE
NEUTRAL = EventDirection.NEUTRAL
MIXED = EventDirection.MIXED
UNKNOWN = EventDirection.UNKNOWN


@dataclass(frozen=True)
class Driver:
    """The identity of a driver - what it is, never what it currently says."""

    key: str
    emoji: str
    name: str
    category: RadarCategory
    #: Why this moves crypto at all, in plain words. Stable: it describes the
    #: channel, not today's reading.
    channel: str
    #: Events whose titles belong to this driver, for « next publication ».
    event_words: tuple[str, ...] = ()


DRIVERS: tuple[Driver, ...] = (
    Driver("fed", "🏛️", "Fed / taux américains", RadarCategory.CENTRAL_BANK,
           "La Fed fixe le taux sans risque. Il commande le coût de l'argent, donc "
           "l'appétit pour les actifs qui ne versent aucun rendement.",
           ("fomc", "federal reserve", "réserve fédérale", "powell")),
    Driver("inflation", "🇺🇸", "Inflation US", RadarCategory.MACRO,
           "L'inflation décide de la marge de manœuvre de la Fed. C'est l'écart avec "
           "les attentes qui fait bouger les marchés, pas le niveau seul.",
           ("cpi", "consumer price", "inflation", "pce", "personal income")),
    Driver("employment", "👷", "Emploi US", RadarCategory.MACRO,
           "L'emploi pèse sur la politique monétaire : un marché du travail qui "
           "ralentit ouvre la porte à des taux plus bas, mais souvent parce que "
           "l'économie faiblit.",
           ("payroll", "employment situation", "jobless", "unemployment")),
    Driver("yields", "📈", "Rendements US", RadarCategory.RATES,
           "Le rendement réel est le coût d'opportunité de détenir une crypto : "
           "plus il monte, plus renoncer à un rendement sûr coûte cher.",
           ("treasury auction", "adjudication")),
    Driver("dollar", "💵", "Dollar", RadarCategory.FX,
           "Le dollar est l'unité dans laquelle la crypto est cotée et la jauge de "
           "la liquidité mondiale. Un dollar fort resserre les conditions partout.",
           ()),
    Driver("liquidity", "💧", "Liquidité banque centrale", RadarCategory.LIQUIDITY,
           "Bilan de la Fed, compte du Trésor et prises en pension : ce qui reste "
           "de liquidités dans le système bancaire pour alimenter les actifs risqués.",
           ()),
    Driver("credit", "🏦", "Conditions de crédit", RadarCategory.FINANCIAL_RISK,
           "Les primes de risque séparent une correction d'un vrai stress : des "
           "actions qui baissent avec des primes calmes n'ont pas le même sens que "
           "des actions qui baissent avec des primes qui s'écartent.",
           ()),
    Driver("ecb", "🇪🇺", "BCE / Europe", RadarCategory.CENTRAL_BANK,
           "La BCE agit sur la liquidité en euro et sur le dollar par le taux de "
           "change. Son poids sur la crypto reste inférieur à celui de la Fed.",
           ("bce", "ecb", "lagarde")),
    Driver("boj", "🇯🇵", "BoJ / Japon", RadarCategory.CENTRAL_BANK,
           "Le Japon finance une partie des positions mondiales à effet de levier. "
           "Un resserrement japonais peut forcer des débouclages bien au-delà du yen.",
           ("boj", "banque du japon", "bank of japan")),
    Driver("oil", "🛢️", "Pétrole / énergie", RadarCategory.ENERGY,
           "Le pétrole entre dans l'analyse comme intrant d'inflation : il agit sur "
           "la crypto par les anticipations de taux, jamais directement.",
           ()),
    Driver("etf_flows", "🪙", "Flux ETF crypto", RadarCategory.ETF,
           "Les ETF au comptant mesurent de l'argent institutionnel réellement "
           "engagé, par opposition aux récits.",
           ()),
    Driver("stablecoins", "💰", "Stablecoins", RadarCategory.CRYPTO_NATIVE,
           "L'offre de stablecoins est la mesure la plus proche d'une masse "
           "monétaire crypto : des munitions disponibles dans l'écosystème.",
           ()),
    Driver("regulation", "⚖️", "Réglementation", RadarCategory.REGULATION,
           "Le cadre légal décide de ce qui est possible. Un texte discuté n'est "
           "pas un texte adopté, et la distinction est conservée à chaque étape.",
           ("sec", "règlement", "regulation", "bill", "mica")),
    Driver("geopolitics", "🌍", "Risque géopolitique", RadarCategory.GEOPOLITICS,
           "La géopolitique n'atteint la crypto que par des canaux mesurables : "
           "pétrole, dollar, obligations, volatilité.",
           ()),
    Driver("risk_markets", "📊", "Marchés risqués", RadarCategory.MACRO,
           "Actions et volatilité décrivent le régime de risque dans lequel la "
           "crypto évolue, sans en être la cause.",
           ()),
)

BY_KEY = {driver.key: driver for driver in DRIVERS}


# --- what a driver currently says --------------------------------------------------------------


@dataclass
class Value:
    """One figure shown under a driver, with the period it describes."""

    label: str
    value: str
    change: str = ""
    period: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "value": self.value, "change": self.change,
                "period": self.period, "source": self.source}


@dataclass
class Reading:
    driver: Driver
    #: Short state, in French: « Pression négative », « Soutien », « À surveiller ».
    state: str = "Non mesuré"
    direction: EventDirection = UNKNOWN
    attention: AttentionLevel = AttentionLevel.LOW
    importance: int = 0
    #: Why the importance is what it is - one line per contribution.
    importance_reasons: list[str] = field(default_factory=list)
    summary: str = ""
    watching: str = ""
    values: list[Value] = field(default_factory=list)
    last_release: datetime | None = None
    next_release: datetime | None = None
    next_release_label: str = ""
    available: bool = True
    unavailable_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.driver.key,
            "emoji": self.driver.emoji,
            "name": self.driver.name,
            "category": self.driver.category.value,
            "channel": self.driver.channel,
            "state": self.state,
            "direction": self.direction.value,
            "attention": self.attention.value,
            "importance": self.importance,
            "importance_reasons": list(self.importance_reasons),
            "summary": self.summary,
            "watching": self.watching,
            "values": [v.to_dict() for v in self.values],
            "last_release": self.last_release.isoformat() if self.last_release else None,
            "next_release": self.next_release.isoformat() if self.next_release else None,
            "next_release_label": self.next_release_label,
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
        }


# --- importance ---------------------------------------------------------------------------------

#: What a driver is worth before anything happens to it. A central bank can
#: reorder a whole market; the oil price rarely does on its own.
BASE_IMPORTANCE: dict[RadarCategory, int] = {
    RadarCategory.CENTRAL_BANK: 55,
    RadarCategory.MACRO: 45,
    RadarCategory.RATES: 45,
    RadarCategory.FINANCIAL_RISK: 40,
    RadarCategory.LIQUIDITY: 35,
    RadarCategory.FX: 35,
    RadarCategory.ETF: 35,
    RadarCategory.REGULATION: 30,
    RadarCategory.ENERGY: 25,
    RadarCategory.GEOPOLITICS: 25,
    RadarCategory.CRYPTO_NATIVE: 30,
    RadarCategory.OTHER: 20,
}

#: An upcoming date lifts a driver as it approaches, and only then.
PROXIMITY: tuple[tuple[timedelta, int, str], ...] = (
    (timedelta(hours=6), 40, "échéance dans moins de 6 h"),
    (timedelta(hours=24), 30, "échéance dans moins de 24 h"),
    (timedelta(days=3), 18, "échéance dans moins de 3 jours"),
    (timedelta(days=7), 8, "échéance dans la semaine"),
)

#: How long a publication keeps lifting its driver. Deliberately per category:
#: a rule change keeps mattering long after a jobs report stops.
FRESH_RELEASE: dict[RadarCategory, timedelta] = {
    RadarCategory.CENTRAL_BANK: timedelta(hours=48),
    RadarCategory.MACRO: timedelta(hours=30),
    RadarCategory.RATES: timedelta(hours=12),
    RadarCategory.FINANCIAL_RISK: timedelta(hours=72),
    RadarCategory.LIQUIDITY: timedelta(hours=36),
    RadarCategory.FX: timedelta(hours=12),
    RadarCategory.ETF: timedelta(hours=24),
    RadarCategory.REGULATION: timedelta(hours=72),
    RadarCategory.ENERGY: timedelta(hours=24),
    RadarCategory.GEOPOLITICS: timedelta(hours=48),
    RadarCategory.CRYPTO_NATIVE: timedelta(hours=36),
    RadarCategory.OTHER: timedelta(hours=12),
}

ATTENTION_FROM_SCORE: tuple[tuple[int, AttentionLevel], ...] = (
    (85, AttentionLevel.CRITICAL),
    (70, AttentionLevel.HIGH),
    (50, AttentionLevel.MODERATE),
    (30, AttentionLevel.LOW),
    (0, AttentionLevel.NONE),
)


def attention_of(score: int) -> AttentionLevel:
    for floor, level in ATTENTION_FROM_SCORE:
        if score >= floor:
            return level
    return AttentionLevel.NONE


@dataclass
class Score:
    """An importance built by addition, so it can be explained line by line."""

    points: int = 0
    reasons: list[str] = field(default_factory=list)

    def add(self, points: int, reason: str) -> None:
        if points:
            self.points += points
            self.reasons.append(f"{reason} ({points:+d})")

    @property
    def clamped(self) -> int:
        return max(0, min(100, self.points))


# --- reading the series -------------------------------------------------------------------------


@dataclass
class Context:
    """Everything the readers share: the data as of now, and what is scheduled."""

    view: Any
    now: datetime
    events: list[Any] = field(default_factory=list)

    def points(self, metric: str) -> list[Any]:
        try:
            return self.view.points(metric)
        except Exception:  # a missing series is a hole, never a zero
            return []

    def latest(self, metric: str) -> Any | None:
        points = self.points(metric)
        return points[-1] if points else None

    def change(self, metric: str, days: int) -> tuple[float | None, float | None, float | None]:
        """(latest, absolute change, percent change) over the window, or Nones."""

        points = self.points(metric)
        if not points:
            return None, None, None
        last = points[-1]
        cutoff = last.timestamp - timedelta(days=days)
        earlier = [p for p in points if p.timestamp <= cutoff]
        if not earlier:
            return last.value, None, None
        base = earlier[-1].value
        delta = last.value - base
        return last.value, delta, (delta / abs(base) * 100 if base else None)

    def abnormality(self, metric: str, days: int) -> float | None:
        """Where the current move sits among past moves of the same length, 0..1.

        0.9 means: larger than ninety per cent of the changes this series has
        made over this many days. It ranks a move, it never predicts one.
        """

        points = self.points(metric)
        if len(points) < 30:
            return None
        values = [(p.timestamp, p.value) for p in points]
        moves: list[float] = []
        step = timedelta(days=days)
        index = 0
        for i, (stamp, value) in enumerate(values):
            while index < i and values[index][0] < stamp - step:
                index += 1
            base = values[index][1]
            if base:
                moves.append(abs(value - base))
        if len(moves) < 20:
            return None
        current = moves[-1]
        return sum(1 for m in moves if m <= current) / len(moves)

    def next_event(self, driver: Driver) -> Any | None:
        """The soonest scheduled event whose title belongs to this driver."""

        if not driver.event_words:
            return None
        best = None
        for event in self.events:
            when = getattr(event, "scheduled_at", None)
            if when is None or when < self.now:
                continue
            title = f"{getattr(event, 'title', '')}".lower()
            if any(word in title for word in driver.event_words) and (
                    best is None or when < best.scheduled_at):
                best = event
        return best


#: Official calendars publish in English; the reader is shown French. The
#: original title stays in the event itself, for anyone checking the source.
_TITLE_FR: tuple[tuple[tuple[str, ...], str], ...] = (
    (("fomc", "monetary policy decision"), "Décision de la Fed sur les taux"),
    (("personal income",), "Revenus et dépenses des ménages (PCE)"),
    (("consumer price", "cpi"), "Inflation américaine (CPI)"),
    (("employment situation", "nonfarm"), "Rapport sur l'emploi américain"),
    (("gdp",), "PIB américain"),
    (("treasury auction",), "Adjudication du Trésor américain"),
)


def title_fr(title: str) -> str:
    low = (title or "").lower()
    for words, label in _TITLE_FR:
        if any(word in low for word in words):
            return label
    return title


def _usd_bn(value: float) -> str:
    return f"{fr_number(value / 1000, 1)} Md$"


def _pct(value: float, digits: int = 2, *, signed: bool = False) -> str:
    return f"{fr_number(value, digits, signed=signed)} %"


def _period_fr(stamp: datetime | None) -> str:
    if stamp is None:
        return ""
    return f"{stamp.day} {MONTHS_FR[stamp.month - 1]} {stamp.year}"


MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
             "septembre", "octobre", "novembre", "décembre"]


# --- the fifteen readers -------------------------------------------------------------------------
#
# Each one answers the same three questions from measured series: what is the
# state, which way does it point through its own channel, and what do we watch
# next. None of them may invent a figure, and each says plainly when its source
# is not connected.


def _unavailable(driver: Driver, reason: str) -> Reading:
    """A driver with no data is declared, never shown as neutral.

    « Neutre » is a measurement: it says the driver was read and found to push
    neither way. A missing source has not been read at all.
    """

    return Reading(driver=driver, state="Source non branchée", direction=UNKNOWN,
                   attention=AttentionLevel.LOW, importance=0,
                   summary=f"{reason} Rien n'en est déduit.",
                   available=False, unavailable_reason=reason)


def read_fed(ctx: Context, driver: Driver) -> Reading:
    upper = ctx.latest("cb.fed.target_upper")
    lower = ctx.latest("cb.fed.target_lower")
    effr = ctx.latest("macro.fed_funds_rate")
    if upper is None and effr is None:
        return _unavailable(driver, "Aucun taux directeur américain n'est collecté.")
    reading = Reading(driver=driver)
    if upper is not None and lower is not None:
        reading.values.append(Value("Fourchette cible", f"{_pct(lower.value, 2)} – {_pct(upper.value, 2)}",
                                    period=_period_fr(upper.timestamp), source="Fed de New York"))
        reading.last_release = upper.timestamp
    if effr is not None:
        reading.values.append(Value("Taux effectif (EFFR)", _pct(effr.value, 2),
                                    period=_period_fr(effr.timestamp), source="Fed de New York"))
        reading.last_release = reading.last_release or effr.timestamp

    _, change_90d, _ = ctx.change("macro.fed_funds_rate", 90)
    easing = change_90d is not None and change_90d <= -0.1
    tightening = change_90d is not None and change_90d >= 0.1
    if change_90d is not None:
        reading.values.append(Value("Évolution sur 90 jours", f"{fr_number(change_90d * 100, 0, signed=True)} pb",
                                    period="90 jours", source="Fed de New York"))

    event = ctx.next_event(driver)
    hours = None
    if event is not None:
        reading.next_release = event.scheduled_at
        reading.next_release_label = title_fr(getattr(event, "title", "Décision de la Fed"))
        hours = (event.scheduled_at - ctx.now).total_seconds() / 3600

    # Direction. A rate path is not a verdict: an easing cycle driven by a
    # deteriorating economy is not the easing cycle of a solid one, which is
    # why the credit reading is consulted before any direction is claimed.
    stressed = _credit_is_stressed(ctx)
    if hours is not None and hours <= 72:
        reading.direction = UNKNOWN
        reading.state = "Décision imminente"
        reading.summary = (
            f"La décision tombe dans {int(hours)} h. Le sens dépendra de l'écart entre la "
            "décision et ce que le marché attendait, pas de la décision elle-même : "
            "tant que le résultat n'est pas publié, la direction reste inconnue.")
    elif easing and stressed:
        reading.direction = MIXED
        reading.state = "Assouplissement en contexte tendu"
        reading.summary = (
            "La Fed a baissé ses taux sur les trois derniers mois, mais les primes de "
            "risque du crédit sont tendues au même moment. Des baisses provoquées par une "
            "dégradation économique n'ont pas la même portée que des baisses préventives.")
    elif easing:
        reading.direction = FAVORABLE
        reading.state = "Assouplissement"
        reading.summary = ("Le taux directeur a baissé sur trois mois, dans un marché du crédit "
                           "qui reste calme : le coût de l'argent se détend.")
    elif tightening:
        reading.direction = UNFAVORABLE
        reading.state = "Resserrement"
        reading.summary = ("Le taux directeur a monté sur trois mois : détenir un actif sans "
                           "rendement coûte plus cher.")
    else:
        reading.direction = NEUTRAL
        reading.state = "Taux stables"
        reading.summary = "Le taux directeur n'a pas bougé sur trois mois."
    reading.watching = (
        f"{reading.next_release_label} — {_period_fr(reading.next_release)}"
        if reading.next_release else "La prochaine communication de la Fed.")
    return reading


def _credit_is_stressed(ctx: Context) -> bool:
    """High-yield spreads wide or widening fast - the stress test used elsewhere."""

    level, change_30d, _ = ctx.change("macro.hy_spread", 30)
    if level is None:
        return False
    return level >= 5.0 or (change_30d is not None and change_30d >= 0.75)


def read_inflation(ctx: Context, driver: Driver) -> Reading:
    core = ctx.points("macro.core_cpi")
    if not core:
        return _unavailable(driver, "Aucune série d'inflation américaine n'est collectée.")
    reading = Reading(driver=driver)
    last = core[-1]
    reading.last_release = last.timestamp
    year_ago = [p for p in core if p.timestamp <= last.timestamp - timedelta(days=360)]
    yoy = ((last.value / year_ago[-1].value - 1) * 100) if year_ago else None
    if yoy is not None:
        reading.values.append(Value("Inflation sous-jacente (CPI)", _pct(yoy, 1),
                                    period=f"sur un an, {_period_fr(last.timestamp)}",
                                    source="Bureau of Labor Statistics"))
    pce = ctx.points("macro.core_pce")
    pce_yoy = None
    if pce:
        base = [p for p in pce if p.timestamp <= pce[-1].timestamp - timedelta(days=360)]
        if base:
            pce_yoy = (pce[-1].value / base[-1].value - 1) * 100
            reading.values.append(Value("PCE sous-jacent (cible de la Fed)", _pct(pce_yoy, 1),
                                        period=f"sur un an, {_period_fr(pce[-1].timestamp)}",
                                        source="Bureau of Economic Analysis"))
    # Six months earlier, to say whether it is receding or re-accelerating.
    half = [p for p in core if p.timestamp <= last.timestamp - timedelta(days=180)]
    trend = None
    if half and year_ago:
        earlier_base = [p for p in core if p.timestamp <= half[-1].timestamp - timedelta(days=360)]
        if earlier_base:
            previous_yoy = (half[-1].value / earlier_base[-1].value - 1) * 100
            trend = (yoy or 0) - previous_yoy

    event = ctx.next_event(driver)
    if event is not None:
        reading.next_release = event.scheduled_at
        reading.next_release_label = title_fr(getattr(event, "title", "Prochaine publication"))

    gauge = pce_yoy if pce_yoy is not None else yoy
    if gauge is None:
        reading.state = "Mesure incomplète"
        reading.direction = UNKNOWN
        reading.summary = "L'historique est trop court pour calculer une variation sur un an."
    elif trend is not None and trend <= -0.2 and gauge <= 3.0:
        reading.direction = FAVORABLE
        reading.state = "Inflation qui reflue"
        reading.summary = (f"L'inflation sous-jacente est à {_pct(gauge, 1)} sur un an et recule "
                           "par rapport à il y a six mois : la Fed retrouve de la marge.")
    elif trend is not None and trend >= 0.2:
        reading.direction = UNFAVORABLE
        reading.state = "Inflation qui réaccélère"
        reading.summary = (f"L'inflation sous-jacente est à {_pct(gauge, 1)} sur un an et remonte "
                           "par rapport à il y a six mois : la marge de la Fed se réduit.")
    else:
        reading.direction = NEUTRAL
        reading.state = "Inflation stable"
        reading.summary = (f"L'inflation sous-jacente tient autour de {_pct(gauge, 1)} sur un an, "
                           "sans direction nette depuis six mois.")
    reading.summary += (
        " Aucune attente de marché n'est branchée : la surprise par rapport au consensus, "
        "qui est ce qui fait réagir les marchés, ne peut pas être calculée ici.")
    reading.watching = (
        f"{reading.next_release_label} — {_period_fr(reading.next_release)}"
        if reading.next_release else "La prochaine publication mensuelle.")
    return reading


def read_employment(ctx: Context, driver: Driver) -> Reading:
    unemployment = ctx.points("macro.unemployment")
    claims = ctx.points("macro.jobless_claims")
    if not unemployment and not claims:
        return _unavailable(driver, "Aucune donnée d'emploi américaine n'est collectée.")
    reading = Reading(driver=driver)
    rate_change = None
    if unemployment:
        last = unemployment[-1]
        reading.last_release = last.timestamp
        _, rate_change, _ = ctx.change("macro.unemployment", 180)
        reading.values.append(Value("Taux de chômage", _pct(last.value, 1),
                                    change=(f"{fr_number(rate_change, 1, signed=True)} pt sur 6 mois"
                                            if rate_change is not None else ""),
                                    period=_period_fr(last.timestamp),
                                    source="Bureau of Labor Statistics"))
    payroll_change = None
    payrolls = ctx.points("macro.nonfarm_payrolls")
    if len(payrolls) >= 2:
        payroll_change = payrolls[-1].value - payrolls[-2].value
        reading.values.append(Value("Emplois créés sur le mois",
                                    f"{fr_number(payroll_change, 0, signed=True)} k",
                                    period=_period_fr(payrolls[-1].timestamp),
                                    source="Bureau of Labor Statistics"))
    if claims:
        reading.values.append(Value("Nouvelles inscriptions au chômage",
                                    f"{fr_number(claims[-1].value / 1000, 0)} k",
                                    period=f"semaine du {_period_fr(claims[-1].timestamp)}",
                                    source="FRED / Department of Labor"))
        reading.last_release = max(reading.last_release or claims[-1].timestamp,
                                   claims[-1].timestamp)
    event = ctx.next_event(driver)
    if event is not None:
        reading.next_release = event.scheduled_at
        reading.next_release_label = title_fr(getattr(event, "title", "Rapport sur l'emploi"))

    # Employment is genuinely two-sided: a cooling labour market brings rate
    # cuts closer and weaker growth at the same time. Saying MIXED is the
    # honest answer, not a failure to decide.
    cooling = rate_change is not None and rate_change >= 0.3
    strong = payroll_change is not None and payroll_change >= 150
    if cooling:
        reading.direction = MIXED
        reading.state = "Marché du travail qui se détend"
        reading.summary = ("Le chômage monte sur six mois. Cela rapproche des baisses de taux et "
                           "signale en même temps une économie qui ralentit : les deux effets "
                           "jouent en sens contraire pour les actifs risqués.")
    elif strong:
        reading.direction = NEUTRAL
        reading.state = "Emploi solide"
        reading.summary = ("Les créations d'emplois restent fermes : pas de pression sur la Fed "
                           "pour agir, dans un sens comme dans l'autre.")
    else:
        reading.direction = NEUTRAL
        reading.state = "Emploi sans tendance nette"
        reading.summary = "Ni dégradation marquée ni accélération sur les dernières publications."
    reading.watching = (
        f"{reading.next_release_label} — {_period_fr(reading.next_release)}"
        if reading.next_release else
        "Les inscriptions hebdomadaires au chômage. Le calendrier du BLS refuse les "
        "requêtes automatisées depuis ce serveur : la date du prochain rapport mensuel "
        "n'est pas affichée plutôt qu'estimée.")
    return reading


def read_yields(ctx: Context, driver: Driver) -> Reading:
    real = ctx.points("macro.real10y")
    if not real:
        return _unavailable(driver, "La courbe des taux réels américains n'est pas collectée.")
    reading = Reading(driver=driver)
    last = real[-1]
    reading.last_release = last.timestamp
    _, change_30d, _ = ctx.change("macro.real10y", 30)
    reading.values.append(Value("Taux réel 10 ans", _pct(last.value, 2),
                                change=(f"{fr_number(change_30d * 100, 0, signed=True)} pb sur 30 j"
                                        if change_30d is not None else ""),
                                period=_period_fr(last.timestamp),
                                source="U.S. Department of the Treasury"))
    for metric, label in (("macro.us2y", "Taux 2 ans"), ("macro.us10y", "Taux 10 ans")):
        point = ctx.latest(metric)
        if point is not None:
            _, change, _ = ctx.change(metric, 30)
            reading.values.append(Value(label, _pct(point.value, 2),
                                        change=(f"{fr_number(change * 100, 0, signed=True)} pb sur 30 j"
                                                if change is not None else ""),
                                        period=_period_fr(point.timestamp),
                                        source="U.S. Department of the Treasury"))
    if change_30d is None:
        reading.direction, reading.state = UNKNOWN, "Variation non calculable"
        reading.summary = "L'historique disponible ne couvre pas trente jours."
    elif change_30d >= 0.15:
        reading.direction, reading.state = UNFAVORABLE, "Rendements en hausse"
        reading.summary = (f"Le taux réel 10 ans est monté de {fr_number(change_30d * 100, 0)} pb "
                           "en un mois : le coût d'opportunité de détenir un actif sans rendement "
                           "augmente d'autant.")
    elif change_30d <= -0.15:
        reading.direction, reading.state = FAVORABLE, "Rendements en baisse"
        reading.summary = (f"Le taux réel 10 ans a reculé de {fr_number(abs(change_30d) * 100, 0)} pb "
                           "en un mois : renoncer à un rendement sûr coûte moins cher.")
    else:
        reading.direction, reading.state = NEUTRAL, "Rendements stables"
        reading.summary = "Le taux réel 10 ans n'a pas bougé significativement en un mois."
    reading.watching = "Le taux réel 10 ans, et la vitesse de son mouvement."
    return reading


def read_dollar(ctx: Context, driver: Driver) -> Reading:
    points = ctx.points("macro.dxy")
    if not points:
        return _unavailable(driver, "L'indice du dollar n'est pas collecté.")
    reading = Reading(driver=driver)
    last = points[-1]
    reading.last_release = last.timestamp
    _, _, change_30d = ctx.change("macro.dxy", 30)
    reading.values.append(Value("Indice du dollar (DXY)", fr_number(last.value, 2),
                                change=(f"{fr_number(change_30d, 1, signed=True)} % sur 30 j"
                                        if change_30d is not None else ""),
                                period=_period_fr(last.timestamp), source="Yahoo Finance"))
    if change_30d is None:
        reading.direction, reading.state = UNKNOWN, "Variation non calculable"
        reading.summary = "L'historique disponible ne couvre pas trente jours."
    elif change_30d >= 1.5:
        reading.direction, reading.state = UNFAVORABLE, "Dollar qui se renforce"
        reading.summary = (f"Le dollar a pris {_pct(change_30d, 1)} en un mois. Un dollar fort "
                           "resserre en général les conditions financières mondiales et pèse sur "
                           "les actifs risqués.")
    elif change_30d <= -1.5:
        reading.direction, reading.state = FAVORABLE, "Dollar qui recule"
        reading.summary = (f"Le dollar a cédé {_pct(abs(change_30d), 1)} en un mois, ce qui "
                           "desserre en général les conditions financières mondiales.")
    else:
        reading.direction, reading.state = NEUTRAL, "Dollar stable"
        reading.summary = "Le dollar évolue sans mouvement notable sur un mois."
    reading.watching = "Un retournement du dollar, dans un sens comme dans l'autre."
    return reading


def read_liquidity(ctx: Context, driver: Driver) -> Reading:
    assets = ctx.latest("liquidity.fed_total_assets")
    tga = ctx.latest("liquidity.tga")
    rrp = ctx.latest("liquidity.rrp")
    if assets is None:
        return _unavailable(driver, "Le bilan de la Réserve fédérale n'est pas collecté.")
    reading = Reading(driver=driver)
    reading.last_release = assets.timestamp
    reading.values.append(Value("Bilan de la Fed", _usd_bn(assets.value),
                                period=_period_fr(assets.timestamp),
                                source="Réserve fédérale (H.4.1)"))
    if tga is not None:
        reading.values.append(Value("Compte du Trésor (TGA)", _usd_bn(tga.value),
                                    period=_period_fr(tga.timestamp),
                                    source="U.S. Treasury (DTS)"))
    if rrp is not None:
        reading.values.append(Value("Prises en pension inversées (RRP)", _usd_bn(rrp.value * 1000),
                                    period=_period_fr(rrp.timestamp),
                                    source="Fed de New York"))
    # Net liquidity: what the balance sheet leaves in the banking system once
    # the Treasury's cash and the overnight facility are taken out.
    net_change = None
    if tga is not None and rrp is not None:
        _, assets_change, _ = ctx.change("liquidity.fed_total_assets", 60)
        _, tga_change, _ = ctx.change("liquidity.tga", 60)
        _, rrp_change, _ = ctx.change("liquidity.rrp", 60)
        if None not in (assets_change, tga_change, rrp_change):
            net_change = assets_change - tga_change - rrp_change * 1000
            reading.values.append(Value("Liquidité nette, variation", _usd_bn(net_change),
                                        period="60 jours", source="Calcul : bilan − TGA − RRP"))
    if net_change is None:
        reading.direction, reading.state = UNKNOWN, "Variation non calculable"
        reading.summary = ("Le bilan est connu mais l'historique ne permet pas de calculer la "
                           "variation de liquidité nette sur deux mois.")
    elif net_change >= 50_000:
        reading.direction, reading.state = FAVORABLE, "Liquidité en hausse"
        reading.summary = ("La liquidité nette du système bancaire américain a augmenté sur deux "
                           "mois : davantage de munitions disponibles pour les actifs risqués.")
    elif net_change <= -50_000:
        reading.direction, reading.state = UNFAVORABLE, "Liquidité en baisse"
        reading.summary = ("La liquidité nette du système bancaire américain s'est contractée sur "
                           "deux mois : moins de munitions pour les actifs risqués.")
    else:
        reading.direction, reading.state = NEUTRAL, "Liquidité stable"
        reading.summary = "La liquidité nette varie peu sur deux mois."
    reading.watching = "Le bilan hebdomadaire H.4.1 et le solde du compte du Trésor."
    return reading


def read_credit(ctx: Context, driver: Driver) -> Reading:
    hy = ctx.points("macro.hy_spread")
    if not hy:
        return _unavailable(driver, "Les primes de risque du crédit ne sont pas collectées.")
    reading = Reading(driver=driver)
    last = hy[-1]
    reading.last_release = last.timestamp
    _, change_30d, _ = ctx.change("macro.hy_spread", 30)
    reading.values.append(Value("Prime haut rendement", _pct(last.value, 2),
                                change=(f"{fr_number(change_30d * 100, 0, signed=True)} pb sur 30 j"
                                        if change_30d is not None else ""),
                                period=_period_fr(last.timestamp),
                                source="ICE BofA via FRED"))
    ig = ctx.latest("macro.ig_spread")
    if ig is not None:
        reading.values.append(Value("Prime qualité investissement", _pct(ig.value, 2),
                                    period=_period_fr(ig.timestamp), source="ICE BofA via FRED"))
    widening = change_30d is not None and change_30d >= 0.5
    if last.value >= 5.0 or widening:
        reading.direction, reading.state = UNFAVORABLE, "Crédit sous tension"
        reading.summary = (f"La prime du haut rendement est à {_pct(last.value, 2)} et "
                           "s'écarte : le marché du crédit corrobore le stress, ce qui distingue "
                           "une vraie dégradation d'une simple correction.")
    elif last.value <= 3.5:
        reading.direction, reading.state = FAVORABLE, "Crédit calme"
        reading.summary = (f"La prime du haut rendement est à {_pct(last.value, 2)}, dans le bas "
                           "de son histoire : le crédit ne signale aucune tension.")
    else:
        reading.direction, reading.state = NEUTRAL, "Crédit sans tension marquée"
        reading.summary = "Les primes de risque restent dans leur zone habituelle."
    reading.watching = "Un écartement rapide des primes, qui signalerait un stress réel."
    return reading


def _central_bank(ctx: Context, driver: Driver, metric: str, bank: str,
                  source: str) -> Reading:
    points = ctx.points(metric)
    if not points:
        return _unavailable(driver, f"Le taux directeur de {bank} n'est pas collecté.")
    reading = Reading(driver=driver)
    last = points[-1]
    reading.last_release = last.timestamp
    _, change_180d, _ = ctx.change(metric, 180)
    reading.values.append(Value(f"Taux directeur {bank}", _pct(last.value, 2),
                                change=(f"{fr_number(change_180d * 100, 0, signed=True)} pb sur 6 mois"
                                        if change_180d is not None else ""),
                                period=_period_fr(last.timestamp), source=source))
    event = ctx.next_event(driver)
    if event is not None:
        reading.next_release = event.scheduled_at
        reading.next_release_label = title_fr(getattr(event, "title", f"Prochaine décision {bank}"))
    hours = ((reading.next_release - ctx.now).total_seconds() / 3600
             if reading.next_release else None)
    if hours is not None and hours <= 72:
        reading.direction, reading.state = UNKNOWN, "Décision imminente"
        reading.summary = (f"{bank} se prononce dans {int(hours)} h. Le sens dépendra de l'écart "
                           "avec ce qui est attendu : il n'est pas connu avant la publication.")
    elif change_180d is not None and change_180d >= 0.1:
        reading.direction, reading.state = UNFAVORABLE, "Resserrement"
        reading.summary = f"{bank} a relevé son taux sur six mois."
    elif change_180d is not None and change_180d <= -0.1:
        reading.direction, reading.state = FAVORABLE, "Assouplissement"
        reading.summary = f"{bank} a baissé son taux sur six mois."
    else:
        reading.direction, reading.state = NEUTRAL, "Taux inchangé"
        reading.summary = f"{bank} n'a pas modifié son taux sur six mois."
    return reading


def read_ecb(ctx: Context, driver: Driver) -> Reading:
    reading = _central_bank(ctx, driver, "cb.ecb.deposit_rate", "la BCE", "Banque centrale européenne")
    if reading.available:
        reading.summary += (" Son effet sur la crypto passe par la liquidité en euro et par le "
                            "taux de change, un canal plus indirect que celui de la Fed.")
        reading.watching = (f"{reading.next_release_label} — {_period_fr(reading.next_release)}"
                            if reading.next_release else "La prochaine réunion de la BCE.")
    return reading


def read_boj(ctx: Context, driver: Driver) -> Reading:
    reading = _central_bank(ctx, driver, "cb.boj.call_rate", "la BoJ", "Banque du Japon")
    if reading.available:
        if reading.direction is UNFAVORABLE:
            reading.summary += (" Un resserrement japonais renchérit le financement en yen des "
                                "positions à effet de levier et peut forcer des débouclages "
                                "bien au-delà du Japon.")
        reading.watching = (f"{reading.next_release_label} — {_period_fr(reading.next_release)}"
                            if reading.next_release else "La prochaine décision de la BoJ.")
    return reading


def read_oil(ctx: Context, driver: Driver) -> Reading:
    points = ctx.points("macro.oil_wti")
    if not points:
        return _unavailable(driver, "Le prix du pétrole n'est pas collecté.")
    reading = Reading(driver=driver)
    last = points[-1]
    reading.last_release = last.timestamp
    _, _, change_30d = ctx.change("macro.oil_wti", 30)
    reading.values.append(Value("Pétrole WTI", f"{fr_number(last.value, 2)} $",
                                change=(f"{fr_number(change_30d, 1, signed=True)} % sur 30 j"
                                        if change_30d is not None else ""),
                                period=_period_fr(last.timestamp), source="Yahoo Finance"))
    # Oil only becomes macro-relevant when the move is large enough to change
    # inflation expectations. Below that, it is a commodity price.
    if change_30d is None:
        reading.direction, reading.state = UNKNOWN, "Variation non calculable"
        reading.summary = "L'historique disponible ne couvre pas trente jours."
    elif change_30d >= 12:
        reading.direction, reading.state = UNFAVORABLE, "Pétrole en forte hausse"
        reading.summary = (f"Le pétrole a pris {_pct(change_30d, 1)} en un mois. À cette ampleur, "
                           "il ravive la pression inflationniste attendue et donc la perspective "
                           "de taux plus hauts.")
    elif change_30d <= -12:
        reading.direction, reading.state = FAVORABLE, "Pétrole en forte baisse"
        reading.summary = (f"Le pétrole a cédé {_pct(abs(change_30d), 1)} en un mois, ce qui "
                           "réduit la pression inflationniste attendue.")
    else:
        reading.direction, reading.state = NEUTRAL, "Pétrole sans effet macro"
        reading.summary = ("Le mouvement du pétrole reste trop limité pour peser sur les "
                           "anticipations d'inflation.")
    reading.watching = "Un mouvement de plus de 12 % en un mois, seuil à partir duquel il compte."
    return reading


def read_etf_flows(ctx: Context, driver: Driver) -> Reading:
    from ..db import repo

    try:
        rows = repo.get_etf_flows(Asset("BTC"), days=30)
    except Exception:
        rows = []
    if not rows:
        return _unavailable(driver, "Les flux des ETF au comptant ne sont pas disponibles.")
    # One row per ticker per day: the day's net flow is their sum.
    by_day: dict[Any, float] = {}
    for row in rows:
        day = row["date"].date()
        by_day[day] = by_day.get(day, 0.0) + (row.get("flow_musd") or 0.0)
    days = sorted(by_day)
    reading = Reading(driver=driver)
    last_day = days[-1]
    reading.last_release = datetime(last_day.year, last_day.month, last_day.day, tzinfo=UTC)
    reading.values.append(Value("Flux net de la dernière séance",
                                f"{fr_number(by_day[last_day], 0, signed=True)} M$",
                                period=_period_fr(reading.last_release),
                                source="Farside Investors"))
    week = sum(by_day[d] for d in days[-5:])
    reading.values.append(Value("Cumul sur cinq séances",
                                f"{fr_number(week, 0, signed=True)} M$",
                                period="5 séances", source="Farside Investors"))
    if week >= 500:
        reading.direction, reading.state = FAVORABLE, "Entrées institutionnelles"
        reading.summary = ("Les ETF au comptant enregistrent des entrées nettes soutenues sur "
                           "cinq séances : de l'argent institutionnel réellement engagé, par "
                           "opposition aux récits.")
    elif week <= -500:
        reading.direction, reading.state = UNFAVORABLE, "Sorties institutionnelles"
        reading.summary = ("Les ETF au comptant enregistrent des sorties nettes sur cinq "
                           "séances : des institutionnels réduisent leur exposition.")
    else:
        reading.direction, reading.state = NEUTRAL, "Flux sans tendance"
        reading.summary = "Les flux ETF s'équilibrent sur cinq séances."
    reading.watching = "Une série d'entrées ou de sorties, qui ferait un changement de régime."
    return reading


def read_stablecoins(ctx: Context, driver: Driver) -> Reading:
    points = ctx.points("stablecoin.supply.total")
    if not points:
        return _unavailable(driver, "L'offre de stablecoins n'est pas collectée.")
    reading = Reading(driver=driver)
    last = points[-1]
    reading.last_release = last.timestamp
    _, _, change_30d = ctx.change("stablecoin.supply.total", 30)
    reading.values.append(Value("Offre totale de stablecoins", f"{fr_number(last.value / 1e9, 1)} Md$",
                                change=(f"{fr_number(change_30d, 1, signed=True)} % sur 30 j"
                                        if change_30d is not None else ""),
                                period=_period_fr(last.timestamp), source="DefiLlama"))
    if change_30d is None:
        reading.direction, reading.state = UNKNOWN, "Variation non calculable"
        reading.summary = "L'historique disponible ne couvre pas trente jours."
    elif change_30d >= 1.5:
        reading.direction, reading.state = FAVORABLE, "Offre en expansion"
        reading.summary = ("L'offre de stablecoins progresse : des capitaux entrent dans "
                           "l'écosystème et y restent disponibles.")
    elif change_30d <= -1.5:
        reading.direction, reading.state = UNFAVORABLE, "Offre en contraction"
        reading.summary = "L'offre de stablecoins recule : des capitaux quittent l'écosystème."
    else:
        reading.direction, reading.state = NEUTRAL, "Offre stable"
        reading.summary = "L'offre de stablecoins varie peu sur un mois."
    reading.watching = "Le rythme de création ou de destruction sur les prochaines semaines."
    return reading


def read_regulation(ctx: Context, driver: Driver) -> Reading:
    pending = [e for e in ctx.events
               if str(getattr(e, "category", "")).upper().endswith("REGULATION")
               or "REGULAT" in str(getattr(e, "category", "")).upper()]
    reading = Reading(driver=driver)
    upcoming = [e for e in pending
                if getattr(e, "scheduled_at", None) and e.scheduled_at >= ctx.now]
    reading.state = "Aucune échéance réglementaire datée"
    reading.direction = NEUTRAL
    reading.summary = ("Aucun texte à échéance datée n'est suivi actuellement. Les textes en "
                       "discussion ne sont jamais présentés comme adoptés.")
    if upcoming:
        nearest = min(upcoming, key=lambda e: e.scheduled_at)
        reading.next_release = nearest.scheduled_at
        reading.next_release_label = getattr(nearest, "title", "Échéance réglementaire")
        reading.last_release = getattr(nearest, "detected_at", None)
        reading.state = "Échéance réglementaire suivie"
        # Before the outcome, a regulatory deadline has an attention level and
        # no direction: the text can land either way.
        reading.direction = UNKNOWN
        reading.summary = (f"{reading.next_release_label} est à l'ordre du jour. Tant que le texte "
                           "n'est pas voté, son sens reste inconnu : une étape franchie n'est pas "
                           "une loi en vigueur.")
        reading.values.append(Value("Prochaine étape", reading.next_release_label,
                                    period=_period_fr(reading.next_release),
                                    source=getattr(nearest, "source", "")))
    reading.watching = "Le passage d'une étape à la suivante, jamais l'annonce elle-même."
    return reading


def read_geopolitics(ctx: Context, driver: Driver) -> Reading:
    reading = Reading(driver=driver)
    # Geopolitics only counts through measurable channels. Oil and equity
    # volatility are the two this project measures; without a move in either,
    # there is nothing to report, and headlines alone are not a signal.
    _, _, oil_change = ctx.change("macro.oil_wti", 7)
    vix = ctx.latest("macro.vix")
    _, vix_change, _ = ctx.change("macro.vix", 7)
    channels: list[str] = []
    if oil_change is not None and abs(oil_change) >= 7:
        channels.append(f"le pétrole ({fr_number(oil_change, 1, signed=True)} % en une semaine)")
        reading.values.append(Value("Pétrole, 7 jours", f"{fr_number(oil_change, 1, signed=True)} %",
                                    period="7 jours", source="Yahoo Finance"))
    if vix is not None and vix_change is not None and vix_change >= 5:
        channels.append(f"la volatilité des actions (VIX {fr_number(vix.value, 1)})")
        reading.values.append(Value("VIX", fr_number(vix.value, 1),
                                    change=f"{fr_number(vix_change, 1, signed=True)} pt sur 7 j",
                                    period=_period_fr(vix.timestamp), source="Yahoo Finance"))
    if channels:
        reading.direction, reading.state = UNFAVORABLE, "Tension visible sur les marchés"
        reading.summary = ("Une tension se lit dans " + " et ".join(channels) +
                           ". C'est l'effet mesuré sur les marchés qui est retenu, pas "
                           "l'actualité elle-même.")
        reading.last_release = ctx.now
    else:
        reading.direction, reading.state = NEUTRAL, "Aucun effet de marché mesuré"
        reading.summary = ("Aucun mouvement notable sur le pétrole ni sur la volatilité des "
                           "actions. Une actualité géopolitique sans effet mesurable n'est pas "
                           "traitée comme un signal crypto.")
    reading.watching = "Le pétrole et la volatilité des actions, les deux canaux mesurés ici."
    return reading


def read_risk_markets(ctx: Context, driver: Driver) -> Reading:
    nasdaq = ctx.points("macro.nasdaq")
    vix = ctx.latest("macro.vix")
    if not nasdaq:
        return _unavailable(driver, "Les indices actions ne sont pas collectés.")
    reading = Reading(driver=driver)
    last = nasdaq[-1]
    reading.last_release = last.timestamp
    _, _, change_30d = ctx.change("macro.nasdaq", 30)
    reading.values.append(Value("Nasdaq", fr_number(last.value, 0),
                                change=(f"{fr_number(change_30d, 1, signed=True)} % sur 30 j"
                                        if change_30d is not None else ""),
                                period=_period_fr(last.timestamp), source="Yahoo Finance"))
    if vix is not None:
        reading.values.append(Value("VIX", fr_number(vix.value, 1),
                                    period=_period_fr(vix.timestamp), source="Yahoo Finance"))
    calm = vix is not None and vix.value <= 20
    nervous = vix is not None and vix.value >= 25
    rising = change_30d is not None and change_30d >= 2
    falling = change_30d is not None and change_30d <= -2
    if rising and calm:
        reading.direction, reading.state = FAVORABLE, "Régime favorable au risque"
        reading.summary = ("Les actions technologiques progressent et la volatilité reste basse : "
                           "un environnement qui favorise en général les actifs risqués.")
    elif falling and nervous:
        reading.direction, reading.state = UNFAVORABLE, "Aversion au risque"
        reading.summary = ("Les actions reculent et la volatilité monte : les investisseurs "
                           "réduisent le risque, crypto comprise.")
    elif (rising and nervous) or (falling and calm):
        reading.direction, reading.state = MIXED, "Signaux contradictoires"
        reading.summary = ("Les actions et la volatilité ne racontent pas la même histoire : le "
                           "régime de risque n'est pas tranché.")
    else:
        reading.direction, reading.state = NEUTRAL, "Régime sans direction"
        reading.summary = "Ni franche prise de risque ni aversion marquée sur un mois."
    reading.watching = "La volatilité des actions, qui bascule avant les indices eux-mêmes."
    return reading


READERS: dict[str, Any] = {
    "fed": read_fed,
    "inflation": read_inflation,
    "employment": read_employment,
    "yields": read_yields,
    "dollar": read_dollar,
    "liquidity": read_liquidity,
    "credit": read_credit,
    "ecb": read_ecb,
    "boj": read_boj,
    "oil": read_oil,
    "etf_flows": read_etf_flows,
    "stablecoins": read_stablecoins,
    "regulation": read_regulation,
    "geopolitics": read_geopolitics,
    "risk_markets": read_risk_markets,
}


# --- the cycle: read everything, rank it, keep five ------------------------------------------


#: Importance is recomputed every cycle; a value is not. These are the hours,
#: in UTC, at which a full macro cycle runs.
CYCLE_HOURS: tuple[int, ...] = (0, 3, 6, 9, 12, 15, 18, 21)


def next_cycle(now: datetime) -> datetime:
    """The next scheduled cycle, in UTC - what the page shows as « prochaine vérification »."""

    for hour in CYCLE_HOURS:
        candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if candidate > now:
            return candidate
    return (now + timedelta(days=1)).replace(hour=CYCLE_HOURS[0], minute=0, second=0, microsecond=0)


def score_of(reading: Reading, ctx: Context) -> Score:
    """How much this driver deserves the reader's attention right now.

    Additive and explainable: the page can say why a driver is at 94 instead of
    showing a number nobody can question. Importance never looks at the
    direction - an unknown outcome can be the most important thing on the page.
    """

    score = Score()
    if not reading.available:
        return score
    driver = reading.driver
    score.add(BASE_IMPORTANCE.get(driver.category, 20), "poids de la famille")

    if reading.next_release is not None:
        remaining = reading.next_release - ctx.now
        for window, points, label in PROXIMITY:
            if remaining <= window:
                score.add(points, label)
                break

    if reading.last_release is not None:
        age = ctx.now - reading.last_release
        window = FRESH_RELEASE.get(driver.category, timedelta(hours=24))
        if age <= window:
            score.add(12, "publication récente")
        elif age > timedelta(days=45):
            # Importance decays on its own: a page that accumulates is a page
            # nobody reads.
            score.add(-10, "donnée ancienne")

    # An unusual move is what makes a standing driver suddenly matter.
    for metric, days, label in _ABNORMALITY_WATCH.get(driver.key, ()):
        rank = ctx.abnormality(metric, days)
        if rank is None:
            continue
        if rank >= 0.95:
            score.add(25, f"{label} : mouvement plus ample que 95 % de son histoire")
        elif rank >= 0.85:
            score.add(15, f"{label} : mouvement inhabituel")
        break

    if reading.direction is MIXED:
        score.add(5, "signaux contradictoires à trancher")
    return score


#: Which series makes each driver abnormal, and over how many days.
_ABNORMALITY_WATCH: dict[str, tuple[tuple[str, int, str], ...]] = {
    "yields": (("macro.real10y", 30, "taux réel 10 ans"),),
    "dollar": (("macro.dxy", 30, "dollar"),),
    "credit": (("macro.hy_spread", 30, "prime du haut rendement"),),
    "oil": (("macro.oil_wti", 30, "pétrole"),),
    "risk_markets": (("macro.vix", 7, "volatilité des actions"),),
    "liquidity": (("liquidity.fed_total_assets", 60, "bilan de la Fed"),),
    "stablecoins": (("stablecoin.supply.total", 30, "offre de stablecoins"),),
    "inflation": (("macro.core_cpi", 180, "inflation sous-jacente"),),
    "employment": (("macro.jobless_claims", 60, "inscriptions au chômage"),),
}

#: How many drivers reach the home. The rest stay one tap away.
TOP = 5


def build(view: Any, *, now: datetime | None = None, events: list[Any] | None = None,
          previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read the fifteen drivers, rank them, and keep the five that explain now.

    `previous` is the snapshot of an earlier cycle: when given, each driver
    says what changed since. Nothing is rewritten retroactively - the earlier
    snapshot keeps the reading it had.
    """

    now = now or datetime.now(UTC)
    if events is None:
        events = _load_events(now)
    ctx = Context(view=view, now=now, events=events)

    readings: list[Reading] = []
    for driver in DRIVERS:
        reader = READERS[driver.key]
        try:
            reading = reader(ctx, driver)
        except Exception as exc:  # one broken series never takes the page down
            reading = _unavailable(driver, f"Lecture impossible : {str(exc)[:120]}")
        score = score_of(reading, ctx)
        reading.importance = score.clamped
        reading.importance_reasons = score.reasons
        reading.attention = attention_of(reading.importance)
        readings.append(reading)

    ranked = sorted(readings, key=lambda r: (-r.importance, r.driver.name))
    top = [r for r in ranked if r.available][:TOP]
    changes = _changes_since(ranked, previous)
    return {
        "as_of": now.isoformat(),
        "next_check": next_cycle(now).isoformat(),
        "top": [r.to_dict() for r in top],
        "drivers": [r.to_dict() for r in ranked],
        "changes": changes,
        "summary": _summary(top),
        "watched": len(DRIVERS),
        "unavailable": [r.driver.key for r in ranked if not r.available],
    }


def _load_events(now: datetime) -> list[Any]:
    from ..db import repo

    try:
        return repo.list_future_events(start=now - timedelta(days=2),
                                       end=now + timedelta(days=120), limit=200)
    except Exception:
        return []


def _changes_since(readings: list[Reading], previous: dict[str, Any] | None) -> list[dict[str, Any]]:
    """What moved since the previous cycle, stated as a change, not rewritten."""

    if not previous:
        return []
    before = {d["key"]: d for d in (previous.get("drivers") or [])}
    out: list[dict[str, Any]] = []
    for reading in readings:
        old = before.get(reading.driver.key)
        if old is None:
            continue
        if old.get("direction") != reading.direction.value:
            out.append({
                "key": reading.driver.key,
                "emoji": reading.driver.emoji,
                "name": reading.driver.name,
                "from": old.get("direction"),
                "to": reading.direction.value,
                "from_state": old.get("state", ""),
                "to_state": reading.state,
                "since": previous.get("as_of"),
            })
    return out


DIRECTION_FR = {
    FAVORABLE.value: ("🟢", "Soutien"),
    UNFAVORABLE.value: ("🔴", "Pression"),
    NEUTRAL.value: ("⚪", "Neutre"),
    MIXED.value: ("🟡", "Partagé"),
    UNKNOWN.value: ("🔵", "Inconnu tant que le résultat n'est pas publié"),
}


def _summary(top: list[Reading]) -> str:
    """One line over the five: what the macro environment does to crypto now."""

    if not top:
        return "Aucun moteur macro n'est mesurable actuellement."
    pressure = [r for r in top if r.direction is UNFAVORABLE]
    support = [r for r in top if r.direction is FAVORABLE]
    pending = [r for r in top if r.direction is UNKNOWN]
    if pending and not pressure and not support:
        return ("Le contexte macro est suspendu à des résultats qui ne sont pas encore publiés : "
                + ", ".join(r.driver.name for r in pending) + ".")
    if len(pressure) > len(support):
        lead = pressure[0]
        return (f"Le contexte macro pèse sur les actifs risqués, {lead.driver.name} en tête"
                + (f", malgré {support[0].driver.name}." if support else "."))
    if len(support) > len(pressure):
        lead = support[0]
        return (f"Le contexte macro soutient les actifs risqués, {lead.driver.name} en tête"
                + (f", malgré {pressure[0].driver.name}." if pressure else "."))
    return ("Le contexte macro est partagé : "
            + ", ".join(f"{r.driver.name} {DIRECTION_FR[r.direction.value][1].lower()}"
                        for r in top[:3]) + ".")
