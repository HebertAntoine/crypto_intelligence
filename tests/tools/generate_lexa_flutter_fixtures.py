"""Regenerate app/test/fixtures/lexa_fictive.json from the real backend.

FICTIONAL levels on a scripted market (see tests/unit/test_lexa_plans.py):
no Lexa content is ever committed. Run from the repository root:

    PYTHONPATH=backend:. .venv/bin/python tests/tools/generate_lexa_flutter_fixtures.py
"""

import json
import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ["LEXA_DATABASE_PATH"] = tempfile.mkdtemp() + "/lexa.db"
sys.path.insert(0, "tests/unit")

import test_lexa_plans as t

from crypto_intel.lexa import service, store
from crypto_intel.lexa.repository import AssetInput, LevelInput, set_user_plan

OURS_BTC = {
    "action": "WAIT", "sentence": "Levier élevé, marché étiré.",
    "etf": {"emoji": "🟢", "status": "Flux ETF"},
    "home_families": [
        {"family": "technical", "tone": "ORANGE", "status": "Haussière mais étirée"},
        {"family": "flows", "tone": "GREEN", "status": "Acheteurs dominants"},
        {"family": "derivatives", "tone": "RED", "status": "Longs encombrés"},
        {"family": "macro", "tone": "ORANGE", "status": "Défavorable"},
        {"family": "cycle", "tone": "GREEN", "status": "Récupération"},
    ],
}


def main() -> None:
    store.reset_engine()
    service.our_reading = lambda asset: OURS_BTC if asset == "BTC" else None
    service.macro_events = lambda days=14: []

    xrp = t.add(t.xrp_levels())
    early = t.FakeMarket(t.flat(2.346, 10), t.PUBLISHED + timedelta(hours=1))
    ids = {lv["kind"]: lv["id"] for lv in service.plan_for(xrp, early)["levels"]}
    set_user_plan(xrp, [
        {"level_id": ids["BUY_ZONE"], "amount_type": "EURO", "amount": 60},
        {"level_id": ids["REINFORCEMENT"], "amount_type": "EURO", "amount": 40},
    ])
    t.add(AssetInput(asset="BTC", stance="WAIT", levels=[
        LevelInput("BUY_ZONE", 60000), LevelInput("RESISTANCE", 70000)]))

    now = datetime(2026, 9, 20, 15, tzinfo=UTC)
    hours = int((now - (t.PUBLISHED - timedelta(hours=8))).total_seconds() // 3600)
    xrp_market = t.FakeMarket(t.flat(2.346, hours - 3) + [(2.4514, 2.431, 2.4514)] * 3, now)
    btc_market = t.FakeMarket(t.flat(64250, hours), now)

    class Markets:
        def now(self):
            return now

        def eurusd(self):
            return 1.10

        def _pick(self, asset):
            return btc_market if asset == "BTC" else xrp_market

        def price(self, asset):
            return self._pick(asset).price(asset)

        def bars(self, asset, timeframe, since):
            return self._pick(asset).bars(asset, timeframe, since)

    market = Markets()
    out = {"plan_wait_close": service.plan_for(xrp, market),
           "overview": service.overview(market), "calendar": service.calendar(market)}
    target = Path("app/test/fixtures/lexa_fictive.json")
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print([(r["asset"], r["status"]) for r in out["overview"]["follow"]])


if __name__ == "__main__":
    main()
