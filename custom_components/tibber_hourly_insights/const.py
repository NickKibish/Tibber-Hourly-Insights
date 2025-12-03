"""Constants for the Tibber Hourly Insights integration."""
from datetime import timedelta

# Domain
DOMAIN = "tibber_hourly_insights"

# Configuration keys
CONF_API_TOKEN = "api_token"

# Weighted consensus configuration
CONF_WEIGHT_TIBBER = "weight_tibber"
CONF_WEIGHT_48H = "weight_48h"
CONF_WEIGHT_30D = "weight_30d"
CONF_ENABLE_30D_BASELINE = "enable_30d_baseline"

# Tibber enum to percentage mapping (user configurable)
CONF_VERY_CHEAP_PCT = "very_cheap_pct"
CONF_CHEAP_PCT = "cheap_pct"
CONF_NORMAL_PCT = "normal_pct"
CONF_EXPENSIVE_PCT = "expensive_pct"
CONF_VERY_EXPENSIVE_PCT = "very_expensive_pct"

# Grid fee configuration (Nettleie)
CONF_ENABLE_GRID_FEE = "enable_grid_fee"
CONF_GRID_FEE_DAY = "grid_fee_day"
CONF_GRID_FEE_NIGHT = "grid_fee_night"
CONF_DAY_START_HOUR = "day_start_hour"
CONF_DAY_END_HOUR = "day_end_hour"

# Subsidy configuration (Strømstøtte)
CONF_ENABLE_SUBSIDY = "enable_subsidy"
CONF_SUBSIDY_THRESHOLD = "subsidy_threshold"
CONF_SUBSIDY_PERCENTAGE = "subsidy_percentage"

# Defaults for weights
DEFAULT_WEIGHT_TIBBER = 0.5
DEFAULT_WEIGHT_48H = 0.3
DEFAULT_WEIGHT_30D = 0.2
DEFAULT_ENABLE_30D_BASELINE = False  # Disabled by default for performance

# Default Tibber enum mapping (Symmetric)
DEFAULT_VERY_CHEAP_PCT = -40.0
DEFAULT_CHEAP_PCT = -20.0
DEFAULT_NORMAL_PCT = 0.0
DEFAULT_EXPENSIVE_PCT = 20.0
DEFAULT_VERY_EXPENSIVE_PCT = 40.0

# Default grid fee values (Norwegian standard)
DEFAULT_ENABLE_GRID_FEE = False
DEFAULT_GRID_FEE_DAY = 0.444  # NOK/kWh (06:00-22:00)
DEFAULT_GRID_FEE_NIGHT = 0.305  # NOK/kWh (22:00-06:00)
DEFAULT_DAY_START_HOUR = 6
DEFAULT_DAY_END_HOUR = 22

# Default subsidy values (Norwegian strømstøtte)
DEFAULT_ENABLE_SUBSIDY = False
DEFAULT_SUBSIDY_THRESHOLD = 0.9375  # NOK/kWh (93.75 øre/kWh)
DEFAULT_SUBSIDY_PERCENTAGE = 90.0  # Government covers 90% above threshold

# Update interval
UPDATE_INTERVAL = timedelta(hours=1)

# Entry data keys
ENTRY_DATA_COORDINATOR = "coordinator"

# Sensor constants
ATTR_CURRENCY = "currency"
ATTR_PRICE_LEVEL = "price_level"

# 48-hour comparison attributes
ATTR_PRICE_CATEGORY = "price_category"
ATTR_PERCENTILE = "percentile"
ATTR_MIN_PRICE_48H = "min_price_48h"
ATTR_MAX_PRICE_48H = "max_price_48h"
ATTR_AVG_PRICE_48H = "avg_price_48h"
ATTR_PCT_VS_AVERAGE_48H = "pct_vs_average_48h"
ATTR_DATA_SOURCE = "data_source"

# 30-day baseline attributes
ATTR_BASELINE_PRICE = "baseline_price"
ATTR_COMPARISON = "comparison"
ATTR_DIFFERENCE_PERCENT = "difference_percent"
ATTR_SAMPLE_COUNT = "sample_count"

# Weighted consensus attributes
ATTR_TIBBER_CONTRIBUTION = "tibber_contribution"
ATTR_48H_CONTRIBUTION = "48h_contribution"
ATTR_30D_CONTRIBUTION = "30d_contribution"
ATTR_WEIGHTS_USED = "weights_used"
ATTR_AVAILABLE_INPUTS = "available_inputs"
ATTR_SCORE_DESCRIPTION = "score_description"

# Price adjustment attributes
ATTR_RAW_SPOT_PRICE = "raw_spot_price"
ATTR_SUBSIDY_AMOUNT = "subsidy_amount"
ATTR_GRID_FEE = "grid_fee"
ATTR_ADJUSTED_PRICE = "adjusted_price"

# Price category thresholds (percentiles)
PRICE_CATEGORY_CHEAP_THRESHOLD = 33
PRICE_CATEGORY_EXPENSIVE_THRESHOLD = 66

# Tibber API
TIBBER_API_URL = "https://api.tibber.com/v1-beta/gql"
TIBBER_USER_AGENT = "Tibber-Hourly-Insights/0.2.0"

# Official Tibber integration entity
TIBBER_PRICE_ENTITY = "sensor.home_electricity_price"
