#fundamentals.py-
import yfinance as yf
import pandas as pd
import json
import os
import re
import requests
from bs4 import BeautifulSoup

def get_nse_holdings(symbol):
    """
    holdings.json फ़ाइल से शेयरहोल्डिंग डेटा पढ़ें।
    symbol बिना .NS के, जैसे 'TCS'
    """
    try:
        # फ़ाइल का पूरा पथ (fundamentals.py के समान फ़ोल्डर में)
        json_path = os.path.join(os.path.dirname(__file__), "holdings.json")
        if not os.path.exists(json_path):
            return {}
        with open(json_path, "r") as f:
            data = json.load(f)
        return data.get(symbol.upper(), {})
    except Exception:
        return {}

# ========== फंडामेंटल डेटा (yfinance + JSON) ==========
def get_fundamentals(symbol):
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        ticker = symbol + ".NS"
    else:
        ticker = symbol

    fundamentals = {
        "Market Cap": "N/A", "PE Ratio": "N/A", "EPS": "N/A",
        "Book Value": "N/A", "Dividend Yield": "N/A",
        "ROE": None, "ROCE": None, "Debt/Equity": None, "OPM": None,
        "Revenue Growth": None, "Profit Growth": None,
        "Promoter Holding": None, "Institutional Holding": None,
        "Public Holding": None, "Shares Outstanding": None,
        "FII/FPI": None
    }

    try:
        stk = yf.Ticker(ticker)
        info = stk.info
        bs = stk.balance_sheet
        is_ = stk.financials
        q_is = stk.quarterly_financials

        fundamentals["Market Cap"] = info.get("marketCap", "N/A")
        fundamentals["PE Ratio"] = info.get("trailingPE", "N/A")
        fundamentals["EPS"] = info.get("trailingEps", "N/A")
        fundamentals["Book Value"] = info.get("bookValue", "N/A")
        fundamentals["Dividend Yield"] = info.get("dividendYield", "N/A")
        fundamentals["Shares Outstanding"] = info.get("sharesOutstanding", None)

        # yfinance से फ़ॉलबैक (ज़्यादातर N/A)
        fundamentals["Promoter Holding"] = info.get("heldPercentInsiders") or info.get("insiderPercentHeld")
        fundamentals["Institutional Holding"] = info.get("heldPercentInstitutions") or info.get("institutionPercentHeld")
        fundamentals["Public Holding"] = info.get("heldPercentPublic")
        fundamentals["FII/FPI"] = info.get("fundOwnership")

        # फाइनेंशियल रेश्यो
        if not bs.empty and not is_.empty:
            try:
                total_equity = bs.loc["Total Equity Gross Minority Interest"].iloc[0]
                net_income = is_.loc["Net Income"].iloc[0]
                total_debt = bs.loc["Total Debt"].iloc[0] if "Total Debt" in bs.index else None
                total_assets = bs.loc["Total Assets"].iloc[0]
                current_liab = bs.loc["Total Current Liabilities"].iloc[0] if "Total Current Liabilities" in bs.index else None
                ebit = is_.loc["EBIT"].iloc[0] if "EBIT" in is_.index else None
                revenue = is_.loc["Total Revenue"].iloc[0]

                if total_equity and total_equity != 0:
                    fundamentals["ROE"] = (net_income / total_equity) * 100
                if ebit and total_assets and current_liab:
                    capital_employed = total_assets - current_liab
                    if capital_employed != 0:
                        fundamentals["ROCE"] = (ebit / capital_employed) * 100
                if total_debt is not None and total_equity and total_equity != 0:
                    fundamentals["Debt/Equity"] = total_debt / total_equity
                if ebit and revenue and revenue != 0:
                    fundamentals["OPM"] = (ebit / revenue) * 100
            except:
                pass

        # ग्रोथ
        rev_series = is_.loc["Total Revenue"] if "Total Revenue" in is_.index else None
        profit_series = is_.loc["Net Income"] if "Net Income" in is_.index else None
        if rev_series is not None and len(rev_series) >= 2:
            fundamentals["Revenue Growth"] = ((rev_series.iloc[0] - rev_series.iloc[1]) / abs(rev_series.iloc[1])) * 100
        elif not q_is.empty and "Total Revenue" in q_is.index and q_is.shape[1] >= 5:
            q_rev = q_is.loc["Total Revenue"]
            if len(q_rev) >= 5:
                fundamentals["Revenue Growth"] = ((q_rev.iloc[0] - q_rev.iloc[4]) / abs(q_rev.iloc[4])) * 100

        if profit_series is not None and len(profit_series) >= 2:
            fundamentals["Profit Growth"] = ((profit_series.iloc[0] - profit_series.iloc[1]) / abs(profit_series.iloc[1])) * 100
        elif not q_is.empty and "Net Income" in q_is.index and q_is.shape[1] >= 5:
            q_profit = q_is.loc["Net Income"]
            if len(q_profit) >= 5:
                fundamentals["Profit Growth"] = ((q_profit.iloc[0] - q_profit.iloc[4]) / abs(q_profit.iloc[4])) * 100

        # 🔥 JSON से सटीक शेयरहोल्डिंग ओवरराइट करें
        nse_hold = get_nse_holdings(symbol.replace(".NS", "").replace(".BO", ""))
        if nse_hold:
            fundamentals.update(nse_hold)

    except Exception:
        pass

    return fundamentals

# ========== फंडामेंटल स्कोर ==========
def fundamental_score(fundamentals):
    if not fundamentals:
        return None, "Data Unavailable", "gray"

    weights = {
        "ROE": 0.20,
        "ROCE": 0.20,
        "Debt/Equity": 0.15,
        "Revenue Growth": 0.15,
        "Profit Growth": 0.15,
        "OPM": 0.15
    }

    score = 0
    for metric, weight in weights.items():
        val = fundamentals.get(metric)
        if val is None or val == "N/A":
            continue

        if metric == "ROE":
            s = min(max((val - 0) / 20 * 100, 0), 100)
        elif metric == "ROCE":
            s = min(max((val - 0) / 20 * 100, 0), 100)
        elif metric == "Debt/Equity":
            if val <= 0.5:
                s = 100
            elif val >= 2:
                s = 0
            else:
                s = 100 - ((val - 0.5) / 1.5) * 100
        elif metric == "Revenue Growth":
            s = min(max(val, 0) / 20 * 100, 100)
        elif metric == "Profit Growth":
            s = min(max(val, 0) / 20 * 100, 100)
        elif metric == "OPM":
            s = min(max((val - 5) / 20 * 100, 0), 100)
        else:
            s = 50
        score += s * weight

    score = round(score, 1)

    if score >= 80:
        interp, color = "Strong Buy 🟢", "green"
    elif score >= 60:
        interp, color = "Good 🟡", "gold"
    elif score >= 40:
        interp, color = "Average 🟠", "orange"
    else:
        interp, color = "Weak 🔴", "red"

    return score, interp, color
