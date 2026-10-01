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

    for a in soup.find_all("a", href=True):
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

        if any(path in href_lower for path in [
            "/pg2021/",
            "/pg2022/",
            "/pg2023/",
            "/pg2024/",
        ]):
            continue

        if "/refund/" in href_lower:
            continue

        if "compiled_closure" in href_lower:
            continue

        item = {
            "text": text,
            "url": href,
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
        print("Telegram credentials not found.")
        return

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

    # None means the portal was unavailable.
    # Never overwrite state in this situation.
    if updates is None:
        return

    print(f"\nFound {len(updates)} relevant Gujarat PG updates:\n")

    for item in updates:
        print(f"- {item['text']}")
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
        save_state(state)
        return

    # Alert immediately for newly appearing notices.
    for item in new_updates:
        message = (
            "🟢 GUJARAT PG ADMISSION UPDATE\n\n"
            "🆕 NEW NOTICE\n\n"
            f"{item['text']}\n\n"
            f"🔗 {item['url']}"
        )

        send_telegram(message)
        print(f"Telegram alert sent for NEW notice: {item['text']}")

    # Deep-check existing PDFs every 10 minutes.
    now = int(time.time())
    last_deep_check = state.get("last_deep_check", 0)

    if now - last_deep_check >= DEEP_CHECK_INTERVAL:
        print("\nRunning PDF content check...")

        for item in updates:
            key = (item["text"], item["url"])

            # New items have already been handled above.
            if key in {
                (x["text"], x["url"])
                for x in new_updates
            }:
                continue

            old_item = old_by_key.get(key)

            if not old_item:
                continue

            old_hash = old_item.get("content_hash")

            new_hash = pdf_hash(item["url"])

            if new_hash is None:
                continue

            if old_hash and old_hash != new_hash:
                message = (
                    "🟢 GUJARAT PG ADMISSION UPDATE\n\n"
                    "🔄 UPDATED NOTICE\n\n"
                    f"{item['text']}\n\n"
                    f"🔗 {item['url']}"
                )

                send_telegram(message)
                print(f"Telegram alert sent for UPDATED notice: {item['text']}")

            item["content_hash"] = new_hash

        state["last_deep_check"] = now

    # Preserve hashes for notices that weren't deep-checked this run.
    for item in updates:
        key = (item["text"], item["url"])

        if key in old_by_key and "content_hash" in old_by_key[key]:
            if "content_hash" not in item:
                item["content_hash"] = old_by_key[key]["content_hash"]

    state["updates"] = updates
    save_state(state)

    if not new_updates:
        print("\nNo new Gujarat PG updates.")


if __name__ == "__main__":
    main()
