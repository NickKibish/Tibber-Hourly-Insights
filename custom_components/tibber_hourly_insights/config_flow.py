"""Config flow for Tibber Hourly Insights integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .const import (
    CONF_API_TOKEN,
    CONF_CHEAP_PCT,
    CONF_DAY_END_HOUR,
    CONF_DAY_START_HOUR,
    CONF_ENABLE_30D_BASELINE,
    CONF_ENABLE_GRID_FEE,
    CONF_ENABLE_SUBSIDY,
    CONF_ENABLE_TIBBER_FALLBACK,
    CONF_EXPENSIVE_PCT,
    CONF_FALLBACK_MAX_FETCH_HOURS,
    CONF_FALLBACK_MIN_SAMPLES,
    CONF_GRID_FEE_DAY,
    CONF_GRID_FEE_NIGHT,
    CONF_NORMAL_PCT,
    CONF_SUBSIDY_PERCENTAGE,
    CONF_SUBSIDY_THRESHOLD,
    CONF_VERY_CHEAP_PCT,
    CONF_VERY_EXPENSIVE_PCT,
    CONF_WEIGHT_48H,
    CONF_WEIGHT_30D,
    CONF_WEIGHT_TIBBER,
    DEFAULT_CHEAP_PCT,
    DEFAULT_DAY_END_HOUR,
    DEFAULT_DAY_START_HOUR,
    DEFAULT_ENABLE_30D_BASELINE,
    DEFAULT_ENABLE_GRID_FEE,
    DEFAULT_ENABLE_SUBSIDY,
    DEFAULT_ENABLE_TIBBER_FALLBACK,
    DEFAULT_EXPENSIVE_PCT,
    DEFAULT_FALLBACK_MAX_FETCH_HOURS,
    DEFAULT_FALLBACK_MIN_SAMPLES,
    DEFAULT_GRID_FEE_DAY,
    DEFAULT_GRID_FEE_NIGHT,
    DEFAULT_NORMAL_PCT,
    DEFAULT_SUBSIDY_PERCENTAGE,
    DEFAULT_SUBSIDY_THRESHOLD,
    DEFAULT_VERY_CHEAP_PCT,
    DEFAULT_VERY_EXPENSIVE_PCT,
    DEFAULT_WEIGHT_48H,
    DEFAULT_WEIGHT_30D,
    DEFAULT_WEIGHT_TIBBER,
    DOMAIN,
)
from .tibber_api import TibberApiClient

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_API_TOKEN): str,
})


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from DATA_SCHEMA with values provided by the user.
    """
    api_token = data[CONF_API_TOKEN]

    # Create API client and test connection
    client = TibberApiClient(api_token, hass)

    try:
        # Validate token by fetching current price
        await client.get_current_price()
    except Exception as err:
        _LOGGER.error("Failed to validate Tibber API token: %s", err)
        raise InvalidAuth from err

    # Return info that you want to store in the config entry
    return {"title": "Tibber"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tibber Hourly Insights."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Create config entry
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        _LOGGER.warning("🔵 async_get_options_flow called with config_entry: %s", config_entry.entry_id if config_entry else "None")
        handler = OptionsFlowHandler()
        _LOGGER.warning("🔵 OptionsFlowHandler instantiated: %s", handler)
        return handler


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Tibber Hourly Insights."""

    def __init__(self) -> None:
        """Initialize options flow."""
        super().__init__()
        _LOGGER.warning("🟢 OptionsFlowHandler.__init__ called")

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        _LOGGER.warning("🟡 async_step_init called with user_input: %s", "provided" if user_input else "None")

        # Check what attributes are available
        _LOGGER.warning("🟡 Has config_entry: %s", hasattr(self, 'config_entry'))
        _LOGGER.warning("🟡 Has handler: %s", hasattr(self, 'handler'))
        _LOGGER.warning("🟡 Has _handler: %s", hasattr(self, '_handler'))

        if user_input is not None:
            _LOGGER.warning("🟡 Saving user input")
            return self.async_create_entry(title="", data=user_input)

        # Try to get config_entry
        try:
            _LOGGER.warning("🟡 Attempting to access self.config_entry")
            config_entry = self.config_entry
            _LOGGER.warning("🟢 config_entry accessed successfully: %s", config_entry.entry_id)
            options = config_entry.options
            _LOGGER.warning("🟢 options retrieved: %s keys", len(options))
        except AttributeError as e:
            _LOGGER.error("🔴 AttributeError accessing config_entry: %s", e)
            _LOGGER.error("🔴 Available attributes: %s", [a for a in dir(self) if not a.startswith('_')])
            raise
        except Exception as e:
            _LOGGER.error("🔴 Unexpected error: %s", e, exc_info=True)
            raise

        _LOGGER.warning("🟡 Building options schema")

        try:
            options_schema = vol.Schema({
                vol.Optional(
                    CONF_WEIGHT_TIBBER,
                    default=options.get(CONF_WEIGHT_TIBBER, DEFAULT_WEIGHT_TIBBER)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.0,
                        max=1.0,
                        step=0.1,
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Optional(
                    CONF_WEIGHT_48H,
                    default=options.get(CONF_WEIGHT_48H, DEFAULT_WEIGHT_48H)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.0,
                        max=1.0,
                        step=0.1,
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Optional(
                    CONF_WEIGHT_30D,
                    default=options.get(CONF_WEIGHT_30D, DEFAULT_WEIGHT_30D)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.0,
                        max=1.0,
                        step=0.1,
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Optional(
                    CONF_VERY_CHEAP_PCT,
                    default=options.get(CONF_VERY_CHEAP_PCT, DEFAULT_VERY_CHEAP_PCT)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-100.0,
                        max=0.0,
                        step=5.0,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_CHEAP_PCT,
                    default=options.get(CONF_CHEAP_PCT, DEFAULT_CHEAP_PCT)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-100.0,
                        max=0.0,
                        step=5.0,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="%",
                    )
                ),
                vol.Optional(
                    CONF_NORMAL_PCT,
                    default=options.get(CONF_NORMAL_PCT, DEFAULT_NORMAL_PCT)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-50.0,
                        max=50.0,
                        step=5.0,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="%",
                    )
                ),
                vol.Optional(
                    CONF_EXPENSIVE_PCT,
                    default=options.get(CONF_EXPENSIVE_PCT, DEFAULT_EXPENSIVE_PCT)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.0,
                        max=100.0,
                        step=5.0,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="%",
                    )
                ),
                vol.Optional(
                    CONF_VERY_EXPENSIVE_PCT,
                    default=options.get(CONF_VERY_EXPENSIVE_PCT, DEFAULT_VERY_EXPENSIVE_PCT)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.0,
                        max=100.0,
                        step=5.0,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="%",
                    )
                ),
                vol.Optional(
                    CONF_ENABLE_30D_BASELINE,
                    default=options.get(CONF_ENABLE_30D_BASELINE, DEFAULT_ENABLE_30D_BASELINE)
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_ENABLE_TIBBER_FALLBACK,
                    default=options.get(CONF_ENABLE_TIBBER_FALLBACK, DEFAULT_ENABLE_TIBBER_FALLBACK)
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_FALLBACK_MIN_SAMPLES,
                    default=options.get(CONF_FALLBACK_MIN_SAMPLES, DEFAULT_FALLBACK_MIN_SAMPLES)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=30,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_FALLBACK_MAX_FETCH_HOURS,
                    default=options.get(CONF_FALLBACK_MAX_FETCH_HOURS, DEFAULT_FALLBACK_MAX_FETCH_HOURS)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=24,
                        max=1000,
                        step=24,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_ENABLE_GRID_FEE,
                    default=options.get(CONF_ENABLE_GRID_FEE, DEFAULT_ENABLE_GRID_FEE)
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_GRID_FEE_DAY,
                    default=options.get(CONF_GRID_FEE_DAY, DEFAULT_GRID_FEE_DAY)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.0,
                        max=2.0,
                        step=0.001,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="NOK/kWh",
                    )
                ),
                vol.Optional(
                    CONF_GRID_FEE_NIGHT,
                    default=options.get(CONF_GRID_FEE_NIGHT, DEFAULT_GRID_FEE_NIGHT)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.0,
                        max=2.0,
                        step=0.001,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="NOK/kWh",
                    )
                ),
                vol.Optional(
                    CONF_DAY_START_HOUR,
                    default=options.get(CONF_DAY_START_HOUR, DEFAULT_DAY_START_HOUR)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=23,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_DAY_END_HOUR,
                    default=options.get(CONF_DAY_END_HOUR, DEFAULT_DAY_END_HOUR)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=23,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_ENABLE_SUBSIDY,
                    default=options.get(CONF_ENABLE_SUBSIDY, DEFAULT_ENABLE_SUBSIDY)
                ): selector.BooleanSelector(),
            vol.Optional(
                CONF_SUBSIDY_THRESHOLD,
                default=options.get(CONF_SUBSIDY_THRESHOLD, DEFAULT_SUBSIDY_THRESHOLD)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=5.0,
                    # HA validation rejects overly small steps; 0.001 keeps options flow valid
                    step=0.001,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="NOK/kWh",
                )
            ),
                vol.Optional(
                    CONF_SUBSIDY_PERCENTAGE,
                    default=options.get(CONF_SUBSIDY_PERCENTAGE, DEFAULT_SUBSIDY_PERCENTAGE)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.0,
                        max=100.0,
                        step=1.0,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="%",
                    )
                ),
            })

            _LOGGER.warning("🟢 Schema built successfully, returning form")

        except Exception as e:
            _LOGGER.error("🔴 CRITICAL: Schema building failed!")
            _LOGGER.error("🔴 Error type: %s", type(e).__name__)
            _LOGGER.error("🔴 Error message: %s", str(e))
            _LOGGER.error("🔴 Full traceback:", exc_info=True)

            # Return a minimal fallback schema to prevent complete failure
            _LOGGER.warning("🟡 Returning minimal fallback schema")
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({}),
                errors={"base": "schema_error"},
            )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
