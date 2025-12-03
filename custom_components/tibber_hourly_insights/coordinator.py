"""Data update coordinator for Tibber Hourly Insights."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DAY_END_HOUR,
    CONF_DAY_START_HOUR,
    CONF_ENABLE_GRID_FEE,
    CONF_ENABLE_SUBSIDY,
    CONF_GRID_FEE_DAY,
    CONF_GRID_FEE_NIGHT,
    CONF_SUBSIDY_PERCENTAGE,
    CONF_SUBSIDY_THRESHOLD,
    DEFAULT_DAY_END_HOUR,
    DEFAULT_DAY_START_HOUR,
    DEFAULT_ENABLE_GRID_FEE,
    DEFAULT_ENABLE_SUBSIDY,
    DEFAULT_GRID_FEE_DAY,
    DEFAULT_GRID_FEE_NIGHT,
    DEFAULT_SUBSIDY_PERCENTAGE,
    DEFAULT_SUBSIDY_THRESHOLD,
    DOMAIN,
)
from .price_adjustments import adjust_price_list, calculate_adjusted_price
from .tibber_api import TibberApiClient, TibberApiError

_LOGGER = logging.getLogger(__name__)


class TibberDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage fetching Tibber price data."""

    def __init__(
        self, hass: HomeAssistant, client: TibberApiClient, entry: ConfigEntry
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self.entry = entry
        self.yesterday_prices: list[dict[str, Any]] = []

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            # No update_interval - updates triggered by Tibber price state changes
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Tibber API.

        Returns:
            dict with complete price data:
                - current: Current price info (with adjustments applied)
                - today: List of today's hourly prices (with adjustments applied)
                - tomorrow: List of tomorrow's hourly prices (with adjustments applied)
                - yesterday: List of yesterday's hourly prices (with adjustments applied)
        """
        try:
            data = await self.client.get_price_data()
            _LOGGER.debug("Successfully fetched Tibber price data")

            # Store yesterday's prices when tomorrow becomes available
            # Tomorrow typically arrives around 13:00
            if data.get("tomorrow") and not self.yesterday_prices:
                # If we have tomorrow but no yesterday stored, store current today as yesterday
                self.yesterday_prices = data.get("today", [])
                _LOGGER.info("Stored today's prices as yesterday for future comparison")
            elif data.get("tomorrow") and self.yesterday_prices:
                # If tomorrow exists and we already have yesterday, update yesterday to previous today
                # This happens during the daily transition
                current_today_first = data.get("today", [{}])[0].get("startsAt", "")
                yesterday_first = self.yesterday_prices[0].get("startsAt", "") if self.yesterday_prices else ""

                # Check if today has changed (new day)
                if current_today_first and yesterday_first and current_today_first > yesterday_first:
                    self.yesterday_prices = data.get("today", [])
                    _LOGGER.info("Updated yesterday prices to previous today")

            # Add yesterday to the response
            data["yesterday"] = self.yesterday_prices

            # Apply price adjustments to all price data
            data = self._apply_price_adjustments(data)

            return data
        except TibberApiError as err:
            _LOGGER.error("Error fetching Tibber data: %s", err)
            raise UpdateFailed(f"Error communicating with Tibber API: {err}") from err

    def _apply_price_adjustments(self, data: dict[str, Any]) -> dict[str, Any]:
        """Apply price adjustments (subsidy and grid fees) to all price data.

        Args:
            data: Raw price data from Tibber API

        Returns:
            Price data with adjustments applied
        """
        # Get adjustment settings from config entry options
        options = self.entry.options
        enable_subsidy = options.get(CONF_ENABLE_SUBSIDY, DEFAULT_ENABLE_SUBSIDY)
        subsidy_threshold = options.get(CONF_SUBSIDY_THRESHOLD, DEFAULT_SUBSIDY_THRESHOLD)
        subsidy_percentage = options.get(CONF_SUBSIDY_PERCENTAGE, DEFAULT_SUBSIDY_PERCENTAGE)
        enable_grid_fee = options.get(CONF_ENABLE_GRID_FEE, DEFAULT_ENABLE_GRID_FEE)
        grid_fee_day = options.get(CONF_GRID_FEE_DAY, DEFAULT_GRID_FEE_DAY)
        grid_fee_night = options.get(CONF_GRID_FEE_NIGHT, DEFAULT_GRID_FEE_NIGHT)
        day_start_hour = options.get(CONF_DAY_START_HOUR, DEFAULT_DAY_START_HOUR)
        day_end_hour = options.get(CONF_DAY_END_HOUR, DEFAULT_DAY_END_HOUR)

        # Skip adjustments if both are disabled
        if not enable_subsidy and not enable_grid_fee:
            _LOGGER.debug("Price adjustments disabled, returning raw prices")
            return data

        _LOGGER.debug(
            "Applying price adjustments: subsidy=%s, grid_fee=%s",
            enable_subsidy,
            enable_grid_fee,
        )

        # Apply adjustments to current price
        if data.get("current"):
            current = data["current"]
            adjustment = calculate_adjusted_price(
                spot_price=current.get("total", 0.0),
                timestamp=current.get("startsAt", ""),
                enable_subsidy=enable_subsidy,
                subsidy_threshold=subsidy_threshold,
                subsidy_percentage=subsidy_percentage,
                enable_grid_fee=enable_grid_fee,
                grid_fee_day=grid_fee_day,
                grid_fee_night=grid_fee_night,
                day_start_hour=day_start_hour,
                day_end_hour=day_end_hour,
            )
            # Store raw price and update with adjusted price
            current["raw_spot_price"] = adjustment["raw_spot_price"]
            current["subsidy_amount"] = adjustment["subsidy_amount"]
            current["grid_fee"] = adjustment["grid_fee"]
            current["total"] = adjustment["adjusted_price"]

        # Apply adjustments to today, tomorrow, yesterday arrays
        for key in ["today", "tomorrow", "yesterday"]:
            if data.get(key):
                data[key] = adjust_price_list(
                    price_entries=data[key],
                    enable_subsidy=enable_subsidy,
                    subsidy_threshold=subsidy_threshold,
                    subsidy_percentage=subsidy_percentage,
                    enable_grid_fee=enable_grid_fee,
                    grid_fee_day=grid_fee_day,
                    grid_fee_night=grid_fee_night,
                    day_start_hour=day_start_hour,
                    day_end_hour=day_end_hour,
                )

        return data
