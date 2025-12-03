"""Historical data utilities for Tibber price analysis."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components import recorder
from homeassistant.components.recorder import history
from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)


class TibberHistoryHelper:
    """Helper class for querying historical Tibber price data."""

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        """Initialize the history helper."""
        self.hass = hass
        self.entity_id = entity_id

    async def get_same_hour_average(self, days: int = 30) -> dict[str, Any]:
        """Calculate average price for the current hour over the last N days.

        Note: Historical prices are stored with adjustments already applied
        by the coordinator, so this will return adjusted prices if
        subsidy/grid fees were enabled when the prices were stored.

        Args:
            days: Number of days to look back (default: 30)

        Returns:
            dict with keys:
                - average: Average price for this hour
                - sample_count: Number of valid samples found
                - min: Minimum price in samples
                - max: Maximum price in samples
        """
        now = dt_util.now()
        current_hour = now.hour

        # Calculate start time (N days ago)
        end_time = now
        start_time = now - timedelta(days=days)

        _LOGGER.debug(
            "Querying historical data for %s from %s to %s",
            self.entity_id,
            start_time,
            end_time,
        )

        try:
            # Query historical states
            states = await self.hass.async_add_executor_job(
                self._get_history_states,
                start_time,
                end_time,
            )

            if not states:
                _LOGGER.warning("No historical data found for %s", self.entity_id)
                return {
                    "average": None,
                    "sample_count": 0,
                    "min": None,
                    "max": None,
                }

            # Filter states for the same hour and collect prices
            same_hour_prices = []

            for state in states:
                # Skip if state is unavailable or unknown
                if state.state in ("unavailable", "unknown", None):
                    continue

                # Check if state timestamp matches current hour
                state_time = state.last_updated.replace(tzinfo=dt_util.UTC)
                if state_time.hour == current_hour:
                    try:
                        price = float(state.state)
                        same_hour_prices.append(price)
                    except (ValueError, TypeError):
                        continue

            if not same_hour_prices:
                _LOGGER.warning(
                    "No valid price data found for hour %d in the last %d days",
                    current_hour,
                    days,
                )
                return {
                    "average": None,
                    "sample_count": 0,
                    "min": None,
                    "max": None,
                }

            # Calculate statistics
            average = sum(same_hour_prices) / len(same_hour_prices)
            min_price = min(same_hour_prices)
            max_price = max(same_hour_prices)

            _LOGGER.debug(
                "Calculated same-hour average for hour %d: %.4f (from %d samples)",
                current_hour,
                average,
                len(same_hour_prices),
            )

            return {
                "average": average,
                "sample_count": len(same_hour_prices),
                "min": min_price,
                "max": max_price,
            }

        except Exception as err:
            _LOGGER.error("Error querying historical data: %s", err)
            return {
                "average": None,
                "sample_count": 0,
                "min": None,
                "max": None,
            }

    def _get_history_states(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> list[Any]:
        """Get historical states from recorder (runs in executor).

        Args:
            start_time: Start of the time range
            end_time: End of the time range

        Returns:
            List of state objects
        """
        # Use recorder history API to get states
        history_list = history.get_significant_states(
            self.hass,
            start_time,
            end_time,
            entity_ids=[self.entity_id],
            significant_changes_only=False,
        )

        # Extract states for our entity
        states = history_list.get(self.entity_id, [])
        return states
