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
CONF_AUTH_MODE = "auth_mode"
CONF_ADDON_HOST = "addon_host"
CONF_ADDON_PORT = "addon_port"

# Auth Modes
AUTH_MODE_ADDON = "addon"
AUTH_MODE_MANUAL = "manual"

# Default intervals
DEFAULT_SCAN_INTERVAL = 900  # seconds (15 minutes - helps keep session alive)
MIN_SCAN_INTERVAL = 600  # seconds (10 minutes)
DEFAULT_INTEREST_RATE = 2.25  # percent
DEFAULT_ADDON_HOST = "127.0.0.1"
DEFAULT_ADDON_PORT = 8095

ADDON_CONTAINER_HOSTS = [
    "a0d7b954-traderepublic-edge",
    "a0d7b954-traderepublic",
    "traderepublic-edge",
    "traderepublic",
    "localhost",
    "127.0.0.1",
]



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
