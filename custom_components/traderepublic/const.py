"""Constants for the Trade Republic integration."""

import logging

DOMAIN = "traderepublic"
LOGGER = logging.getLogger(__package__)

# Config Keys
CONF_PHONE_NUMBER = "phone_number"
CONF_PIN = "pin"
CONF_SESSION_TOKEN = "session_token"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_INTEREST_RATE = "interest_rate"

# Default intervals
DEFAULT_SCAN_INTERVAL = 3600  # seconds (1 hour)
MIN_SCAN_INTERVAL = 900  # seconds (15 minutes)
DEFAULT_INTEREST_RATE = 2.25  # percent

# API WebSocket URL
TR_WS_URL = "wss://api.traderepublic.com"

# Attribute Constants
ATTR_PORTFOLIO_VALUE = "portfolio_value"
ATTR_AVAILABLE_CASH = "available_cash"
ATTR_INVESTED_CAPITAL = "invested_capital"
ATTR_TOTAL_PROFIT = "total_profit"
ATTR_TOTAL_PROFIT_PERCENT = "total_profit_percent"
ATTR_EXEMPTION_TOTAL = "exemption_total"
ATTR_EXEMPTION_USED = "exemption_used"
ATTR_SAVINGS_PLANS_COUNT = "savings_plans_count"
