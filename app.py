#app.py--
import streamlit as st
st.cache_data.clear()
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from shareholding import display_shareholding_dashboard
from indicators import add_indicators
from ml_model import predict_future
from fundamentals import get_fundamentals, fundamental_score
from news import display_stock_news
# from shareholding import display_shareholding_dashboard  # <--- Already imported above

# ========== PAGE SETUP ==========
st.set_page_config(page_title="AI Swing Trade Analyzer Pro", layout="wide")
st.title("📈 AI Swing Trade Analyzer Pro")


stock_input = st.text_input("Enter Stock Symbol (e.g., RELIANCE, TCS)", "RELIANCE").upper().strip()

if "analyzed" not in st.session_state:
    st.session_state.analyzed = False

# ========== HELPER: FORMAT CRORE ==========
def format_crore(value):
    if value is None or value == "N/A":
        return "N/A"
    crore = value / 1e7
    return f"₹ {crore:,.2f} CR"

# ========== HELPER: FETCH DATA ==========
@st.cache_data(show_spinner=False)
def fetch_data(symbol):
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        ticker = symbol + ".NS"
    else:
        ticker = symbol
    stock = yf.Ticker(ticker)
    try:
        data = stock.history(period="1y")
        if data.empty:
            return symbol, None
        return ticker, data
    except:
        return symbol, None

def generate_trade_signal(price, rsi, macd, signal, sma20, sma50, prediction):
    reasons = []
    bull = 0
    bear = 0

    if sma20 > sma50:
        bull += 1
        reasons.append("Trend bullish (20-day SMA > 50-Day SMA)")
    else:
        bear += 1
        reasons.append("Trend bearish (20-day SMA < 50-Day SMA)")

    if rsi < 30:
        bull += 1
        reasons.append("RSI oversold (<30)")
    elif rsi > 70:
        bear += 1
        reasons.append("RSI overbought (>70)")
    else:
        reasons.append("RSI neutral (30-70)")

    if macd > signal:
        bull += 1
        reasons.append("MACD above signal")
    else:
        bear += 1
        reasons.append("MACD below signal")

    if "Bullish" in prediction:
        bull += 1
        reasons.append("20‑day forecast: Bullish")
    else:
        bear += 1
        reasons.append("20‑day forecast: Bearish")

    if bull > bear:
        rec = "📈 TRADE SIGNAL: BUY / HOLD"
    elif bear > bull:
        rec = "📉 TRADE SIGNAL: SELL / AVOID"
    else:
        rec = "⚖️ NEUTRAL"

    return {"recommendation": rec, "explanation": reasons}

# ========== ANALYZE BUTTON ==========
if st.button("🔍 Analyze Stock"):
    st.session_state.analyzed = True

if st.session_state.analyzed:
    with st.spinner("Fetching & analyzing..."):
        ticker_name, raw_data = fetch_data(stock_input)

    if raw_data is None or raw_data.empty:
        st.error(f"No data found for '{stock_input}'. Check symbol.")
        st.stop()

    # Clean
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if isinstance(raw_data[col], pd.DataFrame):
            raw_data[col] = raw_data[col].iloc[:, 0]
        raw_data[col] = pd.to_numeric(raw_data[col], errors="coerce")
    raw_data.dropna(inplace=True)

    # Indicators
    data = add_indicators(raw_data)
    latest = data.iloc[-1]

    price = float(latest["Close"])
    rsi_val = float(latest["RSI"])
    macd_val = float(latest["MACD"])
    sig_val = float(latest["Signal"])
    sma20 = float(latest["SMA20"])
    sma50 = float(latest["SMA50"])

    prediction = predict_future(data)
    fundamentals = get_fundamentals(stock_input)
    analysis = generate_trade_signal(price, rsi_val, macd_val, sig_val, sma20, sma50, prediction)

    # ---- METRICS ----
    
    st.subheader(f"📊 {ticker_name.replace('.NS','').replace('.BO','').upper()}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Price", f"₹ {price:.2f}")
    c2.metric("RSI:(Relative strength Index)", f"{rsi_val:.1f}")
    c3.metric("MACD:(Moving Average Convergence Divergence)", f"{macd_val:.2f}")
    c4.metric("Trend", "Bullish 📈" if sma20 > sma50 else "Bearish 📉")

    st.markdown("---")
    st.success(analysis["recommendation"])
    st.write("### 🔎 Reasoning")
    for r in analysis["explanation"]:
        st.write("✅", r)
    st.markdown("---")

    # ========== NEW: SHAREHOLDING DASHBOARD (Screener.in based) ==========
    # st.header("🏢 Ownership Pattern (MarketSmithIndia Style)")
    # display_shareholding_dashboard(stock_input)
    clean_symbol = stock_input.replace(".NS", "").replace(".BO", "").strip()
    display_shareholding_dashboard(clean_symbol)
    st.markdown("---")
    # ====================================================================

    # ---- TABS ----
    # tab_chart, tab_data, tab_funda = st.tabs(["📈 Chart", "📋 Raw Data", "📊 Fundamentals"])
    tab_chart, tab_data, tab_funda, tab_news = st.tabs([
    "📈 Chart",
    "📋 Raw Data",
    "📊 Fundamentals",
    "📰 News"
])

    with tab_chart:
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                            vertical_spacing=0.03,
                            row_heights=[0.6, 0.2, 0.2])
        fig.add_trace(go.Candlestick(x=data.index, open=data["Open"], high=data["High"],
                                     low=data["Low"], close=data["Close"], name="Price"), row=1, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=data["SMA20"], name="SMA20", line=dict(color="blue")), row=1, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=data["SMA50"], name="SMA50", line=dict(color="orange")), row=1, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=data["RSI"], name="RSI", line=dict(color="purple")), row=2, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=data["MACD"], name="MACD", line=dict(color="green")), row=3, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=data["Signal"], name="Signal", line=dict(color="red")), row=3, col=1)
        fig.update_layout(height=800, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

    with tab_data:
        st.subheader("🔍 Raw Data Explorer")
        min_date = data.index.min().date()
        max_date = data.index.max().date()
        date_range = st.date_input("Select Date Range", value=(min_date, max_date),
                                   min_value=min_date, max_value=max_date)
        if len(date_range) == 2:
            start_date, end_date = date_range
            mask = (data.index.date >= start_date) & (data.index.date <= end_date)
            filtered = data.loc[mask]
        else:
            filtered = data

        all_columns = ["Open", "High", "Low", "Close", "Volume",
                       "RSI", "MACD", "Signal", "SMA20", "SMA50"]
        selected_columns = st.multiselect("Select columns to view", all_columns,
                                          default=["Open", "High", "RSI", "Close"])
        display_df = filtered[selected_columns] if selected_columns else filtered
        st.dataframe(display_df)

    with tab_funda:
        if fundamentals:
            # ---- Fundamental Score ----
            score, score_text, score_color = fundamental_score(fundamentals)
            st.subheader("🏢 Company Health Card")
            st.markdown(f"### Fundamental Score: <span style='color:{score_color}; font-size:28px'>{score}</span> / 100", unsafe_allow_html=True)
            st.markdown(f"**Rating:** <span style='color:{score_color}; font-size:20px'>{score_text}</span>", unsafe_allow_html=True)
            st.markdown("---")

            # ---- Key Ratios ----
            colf1, colf2, colf3 = st.columns(3)

            def color_metric(val, good, bad=None):
                if val is None or val == "N/A":
                    return "gray"
                if good[0] <= val <= good[1]:
                    return "green"
                if bad and bad[0] <= val <= bad[1]:
                    return "red"
                return "orange"

            roe_c = color_metric(fundamentals["ROE"], (15,100), (-100,0))
            roce_c = color_metric(fundamentals["ROCE"], (15,100), (-100,0))
            de_c = color_metric(fundamentals["Debt/Equity"], (0,0.5), (1,10))
            opm_c = color_metric(fundamentals["OPM"], (15,100), (-100,5))

            with colf1:
                st.markdown(f"**ROE(Return on Equity):** <span style='color:{roe_c}'>{fundamentals['ROE']:.1f}%</span>" if isinstance(fundamentals['ROE'], float) else f"**ROE(Return on Equity):** {fundamentals['ROE']}", unsafe_allow_html=True)
                st.markdown(f"**ROCE(Return on Capital Employed):** <span style='color:{roce_c}'>{fundamentals['ROCE']:.1f}%</span>" if isinstance(fundamentals['ROCE'], float) else f"**ROCE(Return on Capital Employed):** {fundamentals['ROCE']}", unsafe_allow_html=True)
            with colf2:
                st.markdown(f"**Debt/Equity:** <span style='color:{de_c}'>{fundamentals['Debt/Equity']:.2f}</span>" if isinstance(fundamentals['Debt/Equity'], float) else f"**Debt/Equity:** {fundamentals['Debt/Equity']}", unsafe_allow_html=True)
                st.markdown(f"**OPM(Operating Profit Margin):** <span style='color:{opm_c}'>{fundamentals['OPM']:.1f}%</span>" if isinstance(fundamentals['OPM'], float) else f"**OPM(Operating Profit Margin):** {fundamentals['OPM']}", unsafe_allow_html=True)
            with colf3:
                st.metric("Market Cap", format_crore(fundamentals["Market Cap"]))
                pe_val = fundamentals.get("PE Ratio", "N/A")
                pe_display = f"{pe_val:.2f}" if isinstance(pe_val, (int, float)) else pe_val
                st.metric("P/E Ratio(Price to Earnings Ratio)", pe_display)
                st.metric("EPS(Earnings Per Share)", fundamentals["EPS"])

            # ---- Growth ----
            st.markdown("---")
            st.subheader("📈 Growth (YoY)")
            gcol1, gcol2 = st.columns(2)
            rev_g = fundamentals.get("Revenue Growth")
            prof_g = fundamentals.get("Profit Growth")
            gcol1.metric("Revenue Growth", f"{rev_g:.1f}%" if isinstance(rev_g, float) else "N/A")
            gcol2.metric("Profit Growth", f"{prof_g:.1f}%" if isinstance(prof_g, float) else "N/A")

            # NOTE: Old shareholding section REMOVED - replaced by screener.in dashboard above
        else:
            st.warning("Fundamental data not available for this stock.")
    with tab_news:    
        display_stock_news(clean_symbol)