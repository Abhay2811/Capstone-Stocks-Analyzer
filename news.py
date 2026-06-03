from datetime import datetime, timezone

import requests
import streamlit as st


NEWSDATA_API_KEY = "pub_a1b7f23a8ac34d6a8f470bad88662538"


def clean_symbol(symbol):
    return (
        symbol.upper()
        .replace(".NS", "")
        .replace(".NSE", "")
        .replace(".BO", "")
        .replace(".BSE", "")
        .strip()
    )


def parse_newsdata_date(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception:
            return None


def format_date(dt):
    if not dt:
        return "Latest"
    return dt.strftime("%d %b %Y, %I:%M %p")


def normalize_article(item):
    published_dt = parse_newsdata_date(item.get("pubDate"))

    return {
        "title": item.get("title") or "No title",
        "summary": item.get("description") or "",
        "link": item.get("link") or "",
        "source": item.get("source_name") or "NewsData.io",
        "published_dt": published_dt,
        "published": format_date(published_dt),
    }


@st.cache_data(ttl=900, show_spinner=False)
def fetch_stock_news(symbol, limit=30):
    clean_name = clean_symbol(symbol)
    search_query = f"{clean_name} stock"

    all_news = []
    seen_links = set()
    next_page = None

    while len(all_news) < limit:
        params = {
            "apikey": NEWSDATA_API_KEY,
            "q": search_query,
            "language": "en",
            "country": "in",
            "size": 10,
        }

        if next_page:
            params["page"] = next_page

        try:
            response = requests.get(
                "https://newsdata.io/api/1/market",
                params=params,
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            break

        if data.get("status") != "success":
            break

        articles = data.get("results", [])

        if not articles:
            break

        for item in articles:
            article = normalize_article(item)

            if not article["link"] or article["link"] in seen_links:
                continue

            seen_links.add(article["link"])
            all_news.append(article)

            if len(all_news) >= limit:
                break

        next_page = data.get("nextPage")

        if not next_page:
            break

    all_news.sort(
        key=lambda item: item["published_dt"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    return all_news[:limit]


def display_stock_news(symbol):
    clean_name = clean_symbol(symbol)
    search_query = f"{clean_name} stock"

    st.subheader(f"Latest Stock News: {clean_name}")
    st.caption(f"Source: NewsData.io Market API | Search: {search_query}")

    state_key = f"news_visible_count_{clean_name}"

    if state_key not in st.session_state:
        st.session_state[state_key] = 5

    news_items = fetch_stock_news(symbol, limit=30)

    if not news_items:
        st.warning(f"NewsData.io se '{search_query}' News are not Avilable.")
        return

    visible_count = st.session_state[state_key]
    visible_news = news_items[:visible_count]

    news_box = st.container(height=600)

    with news_box:
        for index, item in enumerate(visible_news, start=1):
            st.markdown(f"### {index}. {item['title']}")
            st.caption(f"{item['source']} | {item['published']}")

            if item["summary"]:
                st.write(item["summary"])

            if item["link"]:
                st.link_button("Read full news", item["link"])

            st.markdown("---")

    if visible_count < len(news_items):
        if st.button("Load more news", key=f"load_more_news_{clean_name}"):
            st.session_state[state_key] += 5
            st.rerun()