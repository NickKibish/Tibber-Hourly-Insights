"""Historical data utilities for Tibber price analysis."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any, TYPE_CHECKING

from homeassistant.components import recorder
from homeassistant.components.recorder import history
from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util

if TYPE_CHECKING:
    from .tibber_api import TibberApiClient

_LOGGER = logging.getLogger(__name__)


class TibberHistoryHelper:
    """Helper class for querying historical Tibber price data."""

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        """Initialize the history helper."""
        self.hass = hass
        self.entity_id = entity_id

    async def fetch_tibber_fallback(
        self,
        tibber_client: "TibberApiClient",
        target_hour: int,
        missing_days: int,
        max_hours: int = 720,
    ) -> list[float]:
        """Fetch historical prices from Tibber API for missing days.

        Args:
            tibber_client: Tibber API client instance
            target_hour: Hour of day to filter (0-23)
            missing_days: Estimated days of missing data
            max_hours: Maximum hours to fetch from API (default 720 = 30 days)

        Returns:
            List of prices for the target hour from Tibber consumption API
        """
        try:
            # Calculate hours to fetch, capped at max_hours
            hours_to_fetch = min(missing_days * 24, max_hours)

            _LOGGER.debug(
                "Fetching Tibber API fallback data: target_hour=%d, hours=%d",
                target_hour,
                hours_to_fetch,
            )

            # Fetch consumption data from Tibber API
            nodes = await tibber_client.get_historical_consumption(
                resolution="HOURLY", last=hours_to_fetch
            )

            if not nodes:
                _LOGGER.warning("Tibber API returned no consumption nodes")
                return []

            # Filter nodes to target hour and extract prices
            prices = []
            for node in nodes:
                try:
                    # Parse timestamp
                    from_time_str = node.get("from")
                    if not from_time_str:
                        continue

                    # Convert ISO timestamp to datetime
                    from_time = datetime.fromisoformat(
                        from_time_str.replace("Z", "+00:00")
                    )

                    # Convert to local timezone
                    local_time = dt_util.as_local(from_time)

                    # Check if hour matches
                    if local_time.hour == target_hour:
                        # Get price (unitPrice + unitPriceVAT = total price)
                        unit_price = node.get("unitPrice")
                        unit_price_vat = node.get("unitPriceVAT", 0)

                        if unit_price is not None:
                            total_price = unit_price + unit_price_vat
                            prices.append(total_price)

                except (ValueError, TypeError, AttributeError) as err:
                    _LOGGER.debug("Skipping invalid Tibber node: %s", err)
                    continue

            _LOGGER.info(
                "Fetched %d prices from Tibber API for hour %d (from %d nodes)",
                len(prices),
                target_hour,
                len(nodes),
            )

            return prices

        except Exception as err:
            _LOGGER.error("Error fetching Tibber fallback data: %s", err, exc_info=True)
            return []

    async def get_same_hour_average(
        self,
        days: int = 30,
        tibber_client: "TibberApiClient | None" = None,
        enable_fallback: bool = True,
        min_samples: int = 20,
        max_fetch_hours: int = 720,
    ) -> dict[str, Any]:
        """Calculate average price for the current hour over the last N days.

        Enhanced with Tibber API fallback to fetch missing historical data when
        recorder doesn't have sufficient samples.

        Note: Historical prices are stored with adjustments already applied
        by the coordinator, so this will return adjusted prices if
        subsidy/grid fees were enabled when the prices were stored.

        Args:
            days: Number of days to look back (default: 30)
            tibber_client: Optional Tibber API client for fallback data
            enable_fallback: Whether to use Tibber API fallback (default: True)
            min_samples: Minimum recorder samples before fallback (default: 20)
            max_fetch_hours: Maximum hours to fetch from API (default: 720)

        Returns:
            dict with keys:
                - average: Average price for this hour
                - sample_count: Number of valid samples found
                - min: Minimum price in samples
                - max: Maximum price in samples
                - source: Data source - "recorder", "tibber", or "mixed"
                - recorder_count: (if mixed) Number of recorder samples
                - tibber_count: (if mixed) Number of Tibber API samples
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
            # Step 1: Get recorder data
            states = await self.hass.async_add_executor_job(
                self._get_history_states,
                start_time,
                end_time,
            )

            # Filter states for the same hour and collect prices
            recorder_prices = []

            if states:
                for state in states:
                    # Skip if state is unavailable or unknown
                    if state.state in ("unavailable", "unknown", None):
                        continue

                    # Check if state timestamp matches current hour
                    state_time = state.last_updated.replace(tzinfo=dt_util.UTC)
                    if state_time.hour == current_hour:
                        try:
                            price = float(state.state)
                            recorder_prices.append(price)
                        except (ValueError, TypeError):
                            continue

            _LOGGER.debug(
                "Found %d recorder samples for hour %d",
                len(recorder_prices),
                current_hour,
            )

            # Step 2: Check if fallback is needed
            if len(recorder_prices) >= min_samples or not enable_fallback:
                # Sufficient recorder data or fallback disabled
                if not recorder_prices:
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
                        "source": "recorder",
                    }

                # Calculate statistics from recorder only
                average = sum(recorder_prices) / len(recorder_prices)
                min_price = min(recorder_prices)
                max_price = max(recorder_prices)

                _LOGGER.debug(
                    "Using recorder-only data: %d samples (min_samples=%d)",
                    len(recorder_prices),
                    min_samples,
                )

                return {
                    "average": average,
                    "sample_count": len(recorder_prices),
                    "min": min_price,
                    "max": max_price,
                    "source": "recorder",
                }

            # Step 3: Fetch Tibber fallback if client provided
            tibber_prices = []
            if tibber_client:
                missing_days = max(1, days - len(recorder_prices))

                _LOGGER.info(
                    "Recorder has insufficient samples (%d < %d), fetching Tibber API fallback",
                    len(recorder_prices),
                    min_samples,
                )

                tibber_prices = await self.fetch_tibber_fallback(
                    tibber_client=tibber_client,
                    target_hour=current_hour,
                    missing_days=missing_days,
                    max_hours=max_fetch_hours,
                )

            # Step 4: Merge and calculate statistics
            all_prices = recorder_prices + tibber_prices

            if not all_prices:
                _LOGGER.warning(
                    "No price data available (recorder: %d, Tibber: %d)",
                    len(recorder_prices),
                    len(tibber_prices),
                )
                return {
                    "average": None,
                    "sample_count": 0,
                    "min": None,
                    "max": None,
                    "source": "none",
                }

            # Calculate merged statistics
            average = sum(all_prices) / len(all_prices)
            min_price = min(all_prices)
            max_price = max(all_prices)

            # Determine source
            if recorder_prices and tibber_prices:
                source = "mixed"
                _LOGGER.info(
                    "Using mixed data: recorder=%d, Tibber=%d, total=%d samples",
                    len(recorder_prices),
                    len(tibber_prices),
                    len(all_prices),
                )
            elif tibber_prices:
                source = "tibber"
                _LOGGER.info(
                    "Using Tibber-only data: %d samples",
                    len(tibber_prices),
                )
            else:
                source = "recorder"

            result = {
                "average": average,
                "sample_count": len(all_prices),
                "min": min_price,
                "max": max_price,
                "source": source,
            }

            # Add breakdown for mixed sources
            if source == "mixed":
                result["recorder_count"] = len(recorder_prices)
                result["tibber_count"] = len(tibber_prices)

            return result

        except Exception as err:
            _LOGGER.error("Error querying historical data: %s", err)
            return {
                "average": None,
                "sample_count": 0,
                "min": None,
                "max": None,
                "source": "error",
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
