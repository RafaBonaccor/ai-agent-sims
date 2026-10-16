from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from statistics import median
from typing import Any


DEFAULT_REPORT_DB = Path("projects") / "main-scraper" / "data" / "scraper.db"
INITIAL_OWNED_PROFILES = (
    ("225753959", "https://www.vinted.it/member/225753959", "bonaccarla"),
    ("3178210259", "https://www.vinted.it/member/3178210259", "accordij"),
)


def _normalize_member_id(value: object) -> str:
    raw = str(value or "").strip().rstrip("/")
    if not raw:
        return ""
    candidate = raw.rsplit("/", 1)[-1].split("?", 1)[0].strip()
    return candidate if candidate.isdigit() else ""


def _ensure_owned_profiles_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS vinted_owned_profiles (
            member_id TEXT PRIMARY KEY,
            profile_url TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    now = datetime.now().isoformat(timespec="seconds")
    connection.executemany(
        """
        INSERT INTO vinted_owned_profiles (
            member_id, profile_url, display_name, active, created_at, updated_at
        ) VALUES (?, ?, ?, 1, ?, ?)
        ON CONFLICT(member_id) DO UPDATE SET
            display_name = CASE
                WHEN vinted_owned_profiles.display_name = '' THEN excluded.display_name
                ELSE vinted_owned_profiles.display_name
            END
        """,
        [(member_id, profile_url, name, now, now) for member_id, profile_url, name in INITIAL_OWNED_PROFILES],
    )
    connection.commit()


def save_owned_profile(
    project_root: str | Path,
    *,
    profile_url: str,
    display_name: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    database = Path(db_path).expanduser().resolve() if db_path else (root / DEFAULT_REPORT_DB).resolve()
    normalized_url = str(profile_url or "").strip().rstrip("/")
    member_id = _normalize_member_id(normalized_url)
    if not member_id:
        raise ValueError("Enter a valid marketplace member profile URL.")
    if not database.exists():
        raise ValueError("The marketplace report database is not available yet.")
    now = datetime.now().isoformat(timespec="seconds")
    with closing(sqlite3.connect(database)) as connection:
        _ensure_owned_profiles_schema(connection)
        connection.execute(
            """
            INSERT INTO vinted_owned_profiles (
                member_id, profile_url, display_name, active, created_at, updated_at
            ) VALUES (?, ?, ?, 1, ?, ?)
            ON CONFLICT(member_id) DO UPDATE SET
                profile_url = excluded.profile_url,
                display_name = CASE
                    WHEN excluded.display_name <> '' THEN excluded.display_name
                    ELSE vinted_owned_profiles.display_name
                END,
                active = 1,
                updated_at = excluded.updated_at
            """,
            (member_id, normalized_url, str(display_name or "").strip(), now, now),
        )
        connection.commit()
    return {"member_id": member_id, "profile_url": normalized_url, "display_name": str(display_name or "").strip(), "active": True}


def deactivate_owned_profile(
    project_root: str | Path,
    member_id: str,
    *,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    database = Path(db_path).expanduser().resolve() if db_path else (root / DEFAULT_REPORT_DB).resolve()
    normalized_id = _normalize_member_id(member_id)
    if not normalized_id or not database.exists():
        raise ValueError("Owned profile not found.")
    with closing(sqlite3.connect(database)) as connection:
        _ensure_owned_profiles_schema(connection)
        cursor = connection.execute(
            "UPDATE vinted_owned_profiles SET active = 0, updated_at = ? WHERE member_id = ?",
            (datetime.now().isoformat(timespec="seconds"), normalized_id),
        )
        connection.commit()
        if cursor.rowcount <= 0:
            raise ValueError("Owned profile not found.")
    return {"member_id": normalized_id, "active": False, "history_preserved": True}


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone() is not None


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(connection, table):
        return set()
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _safe_payload(value: object) -> dict[str, Any]:
    try:
        payload = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _elapsed_seconds(start: str, end: str) -> int | None:
    try:
        return max(int((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()), 0)
    except (TypeError, ValueError):
        return None


def _format_duration(seconds: int | float | None) -> str:
    if seconds is None:
        return ""
    total = max(int(seconds), 0)
    days, remainder = divmod(total, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes = remainder // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _sale_duration(first_seen: str, sold_at: str, payload: dict[str, Any]) -> tuple[int | None, str]:
    stored = payload.get("deal_sale_duration_seconds")
    if isinstance(stored, (int, float)):
        return max(int(stored), 0), str(payload.get("deal_sale_duration_source", "") or "listing_age")
    return _elapsed_seconds(first_seen, sold_at), "deal_discovery"


def _count(connection: sqlite3.Connection, table: str, where: str = "", values: tuple = ()) -> int:
    if not _table_exists(connection, table):
        return 0
    suffix = f" WHERE {where}" if where else ""
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}{suffix}", values).fetchone()[0])


def build_vinted_report(
    project_root: str | Path,
    *,
    days: int = 30,
    limit: int = 200,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    normalized_days = max(min(int(days or 30), 3650), 1)
    normalized_limit = max(min(int(limit or 200), 5000), 1)
    root = Path(project_root).expanduser().resolve()
    database = Path(db_path).expanduser().resolve() if db_path else (root / DEFAULT_REPORT_DB).resolve()
    since = (datetime.now() - timedelta(days=normalized_days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    empty = {
        "available": False,
        "db_path": str(database),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "period_days": normalized_days,
        "summary": {},
        "daily_sales": [],
        "status_distribution": [],
        "top_searches": [],
        "articles": [],
        "competitor_profiles": [],
        "trend_queries": [],
        "owned_profiles": [],
    }
    if not database.exists():
        return empty

    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        _ensure_owned_profiles_schema(connection)
        owned_registry = connection.execute(
            "SELECT member_id, profile_url, display_name, created_at, updated_at FROM vinted_owned_profiles WHERE active = 1 ORDER BY created_at, member_id"
        ).fetchall()
        owned_member_ids = {str(row["member_id"] or "") for row in owned_registry}
        total_items = _count(connection, "vinted_items")
        unavailable = _count(connection, "vinted_unavailable_items")
        competitor_exclusion = ""
        competitor_values: tuple[object, ...] = ()
        if owned_member_ids:
            placeholders = ",".join("?" for _ in owned_member_ids)
            competitor_exclusion = f"seller_member_id NOT IN ({placeholders})"
            competitor_values = tuple(sorted(owned_member_ids))
        competitors = _count(connection, "vinted_competitors", competitor_exclusion, competitor_values)
        priority_where = "status IN ('priority', 'confirmed')"
        if competitor_exclusion:
            priority_where += f" AND {competitor_exclusion}"
        priority_competitors = _count(connection, "vinted_competitors", priority_where, competitor_values)
        active_deals = _count(connection, "vinted_deal_sale_tracking", "status = 'active'")
        sold_total = _count(connection, "vinted_deal_sale_tracking", "status = 'sold'")

        tracking_rows: list[sqlite3.Row] = []
        period_sales_rows: list[sqlite3.Row] = []
        if _table_exists(connection, "vinted_deal_sale_tracking"):
            tracking_columns = _table_columns(connection, "vinted_deal_sale_tracking")
            availability_select = (
                "availability_status" if "availability_status" in tracking_columns
                else "'available' AS availability_status"
            )
            unavailable_at_select = (
                "unavailable_at" if "unavailable_at" in tracking_columns
                else "'' AS unavailable_at"
            )
            unavailable_reason_select = (
                "unavailable_reason" if "unavailable_reason" in tracking_columns
                else "'' AS unavailable_reason"
            )
            recent_where = "first_seen_at >= ? OR sold_at >= ?"
            if "unavailable_at" in tracking_columns:
                recent_where += " OR unavailable_at >= ?"
                recent_values: tuple[object, ...] = (
                    since.isoformat(timespec="seconds"),
                    since.isoformat(timespec="seconds"),
                    since.isoformat(timespec="seconds"),
                    normalized_limit,
                )
            else:
                recent_values = (
                    since.isoformat(timespec="seconds"),
                    since.isoformat(timespec="seconds"),
                    normalized_limit,
                )
            period_sales_rows = connection.execute(
                """
                SELECT first_seen_at, sold_at, payload_json
                FROM vinted_deal_sale_tracking
                WHERE status = 'sold' AND sold_at >= ?
                ORDER BY sold_at DESC
                """,
                (since.isoformat(timespec="seconds"),),
            ).fetchall()
            tracking_rows = connection.execute(
                f"""
                SELECT item_link, item_id, item_name, first_seen_at, last_checked_at,
                       sold_at, status, {availability_select}, {unavailable_at_select},
                       {unavailable_reason_select}, payload_json
                FROM vinted_deal_sale_tracking
                WHERE {recent_where}
                ORDER BY CASE
                    WHEN sold_at <> '' THEN sold_at
                    WHEN unavailable_at <> '' THEN unavailable_at
                    ELSE first_seen_at
                END DESC
                LIMIT ?
                """,
                recent_values,
            ).fetchall()

        articles: list[dict[str, Any]] = []
        sold_durations: list[int] = []
        sold_prices: list[float] = []
        daily: dict[str, dict[str, int]] = {}
        for offset in range(normalized_days):
            day = (since + timedelta(days=offset)).date().isoformat()
            daily[day] = {"date": day, "sold_count": 0, "average_seconds": 0, "_total_seconds": 0}

        for record in period_sales_rows:
            first_seen = str(record["first_seen_at"] or "")
            sold_at = str(record["sold_at"] or "")
            payload = _safe_payload(record["payload_json"])
            elapsed, _duration_source = _sale_duration(first_seen, sold_at, payload)
            if elapsed is not None:
                sold_durations.append(elapsed)
                day = sold_at[:10]
                if day in daily:
                    daily[day]["sold_count"] += 1
                    daily[day]["_total_seconds"] += elapsed
            price_value = payload.get("price_value")
            if isinstance(price_value, (int, float)):
                sold_prices.append(float(price_value))

        for record in tracking_rows:
            payload = _safe_payload(record["payload_json"])
            status = str(record["status"] or "active")
            first_seen = str(record["first_seen_at"] or "")
            sold_at = str(record["sold_at"] or "")
            if status == "sold" and sold_at:
                elapsed, duration_source = _sale_duration(first_seen, sold_at, payload)
            else:
                elapsed, duration_source = None, ""
            articles.append(
                {
                    "item_id": str(record["item_id"] or payload.get("item_id", "")),
                    "name": str(record["item_name"] or payload.get("name", "") or "Marketplace item"),
                    "link": str(record["item_link"] or payload.get("link", "")),
                    "image_url": str(payload.get("image_url", "") or ""),
                    "archive_image_path": str(payload.get("archive_image_path", "") or ""),
                    "price": str(payload.get("price", "") or payload.get("price_text", "") or ""),
                    "favorite_count": payload.get("favorite_count"),
                    "status": status,
                    "availability_status": str(record["availability_status"] or "available"),
                    "unavailable_at": str(record["unavailable_at"] or ""),
                    "unavailable_reason": str(record["unavailable_reason"] or ""),
                    "first_seen_at": first_seen,
                    "last_checked_at": str(record["last_checked_at"] or ""),
                    "sold_at": sold_at,
                    "sold_after_seconds": elapsed,
                    "sold_after_text": _format_duration(elapsed),
                    "sale_duration_source": duration_source,
                    "listing_age_text": str(payload.get("deal_listing_age_text", "") or ""),
                    "search_term": str(payload.get("search_term", "") or ""),
                    "archive_screenshot_path": str(payload.get("archive_screenshot_path", "") or ""),
                    "archive_html_path": str(payload.get("archive_html_path", "") or ""),
                }
            )

        # Older versions physically removed page-not-found deals from the
        # tracking table. Keep their tombstones visible as first-class report
        # rows so even the partially recoverable legacy history never appears
        # to vanish from the UI.
        tracked_keys = {
            key
            for article in articles
            for key in (
                f"id:{article.get('item_id')}" if article.get("item_id") else "",
                f"link:{article.get('link')}" if article.get("link") else "",
            )
            if key
        }
        unavailable_columns = _table_columns(connection, "vinted_unavailable_items")
        if "detected_at" in unavailable_columns:
            for record in connection.execute(
                "SELECT * FROM vinted_unavailable_items WHERE detected_at >= ? ORDER BY detected_at DESC",
                (since.isoformat(timespec="seconds"),),
            ).fetchall():
                record_keys = set(record.keys())
                item_id = str(record["item_id"] or "") if "item_id" in record_keys else ""
                link = str(record["item_link"] or "") if "item_link" in record_keys else ""
                identity_keys = {key for key in (f"id:{item_id}" if item_id else "", f"link:{link}" if link else "") if key}
                if tracked_keys.intersection(identity_keys):
                    continue
                payload = _safe_payload(record["snapshot_json"] if "snapshot_json" in record_keys else "")
                previous_status = str(record["previous_status"] or "") if "previous_status" in record_keys else ""
                sold_at = str(record["sold_at"] or "") if "sold_at" in record_keys else ""
                first_seen = str(record["first_seen_at"] or "") if "first_seen_at" in record_keys else ""
                local_image = str(record["local_image_path"] or "") if "local_image_path" in record_keys else ""
                screenshot = str(record["screenshot_path"] or "") if "screenshot_path" in record_keys else ""
                html_path = str(record["html_path"] or "") if "html_path" in record_keys else ""
                elapsed, duration_source = (
                    _sale_duration(first_seen, sold_at, payload)
                    if previous_status == "sold" and sold_at
                    else (None, "")
                )
                articles.append(
                    {
                        "item_id": item_id or str(payload.get("item_id", "") or ""),
                        "name": str(payload.get("name", "") or payload.get("item_name", "") or "Unavailable marketplace item"),
                        "link": link or str(payload.get("link", "") or ""),
                        "image_url": str(
                            (record["image_url"] if "image_url" in record_keys else "")
                            or payload.get("image_url", "")
                            or ""
                        ),
                        "archive_image_path": local_image or str(payload.get("archive_image_path", "") or ""),
                        "price": str(payload.get("price", "") or payload.get("price_text", "") or ""),
                        "favorite_count": payload.get("favorite_count"),
                        "status": "sold" if previous_status == "sold" else "unavailable",
                        "availability_status": "unavailable",
                        "unavailable_at": str(record["detected_at"] or ""),
                        "unavailable_reason": str(record["reason"] or "page_not_found"),
                        "first_seen_at": first_seen,
                        "last_checked_at": str(record["detected_at"] or ""),
                        "sold_at": sold_at,
                        "sold_after_seconds": elapsed,
                        "sold_after_text": _format_duration(elapsed),
                        "sale_duration_source": duration_source,
                        "listing_age_text": str(payload.get("deal_listing_age_text", "") or ""),
                        "search_term": str(payload.get("search_term", "") or ""),
                        "archive_screenshot_path": screenshot or str(payload.get("archive_screenshot_path", "") or ""),
                        "archive_html_path": html_path or str(payload.get("archive_html_path", "") or ""),
                    }
                )
                tracked_keys.update(identity_keys)

        articles = articles[:normalized_limit]

        daily_sales = []
        for entry in daily.values():
            count = entry["sold_count"]
            total_seconds = entry.pop("_total_seconds")
            entry["average_seconds"] = round(total_seconds / count) if count else 0
            daily_sales.append(entry)

        top_searches: list[dict[str, Any]] = []
        if _table_exists(connection, "vinted_search_hits"):
            top_searches = [
                {"term": str(row["search_term"] or "(category only)"), "seen": int(row["seen"] or 0)}
                for row in connection.execute(
                    """
                    SELECT search_term, SUM(times_seen) AS seen
                    FROM vinted_search_hits
                    GROUP BY search_term
                    ORDER BY seen DESC
                    LIMIT 8
                    """
                ).fetchall()
            ]

        competitor_profiles: list[dict[str, Any]] = []
        competitor_columns = _table_columns(connection, "vinted_competitors")
        if competitor_columns:
            def competitor_column(name: str, fallback: str) -> str:
                return name if name in competitor_columns else f"{fallback} AS {name}"

            selected_columns = [
                competitor_column("seller_member_id", "''"),
                competitor_column("seller_name", "''"),
                competitor_column("seller_profile_url", "''"),
                competitor_column("status", "'candidate'"),
                competitor_column("manual_priority", "0"),
                competitor_column("top_deal_keyword", "''"),
                competitor_column("same_keyword_deal_count", "0"),
                competitor_column("interesting_item_count", "0"),
                competitor_column("distinct_search_terms", "0"),
                competitor_column("gone_item_count", "0"),
                competitor_column("max_favorite_count", "0"),
                competitor_column("score", "0"),
                competitor_column("last_seen_at", "''"),
            ]
            owned_filter = ""
            owned_values: list[object] = []
            if owned_member_ids:
                placeholders = ",".join("?" for _ in owned_member_ids)
                owned_filter = f"WHERE seller_member_id NOT IN ({placeholders})"
                owned_values.extend(sorted(owned_member_ids))
            rows = connection.execute(
                f"""
                SELECT {', '.join(selected_columns)}
                FROM vinted_competitors
                {owned_filter}
                ORDER BY
                    CASE status
                        WHEN 'priority' THEN 0
                        WHEN 'confirmed' THEN 1
                        WHEN 'active' THEN 2
                        ELSE 3
                    END,
                    score DESC,
                    seller_name COLLATE NOCASE ASC
                LIMIT ?
                """,
                (*owned_values, normalized_limit),
            ).fetchall()
            competitor_profiles = [
                {
                    "seller_member_id": str(row["seller_member_id"] or ""),
                    "seller_name": str(row["seller_name"] or "") or f"Seller {row['seller_member_id']}",
                    "seller_profile_url": str(row["seller_profile_url"] or ""),
                    "status": str(row["status"] or "candidate"),
                    "manual_priority": bool(row["manual_priority"]),
                    "top_deal_keyword": str(row["top_deal_keyword"] or ""),
                    "same_keyword_deal_count": int(row["same_keyword_deal_count"] or 0),
                    "interesting_item_count": int(row["interesting_item_count"] or 0),
                    "distinct_search_terms": int(row["distinct_search_terms"] or 0),
                    "gone_item_count": int(row["gone_item_count"] or 0),
                    "max_favorite_count": int(row["max_favorite_count"] or 0),
                    "score": round(float(row["score"] or 0), 1),
                    "last_seen_at": str(row["last_seen_at"] or ""),
                }
                for row in rows
            ]

        trend_queries: list[dict[str, Any]] = []
        if _table_exists(connection, "vinted_trend_queries"):
            trend_queries = [dict(row) for row in connection.execute(
                """SELECT query_text,brand,query_kind,status,enabled,mature_count,sold_count,sell_through_percent,
                confidence_lower_percent,scans_count,empty_streak,error_streak,last_scan_at,next_review_at,last_error
                FROM vinted_trend_queries
                ORDER BY sell_through_percent DESC,mature_count DESC,query_text"""
            ).fetchall()]

        owned_profiles: list[dict[str, Any]] = []
        item_columns = _table_columns(connection, "vinted_items")
        snapshot_item_columns = _table_columns(connection, "vinted_profile_snapshot_items")
        for registry in owned_registry:
            member_id = str(registry["member_id"] or "")
            profile_url = str(registry["profile_url"] or "")
            known_items: dict[str, dict[str, Any]] = {}

            if item_columns and "seller_member_id" in item_columns:
                for row in connection.execute(
                    """
                    SELECT item_id, link, name, price_text, seller_name, seller_profile_url,
                           first_seen_at, last_seen_at
                    FROM vinted_items WHERE seller_member_id = ?
                    ORDER BY last_seen_at DESC
                    """,
                    (member_id,),
                ).fetchall():
                    key = str(row["item_id"] or row["link"] or "")
                    known_items[key] = {
                        "item_id": str(row["item_id"] or ""), "link": str(row["link"] or ""),
                        "name": str(row["name"] or "Marketplace item"), "price": str(row["price_text"] or ""),
                        "image_url": "", "status": "observed", "first_seen_at": str(row["first_seen_at"] or ""),
                        "last_seen_at": str(row["last_seen_at"] or ""), "sold_at": "",
                        "sold_after_seconds": None, "sold_after_text": "",
                        "seller_name": str(row["seller_name"] or ""),
                    }

            if _table_exists(connection, "vinted_deal_sale_tracking"):
                for row in connection.execute(
                    "SELECT * FROM vinted_deal_sale_tracking ORDER BY first_seen_at"
                ).fetchall():
                    payload = _safe_payload(row["payload_json"])
                    if str(payload.get("seller_member_id", "") or "") != member_id:
                        continue
                    item_id = str(row["item_id"] or payload.get("item_id", "") or "")
                    link = str(row["item_link"] or payload.get("link", "") or "")
                    key = item_id or link
                    status = str(row["status"] or "active")
                    sold_at = str(row["sold_at"] or "")
                    elapsed, _source = _sale_duration(str(row["first_seen_at"] or ""), sold_at, payload) if status == "sold" and sold_at else (None, "")
                    base = known_items.get(key, {})
                    known_items[key] = {
                        **base, "item_id": item_id, "link": link,
                        "name": str(row["item_name"] or payload.get("name", "") or base.get("name", "Marketplace item")),
                        "price": str(payload.get("price", "") or payload.get("price_text", "") or base.get("price", "")),
                        "image_url": str(payload.get("image_url", "") or base.get("image_url", "")),
                        "status": status, "first_seen_at": str(row["first_seen_at"] or base.get("first_seen_at", "")),
                        "last_seen_at": str(row["last_checked_at"] or base.get("last_seen_at", "")),
                        "sold_at": sold_at, "sold_after_seconds": elapsed,
                        "sold_after_text": _format_duration(elapsed),
                        "seller_name": str(payload.get("seller_name", "") or base.get("seller_name", "")),
                    }

            snapshots_count = 0
            latest_snapshot_at = ""
            latest_active_count = 0
            if _table_exists(connection, "vinted_profile_snapshots"):
                snapshot_summary = connection.execute(
                    "SELECT COUNT(*) AS snapshots_count, MAX(checked_at) AS latest_snapshot_at FROM vinted_profile_snapshots WHERE member_id = ?",
                    (member_id,),
                ).fetchone()
                snapshots_count = int(snapshot_summary["snapshots_count"] or 0)
                latest_snapshot_at = str(snapshot_summary["latest_snapshot_at"] or "")
                latest = connection.execute(
                    "SELECT item_count FROM vinted_profile_snapshots WHERE member_id = ? ORDER BY checked_at DESC, id DESC LIMIT 1",
                    (member_id,),
                ).fetchone()
                latest_active_count = int(latest["item_count"] or 0) if latest else 0

            if snapshot_item_columns:
                rows = connection.execute(
                    """
                    SELECT psi.*, s.checked_at
                    FROM vinted_profile_snapshot_items psi
                    JOIN vinted_profile_snapshots s ON s.id = psi.snapshot_id
                    WHERE psi.member_id = ? ORDER BY s.checked_at, psi.id
                    """,
                    (member_id,),
                ).fetchall()
                for row in rows:
                    payload = _safe_payload(row["snapshot_json"])
                    item_id = str(row["item_id"] or payload.get("item_id", "") or "")
                    link = str(row["item_link"] or payload.get("link", "") or "")
                    key = item_id or link
                    base = known_items.get(key, {})
                    is_gone = str(row["status"] or "") == "gone" or not bool(row["present"])
                    known_items[key] = {
                        **base, "item_id": item_id, "link": link,
                        "name": str(row["item_name"] or payload.get("name", "") or base.get("name", "Marketplace item")),
                        "price": str(row["price_text"] or payload.get("price", "") or base.get("price", "")),
                        "image_url": str(row["image_url"] or payload.get("image_url", "") or base.get("image_url", "")),
                        "status": "gone" if is_gone and base.get("status") != "sold" else base.get("status", "active"),
                        "first_seen_at": str(payload.get("profile_first_seen_at", "") or base.get("first_seen_at", row["checked_at"])),
                        "last_seen_at": str(payload.get("profile_last_seen_at", "") or row["checked_at"]),
                        "sold_at": str(base.get("sold_at", "")),
                        "sold_after_seconds": base.get("sold_after_seconds", payload.get("profile_sold_after_seconds")),
                        "sold_after_text": str(base.get("sold_after_text", "") or payload.get("profile_sold_after_text", "")),
                        "seller_name": str(base.get("seller_name", "")),
                    }

            profile_items = sorted(
                known_items.values(), key=lambda item: str(item.get("sold_at") or item.get("last_seen_at") or item.get("first_seen_at") or ""), reverse=True
            )
            sold_items = [item for item in profile_items if item.get("status") == "sold"]
            active_items = [item for item in profile_items if item.get("status") == "active"]
            durations = [int(item["sold_after_seconds"]) for item in sold_items if isinstance(item.get("sold_after_seconds"), (int, float))]
            detected_name = next((str(item.get("seller_name") or "") for item in profile_items if item.get("seller_name")), "")
            display_name = str(registry["display_name"] or "") or detected_name or f"My profile {member_id}"
            owned_profiles.append({
                "member_id": member_id, "profile_url": profile_url, "display_name": display_name,
                "known_items_count": len(profile_items), "active_items_count": latest_active_count or len(active_items),
                "sold_items_count": len(sold_items), "gone_items_count": sum(1 for item in profile_items if item.get("status") == "gone"),
                "observed_items_count": sum(1 for item in profile_items if item.get("status") == "observed"),
                "snapshots_count": snapshots_count, "latest_snapshot_at": latest_snapshot_at,
                "average_sale_seconds": round(sum(durations) / len(durations)) if durations else 0,
                "average_sale_text": _format_duration(round(sum(durations) / len(durations))) if durations else "",
                "items": profile_items[:normalized_limit],
            })

    period_sold = sum(item["sold_count"] for item in daily_sales)
    denominator = sold_total + active_deals
    return {
        **empty,
        "available": True,
        "summary": {
            "total_items": total_items,
            "active_deals": active_deals,
            "sold_total": sold_total,
            "sold_in_period": period_sold,
            "unavailable_items": unavailable,
            "competitors": competitors,
            "priority_competitors": priority_competitors,
            "average_sale_seconds": round(sum(sold_durations) / len(sold_durations)) if sold_durations else 0,
            "average_sale_text": _format_duration(
                round(sum(sold_durations) / len(sold_durations)) if sold_durations else None
            ),
            "median_sale_seconds": round(median(sold_durations)) if sold_durations else 0,
            "median_sale_text": _format_duration(round(median(sold_durations)) if sold_durations else None),
            "average_sold_price": round(sum(sold_prices) / len(sold_prices), 2) if sold_prices else None,
            "conversion_rate": round((sold_total / denominator) * 100, 1) if denominator else 0.0,
        },
        "daily_sales": daily_sales,
        "status_distribution": [
            {"label": "Active deals", "value": active_deals, "tone": "active"},
            {"label": "Sold deals", "value": sold_total, "tone": "sold"},
            {"label": "Unavailable", "value": unavailable, "tone": "unavailable"},
        ],
        "top_searches": top_searches,
        "articles": articles,
        "competitor_profiles": competitor_profiles,
        "trend_queries": trend_queries,
        "owned_profiles": owned_profiles,
    }


def write_vinted_report_html(
    project_root: str | Path,
    *,
    days: int = 30,
    limit: int = 500,
    db_path: str | Path | None = None,
) -> Path:
    root = Path(project_root).expanduser().resolve()
    snapshot = build_vinted_report(root, days=days, limit=limit, db_path=db_path)
    if not snapshot.get("available"):
        raise ValueError("The marketplace report database is not available yet.")
    output_dir = root / "runtime" / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = datetime.now()
    output_path = output_dir / f"marketplace-report-{generated.strftime('%Y%m%d-%H%M%S')}.html"
    output_path.write_text(render_vinted_report_html(snapshot), encoding="utf-8")
    return output_path


def render_vinted_report_html(snapshot: dict[str, Any]) -> str:
    summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
    competitors = snapshot.get("competitor_profiles") if isinstance(snapshot.get("competitor_profiles"), list) else []
    trend_queries = snapshot.get("trend_queries") if isinstance(snapshot.get("trend_queries"), list) else []
    owned_profiles = snapshot.get("owned_profiles") if isinstance(snapshot.get("owned_profiles"), list) else []
    articles = snapshot.get("articles") if isinstance(snapshot.get("articles"), list) else []
    daily_sales = snapshot.get("daily_sales") if isinstance(snapshot.get("daily_sales"), list) else []
    top_searches = snapshot.get("top_searches") if isinstance(snapshot.get("top_searches"), list) else []

    def text(value: object, fallback: str = "—") -> str:
        normalized = str(value if value not in (None, "") else fallback)
        return escape(normalized, quote=True)

    def number(value: object) -> str:
        try:
            return f"{int(float(value or 0)):,}".replace(",", ".")
        except (TypeError, ValueError):
            return "0"

    metric_rows = [
        ("Analyzed articles", number(summary.get("total_items"))),
        ("Active deals", number(summary.get("active_deals"))),
        ("Sold in period", number(summary.get("sold_in_period"))),
        ("Average sale time", text(summary.get("average_sale_text"))),
        ("Conversion", f"{float(summary.get('conversion_rate') or 0):.1f}%"),
        ("Competitors", number(summary.get("competitors"))),
    ]
    metrics_html = "".join(
        f'<article class="metric"><span>{text(label)}</span><strong>{value}</strong></article>'
        for label, value in metric_rows
    )
    competitor_rows = "".join(
        f'<tr data-competitor-row data-status="{text(row.get("status"), "candidate")}" data-keyword="{text(str(row.get("top_deal_keyword", "")).lower(), "")}">'
        f'<td><a href="{text(row.get("seller_profile_url"), "#")}">{text(row.get("seller_name"))}</a><small>{text(row.get("seller_member_id"))}</small></td>'
        f'<td><span class="pill {text(row.get("status"), "candidate")}">{text(row.get("status"), "candidate")}</span></td>'
        f'<td>{text(row.get("top_deal_keyword"))}</td>'
        f'<td>{number(row.get("same_keyword_deal_count"))}</td>'
        f'<td>{number(row.get("interesting_item_count"))}</td>'
        f'<td>{number(row.get("gone_item_count"))}</td>'
        f'<td>{number(row.get("max_favorite_count"))}</td>'
        f'<td>{number(row.get("score"))}</td>'
        "</tr>"
        for row in competitors
        if isinstance(row, dict)
    ) or '<tr><td colspan="8">No competitor profiles available.</td></tr>'
    trend_rows = "".join(
        f'<tr><td>{text(row.get("query_text"))}<small>{text(row.get("query_kind"))}</small></td>'
        f'<td><span class="pill {text(row.get("status"), "learning")}">{text(row.get("status"), "learning")}</span></td>'
        f'<td>{number(row.get("mature_count"))}</td><td>{number(row.get("sold_count"))}</td>'
        f'<td>{float(row.get("sell_through_percent") or 0):.1f}%</td>'
        f'<td>{float(row.get("confidence_lower_percent") or 0):.1f}%</td>'
        f'<td>{number(row.get("scans_count"))}</td><td>{text(row.get("next_review_at"))}</td></tr>'
        for row in trend_queries if isinstance(row, dict)
    ) or '<tr><td colspan="8">No trend cohorts collected yet.</td></tr>'
    owned_cards = "".join(
        '<article class="owned-card">'
        f'<div><a href="{text(profile.get("profile_url"), "#")}"><strong>{text(profile.get("display_name"))}</strong></a><small>Member ID {text(profile.get("member_id"))}</small></div>'
        '<div class="owned-metrics">'
        f'<span><b>{number(profile.get("known_items_count"))}</b> known</span>'
        f'<span><b>{number(profile.get("active_items_count"))}</b> active</span>'
        f'<span><b>{number(profile.get("sold_items_count"))}</b> sold</span>'
        f'<span><b>{text(profile.get("average_sale_text"))}</b> avg. sale</span>'
        f'<span><b>{number(profile.get("snapshots_count"))}</b> snapshots</span>'
        '</div></article>'
        for profile in owned_profiles if isinstance(profile, dict)
    ) or '<p>No owned profiles configured.</p>'
    def article_display_status(row: dict[str, Any]) -> str:
        if str(row.get("status", "")) == "sold":
            return "sold"
        if str(row.get("availability_status", "")) == "unavailable" or str(row.get("status", "")) == "unavailable":
            return "unavailable"
        return "active"

    article_rows = "".join(
        f'<tr data-article-row data-status="{text(article_display_status(row), "active")}" data-keyword="{text(str(row.get("search_term", "")).lower(), "")}" data-sale-hours="{float(row.get("sold_after_seconds") or -3600) / 3600:.3f}">'
        f'<td><div class="article-cell">{f"<img src=\"{text(row.get('image_url'), '')}\" alt=\"\" loading=\"lazy\" onerror=\"this.classList.add('broken')\">" if row.get("image_url") else "<span class=\"thumb-placeholder\">◇</span>"}<a href="{text(row.get("link"), "#")}">{text(row.get("name"), "Marketplace item")}</a></div></td>'
        f'<td>{text(article_display_status(row), "active")}</td>'
        f'<td>{text(row.get("price"))}</td>'
        f'<td>{number(row.get("favorite_count"))}</td>'
        f'<td>{text(row.get("search_term"))}</td>'
        f'<td>{text(row.get("sold_after_text"))}</td>'
        f'<td>{text(row.get("first_seen_at"))}</td>'
        "</tr>"
        for row in articles
        if isinstance(row, dict)
    ) or '<tr><td colspan="7">No tracked articles available.</td></tr>'
    max_sales = max(1, *[int(row.get("sold_count") or 0) for row in daily_sales if isinstance(row, dict)])
    bars_html = "".join(
        f'<div class="bar-wrap" title="{text(row.get("date"))}: {number(row.get("sold_count"))} sold">'
        f'<i style="height:{max(3, round((int(row.get("sold_count") or 0) / max_sales) * 100))}%"></i>'
        f'<small>{text(str(row.get("date", ""))[-5:])}</small></div>'
        for row in daily_sales
        if isinstance(row, dict)
    )
    searches_html = "".join(
        f'<li><span>{text(row.get("term"))}</span><strong>{number(row.get("seen"))}</strong></li>'
        for row in top_searches
        if isinstance(row, dict)
    ) or "<li>No search history available.</li>"
    generated_at = text(snapshot.get("generated_at"))
    period_days = number(snapshot.get("period_days"))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Marketplace Intelligence Report</title><style>
:root{{--bg:#08111d;--panel:#101d2d;--soft:#15263a;--line:#294058;--ink:#edf7ff;--muted:#93a9bd;--cyan:#5ee7f2;--green:#4ade80;--red:#fb7185;--yellow:#facc15}}
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(145deg,#07101b,#0c1725);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}main{{max-width:1400px;margin:auto;padding:32px}}header{{display:flex;justify-content:space-between;gap:20px;align-items:end;margin-bottom:22px}}h1{{margin:4px 0;font-size:30px}}h2{{margin:0 0 14px;font-size:18px}}p,small{{color:var(--muted)}}.eyebrow{{color:var(--cyan);font-size:11px;font-weight:800;letter-spacing:.15em;text-transform:uppercase}}.metrics{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}}.metric,.card{{border:1px solid var(--line);border-radius:14px;background:rgba(16,29,45,.94)}}.metric{{padding:15px}}.metric span,.metric strong{{display:block}}.metric span{{color:var(--muted);font-size:11px}}.metric strong{{margin-top:8px;font-size:23px}}.grid{{display:grid;grid-template-columns:2fr 1fr;gap:12px;margin:12px 0}}.card{{padding:18px;overflow:auto}}.bars{{display:flex;align-items:end;gap:4px;height:170px;border-bottom:1px solid var(--line)}}.bar-wrap{{display:flex;flex:1;height:100%;min-width:5px;align-items:end;position:relative}}.bar-wrap i{{display:block;width:100%;min-height:3px;border-radius:5px 5px 0 0;background:linear-gradient(var(--cyan),#247e97)}}.bar-wrap small{{display:none}}ul{{list-style:none;padding:0;margin:0}}li{{display:flex;justify-content:space-between;padding:9px;border-bottom:1px solid var(--line)}}section.card{{margin-top:12px}}table{{width:100%;border-collapse:collapse;min-width:850px}}th,td{{padding:10px;text-align:left;border-bottom:1px solid var(--line);vertical-align:middle}}th{{position:sticky;top:0;background:var(--panel);color:var(--muted);font-size:10px;text-transform:uppercase}}td small{{display:block;font-size:10px}}a{{color:var(--cyan);text-decoration:none}}.pill{{padding:4px 8px;border-radius:999px;font-size:10px;font-weight:800;text-transform:uppercase;background:#26384a}}.confirmed{{color:var(--green);background:#163a2b}}.priority{{color:var(--red);background:#442330}}.active{{color:var(--cyan);background:#183948}}.candidate{{color:var(--yellow);background:#40391a}}.filters{{display:flex;flex-wrap:wrap;gap:9px;margin:12px 0 15px}}.filters label{{display:grid;gap:4px;color:var(--muted);font-size:10px;font-weight:700;text-transform:uppercase}}.filters input,.filters select{{min-width:150px;padding:9px 11px;border:1px solid var(--line);border-radius:9px;background:var(--soft);color:var(--ink)}}.visible-count{{margin-left:auto;align-self:end;color:var(--muted);font-size:11px}}.article-cell{{display:flex;align-items:center;gap:10px;min-width:220px}}.article-cell img,.thumb-placeholder{{flex:0 0 54px;width:54px;height:54px;border-radius:9px;object-fit:cover;background:#1c3045}}.article-cell img.broken{{display:none}}.thumb-placeholder{{display:grid;place-items:center;color:var(--muted);font-size:20px}}tr[hidden]{{display:none}}@media(max-width:900px){{main{{padding:18px}}.metrics{{grid-template-columns:repeat(2,1fr)}}.grid{{grid-template-columns:1fr}}header{{align-items:start;flex-direction:column}}.visible-count{{width:100%;margin-left:0}}}}
.owned-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px}}.owned-card{{padding:14px;border:1px solid var(--line);border-radius:12px;background:var(--soft)}}.owned-card small{{display:block}}.owned-metrics{{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin-top:12px}}.owned-metrics span{{padding:8px;border:1px solid var(--line);border-radius:8px;color:var(--muted);font-size:11px}}.owned-metrics b{{display:block;color:var(--ink)}}
</style></head><body><main>
<header><div><div class="eyebrow">Marketplace intelligence</div><h1>Performance report</h1><p>Saved data snapshot for the last {period_days} days.</p></div><small>Generated {generated_at}</small></header>
<section class="metrics">{metrics_html}</section>
<div class="grid"><article class="card"><h2>Confirmed sales trend</h2><div class="bars">{bars_html}</div></article><article class="card"><h2>Top searches</h2><ul>{searches_html}</ul></article></div>
<section class="card"><h2>My profiles</h2><p>Owned inventory is separated from competitor intelligence.</p><div class="owned-grid">{owned_cards}</div></section>
<section class="card"><h2>Competitors</h2><p>A seller is confirmed after at least 3 distinct deals for the same search keyword.</p><div class="filters"><label>Status<select id="competitor-status"><option value="all">All statuses</option><option>priority</option><option>confirmed</option><option>active</option><option>candidate</option></select></label><label>Keyword<input id="competitor-keyword" type="search" placeholder="charm, pandora…"></label><span class="visible-count" id="competitor-count"></span></div><table><thead><tr><th>Seller</th><th>Status</th><th>Top keyword</th><th>Keyword deals</th><th>Items</th><th>Gone/sold</th><th>Max likes</th><th>Score</th></tr></thead><tbody>{competitor_rows}</tbody></table></section>
<section class="card"><h2>Category trend cohorts</h2><p>The umbrella category is a market benchmark; leaf categories are compared with each other. Only mature observations enter sell-through. Technical failures and unavailable pages do not count as unsold stock.</p><table><thead><tr><th>Segment / kind</th><th>Status</th><th>Mature sample</th><th>Sold ≤ window</th><th>Sell-through</th><th>95% lower bound</th><th>Scans</th><th>Next probe</th></tr></thead><tbody>{trend_rows}</tbody></table></section>
<section class="card"><h2>Tracked articles</h2><div class="filters"><label>Status<select id="article-status"><option value="all">All statuses</option><option value="sold">Sold</option><option value="active">Active</option><option value="unavailable">Unavailable</option></select></label><label>Keyword<input id="article-keyword" type="search" placeholder="Search keyword…"></label><label>Sale time<select id="article-sale-time"><option value="all">Any duration</option><option value="under-1">Under 1 hour</option><option value="1-6">1–6 hours</option><option value="6-24">6–24 hours</option><option value="over-24">Over 24 hours</option></select></label><span class="visible-count" id="article-count"></span></div><table><thead><tr><th>Photo / article</th><th>Status</th><th>Price</th><th>Likes</th><th>Search</th><th>Sold after</th><th>First seen</th></tr></thead><tbody>{article_rows}</tbody></table></section>
</main><script>
const rows=(name)=>[...document.querySelectorAll(`[data-${{name}}-row]`)];
function filterCompetitors(){{const status=document.querySelector('#competitor-status').value;const keyword=document.querySelector('#competitor-keyword').value.trim().toLowerCase();let visible=0;for(const row of rows('competitor')){{const show=(status==='all'||row.dataset.status===status)&&(!keyword||row.dataset.keyword.includes(keyword));row.hidden=!show;if(show)visible++}}document.querySelector('#competitor-count').textContent=`${{visible}} visible`;}}
function filterArticles(){{const status=document.querySelector('#article-status').value;const keyword=document.querySelector('#article-keyword').value.trim().toLowerCase();const timing=document.querySelector('#article-sale-time').value;let visible=0;for(const row of rows('article')){{const hours=Number(row.dataset.saleHours);let timeOk=timing==='all'||(timing==='under-1'&&hours>=0&&hours<1)||(timing==='1-6'&&hours>=1&&hours<6)||(timing==='6-24'&&hours>=6&&hours<24)||(timing==='over-24'&&hours>=24);const show=(status==='all'||row.dataset.status===status)&&(!keyword||row.dataset.keyword.includes(keyword))&&timeOk;row.hidden=!show;if(show)visible++}}document.querySelector('#article-count').textContent=`${{visible}} visible`;}}
for(const id of ['competitor-status','competitor-keyword'])document.querySelector(`#${{id}}`).addEventListener('input',filterCompetitors);
for(const id of ['article-status','article-keyword','article-sale-time'])document.querySelector(`#${{id}}`).addEventListener('input',filterArticles);
filterCompetitors();filterArticles();
</script></body></html>"""
