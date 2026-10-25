import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from agent_runtime.vinted_reports import (
    _best_item_name,
    build_vinted_report,
    deactivate_owned_profile,
    save_owned_profile,
    write_vinted_report_html,
)


class VintedReportsTests(unittest.TestCase):
    def test_generic_profile_labels_do_not_overwrite_real_listing_title(self) -> None:
        self.assertEqual("Charm kitty portafortuna", _best_item_name("Charm", "Charm kitty portafortuna"))
        self.assertEqual("Charm Japan compatibile Pandora", _best_item_name("No Label", "Charm Japan compatibile Pandora"))
        self.assertEqual("Pandora", _best_item_name("Pandora", ""))

    def test_keyword_metrics_combine_runs_and_tracked_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            db_path = root / "scraper.db"
            now = datetime.now().replace(microsecond=0)
            sold_at = now - timedelta(minutes=20)
            first_seen = sold_at - timedelta(hours=2)
            with sqlite3.connect(db_path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE vinted_items(link TEXT PRIMARY KEY, item_id TEXT);
                    CREATE TABLE vinted_unavailable_items(item_link TEXT PRIMARY KEY, item_id TEXT);
                    CREATE TABLE vinted_search_hits(
                        item_link TEXT, search_term TEXT, first_seen_at TEXT, last_seen_at TEXT, times_seen INTEGER
                    );
                    CREATE TABLE vinted_search_runs(
                        search_term TEXT, query_label TEXT, created_at TEXT, item_count INTEGER
                    );
                    CREATE TABLE vinted_deal_sale_tracking(
                        item_link TEXT PRIMARY KEY, item_id TEXT, item_name TEXT,
                        first_seen_at TEXT, last_checked_at TEXT, sold_at TEXT,
                        status TEXT, payload_json TEXT
                    );
                    """
                )
                connection.executemany(
                    "INSERT INTO vinted_items VALUES (?, ?)",
                    [("https://example/items/sold", "sold"), ("https://example/items/active", "active")],
                )
                connection.executemany(
                    "INSERT INTO vinted_search_hits VALUES (?, 'charm', ?, ?, ?)",
                    [
                        ("https://example/items/sold", first_seen.isoformat(), now.isoformat(), 3),
                        ("https://example/items/active", now.isoformat(), now.isoformat(), 1),
                    ],
                )
                connection.executemany(
                    "INSERT INTO vinted_search_runs VALUES ('charm', 'charm', ?, ?)",
                    [(now.isoformat(), 2), ((now - timedelta(hours=1)).isoformat(), 4)],
                )
                connection.executemany(
                    "INSERT INTO vinted_deal_sale_tracking VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        ("https://example/items/sold", "sold", "Sold charm", first_seen.isoformat(), now.isoformat(), sold_at.isoformat(), "sold", json.dumps({"price_value": 15.0, "favorite_count": 30, "deal_sale_duration_seconds": 7200})),
                        ("https://example/items/active", "active", "Active charm", now.isoformat(), now.isoformat(), "", "active", json.dumps({"price_value": 25.0, "favorite_count": 10})),
                    ],
                )

            report = build_vinted_report(root, days=7, db_path=db_path)

        charm = next(row for row in report["keyword_metrics"] if row["keyword"] == "charm")
        self.assertEqual(2, charm["search_runs"])
        self.assertEqual(6, charm["run_result_count"])
        self.assertEqual(2, charm["items_seen"])
        self.assertEqual(1, charm["sold_items"])
        self.assertEqual(1, charm["active_items"])
        self.assertEqual(50.0, charm["sell_through_percent"])
        self.assertEqual(20.0, charm["average_price"])
        self.assertEqual(7200, charm["average_sale_seconds"])

    def test_owned_profile_active_count_excludes_items_checked_as_sold(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            db_path = root / "scraper.db"
            with sqlite3.connect(db_path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE vinted_profile_snapshots(
                        id INTEGER PRIMARY KEY, member_id TEXT, profile_url TEXT,
                        checked_at TEXT, item_count INTEGER, new_count INTEGER,
                        gone_count INTEGER, still_count INTEGER
                    );
                    CREATE TABLE vinted_profile_snapshot_items(
                        id INTEGER PRIMARY KEY, snapshot_id INTEGER, member_id TEXT,
                        profile_url TEXT, item_link TEXT, item_id TEXT, item_name TEXT,
                        price_text TEXT, image_url TEXT, status TEXT, present INTEGER,
                        snapshot_json TEXT
                    );
                    """
                )
                connection.execute(
                    "INSERT INTO vinted_profile_snapshots VALUES (1, '123', 'https://www.vinted.it/member/123', '2026-10-21T10:00:00', 1, 0, 0, 1)"
                )
                connection.executemany(
                    "INSERT INTO vinted_profile_snapshot_items VALUES (?, 1, '123', 'https://www.vinted.it/member/123', ?, ?, ?, '', '', ?, ?, ?) ",
                    [
                        (1, "https://www.vinted.it/items/1", "1", "Sold bracelet", "sold", 0,
                         json.dumps({"profile_sold_at": "2026-10-21T10:00:00", "profile_sold_after_seconds": 3600})),
                        (2, "https://www.vinted.it/items/2", "2", "Active bracelet", "still_active", 1, "{}"),
                    ],
                )
            save_owned_profile(root, profile_url="https://www.vinted.it/member/123", db_path=db_path)

            report = build_vinted_report(root, db_path=db_path)
            profile = report["owned_profiles"][0]

        self.assertEqual(1, profile["active_items_count"])
        self.assertEqual(1, profile["sold_items_count"])

    def test_report_aggregates_metrics_series_and_article_cards(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            db_path = root / "scraper.db"
            now = datetime.now().replace(microsecond=0)
            first_seen = now - timedelta(hours=3)
            with sqlite3.connect(db_path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE vinted_items(
                        link TEXT PRIMARY KEY, item_id TEXT, name TEXT, price_text TEXT,
                        seller_name TEXT, seller_profile_url TEXT, seller_member_id TEXT,
                        first_seen_at TEXT, last_seen_at TEXT
                    );
                    CREATE TABLE vinted_unavailable_items(item_link TEXT PRIMARY KEY, item_id TEXT);
                    CREATE TABLE vinted_competitors(
                        seller_member_id TEXT PRIMARY KEY, seller_name TEXT,
                        seller_profile_url TEXT, status TEXT, top_deal_keyword TEXT,
                        same_keyword_deal_count INTEGER, interesting_item_count INTEGER,
                        distinct_search_terms INTEGER, gone_item_count INTEGER,
                        max_favorite_count INTEGER, score REAL, last_seen_at TEXT
                    );
                    CREATE TABLE vinted_search_hits(search_term TEXT, times_seen INTEGER);
                    CREATE TABLE vinted_deal_sale_tracking(
                        item_link TEXT PRIMARY KEY, item_id TEXT, item_name TEXT,
                        first_seen_at TEXT, last_checked_at TEXT, sold_at TEXT,
                        status TEXT, payload_json TEXT
                    );
                    CREATE TABLE vinted_trend_queries(
                        query_text TEXT, brand TEXT, query_kind TEXT, status TEXT, enabled INTEGER,
                        mature_count INTEGER, sold_count INTEGER, sell_through_percent REAL,
                        confidence_lower_percent REAL, scans_count INTEGER, empty_streak INTEGER,
                        error_streak INTEGER, last_scan_at TEXT, next_review_at TEXT, last_error TEXT
                    );
                    """
                )
                connection.executemany(
                    "INSERT INTO vinted_items(link, item_id) VALUES (?, ?)",
                    [("https://example/items/1", "1"), ("https://example/items/2", "2")],
                )
                connection.execute(
                    "INSERT INTO vinted_unavailable_items(item_link, item_id) VALUES (?, ?)",
                    ("https://example/items/3", "3"),
                )
                connection.executemany(
                    """INSERT INTO vinted_competitors(
                        seller_member_id, seller_name, seller_profile_url, status,
                        top_deal_keyword, same_keyword_deal_count, interesting_item_count,
                        distinct_search_terms, gone_item_count, max_favorite_count, score, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        ("10", "Charm Seller", "https://example/member/10", "confirmed", "charm", 3, 4, 1, 0, 75, 149, now.isoformat()),
                        ("11", "Candidate Seller", "https://example/member/11", "candidate", "pandora", 1, 1, 1, 0, 20, 45, now.isoformat()),
                    ],
                )
                connection.execute("INSERT INTO vinted_search_hits(search_term, times_seen) VALUES ('charm', 12)")
                connection.execute(
                    "INSERT INTO vinted_deal_sale_tracking VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "https://example/items/1", "1", "Silver charm",
                        first_seen.isoformat(), now.isoformat(), now.isoformat(), "sold",
                        json.dumps({
                            "price": "15,00 €",
                            "price_value": 15.0,
                            "image_url": "https://img/1.jpg",
                            "deal_sale_duration_seconds": 7_200,
                            "deal_sale_duration_source": "listing_age",
                            "deal_listing_age_text": "2 ore fa",
                            "seller_member_id": "10",
                            "seller_name": "Charm Seller",
                        }),
                    ),
                )
                connection.execute(
                    "INSERT INTO vinted_trend_queries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ("collane", "Categoria", "category", "promising", 1, 40, 8, 20.0, 10.5, 6, 0, 0, now.isoformat(), "", ""),
                )
                connection.execute(
                    "INSERT INTO vinted_deal_sale_tracking VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "https://example/items/2", "2", "Active ring",
                        now.isoformat(), now.isoformat(), "", "active", json.dumps({"price": "20,00 €"}),
                    ),
                )

            save_owned_profile(
                root,
                profile_url="https://example/member/10",
                display_name="My shop",
                db_path=db_path,
            )
            report = build_vinted_report(root, days=7, db_path=db_path)
            limited_report = build_vinted_report(root, days=7, limit=1, db_path=db_path)
            html_path = write_vinted_report_html(root, days=7, db_path=db_path)
            html = html_path.read_text(encoding="utf-8")
            removed = deactivate_owned_profile(root, "10", db_path=db_path)
            after_removal = build_vinted_report(root, days=7, db_path=db_path)

        self.assertTrue(report["available"])
        self.assertEqual(2, report["summary"]["total_items"])
        self.assertEqual(1, report["summary"]["active_deals"])
        self.assertEqual(1, report["summary"]["sold_total"])
        self.assertEqual(1, report["summary"]["sold_in_period"])
        self.assertEqual("2h 0m", report["summary"]["average_sale_text"])
        self.assertEqual(50.0, report["summary"]["conversion_rate"])
        self.assertEqual(7, len(report["daily_sales"]))
        self.assertEqual(2, len(report["articles"]))
        self.assertEqual("charm", report["top_searches"][0]["term"])
        self.assertEqual(1, len(report["competitor_profiles"]))
        self.assertEqual("collane", report["trend_queries"][0]["query_text"])
        self.assertEqual("Candidate Seller", report["competitor_profiles"][0]["seller_name"])
        self.assertEqual(1, len([profile for profile in report["owned_profiles"] if profile["member_id"] == "10"]))
        owned = next(profile for profile in report["owned_profiles"] if profile["member_id"] == "10")
        self.assertEqual("My shop", owned["display_name"])
        self.assertEqual(1, owned["sold_items_count"])
        sold_article = next(article for article in report["articles"] if article["status"] == "sold")
        self.assertEqual(7_200, sold_article["sold_after_seconds"])
        self.assertEqual("listing_age", sold_article["sale_duration_source"])
        self.assertEqual(1, len(limited_report["articles"]))
        self.assertEqual(1, limited_report["summary"]["sold_in_period"])
        self.assertIn("Marketplace Intelligence Report", html)
        self.assertIn("My shop", html)
        self.assertIn("Silver charm", html)
        self.assertIn("Category trend cohorts", html)
        self.assertIn("Keyword performance", html)
        self.assertIn("Results returned", html)
        self.assertIn("collane", html)
        self.assertTrue(html_path.name.startswith("marketplace-report-"))
        self.assertTrue(removed["history_preserved"])
        self.assertFalse(any(profile["member_id"] == "10" for profile in after_removal["owned_profiles"]))

    def test_report_supports_legacy_trend_schema_without_query_kind(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            db_path = root / "scraper.db"
            with sqlite3.connect(db_path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE vinted_trend_queries(
                        query_text TEXT, brand TEXT, status TEXT, enabled INTEGER,
                        mature_count INTEGER, sold_count INTEGER, sell_through_percent REAL,
                        confidence_lower_percent REAL, scans_count INTEGER, empty_streak INTEGER,
                        error_streak INTEGER, last_scan_at TEXT, next_review_at TEXT, last_error TEXT
                    );
                    INSERT INTO vinted_trend_queries VALUES
                        ('charm', 'Pandora', 'learning', 1, 2, 0, 0, 0, 1, 0, 0, '', '', '');
                    """
                )
            report = build_vinted_report(root, db_path=db_path)
        self.assertEqual("brand_product", report["trend_queries"][0]["query_kind"])


if __name__ == "__main__":
    unittest.main()
