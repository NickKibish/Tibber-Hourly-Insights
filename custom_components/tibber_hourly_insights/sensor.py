"""Sensor platform for Tibber Hourly Insights."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import homeassistant.util.dt as dt_util

from .const import (
    ATTR_48H_CONTRIBUTION,
    ATTR_30D_CONTRIBUTION,
    ATTR_AVAILABLE_INPUTS,
    ATTR_AVG_PRICE_48H,
    ATTR_BASELINE_PRICE,
    ATTR_COMPARISON,
    ATTR_CURRENCY,
    ATTR_DATA_SOURCE,
    ATTR_DIFFERENCE_PERCENT,
    ATTR_GRID_FEE,
    ATTR_MAX_PRICE_48H,
    ATTR_MIN_PRICE_48H,
    ATTR_PCT_VS_AVERAGE_48H,
    ATTR_PERCENTILE,
    ATTR_PRICE_CATEGORY,
    ATTR_PRICE_LEVEL,
    ATTR_RAW_SPOT_PRICE,
    ATTR_SAMPLE_COUNT,
    ATTR_SCORE_DESCRIPTION,
    ATTR_SUBSIDY_AMOUNT,
    ATTR_TIBBER_CONTRIBUTION,
    ATTR_WEIGHTS_USED,
    CONF_CHEAP_PCT,
    CONF_ENABLE_30D_BASELINE,
    CONF_ENABLE_TIBBER_FALLBACK,
    CONF_EXPENSIVE_PCT,
    CONF_FALLBACK_MAX_FETCH_HOURS,
    CONF_FALLBACK_MIN_SAMPLES,
    CONF_NORMAL_PCT,
    CONF_VERY_CHEAP_PCT,
    CONF_VERY_EXPENSIVE_PCT,
    CONF_WEIGHT_48H,
    CONF_WEIGHT_30D,
    CONF_WEIGHT_TIBBER,
    DEFAULT_CHEAP_PCT,
    DEFAULT_ENABLE_30D_BASELINE,
    DEFAULT_ENABLE_TIBBER_FALLBACK,
    DEFAULT_EXPENSIVE_PCT,
    DEFAULT_FALLBACK_MAX_FETCH_HOURS,
    DEFAULT_FALLBACK_MIN_SAMPLES,
    DEFAULT_NORMAL_PCT,
    DEFAULT_VERY_CHEAP_PCT,
    DEFAULT_VERY_EXPENSIVE_PCT,
    DEFAULT_WEIGHT_48H,
    DEFAULT_WEIGHT_30D,
    DEFAULT_WEIGHT_TIBBER,
    DOMAIN,
    ENTRY_DATA_COORDINATOR,
    PRICE_CATEGORY_CHEAP_THRESHOLD,
    PRICE_CATEGORY_EXPENSIVE_THRESHOLD,
)
from .coordinator import TibberDataUpdateCoordinator
from .history import TibberHistoryHelper

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tibber sensor from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id][ENTRY_DATA_COORDINATOR]

    # Create core sensors (always created)
    sensors = [
        TibberCurrentPriceSensor(coordinator, entry),
        TibberApiPriceLevelSensor(coordinator, entry),
        Tibber48HourComparisonSensor(coordinator, entry),
        TibberWeightedConsensusSensor(coordinator, entry, hass),
    ]

    # Conditionally add 30d baseline sensor if enabled in options
    enable_30d = entry.options.get(CONF_ENABLE_30D_BASELINE, DEFAULT_ENABLE_30D_BASELINE)
    if enable_30d:
        sensors.append(Tibber30DayBaselineSensor(coordinator, entry, hass))

    async_add_entities(sensors, True)


class TibberCurrentPriceSensor(CoordinatorEntity[TibberDataUpdateCoordinator], SensorEntity):
    """Sensor representing the current electricity price from Tibber."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.MONETARY

    def __init__(
        self,
        coordinator: TibberDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._attr_unique_id = f"{entry.entry_id}_current_price"
        self._attr_name = "Current Price"

    @property
    def native_value(self) -> float | None:
        """Return the current price."""
        if self.coordinator.data is None:
            return None

        current = self.coordinator.data.get("current", {})
        price = current.get("total")
        if price is None:
            _LOGGER.warning("No price data available from coordinator")
            return None

        return price

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement."""
        if self.coordinator.data is None:
            return None

        current = self.coordinator.data.get("current", {})
        currency = current.get("currency", "NOK")
        return f"{currency}/kWh"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional attributes."""
        if self.coordinator.data is None:
            return None

        current = self.coordinator.data.get("current", {})

        attributes = {
            ATTR_CURRENCY: current.get("currency"),
            ATTR_PRICE_LEVEL: current.get("level"),
        }

        # Add price adjustment details if available
        if "raw_spot_price" in current:
            attributes[ATTR_RAW_SPOT_PRICE] = current.get("raw_spot_price")
            attributes[ATTR_SUBSIDY_AMOUNT] = current.get("subsidy_amount", 0.0)
            attributes[ATTR_GRID_FEE] = current.get("grid_fee", 0.0)

        return attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self.coordinator.data.get("current", {}).get("total") is not None
        )


class TibberApiPriceLevelSensor(CoordinatorEntity[TibberDataUpdateCoordinator], SensorEntity):
    """Sensor showing Tibber's native price level classification."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TibberDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._attr_unique_id = f"{entry.entry_id}_api_price_level"
        self._attr_name = "API Price Level"
        self._attr_icon = "mdi:flash"

    @property
    def native_value(self) -> str | None:
        """Return the Tibber API price level."""
        if self.coordinator.data is None:
            return None

        current = self.coordinator.data.get("current", {})
        return current.get("level")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional attributes."""
        if self.coordinator.data is None:
            return None

        current = self.coordinator.data.get("current", {})
        return {
            "current_price": current.get("total"),
            ATTR_CURRENCY: current.get("currency"),
            "level_description": self._get_level_description(current.get("level")),
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self.coordinator.data.get("current", {}).get("level") is not None
        )

    def _get_level_description(self, level: str | None) -> str:
        """Get human-readable description of price level."""
        descriptions = {
            "VERY_CHEAP": "Very cheap electricity price",
            "CHEAP": "Cheap electricity price",
            "NORMAL": "Normal electricity price",
            "EXPENSIVE": "Expensive electricity price",
            "VERY_EXPENSIVE": "Very expensive electricity price",
        }
        return descriptions.get(level, "Unknown")


class Tibber48HourComparisonSensor(CoordinatorEntity[TibberDataUpdateCoordinator], SensorEntity):
    """Sensor comparing current price to 48-hour window (today+tomorrow or yesterday+today)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TibberDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._attr_unique_id = f"{entry.entry_id}_48h_comparison"
        self._attr_name = "48h Price Comparison"
        self._attr_icon = "mdi:chart-bell-curve"
        self._attr_native_unit_of_measurement = "%"

    @property
    def native_value(self) -> float | None:
        """Return the percentile rank of current price in 48h window."""
        if self.coordinator.data is None:
            return None

        current = self.coordinator.data.get("current", {})
        current_price = current.get("total")
        if current_price is None:
            return None

        # Get 48-hour price window
        prices_48h = self._get_48h_prices()
        if not prices_48h:
            return None

        # Calculate percentile
        percentile = self._calculate_percentile(current_price, prices_48h)
        return round(percentile, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional attributes."""
        if self.coordinator.data is None:
            return None

        current = self.coordinator.data.get("current", {})
        current_price = current.get("total")
        if current_price is None:
            return None

        prices_48h = self._get_48h_prices()
        if not prices_48h:
            return None

        percentile = self._calculate_percentile(current_price, prices_48h)
        price_category = self._get_price_category(percentile)
        pct_vs_avg = self._calculate_pct_vs_average(current_price, prices_48h)

        tomorrow = self.coordinator.data.get("tomorrow", [])
        data_source = "today+tomorrow" if tomorrow else "yesterday+today"

        return {
            ATTR_PRICE_CATEGORY: price_category,
            ATTR_PERCENTILE: round(percentile, 1),
            ATTR_PCT_VS_AVERAGE_48H: round(pct_vs_avg, 2),
            "current_price": current_price,
            ATTR_MIN_PRICE_48H: round(min(prices_48h), 4),
            ATTR_MAX_PRICE_48H: round(max(prices_48h), 4),
            ATTR_AVG_PRICE_48H: round(sum(prices_48h) / len(prices_48h), 4),
            ATTR_DATA_SOURCE: data_source,
            ATTR_CURRENCY: current.get("currency"),
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success or self.coordinator.data is None:
            return False

        current = self.coordinator.data.get("current", {})
        if current.get("total") is None:
            return False

        # Need at least today's prices
        today = self.coordinator.data.get("today", [])
        return len(today) > 0

    def _get_48h_prices(self) -> list[float]:
        """Get 48 hours of price data.

        Returns list of prices from either:
        - today + tomorrow (after ~13:00 when tomorrow is available)
        - yesterday + today (before tomorrow is available)
        """
        today = self.coordinator.data.get("today", [])
        tomorrow = self.coordinator.data.get("tomorrow", [])
        yesterday = self.coordinator.data.get("yesterday", [])

        prices = []

        if tomorrow:
            # Use today + tomorrow
            for entry in today + tomorrow:
                if entry.get("total") is not None:
                    prices.append(entry["total"])
        elif yesterday:
            # Use yesterday + today
            for entry in yesterday + today:
                if entry.get("total") is not None:
                    prices.append(entry["total"])
        else:
            # Fallback to just today if no other data available
            for entry in today:
                if entry.get("total") is not None:
                    prices.append(entry["total"])

        return prices

    def _calculate_percentile(self, current_price: float, prices: list[float]) -> float:
        """Calculate percentile rank of current price in price list."""
        if not prices:
            return 50.0  # Default to middle if no data

        # Count how many prices are less than current price
        count_below = sum(1 for p in prices if p < current_price)

        # Calculate percentile (0-100)
        percentile = (count_below / len(prices)) * 100
        return percentile

    def _get_price_category(self, percentile: float) -> str:
        """Get price category based on percentile."""
        if percentile < PRICE_CATEGORY_CHEAP_THRESHOLD:
            return "cheap"
        elif percentile < PRICE_CATEGORY_EXPENSIVE_THRESHOLD:
            return "normal"
        else:
            return "expensive"

    def _calculate_pct_vs_average(self, current_price: float, prices: list[float]) -> float:
        """Calculate percentage difference from 48h average.

        Returns:
            Percentage difference (e.g., 12.5 means 12.5% more expensive than average)
        """
        if not prices:
            return 0.0

        avg_price = sum(prices) / len(prices)
        if avg_price == 0:
            return 0.0

        pct_diff = ((current_price - avg_price) / avg_price) * 100
        return pct_diff


class Tibber30DayBaselineSensor(CoordinatorEntity[TibberDataUpdateCoordinator], SensorEntity):
    """Sensor comparing current price to 30-day baseline for same hour."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TibberDataUpdateCoordinator,
        entry: ConfigEntry,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._attr_unique_id = f"{entry.entry_id}_30d_baseline"
        self._attr_name = "30-Day Baseline Comparison"
        self._attr_icon = "mdi:chart-line"
        self._hass = hass
        self._entry = entry
        self._history_helper: TibberHistoryHelper | None = None
        self._baseline_data: dict[str, Any] | None = None

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

        # Initialize history helper
        current_price_entity = f"sensor.tibber_current_price"
        self._history_helper = TibberHistoryHelper(self._hass, current_price_entity)

        # Fetch initial baseline data
        await self._update_baseline()

    async def async_update(self) -> None:
        """Update the sensor."""
        await super().async_update()
        await self._update_baseline()

    async def _update_baseline(self) -> None:
        """Update the 30-day baseline data with optional Tibber API fallback."""
        if self._history_helper is None:
            return

        # Get fallback configuration from options
        options = self._entry.options
        enable_fallback = options.get(
            CONF_ENABLE_TIBBER_FALLBACK, DEFAULT_ENABLE_TIBBER_FALLBACK
        )
        min_samples = options.get(
            CONF_FALLBACK_MIN_SAMPLES, DEFAULT_FALLBACK_MIN_SAMPLES
        )
        max_fetch_hours = options.get(
            CONF_FALLBACK_MAX_FETCH_HOURS, DEFAULT_FALLBACK_MAX_FETCH_HOURS
        )

        # Get Tibber client from coordinator if fallback is enabled
        tibber_client = self.coordinator.client if enable_fallback else None

        try:
            self._baseline_data = await self._history_helper.get_same_hour_average(
                days=30,
                tibber_client=tibber_client,
                enable_fallback=enable_fallback,
                min_samples=min_samples,
                max_fetch_hours=max_fetch_hours,
            )
        except Exception as err:
            _LOGGER.error("Error updating 30-day baseline: %s", err)
            self._baseline_data = None

    @property
    def native_value(self) -> str | None:
        """Return the percentage difference from baseline."""
        if self.coordinator.data is None or self._baseline_data is None:
            return None

        current = self.coordinator.data.get("current", {})
        current_price = current.get("total")
        baseline_price = self._baseline_data.get("average")

        if current_price is None or baseline_price is None:
            return None

        # Calculate percentage difference
        diff_percent = ((current_price - baseline_price) / baseline_price) * 100

        # Format as string with sign
        if diff_percent > 0:
            return f"+{diff_percent:.1f}%"
        else:
            return f"{diff_percent:.1f}%"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional attributes."""
        if self.coordinator.data is None:
            return None

        current = self.coordinator.data.get("current", {})
        current_price = current.get("total")

        if current_price is None:
            return None

        attrs = {
            "current_price": current_price,
            ATTR_CURRENCY: current.get("currency"),
        }

        if self._baseline_data:
            baseline_price = self._baseline_data.get("average")
            sample_count = self._baseline_data.get("sample_count", 0)
            data_source = self._baseline_data.get("source", "recorder")

            if baseline_price is not None:
                diff_percent = ((current_price - baseline_price) / baseline_price) * 100

                attrs.update({
                    ATTR_BASELINE_PRICE: round(baseline_price, 4),
                    ATTR_COMPARISON: self._get_comparison_text(diff_percent),
                    ATTR_DIFFERENCE_PERCENT: round(diff_percent, 1),
                    ATTR_SAMPLE_COUNT: sample_count,
                    ATTR_DATA_SOURCE: data_source,
                })

                # Add breakdown for mixed sources
                if data_source == "mixed":
                    attrs["recorder_samples"] = self._baseline_data.get("recorder_count", 0)
                    attrs["tibber_samples"] = self._baseline_data.get("tibber_count", 0)

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success or self.coordinator.data is None:
            return False

        current = self.coordinator.data.get("current", {})
        if current.get("total") is None:
            return False

        # Initially available even without baseline data
        # Baseline will populate over time
        return True

    def _get_comparison_text(self, diff_percent: float) -> str:
        """Get human-readable comparison text."""
        if abs(diff_percent) < 5:
            return "similar"
        elif diff_percent < 0:
            return "cheaper"
        else:
            return "more expensive"

class TibberWeightedConsensusSensor(CoordinatorEntity[TibberDataUpdateCoordinator], SensorEntity):
    """Weighted consensus price score combining Tibber API, 48h, and 30d metrics."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:gauge"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: TibberDataUpdateCoordinator,
        entry: ConfigEntry,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the consensus sensor."""
        super().__init__(coordinator)

        self._attr_unique_id = f"{entry.entry_id}_price_consensus"
        self._attr_name = "Price Consensus"
        self._hass = hass
        self._entry = entry

    @property
    def native_value(self) -> float | None:
        """Return consensus score as decimal percentage.

        0.0 = normal price
        +0.3 = 30% more expensive than normal
        -0.25 = 25% cheaper than normal
        """
        if self.coordinator.data is None:
            return None

        # Get configuration options
        options = self._entry.options
        weights = {
            "tibber": options.get(CONF_WEIGHT_TIBBER, DEFAULT_WEIGHT_TIBBER),
            "48h": options.get(CONF_WEIGHT_48H, DEFAULT_WEIGHT_48H),
            "30d": options.get(CONF_WEIGHT_30D, DEFAULT_WEIGHT_30D),
        }
        enum_map = {
            "VERY_CHEAP": options.get(CONF_VERY_CHEAP_PCT, DEFAULT_VERY_CHEAP_PCT),
            "CHEAP": options.get(CONF_CHEAP_PCT, DEFAULT_CHEAP_PCT),
            "NORMAL": options.get(CONF_NORMAL_PCT, DEFAULT_NORMAL_PCT),
            "EXPENSIVE": options.get(CONF_EXPENSIVE_PCT, DEFAULT_EXPENSIVE_PCT),
            "VERY_EXPENSIVE": options.get(CONF_VERY_EXPENSIVE_PCT, DEFAULT_VERY_EXPENSIVE_PCT),
        }
        enable_30d = options.get(CONF_ENABLE_30D_BASELINE, DEFAULT_ENABLE_30D_BASELINE)

        # 1. Collect available metrics as percentages
        metrics = {}

        # Tibber enum → percentage
        tibber_level = self.coordinator.data.get("current", {}).get("level")
        if tibber_level:
            metrics["tibber"] = enum_map.get(tibber_level, 0.0)

        # 48h comparison → % vs average (from attributes)
        prices_48h = self._get_48h_prices()
        current_price = self.coordinator.data.get("current", {}).get("total")
        if current_price and prices_48h:
            pct_48h = self._calculate_pct_vs_average(current_price, prices_48h)
            metrics["48h"] = pct_48h

        # 30d baseline → % vs baseline (if enabled and available)
        if enable_30d:
            pct_30d = self._get_30d_percentage()
            if pct_30d is not None:
                metrics["30d"] = pct_30d

        if not metrics:
            return None

        # 2. Renormalize weights for available inputs
        active_weights = {k: weights[k] for k in metrics.keys()}
        total_weight = sum(active_weights.values())

        if total_weight == 0:
            return 0.0  # Fallback to neutral (0 = normal)

        normalized_weights = {k: v / total_weight for k, v in active_weights.items()}

        # 3. Calculate weighted average percentage
        weighted_pct = sum(metrics[k] * normalized_weights[k] for k in metrics.keys())

        # 4. Return as decimal percentage (0.0 = normal, +0.3 = 30% more expensive, -0.25 = 25% cheaper)
        # Convert from percentage to decimal: divide by 100
        score = weighted_pct / 100.0

        return round(score, 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return detailed breakdown attributes."""
        if self.coordinator.data is None:
            return None

        options = self._entry.options
        weights = {
            "tibber": options.get(CONF_WEIGHT_TIBBER, DEFAULT_WEIGHT_TIBBER),
            "48h": options.get(CONF_WEIGHT_48H, DEFAULT_WEIGHT_48H),
            "30d": options.get(CONF_WEIGHT_30D, DEFAULT_WEIGHT_30D),
        }
        enum_map = {
            "VERY_CHEAP": options.get(CONF_VERY_CHEAP_PCT, DEFAULT_VERY_CHEAP_PCT),
            "CHEAP": options.get(CONF_CHEAP_PCT, DEFAULT_CHEAP_PCT),
            "NORMAL": options.get(CONF_NORMAL_PCT, DEFAULT_NORMAL_PCT),
            "EXPENSIVE": options.get(CONF_EXPENSIVE_PCT, DEFAULT_EXPENSIVE_PCT),
            "VERY_EXPENSIVE": options.get(CONF_VERY_EXPENSIVE_PCT, DEFAULT_VERY_EXPENSIVE_PCT),
        }
        enable_30d = options.get(CONF_ENABLE_30D_BASELINE, DEFAULT_ENABLE_30D_BASELINE)

        # Collect metrics
        metrics = {}
        tibber_pct = None
        pct_48h = None
        pct_30d = None

        tibber_level = self.coordinator.data.get("current", {}).get("level")
        if tibber_level:
            tibber_pct = enum_map.get(tibber_level, 0.0)
            metrics["tibber"] = tibber_pct

        prices_48h = self._get_48h_prices()
        current_price = self.coordinator.data.get("current", {}).get("total")
        if current_price and prices_48h:
            pct_48h = self._calculate_pct_vs_average(current_price, prices_48h)
            metrics["48h"] = pct_48h

        if enable_30d:
            pct_30d = self._get_30d_percentage()
            if pct_30d is not None:
                metrics["30d"] = pct_30d

        # Calculate normalized weights
        active_weights = {k: weights[k] for k in metrics.keys()}
        total_weight = sum(active_weights.values())
        normalized_weights = {k: v / total_weight for k, v in active_weights.items()} if total_weight > 0 else {}

        # Get score
        score = self.native_value or 0.0

        return {
            ATTR_TIBBER_CONTRIBUTION: round(tibber_pct, 2) if tibber_pct is not None else None,
            ATTR_48H_CONTRIBUTION: round(pct_48h, 2) if pct_48h is not None else None,
            ATTR_30D_CONTRIBUTION: round(pct_30d, 2) if pct_30d is not None else None,
            ATTR_WEIGHTS_USED: {k: round(v, 3) for k, v in normalized_weights.items()},
            ATTR_AVAILABLE_INPUTS: list(metrics.keys()),
            ATTR_SCORE_DESCRIPTION: self._get_score_description(score),
            "current_price": current_price,
            ATTR_CURRENCY: self.coordinator.data.get("current", {}).get("currency"),
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success or self.coordinator.data is None:
            return False

        current = self.coordinator.data.get("current", {})
        if current.get("total") is None or current.get("level") is None:
            return False

        return True

    def _get_48h_prices(self) -> list[float]:
        """Get 48 hours of price data."""
        today = self.coordinator.data.get("today", [])
        tomorrow = self.coordinator.data.get("tomorrow", [])
        yesterday = self.coordinator.data.get("yesterday", [])

        prices = []

        if tomorrow:
            for entry in today + tomorrow:
                if entry.get("total") is not None:
                    prices.append(entry["total"])
        elif yesterday:
            for entry in yesterday + today:
                if entry.get("total") is not None:
                    prices.append(entry["total"])
        else:
            for entry in today:
                if entry.get("total") is not None:
                    prices.append(entry["total"])

        return prices

    def _calculate_pct_vs_average(self, current_price: float, prices: list[float]) -> float:
        """Calculate percentage difference from average."""
        if not prices:
            return 0.0

        avg_price = sum(prices) / len(prices)
        if avg_price == 0:
            return 0.0

        pct_diff = ((current_price - avg_price) / avg_price) * 100
        return pct_diff

    def _get_30d_percentage(self) -> float | None:
        """Get 30d baseline percentage if available."""
        # Try to get from 30d baseline sensor if it exists
        baseline_entity = f"sensor.tibber_30d_baseline_comparison"
        state = self._hass.states.get(baseline_entity)

        if not state or state.state in ("unavailable", "unknown", None):
            return None

        # Get difference_percent attribute
        diff_percent = state.attributes.get(ATTR_DIFFERENCE_PERCENT)
        if diff_percent is None:
            return None

        try:
            return float(diff_percent)
        except (ValueError, TypeError):
            return None

    def _get_score_description(self, score: float) -> str:
        """Convert score to human-readable description.

        Args:
            score: Decimal percentage (0.0 = normal, +0.3 = 30% more, -0.25 = 25% less)
        """
        # Convert decimal to percentage
        pct_diff = score * 100

        if abs(pct_diff) < 5:
            return "Normal price"
        elif pct_diff < 0:
            return f"{abs(pct_diff):.1f}% cheaper than normal"
        else:
            return f"{pct_diff:.1f}% more expensive than normal"
