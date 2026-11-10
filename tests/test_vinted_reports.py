import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from agent_runtime.vinted_reports import (
    _best_item_name,
    build_vinted_competitor_report,
    build_vinted_report,
    deactivate_owned_profile,
    ignore_owned_profile_item,
    save_owned_profile,
    write_vinted_report_html,
)


class VintedReportsTests(unittest.TestCase):
    def test_owned_report_hides_unverified_legacy_profile_items(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            db_path = root / "scraper.db"
            with sqlite3.connect(db_path) as connection:
                connection.executescript("""
                    CREATE TABLE vinted_profile_snapshots (
                        id INTEGER PRIMARY KEY, member_id TEXT, profile_url TEXT,
                        checked_at TEXT, item_count INTEGER, new_count INTEGER,
                        gone_count INTEGER, still_count INTEGER
                    );
                    CREATE TABLE vinted_profile_snapshot_items (
                        id INTEGER PRIMARY KEY, snapshot_id INTEGER, member_id TEXT,
                        profile_url TEXT, item_link TEXT, item_id TEXT, item_name TEXT,
                        price_text TEXT, image_url TEXT, status TEXT, present INTEGER,
                        snapshot_json TEXT
                    );
                    CREATE TABLE vinted_items (
                        link TEXT PRIMARY KEY, item_id TEXT, name TEXT, price_text TEXT,
                        seller_name TEXT, seller_profile_url TEXT, seller_member_id TEXT,
                        first_seen_at TEXT, last_seen_at TEXT
                    );
                """)
                url = "https://www.vinted.it/member/225753959"
                connection.execute("INSERT INTO vinted_profile_snapshots VALUES (1,?,?,?,2,2,0,0)", ("225753959", url, "2026-11-01T10:00:00"))
                connection.execute("INSERT INTO vinted_profile_snapshots VALUES (2,?,?,?,1,0,0,1)", ("225753959", url, "2026-11-07T10:00:00"))
                connection.execute(
                    "INSERT INTO vinted_items VALUES (?,?,?,?,?,?,?,?,?)",
                    ("https://www.vinted.it/items/3", "3", "Sold owned", "15 €", "bonaccarla", url, "225753959", "2026-11-01T10:00:00", "2026-11-01T11:00:00"),
                )
                connection.executemany(
                    "INSERT INTO vinted_profile_snapshot_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        (1, 1, "225753959", url, "https://www.vinted.it/items/1", "1", "Owned", "10 €", "", "unknown", 1, "{}"),
                        (2, 1, "225753959", url, "https://www.vinted.it/items/2", "2", "Recommendation", "20 €", "", "new", 1, "{}"),
                        (3, 2, "225753959", url, "https://www.vinted.it/items/1", "1", "Owned", "10 €", "", "still_active", 1, json.dumps({"profile_inventory_source": "wardrobe_api"})),
                        (4, 1, "225753959", url, "https://www.vinted.it/items/3", "3", "Sold owned", "15 €", "", "sold", 0, json.dumps({"profile_item_status": "sold", "profile_sold_at": "2026-11-01T11:00:00", "profile_sold_after_seconds": 3600})),
                    ],
                )
            save_owned_profile(root, profile_url=url, db_path=db_path)
            profile = next(item for item in build_vinted_report(root, db_path=db_path)["owned_profiles"] if item["member_id"] == "225753959")
            ignored = ignore_owned_profile_item(root, "225753959", "3", db_path=db_path)
            after_ignore = next(item for item in build_vinted_report(root, db_path=db_path)["owned_profiles"] if item["member_id"] == "225753959")
            with sqlite3.connect(db_path) as connection:
                historical_rows = connection.execute("SELECT COUNT(*) FROM vinted_profile_snapshot_items WHERE member_id = '225753959' AND item_id = '3'").fetchone()[0]

        self.assertEqual({"1", "3"}, {item["item_id"] for item in profile["items"]})
        self.assertEqual(2, profile["known_items_count"])
        self.assertEqual(1, profile["active_items_count"])
        self.assertEqual(1, profile["sold_items_count"])
        self.assertEqual(3600, profile["average_sale_seconds"])
        self.assertEqual("active", next(item for item in profile["items"] if item["item_id"] == "1")["status"])
        self.assertTrue(ignored["history_preserved"])
        self.assertEqual(1, historical_rows)
        self.assertEqual(["1"], [item["item_id"] for item in after_ignore["items"]])
        self.assertEqual(0, after_ignore["sold_items_count"])

    def test_procacciatore_report_adds_velocity_cohorts_and_demand_supply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            shared_db, proc_db = root / "scraper.db", root / "procacciatore.db"
            now = datetime.now().replace(microsecond=0)
            first, prior = (now - timedelta(hours=2)).isoformat(), (now - timedelta(hours=1)).isoformat()
            with sqlite3.connect(shared_db):
                pass
            with sqlite3.connect(proc_db) as connection:
                connection.executescript("""
                    CREATE TABLE vinted_deal_sale_tracking (
                        item_link TEXT PRIMARY KEY,item_id TEXT,item_name TEXT,first_seen_at TEXT,last_checked_at TEXT,
                        sold_at TEXT,status TEXT,availability_status TEXT,unavailable_at TEXT,unavailable_reason TEXT,payload_json TEXT
                    );
                    CREATE TABLE vinted_procacciatore_listings (
                        item_link TEXT,search_term TEXT,item_id TEXT,item_name TEXT,category TEXT,image_url TEXT,
                        first_seen_at TEXT,last_seen_at TEXT,first_price_value REAL,price_value REAL,price_text TEXT,
                        favorite_count INTEGER,times_seen INTEGER
                    );
                    CREATE TABLE vinted_procacciatore_snapshots (
                        item_link TEXT,search_term TEXT,observed_at TEXT,price_value REAL,favorite_count INTEGER
                    );
                """)
                links = ["https://vinted.test/items/sold", "https://vinted.test/items/active", "https://vinted.test/items/gone"]
                tracking = [
                    (links[0], "1", "Anello venduto", first, now.isoformat(), now.isoformat(), "sold", "available", "", "", json.dumps({"favorite_count": 20, "deal_sale_duration_seconds": 7200, "price": "15 €", "search_term": "anelli"})),
                    (links[1], "2", "Anello attivo", first, now.isoformat(), "", "active", "available", "", "", json.dumps({"favorite_count": 12, "price": "13 €", "search_term": "anelli"})),
                    (links[2], "3", "Anello non disponibile", first, now.isoformat(), "", "unavailable", "unavailable", now.isoformat(), "not_found", json.dumps({"favorite_count": 9, "price": "15 €", "search_term": "anelli"})),
                ]
                connection.executemany("INSERT INTO vinted_deal_sale_tracking VALUES (?,?,?,?,?,?,?,?,?,?,?)", tracking)
                connection.executemany(
                    "INSERT INTO vinted_procacciatore_listings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(link, "anelli", str(index + 1), name, "Gioielli", "", first, now.isoformat(), 15.0, price, f"{price} €", likes, 2)
                     for index, (link, name, price, likes) in enumerate(zip(links, ["Pandora", "Pandora", "Silver"], [15, 13, 15], [20, 12, 9]))],
                )
                connection.executemany(
                    "INSERT INTO vinted_procacciatore_snapshots VALUES (?,?,?,?,?)",
                    [(links[1], "anelli", prior, 15, 8), (links[1], "anelli", now.isoformat(), 13, 12)],
                )
            report = build_vinted_report(root, db_path=shared_db, procacciatore_db_path=proc_db)
            procacciatore = report["procacciatore"]
            self.assertEqual(3, procacciatore["summary"]["observed_count"])
            self.assertEqual(3, procacciatore["summary"]["observed_supply_24h"])
            self.assertEqual(1, procacciatore["summary"]["tracked_unavailable_count"])
            self.assertEqual(2, procacciatore["summary"]["tracked_active_count"] + procacciatore["summary"]["tracked_sold_count"])
            self.assertEqual(50.0, procacciatore["summary"]["tracked_sell_through_rate"])
            self.assertAlmostEqual(1 / 3, procacciatore["summary"]["demand_supply_ratio"], places=3)
            cohort = procacciatore["cohorts"][0]
            self.assertEqual("anelli", cohort["search_term"])
            self.assertEqual(50.0, cohort["sell_through_rate"])
            self.assertEqual(1, cohort["sold_within_24h"])
            active = next(article for article in procacciatore["articles"] if article["item_id"] == "2")
            self.assertEqual(4.0, active["likes_per_hour"])
            self.assertEqual(-2.0, active["price_change_value"])
            pandora = next(brand for brand in procacciatore["brands"] if brand["name"] == "Pandora")
            self.assertEqual(2, pandora["observed_count"])
            self.assertEqual(1, pandora["sold_count"])
            self.assertEqual(14.0, pandora["average_price"])
            self.assertEqual(7200, pandora["average_sale_seconds"])
            silver = next(brand for brand in procacciatore["brands"] if brand["name"] == "Silver")
            self.assertEqual("Etichetta generica / da verificare", silver["label_type"])

    def test_procacciatore_report_reads_independent_tracking_database(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            shared_db = root / "scraper.db"
            proc_db = root / "procacciatore.db"
            now = datetime.now().replace(microsecond=0)
            first_seen = now - timedelta(hours=4)
            with sqlite3.connect(shared_db):
                pass
            with sqlite3.connect(proc_db) as connection:
                connection.execute(
                    """CREATE TABLE vinted_deal_sale_tracking (
                        item_link TEXT PRIMARY KEY, item_id TEXT, item_name TEXT,
                        first_seen_at TEXT, last_checked_at TEXT, sold_at TEXT,
                        status TEXT, availability_status TEXT, unavailable_at TEXT,
                        unavailable_reason TEXT, payload_json TEXT
                    )"""
                )
                connection.executemany(
                    "INSERT INTO vinted_deal_sale_tracking VALUES (?, ?, ?, ?, ?, ?, ?, 'available', '', '', ?)",
                    [
                        ("https://vinted.test/items/sold", "1", "Anello venduto", first_seen.isoformat(), now.isoformat(), now.isoformat(), "sold", json.dumps({"favorite_count": 42, "deal_sale_duration_seconds": 14400, "price": "15 €", "search_term": "anelli"})),
                        ("https://vinted.test/items/active", "2", "Collana attiva", now.isoformat(), now.isoformat(), "", "active", json.dumps({"favorite_count": 90, "price": "20 €", "search_term": "collane"})),
                    ],
                )

            report = build_vinted_report(root, db_path=shared_db, procacciatore_db_path=proc_db)

        procacciatore = report["procacciatore"]
        self.assertEqual(2, procacciatore["summary"]["tracked_count"])
        self.assertEqual(1, procacciatore["summary"]["sold_count"])
        self.assertEqual(14400, procacciatore["summary"]["average_sale_seconds"])
        self.assertEqual("2", procacciatore["top_liked"][0]["item_id"])
        self.assertEqual("anelli", next(item for item in procacciatore["articles"] if item["status"] == "sold")["search_term"])

    def test_owned_profile_ignores_legacy_empty_snapshot_marked_gone(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            db_path = root / "scraper.db"
            profile_url = "https://www.vinted.it/member/123"
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
                connection.execute("INSERT INTO vinted_profile_snapshots VALUES (1,'123',?,'2026-10-25T10:00:00',1,1,0,0)", (profile_url,))
                connection.execute("INSERT INTO vinted_profile_snapshots VALUES (2,'123',?,'2026-10-26T10:00:00',0,0,1,0)", (profile_url,))
                connection.execute(
                    "INSERT INTO vinted_profile_snapshot_items VALUES (1,1,'123',?, 'https://www.vinted.it/items/55-charm','55','Charm','10,00 €','','new',1,'{}')",
                    (profile_url,),
                )
                connection.execute(
                    "INSERT INTO vinted_profile_snapshot_items VALUES (2,2,'123',?, 'https://www.vinted.it/items/55-charm','55','Charm','10,00 €','','gone',0,'{}')",
                    (profile_url,),
                )
            save_owned_profile(root, profile_url=profile_url, db_path=db_path)

            profile = next(item for item in build_vinted_report(root, db_path=db_path)["owned_profiles"] if item["member_id"] == "123")

        self.assertEqual(1, profile["active_items_count"])
        self.assertEqual("2026-10-25T10:00:00", profile["latest_snapshot_at"])
        self.assertEqual("active", profile["items"][0]["status"])

    def test_competitor_profile_includes_listing_history_and_sale_timing(self) -> None:
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
                        favorite_count INTEGER, seller_name TEXT, seller_profile_url TEXT, seller_member_id TEXT, first_seen_at TEXT, last_seen_at TEXT
                    );
                    CREATE TABLE vinted_competitors(
                        seller_member_id TEXT PRIMARY KEY, seller_name TEXT, seller_profile_url TEXT,
                        status TEXT, top_deal_keyword TEXT, same_keyword_deal_count INTEGER,
                        interesting_item_count INTEGER, distinct_search_terms INTEGER, gone_item_count INTEGER,
                        max_favorite_count INTEGER, score REAL, last_seen_at TEXT, manual_priority INTEGER
                    );
                    CREATE TABLE vinted_deal_sale_tracking(
                        item_link TEXT PRIMARY KEY, item_id TEXT, item_name TEXT, first_seen_at TEXT,
                        last_checked_at TEXT, sold_at TEXT, status TEXT, payload_json TEXT
                    );
                    """
                )
                connection.execute(
                    "INSERT INTO vinted_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ("https://example/items/1", "1", "Gold star charm", "15,00 €", 22, "Seller 55", "https://example/member/55", "55", first_seen.isoformat(), now.isoformat()),
                )
                connection.execute(
                    "INSERT INTO vinted_competitors VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ("55", "Seller 55", "https://example/member/55", "priority", "charm", 3, 1, 1, 0, 22, 90, now.isoformat(), 1),
                )
                connection.execute(
                    "INSERT INTO vinted_deal_sale_tracking VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    ("https://example/items/1", "1", "Gold star charm", first_seen.isoformat(), now.isoformat(), now.isoformat(), "sold", json.dumps({"seller_member_id": "55", "favorite_count": 22, "deal_sale_duration_seconds": 10_800, "image_url": "https://img/1.jpg", "search_term": "charm"})),
                )

            report = build_vinted_competitor_report(root, "55", db_path=db_path)

        profile = report
        self.assertEqual("55", profile["seller_member_id"])
        self.assertEqual(1, profile["sold_items_count"])
        self.assertEqual(10_800, profile["average_sale_seconds"])
        self.assertEqual("Gold star charm", profile["items"][0]["name"])
        self.assertEqual("sold", profile["items"][0]["status"])
        self.assertEqual(10_800, profile["items"][0]["sold_after_seconds"])

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
                    "INSERT INTO vinted_profile_snapshot_items VALUES (?, 1, '123', 'https://www.vinted.it/member/123', ?, ?, ?, '', ?, ?, ?, ?) ",
                    [
                        (1, "https://www.vinted.it/items/1", "1", "Sold bracelet", "", "sold", 0,
                         json.dumps({"profile_sold_at": "2026-10-21T10:00:00", "profile_sold_after_seconds": 3600})),
                        (2, "https://www.vinted.it/items/2", "2", "Active bracelet", "https://images.example/bracelet.webp", "still_active", 1, "{}"),
                        (3, "https://www.vinted.it/items/3", "3", "Unknown listing", "", "unknown", 1, "{}"),
                    ],
                )
            save_owned_profile(root, profile_url="https://www.vinted.it/member/123", db_path=db_path)

            report = build_vinted_report(root, db_path=db_path)
            profile = report["owned_profiles"][0]
            html_path = write_vinted_report_html(root, db_path=db_path)
            html = html_path.read_text(encoding="utf-8")
            (root / "config").mkdir()
            (root / "config" / "owned_profile_exclusions.json").write_text(
                json.dumps({"123": ["2"]}), encoding="utf-8"
            )
            filtered_profile = build_vinted_report(root, db_path=db_path)["owned_profiles"][0]

        self.assertEqual(1, profile["active_items_count"])
        self.assertEqual(1, profile["sold_items_count"])
        self.assertNotIn("Unknown listing", [item["name"] for item in profile["items"]])
        self.assertIn("images.example/bracelet.webp", html)
        self.assertEqual(0, filtered_profile["active_items_count"])
        self.assertEqual(1, filtered_profile["known_items_count"])
        self.assertEqual(["1"], [item["item_id"] for item in filtered_profile["items"]])
        self.assertIn("owned-thumbnails", html)

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
