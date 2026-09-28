import os
import re
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

MCC_URL = "https://mcc.nic.in/pg-medical-counselling/"
STATE_FILE = "state.json"

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    )
}


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def get_page():
    response = requests.get(
        MCC_URL,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def find_heading(soup, title):
    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        if clean(tag.get_text(" ", strip=True)).lower() == title.lower():
            return tag
    return None


def extract_link_section(soup, title):
    """
    Extract notice links belonging to a named section.
    """

    heading = find_heading(soup, title)

    if not heading:
        print(f"WARNING: {title} heading not found")
        return []

    items = []

    # The MCC page places the heading and its list inside a common container.
    container = heading.parent

    # Collect links in the immediate section/container.
    for a in container.find_all("a", href=True):
        text = clean(a.get_text(" ", strip=True))

        if not text:
            continue

        # Ignore generic navigation links.
        if text.lower() in {
            "view more",
            "read more"
        }:
            continue

        href = urljoin(MCC_URL, a["href"])

        items.append({
            "text": text,
            "url": href
        })

    # Remove duplicates while preserving order.
    seen = set()
    unique = []

    for item in items:
        key = (item["text"], item["url"])

        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


def extract_latest_news(soup):
    heading = find_heading(soup, "LATEST NEWS")

    if not heading:
        raise RuntimeError("LATEST NEWS heading not found")

    ticker = heading.find_parent(
        "div",
        class_="news-ticker-horizontal"
    )

    if not ticker:
        raise RuntimeError("LATEST NEWS container not found")

    items = []

    for item in ticker.select(".newsticker li .with-urlchange"):
        badge = item.select_one(".latest-news")

        if badge:
            badge.extract()

        text = clean(item.get_text(" ", strip=True))

        if text:
            items.append(text)

    return items


def normalize(text):
    return clean(text).lower()


def fingerprint(item):
    return (
        normalize(item["text"])
        + "||"
        + item["url"].strip()
    )


def load_state():
    if not os.path.exists(STATE_FILE):
        return None

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            state,
            f,
            indent=2,
            ensure_ascii=False
        )


def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError(
            "Telegram credentials are missing."
        )

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        json={
            "chat_id": CHAT_ID,
            "text": message,
            "disable_web_page_preview": False
        },
        timeout=30
    )

    response.raise_for_status()


def build_snapshot(soup):
    return {
        "latest_news": extract_latest_news(soup),
        "current_events": extract_link_section(
            soup,
            "Current Events"
        ),
        "news_events": extract_link_section(
            soup,
            "News & Events"
        )
    }


def compare_section(previous, current):
    previous = previous or []
    current = current or []

    previous_fingerprints = {
        fingerprint(x)
        for x in previous
    }

    new_items = [
        x for x in current
        if fingerprint(x) not in previous_fingerprints
    ]

    return new_items


def main():
    print("Checking MCC PG Counselling...")

    soup = get_page()

    current = build_snapshot(soup)

    print("\nLATEST NEWS:")
    for item in current["latest_news"]:
        print(" -", item)

    print("\nCURRENT EVENTS:")
    for item in current["current_events"]:
        print(" -", item["text"])
        print("   ", item["url"])

    print("\nNEWS & EVENTS:")
    for item in current["news_events"]:
        print(" -", item["text"])
        print("   ", item["url"])

    previous = load_state()

    # First run after upgrading:
    # establish a clean baseline without sending alerts.
    if previous is None:
        print("\nNo previous state found.")
        print("Creating baseline.")
        save_state(current)
        print("No Telegram alert sent.")
        return

    alerts = []

    # Latest News
    old_latest = previous.get("latest_news", [])
    new_latest = current.get("latest_news", [])

    old_latest_normalized = {
        normalize(x)
        for x in old_latest
    }

    for item in new_latest:
        if normalize(item) not in old_latest_normalized:
            alerts.append({
                "section": "🔵 LATEST NEWS",
                "text": item,
                "url": MCC_URL
            })

    # Current Events
    for item in compare_section(
        previous.get("current_events", []),
        current.get("current_events", [])
    ):
        alerts.append({
            "section": "📰 CURRENT EVENTS",
            "text": item["text"],
            "url": item["url"]
        })

    # News & Events
    for item in compare_section(
        previous.get("news_events", []),
        current.get("news_events", [])
    ):
        alerts.append({
            "section": "📢 NEWS & EVENTS",
            "text": item["text"],
            "url": item["url"]
        })

    if not alerts:
        print("\nNo new notifications.")
        return

    print(f"\n{len(alerts)} new notification(s) detected!")

    message = [
        "🔔 MCC PG COUNSELLING UPDATE",
        ""
    ]

    for alert in alerts:
        message.append(alert["section"])
        message.append("")
        message.append(f"🆕 {alert['text']}")
        message.append("")
        message.append(f"🔗 {alert['url']}")
        message.append("")
        message.append("────────────")
        message.append("")

    send_telegram("\n".join(message))

    save_state(current)

    print("Telegram alert sent.")
    print("State updated.")


if __name__ == "__main__":
    main()