#Indicators.py -

import pandas_ta as ta

def add_indicators(df):
    """Add RSI, MACD, SMA20, SMA50 to a DataFrame with OHLCV."""
    df = df.copy()
    df["RSI"] = ta.rsi(df["Close"], length=14)
    macd = ta.macd(df["Close"], fast=12, slow=26, signal=9)
    df["MACD"] = macd["MACD_12_26_9"]
    df["Signal"] = macd["MACDs_12_26_9"]
    df["SMA20"] = ta.sma(df["Close"], length=20)
    df["SMA50"] = ta.sma(df["Close"], length=50)
    return df