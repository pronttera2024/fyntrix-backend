# Index universe definitions for always-on WebSocket subscriptions
#
# These lists define the core NSE universes (by trading symbol) that we want
# to keep subscribed on the Zerodha WebSocket at all times so that
# get_latest_tick() has a rich cache even before any UI component explicitly
# subscribes. They are intentionally static and can be updated whenever index
# constituents change.

NIFTY50_SYMBOLS = [
    "RELIANCE",
    "HDFCBANK",
    "ICICIBANK",
    "INFY",
    "TCS",
    "ITC",
    "LT",
    "SBIN",
    "AXISBANK",
    "HINDUNILVR",
    "KOTAKBANK",
    "BHARTIARTL",
    "HCLTECH",
    "ASIANPAINT",
    "MARUTI",
    "SUNPHARMA",
    "ULTRACEMCO",
    "BAJFINANCE",
    "BAJAJFINSV",
    "NESTLEIND",
    "TITAN",
    "WIPRO",
    "POWERGRID",
    "ONGC",
    "COALINDIA",
    "TATACONSUM",
    "TATAMOTORS",
    "TATASTEEL",
    "GRASIM",
    "HEROMOTOCO",
    "BPCL",
    "BRITANNIA",
    "CIPLA",
    "DIVISLAB",
    "DRREDDY",
    "EICHERMOT",
    "HDFCLIFE",
    "HINDALCO",
    "JSWSTEEL",
    "NTPC",
    "SBILIFE",
    "SHREECEM",
    "TECHM",
    "UPL",
    "ADANIPORTS",
    "BAJAJ-AUTO",
    "INDUSINDBK",
    "M&M",
    "TATAPOWER",
]

BANKNIFTY_SYMBOLS = [
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "AXISBANK",
    "KOTAKBANK",
    "INDUSINDBK",
    "BANDHANBNK",
    "FEDERALBNK",
    "IDFCFIRSTB",
    "PNB",
    "RBLBANK",
    "AUBANK",
]

# Core always-on subscription set (deduplicated)
ALWAYS_ON_WS_SYMBOLS = sorted({*NIFTY50_SYMBOLS, *BANKNIFTY_SYMBOLS})
