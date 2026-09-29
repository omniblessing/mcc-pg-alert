import os
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

URL = "https://www.medadmgujarat.org/pg/home.aspx"
STATE_FILE = "gujarat_state.json"

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def get_updates():
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(URL, headers=headers, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    updates = []

    for a in soup.find_all("a", href=True):
        text = " ".join(a.get_text(" ", strip=True).split())
        href = urljoin(URL, a["href"])

        if not text:
            continue

        href_lower = href.lower()
        text_lower = text.lower()

        # Only Gujarat PG admission resources
        if "medadmgujarat.ncode.in" not in href_lower:
            continue

        # Ignore navigation / login / general website links
        ignored_text = [
            "login",
            "log-in",
            "registration",
            "home",
            "contact",
            "about us",
        ]

        if any(word in text_lower for word in ignored_text):
            continue

        # Ignore old archive / historical material
        if any(path in href_lower for path in [
            "/pg2021/",
            "/pg2022/",
            "/pg2023/",
            "/pg2024/",
        ]):
            continue

        # Ignore old refund documents
        if "/refund/" in href_lower:
            continue

        # Ignore old closure documents
        if "compiled_closure" in href_lower:
            continue

        item = {
            "text": text,
            "url": href
        }

        if item not in updates:
            updates.append(item)

    return updates


def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials not found.")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=30,
    )

    response.raise_for_status()


def load_state():
    if not os.path.exists(STATE_FILE):
        return []

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_state(updates):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(updates, f, ensure_ascii=False, indent=2)


def main():
    print("Checking Gujarat PG Admission portal...")
    print(URL)

    updates = get_updates()

    print(f"\nFound {len(updates)} relevant Gujarat PG updates:\n")

    for item in updates:
        print(f"- {item['text']}")
        print(f"  {item['url']}")

    old_updates = load_state()

    old_keys = {
        (item["text"], item["url"])
        for item in old_updates
    }

    new_updates = [
        item for item in updates
        if (item["text"], item["url"]) not in old_keys
    ]

    if not old_updates:
        print("\nNo previous Gujarat state found.")
        print("Creating baseline. No Telegram alert sent.")
        save_state(updates)
        return

    if not new_updates:
        print("\nNo new Gujarat PG updates.")
        return

    print(f"\nNew updates found: {len(new_updates)}")

    for item in new_updates:
        message = (
            "🟢 GUJARAT PG ADMISSION UPDATE\n\n"
            f"{item['text']}\n\n"
            f"🔗 {item['url']}"
        )

        send_telegram(message)
        print("Telegram alert sent.")

    save_state(updates)


if __name__ == "__main__":
    main()
