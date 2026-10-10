
import os
import json
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

URL = "https://www.medadmgujarat.org/pg/home.aspx"
STATE_FILE = "gujarat_state.json"

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def get_updates():
    headers = {"User-Agent": "Mozilla/5.0"}

    for attempt in range(3):
        try:
            response = requests.get(URL, headers=headers, timeout=30)

            if response.status_code in (502, 503, 504):
                print(
                    f"Gujarat portal returned HTTP {response.status_code} "
                    f"(attempt {attempt + 1}/3)"
                )
                if attempt < 2:
                    time.sleep(5 * (attempt + 1))
                    continue

                print("Gujarat portal unavailable after 3 attempts. Skipping this check.")
                return None

            response.raise_for_status()
            break

        except requests.RequestException as e:
            print(
                f"Gujarat portal request failed "
                f"(attempt {attempt + 1}/3): {e}"
            )
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue

            print("Gujarat portal unavailable after 3 attempts. Skipping this check.")
            return None

    soup = BeautifulSoup(response.text, "html.parser")
    updates = []

    # Each coloured information box contains its own [Date: ...]
    # and one or more notice/PDF links.
    for section in soup.find_all(
        "div",
        style=lambda value: value and "border:" in value
    ):
        section_text = section.get_text(" ", strip=True)

        posted_at = None
        marker = "[Date:"
        if marker in section_text:
            start = section_text.find(marker) + len(marker)
            end = section_text.find("]", start)
            if end != -1:
                posted_at = section_text[start:end].strip()

        for a in section.find_all("a", href=True):
            text = " ".join(a.get_text(" ", strip=True).split())
            href = urljoin(URL, a["href"])

            if not text:
                continue

            href_lower = href.lower()
            text_lower = text.lower()

            if "medadmgujarat.ncode.in" not in href_lower:
                continue

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

            if any(
                path in href_lower
                for path in [
                    "/pg2021/",
                    "/pg2022/",
                    "/pg2023/",
                    "/pg2024/",
                ]
            ):
                continue

            if "/refund/" in href_lower:
                continue

            if "compiled_closure" in href_lower:
                continue

            item = {
                "text": text,
                "url": href,
                "posted_at": posted_at,
            }

            if item not in updates:
                updates.append(item)

    return updates


def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials not found. Alert not sent.")
        return False

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": message,
                "disable_web_page_preview": False,
            },
            timeout=15,
        )

        response.raise_for_status()
        result = response.json()

        if result.get("ok") is True:
            sent_message = result.get("result", {})
            chat = sent_message.get("chat", {})
            message_id = sent_message.get("message_id")

            print(
                f"Telegram accepted message for "
                f"chat {chat.get('id')}, "
                f"message ID {message_id}"
            )
            return True

        print(
            f"Telegram rejected message: "
            f"{result.get('description', 'Unknown error')}"
        )
        return False

    except (requests.RequestException, ValueError) as e:
        print(f"Telegram delivery failed: {e}")
        return False


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"updates": []}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            return {"updates": data}

        if not isinstance(data, dict):
            return {"updates": []}

        if not isinstance(data.get("updates"), list):
            return {"updates": []}

        return data

    except (OSError, ValueError) as e:
        print(f"Could not load Gujarat state: {e}")
        return {"updates": []}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def main():
    print("Checking Gujarat PG Admission portal...")
    print(URL)

    updates = get_updates()

    # Never overwrite state when the portal is unavailable.
    if updates is None:
        return

    # Avoid overwriting state if parsing unexpectedly finds nothing.
    if not updates:
        print("No Gujarat notices found. Preserving previous state.")
        return

    print(f"\nFound {len(updates)} relevant Gujarat PG updates:\n")

    for item in updates:
        print(f"- {item['text']}")
        print(f"  Date: {item.get('posted_at')}")
        print(f"  {item['url']}")

    state = load_state()
    old_updates = state.get("updates", [])

    old_by_key = {
        (item.get("text"), item.get("url")): item
        for item in old_updates
    }

    new_updates = [
        item
        for item in updates
        if (item["text"], item["url"]) not in old_by_key
    ]

    # First run: establish baseline.
    if not old_updates:
        print("\nNo previous Gujarat state found.")
        print("Creating baseline. No Telegram alert sent.")

        state["updates"] = updates
        save_state(state)
        return

    # Keep all previously confirmed notices.
    # Add new notices only after Telegram accepts the message.
    confirmed_by_key = dict(old_by_key)

    for item in new_updates:
        message = (
            "🟢 GUJARAT PG ADMISSION UPDATE\n\n"
            "🆕 NEW NOTICE\n\n"
            f"{item['text']}\n\n"
            f"📅 Posted: {item.get('posted_at') or 'Date not shown'}\n\n"
            f"🔗 {item['url']}"
        )

        if send_telegram(message):
            print(
                f"Telegram alert sent for NEW notice: "
                f"{item['text']}"
            )
            confirmed_by_key[(item["text"], item["url"])] = item
        else:
            print(
                f"Telegram alert NOT confirmed for: "
                f"{item['text']}. Will retry on next run."
            )

    # Refresh notices that are still visible and confirmed,
    # without recording notices whose Telegram alerts failed.
    confirmed_updates = [
        item
        for item in updates
        if (item["text"], item["url"]) in confirmed_by_key
    ]

    # Retain previously confirmed notices even if they
    # temporarily disappear from the website.
    current_keys = {
        (item["text"], item["url"])
        for item in confirmed_updates
    }

    for old_item in old_updates:
        key = (old_item.get("text"), old_item.get("url"))
        if key not in current_keys:
            confirmed_updates.append(old_item)
            current_keys.add(key)

    state["updates"] = confirmed_updates

    if state["updates"] != old_updates:
        save_state(state)
        print("Gujarat notification state updated.")
    else:
        print("No Gujarat state change.")


if __name__ == "__main__":
    main()

    if os.environ.get("TELEGRAM_TEST") == "1":
        print("\nRunning Telegram delivery test...")
        send_telegram(
            "🧪 GUJARAT PG ALERT TEST\n\n"
            "Testing Telegram delivery from GitHub Actions."
        )
