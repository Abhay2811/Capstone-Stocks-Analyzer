#Ml_model.py-


import pickle
import pandas as pd
import numpy as np
import pandas_ta as ta

# ---------- Rule‑based backup ----------
def _rule_based_predict(data):
    latest = data.iloc[-1]
    close = latest["Close"]
    sma20 = latest["SMA20"]
    sma50 = latest["SMA50"]
    rsi = latest["RSI"]
    macd = latest["MACD"]
    signal = latest["Signal"]

    score = 0
    if close > sma20 > sma50:
        score += 2
    elif close > sma50:
        score += 1
    if 40 <= rsi <= 70 or (30 <= rsi < 40):
        score += 1
    if macd > signal:
        score += 1

    if score >= 3:
        return "Bullish 📈 (Rule‑based)"
    elif score <= 1:
        return "Bearish 📉 (Rule‑based)"
    else:
        return "Neutral ⚖️ (Rule‑based)"

# ---------- ML prediction ----------
def _ml_predict(data):
    with open('model.pkl', 'rb') as f:
        saved = pickle.load(f)
    model = saved['model']
    feature_cols = saved['features']

    df = data.copy()
    df['Return'] = df['Close'].pct_change()
    df['SMA20'] = df['Close'].rolling(20).mean()
    df['SMA50'] = df['Close'].rolling(50).mean()
    df['RSI'] = ta.rsi(df['Close'], length=14)
    macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
    df['MACD'] = macd['MACD_12_26_9']
    df['MACD_Signal'] = macd['MACDs_12_26_9']
    df['Volume_Change'] = df['Volume'].pct_change()
    df['Close_to_SMA20'] = df['Close'] / df['SMA20'] - 1
    df['Close_to_SMA50'] = df['Close'] / df['SMA50'] - 1
    df['Volatility'] = df['Return'].rolling(20).std()

    latest = df.iloc[-1:][feature_cols].fillna(0)
    proba = model.predict_proba(latest)[0]
    pred = model.predict(latest)[0]
    conf = proba[1] if pred == 1 else proba[0]

    direction = "Bullish 📈" if pred == 1 else "Bearish 📉"
    return f"{direction} (ML confidence: {conf:.1%})"

# ---------- Main function ----------
def predict_future(data):
    try:
        if len(data) < 100:   # not enough data for ML
            raise ValueError("Insufficient data")
        return _ml_predict(data)
    except Exception:
        return _rule_based_predict(data)