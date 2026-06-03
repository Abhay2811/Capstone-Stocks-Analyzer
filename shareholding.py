import re
import time
import subprocess
import sys
from io import StringIO
from urllib.parse import quote_plus

import numpy as np
import pandas as pd
import requests
import streamlit as st
from playwright.sync_api import sync_playwright

SUMMARY_LABELS = {
    "promoter": ["promoter", "promoters"],
    "fii": ["fii", "fpi", "foreign institutional"],
    "dii": ["dii", "domestic institutional"],
    "government": ["government", "govt", "president of india"],
    "public": ["public", "others", "retail"],
}

SUMMARY_WORDS = [
    "promoter", "promoters", "fii", "fpi", "dii", "government",
    "govt", "public", "others", "no. of shareholders", "total",
    "total shareholding", "grand total"
]

BAD_HOLDER_WORDS = [
    "sales", "reserves", "fixed assets", "expenses", "borrowings",
    "cash from operating", "other assets", "other liabilities", "cwip",
    "total assets", "net profit", "operating profit", "revenue", "liabilities",
    "equity capital", "cash equivalents", "trade receivables", "inventories",
    "share capital", "balance sheet", "profit loss", "cash flow",
    "promoter and promoter group", "promoters and promoter group",
    "pledged", "locked",
    "individual share capital", "foreign portfolio investors category",
    "clearing members"
]

AGGREGATE_HOLDER_NAMES = {
    "any other",
    "any other (specify)",
    "any others",
    "banks",
    "bodies corporate",
    "foreign portfolio investors category i",
    "foreign portfolio investors category ii",
    "insurance companies",
    "mutual funds",
    "non resident indians",
    "non resident indians (nris)",
    "other financial institutions",
    "trusts",
    "resident individuals",
    "hindu undivided family",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
    "Referer": "https://www.screener.in/",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

@st.cache_resource(show_spinner=False)
def ensure_playwright_chromium():
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=False,
        timeout=180,
    )

def clean_text(value):

def clean_text(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def parse_percent(value):
    if value is None:
        return np.nan

    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value) if not pd.isna(value) else np.nan

    text = clean_text(value)
    if not text or text.lower() in {"nan", "none", "-", "n/a", "--"}:
        return np.nan

    match = re.search(r"-?\d+(?:,\d+)*(?:\.\d+)?", text.replace("%", ""))
    if not match:
        return np.nan

    return float(match.group(0).replace(",", ""))


def format_percent(value):
    num = parse_percent(value)
    return "N/A" if pd.isna(num) else f"{num:.2f}%"


def normalize_columns(df):
    df = df.copy()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            " ".join(clean_text(x) for x in col if clean_text(x))
            for col in df.columns
        ]
    else:
        df.columns = [clean_text(col) for col in df.columns]

    return df


def is_summary_row(name):
    text = clean_text(name).lower()
    if not text:
        return True
    return any(word in text for word in SUMMARY_WORDS)


def is_valid_holder_name(name):
    text = clean_text(name).lower()
    text = re.sub(r"\s+", " ", text).strip(" -:|")

    if len(text) < 3:
        return False

    if text in AGGREGATE_HOLDER_NAMES:
        return False

    if any(word in text for word in BAD_HOLDER_WORDS):
        return False

    if re.fullmatch(r"[\d\W_]+", text):
        return False

    if re.search(r"\b(jun|sep|dec|mar)\s+\d{4}\b", text):
        return False

    return True


def fetch_html(url):
    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        session.get("https://www.screener.in/", timeout=15)
    except Exception:
        pass

    response = session.get(url, timeout=25)
    response.raise_for_status()
    return response.text


def find_shareholding_table(tables):
    for table in tables:
        if table is None or table.empty or len(table.columns) < 2:
            continue

        table = normalize_columns(table)
        first_col = table.iloc[:, 0].map(clean_text).str.lower()

        has_promoter = first_col.str.contains("promoter", na=False).any()
        has_fii = first_col.str.contains("fii|fpi", regex=True, na=False).any()
        has_dii = first_col.str.contains("dii", na=False).any()
        has_public = first_col.str.contains("public|others", regex=True, na=False).any()

        if has_promoter and has_fii and has_dii and has_public:
            return table

    return None


def build_quarterly_data(table):
    table = normalize_columns(table)
    quarters = [clean_text(col) for col in table.columns[1:]]
    data = {"Quarter": quarters}

    row_map = {}

    for idx, label in enumerate(table.iloc[:, 0].tolist()):
        label_text = clean_text(label).lower()

        for key, words in SUMMARY_LABELS.items():
            if key not in row_map and any(word in label_text for word in words):
                row_map[key] = idx

    columns = {
        "promoter": "Promoter (%)",
        "fii": "FII/FPI (%)",
        "dii": "DII (%)",
        "government": "Government (%)",
        "public": "Public (%)",
    }

    for key, col_name in columns.items():
        if key in row_map:
            data[col_name] = [
                format_percent(x) for x in table.iloc[row_map[key], 1:].tolist()
            ]

    return pd.DataFrame(data)


def latest_from_quarters(df):
    latest = {
        "promoter": "N/A",
        "fii": "N/A",
        "dii": "N/A",
        "government": "N/A",
        "public": "N/A",
    }

    if df is None or df.empty:
        return latest

    row = df.iloc[0]
    latest["promoter"] = row.get("Promoter (%)", "N/A")
    latest["fii"] = row.get("FII/FPI (%)", "N/A")
    latest["dii"] = row.get("DII (%)", "N/A")
    latest["government"] = row.get("Government (%)", "N/A")
    latest["public"] = row.get("Public (%)", "N/A")

    return latest


def pick_name_and_holding_columns(df):
    columns = list(df.columns)
    lower_cols = {col: clean_text(col).lower() for col in columns}

    name_candidates = [
        col for col in columns
        if any(word in lower_cols[col] for word in ["name", "shareholder", "holder"])
    ]

    holding_candidates = [
        col for col in columns
        if any(word in lower_cols[col] for word in ["holding", "%", "percent", "share"])
    ]

    if not name_candidates or not holding_candidates:
        return None, None

    name_col = name_candidates[0]
    best_holding_col = None
    best_count = 0

    for col in holding_candidates:
        if col == name_col:
            continue

        values = df[col].map(parse_percent)
        count = values.notna().sum()

        if count > best_count:
            best_count = count
            best_holding_col = col

    return name_col, best_holding_col


def finalize_major_shareholders(rows, limit=10):
    if not rows:
        return None

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["Holding (%)"])
    df = df[(df["Holding (%)"] > 0) & (df["Holding (%)"] <= 100)]
    df = df[df["Shareholder"].map(is_valid_holder_name)]
    df = df[~df["Shareholder"].map(is_summary_row)]
    df = df.drop_duplicates(subset=["Shareholder"], keep="first")

    if df.empty:
        return None

    df = df.sort_values("Holding (%)", ascending=False).head(limit)
    df["Holding (%)"] = df["Holding (%)"].map(lambda x: f"{x:.2f}%")

    return df.reset_index(drop=True)

def extract_major_shareholders_from_tables(tables, limit=10):
    for table in tables:
        if table is None or table.empty or len(table.columns) < 2:
            continue

        df = normalize_columns(table)
        name_col, holding_col = pick_name_and_holding_columns(df)

        if name_col is None or holding_col is None:
            continue

        rows = []

        for _, row in df.iterrows():
            name = clean_text(row[name_col])

            if not is_valid_holder_name(name) or is_summary_row(name):
                continue

            holding = parse_percent(row[holding_col])

            if pd.isna(holding) or holding <= 0 or holding > 100:
                continue

            rows.append({
                "Shareholder": name.title(),
                "Holding (%)": holding,
            })

        result = finalize_major_shareholders(rows, limit=limit)

        if result is not None and not result.empty:
            return result

    return None

# marketsmith fetch

def fetch_major_shareholders_from_marketsmithindia(symbol, limit=10):
    try:
        symbol = symbol.lower().replace(".ns", "").replace(".bo", "").strip()
        url = f"https://marketsmithindia.com/mstool/eval/{symbol}/evaluation.jsp#/"

        rows_data = []
        ensure_playwright_chromium()

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )

            page = browser.new_page(
                viewport={"width": 1366, "height": 768}
            )

            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(12000)

            page.wait_for_selector(".industryGroup.tableBorderCss", timeout=30000)

            sections = page.locator(".industryGroup.tableBorderCss")
            total = sections.count()

            for i in range(total):
                section = sections.nth(i)
                section_text = section.inner_text()

                if "Major Shareholders" in section_text:
                    rows = section.locator("table tr")
                    row_count = rows.count()

                    for r in range(row_count):
                        cells = rows.nth(r).locator("th, td")
                        cell_count = cells.count()

                        if cell_count >= 2:
                            investor_name = cells.nth(0).inner_text().strip()
                            holding_text = cells.nth(1).inner_text().strip()

                            if investor_name.lower() == "investor name":
                                continue

                            holding = parse_percent(holding_text)

                            if (
                                investor_name
                                and not pd.isna(holding)
                                and holding > 0
                                and holding <= 100
                            ):
                                rows_data.append({
                                    "Shareholder": investor_name.title(),
                                    "Holding (%)": holding,
                                })

                    break

            browser.close()

        return finalize_major_shareholders(rows_data, limit=limit)

    except Exception:
        return None
    
    
def fetch_major_shareholders_from_screener(symbol, limit=10):
    try:
        symbol = symbol.upper().replace(".NS", "").replace(".BO", "").strip()
        url = f"https://www.screener.in/company/{symbol}/"

        html = fetch_html(url)
        tables = pd.read_html(StringIO(html))

        return extract_major_shareholders_from_tables(tables, limit=limit)

    except Exception:
        return None


def find_moneycontrol_stock_code(symbol):
    try:
        symbol = symbol.upper().replace(".NS", "").replace(".BO", "").strip()

        search_url = (
            "https://www.moneycontrol.com/mccode/common/autosuggestion_solr.php"
            f"?query={quote_plus(symbol)}&type=1&format=json"
        )

        response = requests.get(search_url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        data = response.json()
        if not data:
            return None

        item = data[0]

        for key in ["sc_id", "id", "code"]:
            value = item.get(key)
            if value:
                return clean_text(value).upper()

        for key in ["link_src", "link", "url"]:
            link = item.get(key)
            if not link:
                continue

            parts = [p for p in clean_text(link).split("/") if p]
            if parts:
                return parts[-1].upper()

        return None

    except Exception:
        return None


def fetch_major_shareholders_from_moneycontrol(symbol, limit=10):
    try:
        symbol = symbol.upper().replace(".NS", "").replace(".BO", "").strip()
        mc_code = find_moneycontrol_stock_code(symbol)

        if not mc_code:
            return None

        urls = [
            f"https://m.moneycontrol.com/stock/{mc_code}/company-facts/shareholding-pattern",
            f"https://www.moneycontrol.com/company-facts/{mc_code}/shareholding-pattern",
        ]

        for url in urls:
            try:
                response = requests.get(url, headers=HEADERS, timeout=20)
                response.raise_for_status()

                tables = pd.read_html(StringIO(response.text))
                major_df = extract_major_shareholders_from_tables(tables, limit=limit)

                if major_df is not None and not major_df.empty:
                    return major_df

            except Exception:
                continue

        return None

    except Exception:
        return None


def fetch_major_shareholders_from_nse(symbol, limit=10):
    symbol = symbol.upper().replace(".NS", "").replace(".BO", "").strip()

    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        session.get(
            f"https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern?symbol={symbol}&tabIndex=equity",
            timeout=15,
        )

        api_url = f"https://www.nseindia.com/api/corporate-share-holdings?index=equities&symbol={symbol}"
        response = session.get(api_url, timeout=20)
        response.raise_for_status()

        filings = response.json()
        if not filings:
            return None

        latest = filings[0]
        xbrl_url = latest.get("xbrl")

        if not xbrl_url:
            return None

        possible_urls = [
            xbrl_url,
            xbrl_url.replace("/corporate/xbrl/", "/corporate/ixbrl/").replace(
                "_WEB.xml",
                "_iXBRL_WEB.html",
            ),
        ]

        for filing_url in possible_urls:
            try:
                html_response = session.get(filing_url, timeout=25)
                html_response.raise_for_status()

                tables = pd.read_html(StringIO(html_response.text))
                major_df = extract_major_shareholders_from_tables(tables, limit=limit)

                if major_df is not None and not major_df.empty:
                    return major_df

            except Exception:
                continue

        return None

    except Exception:
        return None


def fetch_major_shareholders(symbol, limit=10):
    sources = [
        ("marketsmithindia.com", fetch_major_shareholders_from_marketsmithindia),
        ("screener.in", fetch_major_shareholders_from_screener),
        ("moneycontrol.com", fetch_major_shareholders_from_moneycontrol),
        ("nseindia.com", fetch_major_shareholders_from_nse),
    ]

    for source_name, fetcher in sources:
        major_df = fetcher(symbol, limit=limit)

        if major_df is not None and not major_df.empty:
            return major_df, source_name

    return None, None

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_shareholding_data(symbol: str):
    symbol = symbol.upper().replace(".NS", "").replace(".BO", "").strip()

    quarterly_df = pd.DataFrame()
    latest = {
        "promoter": "N/A",
        "fii": "N/A",
        "dii": "N/A",
        "government": "N/A",
        "public": "N/A",
    }

    try:
        url = f"https://www.screener.in/company/{symbol}/"
        html = fetch_html(url)
        tables = pd.read_html(StringIO(html))

        shareholding_table = find_shareholding_table(tables)

        if shareholding_table is not None:
            quarterly_df = build_quarterly_data(shareholding_table)
            latest = latest_from_quarters(quarterly_df)

    except Exception:
        pass

    try:
        major_df, major_source = fetch_major_shareholders(symbol, limit=10)

        if major_df is not None and major_df.empty:
            major_df = None

    except Exception:
        major_df = None
        major_source = None

    return {
        "quarterly_data": quarterly_df,
        "latest": latest,
        "major_shareholders": major_df,
        "major_shareholders_source": major_source,
    }

def display_shareholding_dashboard(symbol: str):
    if not symbol:
        return

    symbol = symbol.upper().replace(".NS", "").replace(".BO", "").strip()

    st.markdown("---")
    st.header("🏢 Ownership Pattern")

    with st.spinner(f"Fetching data for {symbol}..."):
        data = fetch_shareholding_data(symbol)

    if not data:
        st.warning(f"Data not available for {symbol}")
        st.info(f"View manually: https://www.screener.in/company/{symbol}/")
        return

    if "error" in data:
        st.warning("Shareholding data could not be fetched right now.")
        st.code(data["error"])
        st.info(f"View manually: https://www.screener.in/company/{symbol}/#shareholding")
        return

    latest = data["latest"]
    show_government = latest.get("government") not in [None, "", "N/A"]

    cols = st.columns(5 if show_government else 4)

    cols[0].metric("🏢 Promoter", latest.get("promoter", "N/A"))
    cols[1].metric("🌍 FII/FPI", latest.get("fii", "N/A"))
    cols[2].metric("🏦 DII", latest.get("dii", "N/A"))

    if show_government:
        cols[3].metric("🏛️ Government", latest.get("government", "N/A"))
        cols[4].metric("👥 Public", latest.get("public", "N/A"))
    else:
        cols[3].metric("👥 Public", latest.get("public", "N/A"))

    st.subheader("📊 Quarterly Shareholding Pattern")
    st.dataframe(data["quarterly_data"], use_container_width=True)

    st.subheader("🏆 Major Shareholders")
    major_df = data["major_shareholders"]

    if isinstance(major_df, pd.DataFrame) and not major_df.empty:
        st.dataframe(major_df, use_container_width=True)

        csv = major_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Download CSV",
            csv,
            f"{symbol}_major_shareholders.csv",
            "text/csv",
        )
    else:
        st.warning(
            "Major shareholders names could not be fetched from Screener, Moneycontrol, or NSE right now."
        )

    major_source = data.get("major_shareholders_source") or "not available"

    st.caption(
        f"Ownership source: screener.in | Major shareholders source: {major_source} | "
        f"Last updated: {time.strftime('%Y-%m-%d')}"
    )
