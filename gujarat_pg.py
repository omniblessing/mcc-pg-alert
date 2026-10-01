import os
import json
import time
import hashlib
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

URL = "https://www.medadmgujarat.org/pg/home.aspx"
STATE_FILE = "gujarat_state.json"
DEEP_CHECK_INTERVAL = 600  # 10 minutes

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


def pdf_hash(url):
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
            stream=True,
        )
        response.raise_for_status()

        sha = hashlib.sha256()

        for chunk in response.iter_content(chunk_size=65536):
            if chunk:
                sha.update(chunk)

        return sha.hexdigest()

    except requests.RequestException as e:
        print(f"Could not download PDF for fingerprinting: {e}")
        return None


def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials not found. Alert not sent.")
        return False

    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=30,
    )

    response.raise_for_status()
    return True


def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "updates": [],
            "last_deep_check": 0,
        }

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Convert old state format automatically.
        if isinstance(data, list):
            return {
                "updates": data,
                "last_deep_check": 0,
            }

        return data

    except Exception:
        return {
            "updates": [],
            "last_deep_check": 0,
        }


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
        state["last_deep_check"] = int(time.time())

        # Establish PDF fingerprints.
        for item in state["updates"]:
            item["content_hash"] = pdf_hash(item["url"])

        save_state(state)
        return

    # Alert immediately for newly appearing notices.
    for item in new_updates:
        message = (
            "🟢 GUJARAT PG ADMISSION UPDATE\n\n"
            "🆕 NEW NOTICE\n\n"
            f"{item['text']}\n\n"
            f"📅 Posted: {item['posted_at'] or 'Date not shown'}\n\n"
            f"🔗 {item['url']}"
        )

        if send_telegram(message):
            print(f"Telegram alert sent for NEW notice: {item['text']}")

    now = int(time.time())
    last_deep_check = state.get("last_deep_check", 0)

    # Deep-check every 10 minutes.
    if now - last_deep_check >= DEEP_CHECK_INTERVAL:
        print("\nRunning PDF and posted-date checks...")

        for item in updates:
            key = (item["text"], item["url"])
            old_item = old_by_key.get(key)

            if not old_item:
                continue

            old_date = old_item.get("posted_at")
            new_date = item.get("posted_at")

            # Detect the website's posted date/time changing.
            if old_date and new_date and old_date != new_date:
                message = (
                    "🟢 GUJARAT PG ADMISSION UPDATE\n\n"
                    "🕐 NOTICE DATE/TIME UPDATED\n\n"
                    f"{item['text']}\n\n"
                    f"📅 Previous: {old_date}\n"
                    f"📅 Current: {new_date}\n\n"
                    f"🔗 {item['url']}"
                )

                if send_telegram(message):
                    print(f"Telegram alert sent for DATE change: {item['text']}")

            old_hash = old_item.get("content_hash")
            new_hash = pdf_hash(item["url"])

            if new_hash is not None and old_hash:
                if old_hash != new_hash:
                    message = (
                        "🟢 GUJARAT PG ADMISSION UPDATE\n\n"
                        "🔄 UPDATED NOTICE\n\n"
                        f"{item['text']}\n\n"
                        f"📅 Posted: {new_date or 'Date not shown'}\n\n"
                        f"🔗 {item['url']}"
                    )

                    if send_telegram(message):
                        print(f"Telegram alert sent for PDF change: {item['text']}")

            if new_hash is not None:
                item["content_hash"] = new_hash
            elif old_hash:
                item["content_hash"] = old_hash

        state["last_deep_check"] = now

    # Preserve existing hashes.
    for item in updates:
        key = (item["text"], item["url"])

        if key in old_by_key:
            old_item = old_by_key[key]

            if "content_hash" in old_item and "content_hash" not in item:
                item["content_hash"] = old_item["content_hash"]

    state["updates"] = updates
    save_state(state)


if __name__ == "__main__":
    main()
