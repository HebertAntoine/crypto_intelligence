"""Legal status classification - a proposal must never read as adopted law."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from crypto_intel.core.enums import Asset, LegalStatus
from crypto_intel.engines.regulation import (
    RegulationAndPoliticsAnalyzer,
    classify_legal_status,
    detect_assets,
    is_crypto_relevant,
)


class TestLegalStatusClassification:
    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("President signs the GENIUS Act into law", LegalStatus.ADOPTED),
            ("SEC approves spot Ethereum exchange-traded funds", LegalStatus.REGULATORY_DECISION),
            ("SEC charges a crypto firm with fraud", LegalStatus.ENFORCEMENT),
            ("Senate passed the crypto market structure bill", LegalStatus.VOTE_HELD),
            ("House schedules a vote on the digital asset bill", LegalStatus.VOTE_SCHEDULED),
            ("CFTC requests public comment on custody", LegalStatus.CONSULTATION),
            ("Senator introduces the CLARITY Act", LegalStatus.PROPOSED),
            ("Reportedly, sources say the agency may shift stance", LegalStatus.RUMOR),
            ("Fed Chair says digital assets need study", LegalStatus.POLITICAL_STATEMENT),
        ],
    )
    def test_classification(self, title, expected):
        assert classify_legal_status(title)[0] is expected

    def test_proposal_is_never_binding(self):
        """The single most damaging possible error."""
        status, _ = classify_legal_status("Senator introduces a bill to regulate stablecoins")
        assert status is LegalStatus.PROPOSED
        assert status.is_binding is False

    def test_adopted_is_binding(self):
        status, _ = classify_legal_status("The bill was signed into law yesterday")
        assert status.is_binding is True

    def test_unrecognised_is_uncertain_not_guessed(self):
        status, uncertainty = classify_legal_status("Bitcoin blockchain digital asset")
        assert status is LegalStatus.UNCERTAIN
        assert uncertainty > 70

    def test_rumors_carry_high_uncertainty(self):
        _, rumor_unc = classify_legal_status("Reportedly the SEC will act")
        _, adopted_unc = classify_legal_status("The rule was enacted")
        assert rumor_unc > adopted_unc


class TestAssetDetection:
    def test_detects_each_asset(self):
        assert Asset.BTC in detect_assets("Bitcoin ETF approved")
        assert Asset.ETH in detect_assets("Ethereum staking rules")
        assert Asset.SOL in detect_assets("Solana network filing")

    def test_relevance_filter(self):
        assert is_crypto_relevant("SEC approves spot bitcoin ETF")
        assert not is_crypto_relevant("Fed publishes agricultural lending survey")


class TestAnalyzer:
    def _item(self, title, hours_ago=2, tier=1, institution="SEC"):
        return {
            "title": title, "summary": "", "url": "https://example.invalid",
            "source": institution, "tier": tier, "institution": institution,
            "published_at": datetime.now(UTC) - timedelta(hours=hours_ago),
        }

    def test_counts_proposals_separately_from_binding(self):
        r = RegulationAndPoliticsAnalyzer().analyze([
            self._item("SEC approves spot bitcoin ETF listing"),
            self._item("Senator introduces a crypto market structure bill"),
        ])
        assert r.available
        assert r.binding_count == 1
        assert r.proposal_count == 1

    def test_warns_that_proposals_are_not_law(self):
        r = RegulationAndPoliticsAnalyzer().analyze([
            self._item("Senator introduces a crypto tax bill")
        ])
        assert any("NOT adopted law" in f or "not adopted law" in f.lower() for f in r.findings)

    def test_old_items_excluded(self):
        r = RegulationAndPoliticsAnalyzer().analyze([
            self._item("SEC approves spot bitcoin ETF", hours_ago=24 * 90)
        ])
        assert r.available is False

    def test_irrelevant_items_excluded(self):
        r = RegulationAndPoliticsAnalyzer().analyze([
            self._item("Fed publishes agricultural lending survey")
        ])
        assert r.available is False
