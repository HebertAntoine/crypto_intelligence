"""Lexa test chain: transcript -> extraction -> verification -> plan -> reports.

The model is replaced by a scripted one so each rule is pinned:
  - a value absent from the transcript never reaches the plan
  - the evidence is the transcript's own words, at the right timestamp
  - an allocation, a timeframe the passage does not contain are removed
  - « la cassure de X serait mauvaise » as a buy zone is flagged
  - a crypto only named in passing gets no sheet
  - no allocation from Lexa -> the split is labelled CALCUL APP
  - the extraction prompt carries no reference value
"""

from pathlib import Path

import pytest

from crypto_intel.lexa import extraction, test_run
from crypto_intel.lexa.report import human_report, plan, price, validation_report
from crypto_intel.lexa.transcript import assets_in, numbers_in, parse, topic_windows

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "lexa_transcript_fictive.txt"


@pytest.fixture(autouse=True)
def lexa_db(tmp_path, monkeypatch):
    monkeypatch.setenv("LEXA_DATABASE_PATH", str(tmp_path / "lexa" / "lexa.db"))


def scripted(answers):
    def llm(system, user, model=None):
        symbol = user.split("Crypto concernée : ")[1].split("\n")[0]
        return answers.get(symbol, {"analysed": False})
    return llm


ADA = {
    "analysed": True,
    "price_at_video": {"value": 0.512, "timestamp": "02:20"},
    "stance": "UNSPECIFIED", "stance_basis": "UNKNOWN",
    "levels": [
        {"value": 0.487, "kind": "BUY_ZONE", "basis": "INFERRED", "timestamp": "03:02",
         "quote": "si ADA revient vers 0,4870"},
        {"value": 0.461, "kind": "REINFORCEMENT", "basis": "EXPLICIT", "timestamp": "03:25"},
        {"value": 0.539, "kind": "CONFIRMATION", "basis": "EXPLICIT", "timestamp": "04:10",
         "timeframe": "4H", "condition": {"kind": "CLOSE_ABOVE"}},
        {"value": 0.575, "kind": "TARGET", "basis": "EXPLICIT", "timestamp": "04:36"},
        # Said at 04:36, cited at 01:00: the timestamp is corrected.
        {"value": 0.612, "kind": "TARGET", "basis": "EXPLICIT", "timestamp": "01:00"},
        # Never said: rejected.
        {"value": 0.7777, "kind": "TARGET", "basis": "EXPLICIT", "timestamp": "04:36"},
        # 25 % is not in the transcript, nor a 1W timeframe: both removed.
        {"value": 0.66, "kind": "TARGET", "basis": "EXPLICIT", "timestamp": "04:36",
         "allocation_pct": 25, "timeframe": "1W"},
    ],
    "scenarios": [{"id": "A", "condition": "cassure des 0,5390", "targets": [0.575, 0.9],
                   "timestamp": "05:47", "quote": "soit on casse les 0,5390 et on file vers les objectifs"}],
    "arguments": [{"indicator": "RSI", "argument": "Le RSI se retourne", "direction": None,
                   "timestamp": "05:24", "quote": "Le RSI est en train de se retourner à la hausse"},
                  {"indicator": "ETF", "argument": "Flux ETF", "timestamp": "05:24",
                   "quote": "les flux ETF explosent cette semaine"}],
}
BTC = {
    "analysed": True,
    "price_at_video": {"value": 64250, "timestamp": "00:48"},
    "stance": "WAIT", "stance_basis": "EXPLICIT",
    # The trap: « la cassure des 62 000 serait mauvaise » is not a buy zone.
    "levels": [{"value": 62000, "kind": "BUY_ZONE", "basis": "EXPLICIT", "timestamp": "01:06"}],
    "events": [{"event": "Fed", "date": "17 septembre", "timestamp": "00:21",
                "quote": "la Fed annonce sa décision le 17 septembre"}],
}


def _run():
    segments = parse(FIXTURE.read_text())
    return extraction.extract(segments, title="Test", published_at=None, source="fixture",
                              llm=scripted({"ADA": ADA, "BTC": BTC, "SOL": {"analysed": False}}))


# --- transcript ----------------------------------------------------------------------


def test_transcript_formats():
    youtube = parse("0:05\nSalut\n12:31\non regarde XRP\n1:02:03\nfin")
    assert [(s.start_s, s.text) for s in youtube] == [(5, "Salut"), (751, "on regarde XRP"),
                                                       (3723, "fin")]
    srt = parse("1\n00:00:01,000 --> 00:00:04,000\nSalut <i>bitcoin</i>\n")
    assert (srt[0].start_s, srt[0].text) == (1, "Salut bitcoin")
    assert parse("# commentaire\n[00:10] texte")[0].text == "texte"


def test_french_numbers():
    assert numbers_in("2,4531 puis 2.3087, 68 000 $ ou 70k") == [2.4531, 2.3087, 68000, 70000]


def test_market_dominance_is_not_a_bitcoin_analysis():
    assert assets_in("la dominance du bitcoin monte") == []
    assert assets_in("Le Bitcoin puis Cardano") == ["BTC", "ADA"]


def test_passages_follow_the_crypto_being_discussed():
    windows = topic_windows(parse(FIXTURE.read_text()))
    assert min(s.start_s for s in windows["ADA"]) == 140
    assert all(s.start_s < 140 for s in windows["BTC"])


# --- verification ------------------------------------------------------------------


def test_only_values_written_in_the_transcript_survive():
    ada = next(a for a in _run().assets if a.symbol == "ADA")
    values = [lv.value for lv in ada.levels]
    assert 0.7777 not in values
    assert any(r.value == 0.7777 for r in ada.rejected)
    assert any(r.value == 0.9 for r in ada.rejected)  # scenario target never said
    assert ada.scenarios[0].targets == [0.575]


def test_evidence_is_the_transcript_at_the_right_time():
    ada = next(a for a in _run().assets if a.symbol == "ADA")
    level = next(lv for lv in ada.levels if lv.value == 0.612)
    assert level.evidence.timestamp_s == 276  # 04:36, not the cited 01:00
    assert "deuxième objectif 0,6120" in level.evidence.quote
    assert "corrigé" in level.evidence.verification_note


def test_unsaid_allocation_and_timeframe_are_removed():
    ada = next(a for a in _run().assets if a.symbol == "ADA")
    last = next(lv for lv in ada.levels if lv.value == 0.66)
    assert last.allocation_pct is None and last.timeframe is None
    assert any("25 %" in note for note in ada.ambiguous)
    confirmation = next(lv for lv in ada.levels if lv.kind == "CONFIRMATION")
    assert confirmation.timeframe == "4H"


def test_the_stated_split_is_read_from_the_words():
    ada = next(a for a in _run().assets if a.symbol == "ADA")
    entries = {lv.kind: lv for lv in ada.levels}
    assert entries["BUY_ZONE"].allocation_pct == 40
    assert entries["REINFORCEMENT"].allocation_pct == 60
    assert entries["REINFORCEMENT"].allocation_evidence.timestamp_s == 227  # 03:47


def test_an_argument_without_its_passage_is_dropped():
    ada = next(a for a in _run().assets if a.symbol == "ADA")
    assert [a.indicator for a in ada.arguments] == ["RSI"]
    assert ada.arguments[0].direction is None
    assert any("ETF" in note for note in ada.ambiguous)


def test_a_break_level_labelled_buy_zone_is_flagged():
    btc = next(a for a in _run().assets if a.symbol == "BTC")
    assert any("cassure" in note for note in btc.ambiguous)
    assert btc.levels[0].basis == "INFERRED"
    assert btc.events[0].date == "17 septembre"


def test_a_crypto_named_in_passing_gets_no_sheet():
    result = _run()
    assert "SOL" in result.not_analysed
    assert {a.symbol for a in result.assets} == {"ADA", "BTC"}


def test_the_prompt_gives_nothing_away():
    # The only figures in the prompt are small integers (word counts, TP
    # numbers, percentages of an example): no price the model could copy.
    assert all(n == int(n) and n <= 100 for n in extraction.numbers_in(extraction.SYSTEM_PROMPT))
    assert extraction.reference_leak([0.4870, 0.5390, 62000.0, 2.4531]) == []


# --- plan and reports ----------------------------------------------------------------


def test_without_a_stated_split_the_app_split_is_labelled_as_such():
    ada = next(a for a in _run().assets if a.symbol == "ADA")
    for lv in ada.levels:
        lv.allocation_pct = None
    table = plan(ada, capital=100)
    entry = next(r for r in table["rows"] if "Achat principal" in r["interpretation"])
    assert "Non précisée par Lexa" in entry["allocation"]
    assert "CALCUL APP" in entry["allocation"]
    assert table["allocation_source"] == "CALCUL APP"


def test_a_stated_split_is_lexa_s():
    ada = next(a for a in _run().assets if a.symbol == "ADA")
    table = plan(ada, capital=200)
    entry = next(r for r in table["rows"] if "Achat principal" in r["interpretation"])
    assert entry["allocation"].startswith("40 % (Lexa) · 80,00 €")
    assert table["allocation_source"] == "LEXA"


def test_prices_keep_every_decimal_said():
    assert price(2.444175) == "2,444175 $"
    assert price(64250) == "64 250 $"


def test_reports_carry_timestamps_and_the_manual_comparison():
    result = _run()
    tables = {a.symbol: plan(a) for a in result.assets}
    human = human_report(result, tables)
    assert "🎬 03:02" in human and "🟡 Interprétation du contexte" in human
    validation = validation_report(result)
    for section in ("## TRANSCRIPTION", "## CRYPTOS DÉTECTÉES", "## INFORMATIONS AMBIGUËS",
                    "## INFORMATIONS NON TROUVÉES", "## ERREURS POSSIBLES",
                    "## COMPARAISON MANUELLE", "## CONCLUSION TECHNIQUE"):
        assert section in validation
    assert "0,7777" in validation  # the rejected value is reported, not hidden


def test_a_run_writes_its_files_and_nothing_to_the_database(tmp_path):
    path = tmp_path / "run"
    path.mkdir()
    payload = test_run.execute(
        path, FIXTURE.read_text(), title="Test", published_at=None, source="fixture",
        llm=scripted({"ADA": ADA}), prices=lambda *_: None)
    assert payload["schema_version"] == "lexa-extraction/1"
    assert {p.name for p in path.iterdir()} == {"transcript.txt", "extraction.json",
                                                "report.md", "validation.md"}
    assert not (tmp_path / "lexa" / "lexa.db").exists()
    assert oct((path / "report.md").stat().st_mode)[-3:] == "600"


def test_an_unreadable_transcript_is_refused():
    with pytest.raises(ValueError):
        test_run.start("pas d'horodatage ici", title="x", published_at=None, source="x",
                       background=False)


def test_test_run_routes_are_local_and_validate_input():
    from fastapi.testclient import TestClient

    from crypto_intel.main import app

    remote = TestClient(app, client=("203.0.113.9", 5000))
    assert remote.post("/api/lexa/test-runs", json={"transcript": "x", "title": "x"}).status_code == 403
    local = TestClient(app, client=("127.0.0.1", 5000))
    bad = local.post("/api/lexa/test-runs", json={"transcript": "sans horodatage", "title": "x"})
    assert bad.status_code == 422
    assert local.get("/api/lexa/test-runs/../../etc").status_code == 404
    assert local.get("/api/lexa/test-runs").json() == {"runs": []}
