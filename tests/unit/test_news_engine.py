"""News clustering: 30 outlets reporting one story is ONE signal."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from crypto_intel.core.enums import Asset
from crypto_intel.engines.news import NewsEngine, jaccard, normalize_title

NOW = datetime.now(UTC)


def item(title, source="CoinDesk", tier=3, hours=1, institution=None):
    d = {
        "title": title, "url": f"https://example.invalid/{abs(hash(title))}",
        "source": source, "tier": tier, "summary": "",
        "published_at": NOW - timedelta(hours=hours),
    }
    if institution:
        d["institution"] = institution
    return d


class TestNormalisation:
    def test_stopwords_removed(self):
        assert "the" not in normalize_title("The SEC approves the ETF")

    def test_light_stemming_unifies_variants(self):
        a = normalize_title("SEC approves the ETF")
        b = normalize_title("SEC approved the ETF")
        assert jaccard(a, b) > 0.9

    def test_headline_noise_removed(self):
        assert "breaking" not in normalize_title("BREAKING: SEC approves ETF")


class TestClustering:
    def test_same_story_collapses_to_one_event(self):
        items = [
            item("SEC approves spot Ethereum ETF options trading", "SEC", 1, institution="SEC"),
            item("SEC approves options trading on spot Ethereum ETFs"),
            item("Spot Ethereum ETF options approved by the SEC", "The Block"),
            item("SEC greenlights spot Ethereum ETF options", "Decrypt"),
            item("BREAKING: SEC approves Ethereum ETF options trading", "Cointelegraph"),
        ]
        result = NewsEngine().analyze(items)
        assert result.unique_events == 1
        assert result.duplicates_removed == 4

    def test_distinct_stories_stay_separate(self):
        items = [
            item("SEC approves spot Ethereum ETF options"),
            item("Bitcoin miners report record hashrate"),
            item("Solana upgrade improves validator performance"),
        ]
        assert NewsEngine().analyze(items).unique_events == 3

    def test_cluster_attributed_to_most_credible_source(self):
        """An official release must outrank the outlets republishing it."""
        items = [
            item("SEC approves spot Ethereum ETF options", "CoinDesk", 3, hours=1),
            item("SEC approves spot Ethereum ETF options trading", "SEC", 1, hours=2,
                 institution="SEC"),
        ]
        result = NewsEngine().analyze(items)
        assert result.clusters[0].primary_source == "SEC"
        assert result.clusters[0].best_tier == 1


class TestWeighting:
    def test_official_source_outranks_syndicated_blog_pile(self):
        """A tweet-tier pile-on must not outweigh a Fed statement."""
        official = [item("Federal Reserve issues policy statement on digital assets",
                         "Federal Reserve", 1, institution="FED")]
        noise = [item(f"Some random crypto take number {i}", "RandomBlog", 4) for i in range(10)]
        result = NewsEngine().analyze(official + noise)
        top = result.clusters[0]
        assert top.best_tier == 1

    def test_opinion_is_downweighted(self):
        items = [
            item("Why Bitcoin will change everything", "CoinDesk", 3),
            item("SEC issues enforcement order against exchange", "SEC", 1, institution="SEC"),
        ]
        result = NewsEngine().analyze(items)
        opinion = next(c for c in result.clusters if "Why" in c.event_title)
        factual = next(c for c in result.clusters if "SEC issues" in c.event_title)
        assert factual.importance > opinion.importance


class TestFiltering:
    def test_asset_filter(self):
        items = [
            item("Bitcoin ETF sees record inflows"),
            item("Solana network upgrade released"),
        ]
        result = NewsEngine().analyze(items, asset=Asset.BTC)
        titles = [c.event_title for c in result.clusters]
        assert any("Bitcoin" in t for t in titles)
        assert not any("Solana" in t for t in titles)

    def test_old_items_dropped(self):
        result = NewsEngine().analyze([item("Old story", hours=24 * 10)])
        assert result.available is False

    def test_empty_input_unavailable(self):
        assert NewsEngine().analyze([]).available is False
