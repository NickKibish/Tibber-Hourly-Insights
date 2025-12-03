#!/usr/bin/env python3
"""Standalone checker for Tibber same-hour 30-day average.

This mirrors the logic in TibberHistoryHelper.get_same_hour_average():
- pulls states for a single entity from the Home Assistant recorder DB
- keeps samples where the timestamp hour matches the current hour
- ignores unavailable/unknown states
- reports average, min, max, and sample count

By default it uses the system local timezone for the “current hour” and
compares that to timestamps converted from UTC (how HA stores them). Use
--timezone to override.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Iterable, Tuple

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


Row = Tuple[float, datetime]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Compute same-hour average for a HA sensor over the last N days.",
    )
    parser.add_argument(
        "--db",
        default=str(Path("home-assistant_v2.db")),
        help="Path to Home Assistant recorder DB (SQLite). Default: ./home-assistant_v2.db",
    )
    parser.add_argument(
        "--entity",
        default="sensor.tibber_current_price",
        help="Entity ID to query. Default: sensor.tibber_current_price",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Days to look back. Default: 30",
    )
    parser.add_argument(
        "--timezone",
        default=None,
        help="Timezone name (e.g., Europe/Oslo). Defaults to system local.",
    )
    return parser.parse_args()


def load_rows(
    db_path: Path,
    entity_id: str,
    start: datetime,
    end: datetime,
) -> list[Row]:
    """Load numeric states and timestamps for an entity within a time range."""
    query = """
        SELECT s.state, s.last_updated
        FROM states s
        JOIN states_meta m ON s.metadata_id = m.metadata_id
        WHERE m.entity_id = ?
          AND s.last_updated >= ?
          AND s.last_updated <= ?
          AND s.state NOT IN ('unknown', 'unavailable', 'None')
    """

    rows: list[Row] = []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(query, (entity_id, start.isoformat(), end.isoformat())):
            raw_ts = row["last_updated"]
            try:
                ts = datetime.fromisoformat(raw_ts)
            except ValueError:
                # HA sometimes stores with space separator; try a fallback
                try:
                    ts = datetime.fromisoformat(raw_ts.replace(" ", "T"))
                except Exception:
                    continue

            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            try:
                price = float(row["state"])
            except (ValueError, TypeError):
                continue

            rows.append((price, ts))

    return rows


def same_hour_stats(
    rows: Iterable[Row],
    current_hour: int,
    tzinfo: tzinfo,
) -> dict[str, float | int] | None:
    """Compute statistics for samples matching the current hour."""
    same_hour_prices = []

    for price, ts in rows:
        ts_local = ts.astimezone(tzinfo)
        if ts_local.hour == current_hour:
            same_hour_prices.append(price)

    if not same_hour_prices:
        return None

    average = sum(same_hour_prices) / len(same_hour_prices)
    return {
        "average": average,
        "sample_count": len(same_hour_prices),
        "min": min(same_hour_prices),
        "max": max(same_hour_prices),
    }


def main() -> None:
    """Run the script."""
    args = parse_args()

    tz = None
    if args.timezone and ZoneInfo:
        try:
            tz = ZoneInfo(args.timezone)
        except Exception as err:  # pragma: no cover - CLI validation
            raise SystemExit(f"Invalid timezone '{args.timezone}': {err}")

    if tz is None:
        tz = datetime.now().astimezone().tzinfo or timezone.utc

    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=args.days)

    db_path = Path(args.db).expanduser()
    if not db_path.exists():
        raise SystemExit(f"DB file not found: {db_path}")

    rows = load_rows(db_path, args.entity, start, end)
    stats = same_hour_stats(rows, current_hour=datetime.now(tz).hour, tzinfo=tz)

    if not stats:
        print("No valid samples found for the current hour in the given window.")
        return

    print(f"Entity: {args.entity}")
    print(f"Window: {start.isoformat()} to {end.isoformat()}")
    print(f"Hour matched (local): {datetime.now(tz).hour:02d}")
    print(f"Samples: {stats['sample_count']}")
    print(f"Average: {stats['average']:.4f}")
    print(f"Min: {stats['min']:.4f}")
    print(f"Max: {stats['max']:.4f}")


if __name__ == "__main__":
    main()
