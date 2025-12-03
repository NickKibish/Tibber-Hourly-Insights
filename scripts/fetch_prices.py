#!/usr/bin/env python3
"""Fetch and display Tibber prices without Home Assistant or a database."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, List

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

import aiohttp

TIBBER_API_URL = "https://api.tibber.com/v1-beta/gql"


@dataclass
class PricePoint:
    total: float
    currency: str
    level: str | None
    starts_at: str


@dataclass
class ConsumptionPoint:
    starts_at: datetime
    ends_at: datetime
    unit_price: float
    currency: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Tibber prices (current, today, tomorrow).")
    parser.add_argument(
        "--token",
        required=True,
        help="Tibber API token",
    )
    parser.add_argument(
        "--show-tomorrow",
        action="store_true",
        help="Print tomorrow prices if available",
    )
    parser.add_argument(
        "--history-days",
        type=int,
        default=0,
        help="If >0, also fetch hourly history for this many days (uses consumption API).",
    )
    parser.add_argument(
        "--hour",
        type=int,
        default=None,
        help="Hour of day to filter (0-23). Default: current local hour.",
    )
    parser.add_argument(
        "--timezone",
        default=None,
        help="Timezone name for interpreting timestamps (e.g., Europe/Oslo). Defaults to system local.",
    )
    return parser.parse_args()


async def fetch_price_data(session: aiohttp.ClientSession, token: str) -> dict[str, Any]:
    query = """
    {
        viewer {
            homes {
                currentSubscription {
                    priceInfo {
                        current {
                            total
                            currency
                            level
                            startsAt
                        }
                        today {
                            total
                            currency
                            level
                            startsAt
                        }
                        tomorrow {
                            total
                            currency
                            level
                            startsAt
                        }
                    }
                }
            }
        }
    }
    """

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Tibber-Hourly-Insights/standalone",
    }

    async with session.post(
        TIBBER_API_URL,
        json={"query": query},
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        resp.raise_for_status()
        payload = await resp.json()

    if "errors" in payload:
        messages = ", ".join(err.get("message", "") for err in payload["errors"])
        raise RuntimeError(f"Tibber API error: {messages}")

    return payload.get("data", {})


async def fetch_hourly_consumption(
    session: aiohttp.ClientSession,
    token: str,
    hours: int,
) -> dict[str, Any]:
    """Fetch hourly consumption nodes (includes unit prices) for a given hour span."""
    query = """
    query($hours: Int!) {
        viewer {
            homes {
                consumption(resolution: HOURLY, last: $hours) {
                    nodes {
                        from
                        to
                        unitPrice
                        unitPriceVAT
                        currency
                    }
                }
            }
        }
    }
    """

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Tibber-Hourly-Insights/standalone",
    }

    async with session.post(
        TIBBER_API_URL,
        json={"query": query, "variables": {"hours": hours}},
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        resp.raise_for_status()
        payload = await resp.json()

    if "errors" in payload:
        messages = ", ".join(err.get("message", "") for err in payload["errors"])
        raise RuntimeError(f"Tibber API error: {messages}")

    return payload.get("data", {})


def parse_prices(data: dict[str, Any]) -> tuple[PricePoint, list[PricePoint], list[PricePoint]]:
    homes = data.get("viewer", {}).get("homes", [])
    if not homes:
        raise RuntimeError("No homes returned from Tibber API")

    price_info = homes[0].get("currentSubscription", {}).get("priceInfo", {})
    if not price_info:
        raise RuntimeError("No priceInfo in API response")

    def to_points(items: list[dict[str, Any]]) -> list[PricePoint]:
        points: list[PricePoint] = []
        for entry in items:
            total = entry.get("total")
            currency = entry.get("currency")
            starts_at = entry.get("startsAt")
            if total is None or currency is None or starts_at is None:
                continue
            points.append(
                PricePoint(
                    total=float(total),
                    currency=currency,
                    level=entry.get("level"),
                    starts_at=starts_at,
                )
            )
        return points

    current_raw = price_info.get("current")
    if not current_raw:
        raise RuntimeError("No current price returned")

    current = PricePoint(
        total=float(current_raw.get("total")),
        currency=current_raw.get("currency", "NOK"),
        level=current_raw.get("level"),
        starts_at=current_raw.get("startsAt"),
    )

    today = to_points(price_info.get("today", []))
    tomorrow = to_points(price_info.get("tomorrow", []))
    return current, today, tomorrow


def parse_consumption(
    data: dict[str, Any],
    fallback_currency: str = "NOK",
) -> list[ConsumptionPoint]:
    homes = data.get("viewer", {}).get("homes", [])
    if not homes:
        raise RuntimeError("No homes returned from Tibber API")

    nodes = homes[0].get("consumption", {}).get("nodes", [])
    points: list[ConsumptionPoint] = []

    for node in nodes:
        try:
            start = datetime.fromisoformat(node["from"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(node["to"].replace("Z", "+00:00"))
        except Exception:
            continue

        price = node.get("unitPrice") or node.get("unitPriceVAT")
        if price is None:
            continue

        currency = node.get("currency") or fallback_currency
        try:
            points.append(
                ConsumptionPoint(
                    starts_at=start,
                    ends_at=end,
                    unit_price=float(price),
                    currency=currency,
                )
            )
        except (ValueError, TypeError):
            continue

    return points


def filter_same_hour(points: Iterable[ConsumptionPoint], hour: int, tz) -> list[ConsumptionPoint]:
    """Filter consumption points to a specific local hour."""
    filtered: list[ConsumptionPoint] = []
    for p in points:
        local_ts = p.starts_at.astimezone(tz)
        if local_ts.hour == hour:
            filtered.append(p)
    return filtered


def print_prices(current: PricePoint, today: list[PricePoint], tomorrow: list[PricePoint], show_tomorrow: bool) -> None:
    print("Current price")
    print(f"  Total:    {current.total:.4f} {current.currency}/kWh")
    print(f"  Level:    {current.level}")
    print(f"  StartsAt: {current.starts_at}")
    print()

    print("Today")
    for p in today:
        ts = datetime.fromisoformat(p.starts_at.replace("Z", "+00:00"))
        print(f"  {ts.isoformat()} -> {p.total:.4f} {p.currency}/kWh ({p.level})")

    if show_tomorrow and tomorrow:
        print()
        print("Tomorrow")
        for p in tomorrow:
            ts = datetime.fromisoformat(p.starts_at.replace("Z", "+00:00"))
            print(f"  {ts.isoformat()} -> {p.total:.4f} {p.currency}/kWh ({p.level})")


def print_history(points: List[ConsumptionPoint], hour: int, tz) -> None:
    if not points:
        print(f"No samples found for hour {hour:02d}.")
        return

    points = sorted(points, key=lambda p: p.starts_at)
    prices = [p.unit_price for p in points]
    currency = points[0].currency

    print()
    print(f"History for hour {hour:02d} (local time)")
    for p in points:
        ts = p.starts_at.astimezone(tz)
        print(f"  {ts.isoformat()} -> {p.unit_price:.4f} {currency}/kWh")

    avg = sum(prices) / len(prices)
    print(f"\nSamples: {len(points)}")
    print(f"Average: {avg:.4f} {currency}/kWh")
    print(f"Min:     {min(prices):.4f} {currency}/kWh")
    print(f"Max:     {max(prices):.4f} {currency}/kWh")


async def main() -> None:
    args = parse_args()
    tz = None
    if args.timezone and ZoneInfo:
        try:
            tz = ZoneInfo(args.timezone)
        except Exception as err:  # pragma: no cover - CLI validation
            raise SystemExit(f"Invalid timezone '{args.timezone}': {err}")
    if tz is None:
        tz = datetime.now().astimezone().tzinfo or timezone.utc

    async with aiohttp.ClientSession() as session:
        data = await fetch_price_data(session, args.token)
        history_data = None
        if args.history_days > 0:
            hours = max(1, args.history_days * 24)
            history_data = await fetch_hourly_consumption(session, args.token, hours)

    current, today, tomorrow = parse_prices(data)
    print_prices(current, today, tomorrow, args.show_tomorrow)

    if history_data:
        target_hour = args.hour if args.hour is not None else datetime.now(tz).hour
        consumption_points = parse_consumption(history_data, fallback_currency=current.currency)
        filtered = filter_same_hour(consumption_points, target_hour, tz)
        print_history(filtered, target_hour, tz)


if __name__ == "__main__":
    asyncio.run(main())
