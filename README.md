# Tibber Hourly Insights Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

Home Assistant integration that provides hourly electricity price data from Tibber.

## Features

- ⚡ **Current Price Monitoring**: Track current electricity prices in real-time
- 🔄 **Hourly Updates**: Automatic updates every hour to reflect latest pricing
- 📊 **Price Level Indicators**: Get Tibber's native price level classification
- 📈 **48-Hour Price Comparison**: See how current price ranks against today+tomorrow prices
- 📉 **30-Day Historical Baseline**: Compare current price to 30-day average for same hour
- 🌍 **Multi-Currency Support**: Works with NOK, SEK, EUR, and other currencies
- ⚙️ **Easy Setup**: Simple configuration via Home Assistant UI

## Requirements

- Home Assistant 2023.1 or later
- Tibber account with active subscription
- Tibber API token (get it from [developer.tibber.com](https://developer.tibber.com))

## Getting a Tibber API Token

1. Go to [developer.tibber.com](https://developer.tibber.com)
2. Log in with your Tibber account
3. Navigate to **Settings** or **API Explorer**
4. Generate a new API token
5. Copy the token (you'll need it during integration setup)

## Installation

### HACS (Recommended)

1. Add this repository to HACS as a custom repository
2. Install "Tibber Hourly Insights" from HACS
3. Restart Home Assistant
4. Add the integration through the UI

### Manual Installation

1. Copy the `custom_components/tibber_hourly_insights` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Add the integration through the UI

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Tibber Hourly Insights"
3. Enter your Tibber API token
4. Click Submit

The integration will validate your token and set up the sensors.

## Entities Created

The integration creates four sensors to help you understand electricity pricing:

### 1. Current Price
- **Entity ID**: `sensor.tibber_current_price`
- **Description**: Current electricity price including all fees and taxes
- **State**: Current price value
- **Unit**: `{currency}/kWh` (e.g., NOK/kWh)
- **Device Class**: Monetary
- **Update Frequency**: Every hour

**Attributes**:
- `currency`: Currency code (e.g., NOK, SEK, EUR)
- `price_level`: Tibber's price level (VERY_CHEAP, CHEAP, NORMAL, EXPENSIVE, VERY_EXPENSIVE)

### 2. API Price Level
- **Entity ID**: `sensor.tibber_api_price_level`
- **Description**: Tibber's native price level classification
- **State**: Price level string (VERY_CHEAP, CHEAP, NORMAL, EXPENSIVE, VERY_EXPENSIVE)
- **Update Frequency**: Every hour

**Attributes**:
- `current_price`: Current price value
- `currency`: Currency code
- `level_description`: Human-readable description of the price level

### 3. 48-Hour Price Comparison
- **Entity ID**: `sensor.tibber_48h_price_comparison`
- **Description**: Percentile ranking of current price within 48-hour window
- **State**: Percentile (0-100%)
- **Unit**: `%`
- **Update Frequency**: Every hour

**How it works**:
- After ~13:00 when tomorrow's prices are available: Compares against today + tomorrow
- Before tomorrow's prices: Compares against yesterday + today
- Lower percentile = cheaper relative price

**Attributes**:
- `price_category`: `cheap` (0-33%), `normal` (33-66%), or `expensive` (66-100%)
- `percentile`: Numeric percentile ranking
- `current_price`: Current price value
- `min_price_48h`: Minimum price in 48h window
- `max_price_48h`: Maximum price in 48h window
- `avg_price_48h`: Average price in 48h window
- `data_source`: `today+tomorrow` or `yesterday+today`
- `currency`: Currency code

### 4. 30-Day Baseline Comparison
- **Entity ID**: `sensor.tibber_30d_baseline_comparison`
- **Description**: Percentage difference from 30-day historical average for same hour
- **State**: Percentage difference (e.g., "+15.3%" or "-8.2%")
- **Update Frequency**: Every hour

**How it works**:
- Calculates average price for current hour over last 30 days
- Compares current price to this baseline
- Requires historical data (accuracy improves over time)

**Attributes**:
- `current_price`: Current price value
- `baseline_price`: 30-day average for this hour
- `comparison`: `cheaper`, `similar`, or `more expensive`
- `difference_percent`: Numeric percentage difference
- `sample_count`: Number of historical data points used
- `currency`: Currency code

## Usage Examples

### Display All Price Sensors in Lovelace

```yaml
type: entities
title: Electricity Price Analysis
entities:
  - entity: sensor.tibber_current_price
    name: Current Price
  - entity: sensor.tibber_api_price_level
    name: Tibber Price Level
  - entity: sensor.tibber_48h_price_comparison
    name: 48h Comparison
  - entity: sensor.tibber_30d_baseline_comparison
    name: vs 30-Day Average
```

### Automation: Start Dishwasher When Price is Cheap (48h Comparison)

```yaml
automation:
  - alias: "Notify when good time to run dishwasher"
    trigger:
      - platform: state
        entity_id: sensor.tibber_48h_price_comparison
    condition:
      - condition: template
        value_template: "{{ state_attr('sensor.tibber_48h_price_comparison', 'price_category') == 'cheap' }}"
      - condition: time
        after: "20:00:00"
        before: "06:00:00"
    action:
      - service: notify.mobile_app
        data:
          title: "Cheap Electricity"
          message: "Great time to run the dishwasher! Price is in bottom 33% ({{ states('sensor.tibber_48h_price_comparison') }}th percentile)"
```

### Automation: Alert on Expensive Price vs Baseline

```yaml
automation:
  - alias: "Alert when price significantly above normal"
    trigger:
      - platform: state
        entity_id: sensor.tibber_30d_baseline_comparison
    condition:
      - condition: template
        value_template: "{{ state_attr('sensor.tibber_30d_baseline_comparison', 'difference_percent') | float > 25 }}"
    action:
      - service: notify.mobile_app
        data:
          title: "High Electricity Price Alert"
          message: "Current price is {{ states('sensor.tibber_30d_baseline_comparison') }} above the 30-day average for this hour!"
```

### Automation: Use Tibber API Price Level

```yaml
automation:
  - alias: "Turn on heater when electricity is very cheap"
    trigger:
      - platform: state
        entity_id: sensor.tibber_api_price_level
        to: "VERY_CHEAP"
    action:
      - service: climate.set_temperature
        target:
          entity_id: climate.living_room_heater
        data:
          temperature: 22
```

## Troubleshooting

### Invalid API Token Error
- Verify your API token is correct
- Ensure your Tibber account has an active subscription
- Check that you copied the entire token without extra spaces

### No Data Available
- Verify you have an active Tibber subscription with price data
- Check Home Assistant logs for error messages
- Ensure your home is properly configured in the Tibber app

### 48-Hour Comparison Shows "yesterday+today"
- This is normal before ~13:00 when tomorrow's prices aren't published yet
- After 13:00, it should automatically switch to "today+tomorrow"
- The sensor adapts to provide the best 48-hour comparison window

### 30-Day Baseline Shows No Data
- The 30-day baseline requires historical price data from Home Assistant recorder
- It will start working immediately but accuracy improves over time
- After 30 days of operation, you'll have a full baseline
- Check that the recorder integration is enabled and working

### Sensors Not Updating
- Check Home Assistant logs for errors
- Verify internet connectivity to Tibber API
- Integration updates hourly - wait for next update cycle
- Try reloading the integration from Settings → Devices & Services

## Development

See [CLAUDE.md](CLAUDE.md) for development guidelines and workflow.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
