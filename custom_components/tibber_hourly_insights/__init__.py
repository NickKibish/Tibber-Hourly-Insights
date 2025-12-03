"""The Tibber Hourly Insights integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_API_TOKEN, DOMAIN, ENTRY_DATA_COORDINATOR, TIBBER_PRICE_ENTITY
from .coordinator import TibberDataUpdateCoordinator
from .tibber_api import TibberApiClient, TibberApiError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Tibber Hourly Insights integration from YAML configuration."""
    _LOGGER.info("Tibber Hourly Insights integration loaded from YAML configuration")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tibber Hourly Insights from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    _LOGGER.debug("Setting up Tibber Hourly Insights integration")

    # Get API token from config entry
    api_token = entry.data[CONF_API_TOKEN]

    # Create API client
    client = TibberApiClient(api_token, hass)

    # Create coordinator
    coordinator = TibberDataUpdateCoordinator(hass, client, entry)

    # Fetch initial data
    try:
        await coordinator.async_config_entry_first_refresh()
    except TibberApiError as err:
        _LOGGER.error("Failed to fetch initial Tibber data: %s", err)
        raise ConfigEntryNotReady(f"Failed to connect to Tibber API: {err}") from err

    # Set up state change listener for official Tibber price entity
    async def _setup_price_listener(event=None):
        """Set up listener for Tibber price changes."""
        try:
            _LOGGER.debug("Setting up Tibber price change listener")

            # Check if Tibber price entity exists
            if hass.states.get(TIBBER_PRICE_ENTITY) is None:
                _LOGGER.warning(
                    "Official Tibber integration entity '%s' not found. "
                    "Please ensure the Tibber integration is installed and configured. "
                    "Price updates will need to be triggered manually.",
                    TIBBER_PRICE_ENTITY
                )
                return

            # Track the last hour we updated to prevent duplicate refreshes
            last_updated_hour = {"value": None}

            async def _handle_tibber_price_change(event: Event) -> None:
                """Handle state changes from official Tibber price sensor."""
                new_state = event.data.get("new_state")

                # Skip if state is unavailable or None
                if new_state is None or new_state.state in ("unavailable", "unknown"):
                    _LOGGER.debug("Skipping refresh: Tibber price state is %s",
                                 new_state.state if new_state else "None")
                    return

                # Get current hour to debounce updates
                from datetime import datetime
                current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)

                # Only refresh if we haven't updated this hour yet
                if last_updated_hour["value"] == current_hour:
                    _LOGGER.debug("Skipping refresh: Already updated for hour %s", current_hour)
                    return

                _LOGGER.info("Tibber price changed, refreshing insights (hour: %s)", current_hour)
                last_updated_hour["value"] = current_hour

                # Trigger coordinator refresh
                await coordinator.async_request_refresh()

            # Register state change listener
            unsub = async_track_state_change_event(
                hass, TIBBER_PRICE_ENTITY, _handle_tibber_price_change
            )
            entry.async_on_unload(unsub)

            _LOGGER.info(
                "Listening to Tibber price changes from entity: %s",
                TIBBER_PRICE_ENTITY
            )
        except Exception as ex:
            _LOGGER.error("Failed to set up price listener: %s", ex, exc_info=True)

    # Set up listener when HA is running
    if hass.is_running:
        await _setup_price_listener()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _setup_price_listener)

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = {
        ENTRY_DATA_COORDINATOR: coordinator,
    }

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener for options flow
    entry.async_on_unload(entry.add_update_listener(update_listener))

    _LOGGER.info("Tibber Hourly Insights integration setup completed")
    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Tibber Hourly Insights integration")

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Remove entry data
    if unload_ok and DOMAIN in hass.data:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    _LOGGER.info("Tibber Hourly Insights integration unloaded successfully")
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
