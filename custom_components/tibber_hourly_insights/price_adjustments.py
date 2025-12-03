"""Price adjustment utilities for Norwegian electricity pricing.

This module handles:
1. Strømstøtte (electricity subsidy): Government covers 90% of amount above threshold
2. Nettleie (grid fees): Time-based tariffs (day rate 06:00-22:00, night rate 22:00-06:00)

Calculation order:
1. Apply strømstøtte to spot price first
2. Then add time-based grid fee
"""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

import pytz

_LOGGER = logging.getLogger(__name__)

# Oslo timezone for time-based calculations
OSLO_TZ = pytz.timezone("Europe/Oslo")


def calculate_adjusted_price(
    spot_price: float,
    timestamp: datetime | str,
    enable_subsidy: bool = False,
    subsidy_threshold: float = 0.9375,
    subsidy_percentage: float = 90.0,
    enable_grid_fee: bool = False,
    grid_fee_day: float = 0.444,
    grid_fee_night: float = 0.305,
    day_start_hour: int = 6,
    day_end_hour: int = 22,
) -> dict[str, Any]:
    """Calculate adjusted price with subsidy and grid fees.

    Args:
        spot_price: Raw spot price in NOK/kWh
        timestamp: Timestamp for the price (datetime or ISO string)
        enable_subsidy: Whether to apply strømstøtte subsidy
        subsidy_threshold: Threshold in NOK/kWh (default: 0.9375)
        subsidy_percentage: Percentage government covers above threshold (default: 90.0)
        enable_grid_fee: Whether to add grid fees
        grid_fee_day: Day rate grid fee in NOK/kWh (default: 0.444)
        grid_fee_night: Night rate grid fee in NOK/kWh (default: 0.305)
        day_start_hour: Hour when day rate starts (default: 6)
        day_end_hour: Hour when day rate ends (default: 22)

    Returns:
        dict with keys:
            - raw_spot_price: Original spot price
            - subsidy_amount: Amount of subsidy applied (0 if disabled)
            - grid_fee: Grid fee added (0 if disabled)
            - adjusted_price: Final price after all adjustments
            - timestamp: Timestamp used for calculations

    Example:
        spot_price = 1.50 NOK at 10:00
        1. Subsidy: (1.50 - 0.9375) × 0.90 = 0.506 NOK
        2. After subsidy: 1.50 - 0.506 = 0.994 NOK
        3. Add day grid fee: 0.994 + 0.444 = 1.438 NOK/kWh
    """
    # Parse timestamp if string
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

    # Ensure timestamp is timezone-aware (convert to Oslo time)
    if timestamp.tzinfo is None:
        timestamp = pytz.UTC.localize(timestamp)
    oslo_time = timestamp.astimezone(OSLO_TZ)

    # Step 1: Apply strømstøtte (subsidy) if enabled
    subsidy_amount = 0.0
    price_after_subsidy = spot_price

    if enable_subsidy and spot_price > subsidy_threshold:
        excess = spot_price - subsidy_threshold
        subsidy_amount = excess * (subsidy_percentage / 100.0)
        price_after_subsidy = spot_price - subsidy_amount

    # Step 2: Add time-based grid fee if enabled
    grid_fee = 0.0
    final_price = price_after_subsidy

    if enable_grid_fee:
        hour = oslo_time.hour
        if day_start_hour <= hour < day_end_hour:
            grid_fee = grid_fee_day
        else:
            grid_fee = grid_fee_night
        final_price = price_after_subsidy + grid_fee

    _LOGGER.debug(
        "Price adjustment for %s: spot=%.4f, subsidy=%.4f, grid_fee=%.4f, final=%.4f",
        oslo_time.isoformat(),
        spot_price,
        subsidy_amount,
        grid_fee,
        final_price,
    )

    return {
        "raw_spot_price": spot_price,
        "subsidy_amount": subsidy_amount,
        "grid_fee": grid_fee,
        "adjusted_price": final_price,
        "timestamp": oslo_time.isoformat(),
    }


def adjust_price_list(
    price_entries: list[dict[str, Any]],
    enable_subsidy: bool = False,
    subsidy_threshold: float = 0.9375,
    subsidy_percentage: float = 90.0,
    enable_grid_fee: bool = False,
    grid_fee_day: float = 0.444,
    grid_fee_night: float = 0.305,
    day_start_hour: int = 6,
    day_end_hour: int = 22,
) -> list[dict[str, Any]]:
    """Apply price adjustments to a list of price entries.

    Args:
        price_entries: List of price dicts from Tibber API (with 'total' and 'startsAt' keys)
        enable_subsidy: Whether to apply strømstøtte subsidy
        subsidy_threshold: Threshold in NOK/kWh
        subsidy_percentage: Percentage government covers above threshold
        enable_grid_fee: Whether to add grid fees
        grid_fee_day: Day rate grid fee in NOK/kWh
        grid_fee_night: Night rate grid fee in NOK/kWh
        day_start_hour: Hour when day rate starts
        day_end_hour: Hour when day rate ends

    Returns:
        List of price dicts with adjusted 'total' values and additional adjustment details
    """
    adjusted_entries = []

    for entry in price_entries:
        if not entry or "total" not in entry or "startsAt" not in entry:
            _LOGGER.warning("Invalid price entry format: %s", entry)
            continue

        spot_price = entry["total"]
        timestamp = entry["startsAt"]

        # Calculate adjustments
        adjustment = calculate_adjusted_price(
            spot_price=spot_price,
            timestamp=timestamp,
            enable_subsidy=enable_subsidy,
            subsidy_threshold=subsidy_threshold,
            subsidy_percentage=subsidy_percentage,
            enable_grid_fee=enable_grid_fee,
            grid_fee_day=grid_fee_day,
            grid_fee_night=grid_fee_night,
            day_start_hour=day_start_hour,
            day_end_hour=day_end_hour,
        )

        # Create adjusted entry (keep original fields, update total)
        adjusted_entry = entry.copy()
        adjusted_entry["total"] = adjustment["adjusted_price"]
        adjusted_entry["raw_spot_price"] = adjustment["raw_spot_price"]
        adjusted_entry["subsidy_amount"] = adjustment["subsidy_amount"]
        adjusted_entry["grid_fee"] = adjustment["grid_fee"]

        adjusted_entries.append(adjusted_entry)

    return adjusted_entries
