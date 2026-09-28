import os
import re
import requests
from bs4 import BeautifulSoup

MCC_URL = "https://mcc.nic.in/pg-medical-counselling/"
STATE_FILE = "state.txt"

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    )
}


def get_latest_news():
    response = requests.get(
        MCC_URL,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    heading = None

    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        if tag.get_text(" ", strip=True).upper() == "LATEST NEWS":
            heading = tag
            break

    if heading is None:
        raise RuntimeError("LATEST NEWS heading not found")

    ticker = heading.find_parent(
        "div",
        class_="news-ticker-horizontal"
    )

    if ticker is None:
        raise RuntimeError("LATEST NEWS container not found")

    items = []

    for item in ticker.select(".newsticker li .with-urlchange"):
        badge = item.select_one(".latest-news")

        if badge:
            badge.extract()

        text = item.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()

        if text:
            items.append(text)

    if not items:
        raise RuntimeError("No Latest News items found")

    return items


def normalize(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def load_state():
    if not os.path.exists(STATE_FILE):
        return None

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


def save_state(items):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(items))


def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError(
            "Telegram credentials are not available."
        )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

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


def main():
    print("Checking MCC PG Counselling...")

    current_items = get_latest_news()

    print("\nCurrent Latest News:")

    for item in current_items:
        print(" -", item)

    previous_raw = load_state()

    if previous_raw is None:
        print("\nFirst run.")
        print("Saving current notification as baseline.")
        save_state(current_items)
        print("No Telegram alert sent.")
        return

    previous_items = previous_raw.splitlines()

    previous_normalized = {
        normalize(x) for x in previous_items
    }

    current_normalized = {
        normalize(x) for x in current_items
    }

    new_items = [
        item
        for item in current_items
        if normalize(item) not in previous_normalized
    ]

    removed_items = [
        item
        for item in previous_items
        if normalize(item) not in current_normalized
    ]

    if not new_items and not removed_items:
        print("\nNo change detected.")
        return

    print("\nCHANGE DETECTED!")

    message_parts = [
        "🔔 MCC PG COUNSELLING UPDATE",
        "",
        "The MCC LATEST NEWS section has changed.",
        ""
    ]

    if new_items:
        message_parts.append("🆕 NEW:")

        for item in new_items:
            message_parts.append(f"• {item}")

        message_parts.append("")

    if removed_items:
        message_parts.append("ℹ️ PREVIOUS:")

        for item in removed_items:
            message_parts.append(f"• {item}")

        message_parts.append("")

    message_parts.append(f"🔗 {MCC_URL}")

    message = "\n".join(message_parts)

    send_telegram(message)

    save_state(current_items)

    print("\nTelegram alert sent.")


if __name__ == "__main__":
    main()