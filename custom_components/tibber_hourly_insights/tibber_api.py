"""Tibber API client for GraphQL queries."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import TIBBER_API_URL, TIBBER_USER_AGENT

_LOGGER = logging.getLogger(__name__)


class TibberApiClient:
    """Client for interacting with Tibber GraphQL API."""

    def __init__(self, api_token: str, hass: HomeAssistant) -> None:
        """Initialize the Tibber API client."""
        self._api_token = api_token
        self._session = async_get_clientsession(hass)

    async def _query(self, query: str) -> dict[str, Any]:
        """Execute a GraphQL query against the Tibber API."""
        headers = {
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type": "application/json",
            "User-Agent": TIBBER_USER_AGENT,
        }

        payload = {"query": query}

        try:
            async with self._session.post(
                TIBBER_API_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                data = await response.json()

                if "errors" in data:
                    error_messages = [error.get("message", "") for error in data["errors"]]
                    raise TibberApiError(f"GraphQL errors: {', '.join(error_messages)}")

                return data.get("data", {})

        except aiohttp.ClientError as err:
            _LOGGER.error("HTTP error communicating with Tibber API: %s", err)
            raise TibberApiError(f"HTTP error: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error communicating with Tibber API: %s", err)
            raise TibberApiError(f"Unexpected error: {err}") from err

    async def get_current_price(self) -> dict[str, Any]:
        """Get the current electricity price.

        Returns:
            dict with keys:
                - total: Current price including all fees and taxes
                - currency: Currency code (e.g., 'NOK')
                - level: Price level (VERY_CHEAP, CHEAP, NORMAL, EXPENSIVE, VERY_EXPENSIVE)
        """
        full_data = await self.get_price_data()
        return full_data.get("current", {})

    async def get_price_data(self) -> dict[str, Any]:
        """Get complete price data including current, today, and tomorrow.

        Returns:
            dict with keys:
                - current: Current price info {total, currency, level, startsAt}
                - today: List of hourly prices for today
                - tomorrow: List of hourly prices for tomorrow (empty before ~13:00)
        """
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

        data = await self._query(query)

        try:
            homes = data.get("viewer", {}).get("homes", [])
            if not homes:
                raise TibberApiError("No homes found in Tibber account")

            # Get the first home (most users have one home)
            home = homes[0]
            price_info = (
                home.get("currentSubscription", {})
                .get("priceInfo", {})
            )

            if not price_info:
                raise TibberApiError("No price data available")

            current_price = price_info.get("current", {})
            if not current_price:
                raise TibberApiError("No current price data available")

            return {
                "current": {
                    "total": current_price.get("total"),
                    "currency": current_price.get("currency"),
                    "level": current_price.get("level"),
                    "startsAt": current_price.get("startsAt"),
                },
                "today": price_info.get("today", []),
                "tomorrow": price_info.get("tomorrow", []),
            }

        except (KeyError, IndexError) as err:
            _LOGGER.error("Failed to parse Tibber API response: %s", err)
            raise TibberApiError(f"Failed to parse response: {err}") from err

    async def get_historical_consumption(
        self, resolution: str = "HOURLY", last: int = 720
    ) -> list[dict[str, Any]]:
        """Get historical consumption data with prices from Tibber API.

        This retrieves past consumption and pricing data, useful for filling gaps
        when Home Assistant's recorder doesn't have sufficient historical data.

        Args:
            resolution: Time resolution - HOURLY, DAILY, WEEKLY, MONTHLY, ANNUAL
            last: Number of records to fetch (e.g., 720 = 30 days of hourly data)

        Returns:
            List of consumption nodes, each containing:
                - from: ISO timestamp for period start
                - to: ISO timestamp for period end
                - unitPrice: Price per kWh (excluding VAT)
                - unitPriceVAT: VAT amount per kWh
                - cost: Total cost for the period
                - consumption: kWh consumed in the period

        Raises:
            TibberApiError: If API request fails or response is invalid
        """
        # Cap the request to prevent huge API calls
        last = min(last, 1000)  # Tibber API limit

        query = f"""
        {{
            viewer {{
                homes {{
                    consumption(resolution: {resolution}, last: {last}) {{
                        nodes {{
                            from
                            to
                            unitPrice
                            unitPriceVAT
                            cost
                            consumption
                        }}
                    }}
                }}
            }}
        }}
        """

        try:
            data = await self._query(query)

            homes = data.get("viewer", {}).get("homes", [])
            if not homes:
                raise TibberApiError("No homes found in Tibber account")

            # Get the first home
            home = homes[0]
            consumption_data = home.get("consumption", {})

            if not consumption_data:
                _LOGGER.warning("No consumption data available from Tibber API")
                return []

            nodes = consumption_data.get("nodes", [])

            _LOGGER.debug(
                "Fetched %d consumption nodes from Tibber API (resolution: %s, last: %d)",
                len(nodes),
                resolution,
                last,
            )

            return nodes

        except (KeyError, IndexError) as err:
            _LOGGER.error("Failed to parse Tibber consumption API response: %s", err)
            raise TibberApiError(f"Failed to parse consumption response: {err}") from err


class TibberApiError(Exception):
    """Exception raised for Tibber API errors."""
