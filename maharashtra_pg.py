"""Public Maharashtra NEET PG notices -> Telegram. Standard library only."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

URL = 'https://medical2026.mahacet.org/NEET-PGM-2026/login'
STATE = Path('maharashtra_state.json')


class Notices(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.list_depth = 0
        self.active = None
        self.items = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'ul':
            if self.list_depth or 'steps' in attrs.get('class', '').split():
                self.list_depth += 1
        if tag == 'a' and self.list_depth and attrs.get('href'):
            self.active = [urljoin(URL, attrs['href']), []]

    def handle_data(self, data):
        if self.active:
            self.active[1].append(data)

    def handle_endtag(self, tag):
        if tag == 'ul' and self.list_depth:
            self.list_depth -= 1
        if tag == 'a' and self.active:
            url, parts = self.active
            title = ' '.join(''.join(parts).split())
            if title and urlparse(url).scheme in ('https', 'http') and not url.endswith('#'):
                self.items.append({'title': title, 'url': url})
            self.active = None


def parse_notices(html):
    parser = Notices()
    parser.feed(html)
    unique = {}
    for item in parser.items:
        key = hashlib.sha256((item['title'] + '\n' + item['url']).encode()).hexdigest()
        unique[key] = item
    if not unique:
        raise RuntimeError('No notices found; refusing to replace state. Check site/layout.')
    return unique


def fetch_page():
    for attempt in range(3):
        try:
            req = Request(URL, headers={'User-Agent': 'Mozilla/5.0 (compatible; MaharashtraPGNoticeMonitor/1.0)'})
            with urlopen(req, timeout=45) as response:
                return response.read().decode('utf-8')
        except Exception:
            if attempt == 2:
                raise RuntimeError('Could not fetch Maharashtra notices') from None
            time.sleep(3 * (attempt + 1))


def send_telegram(message):
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    chat = os.environ.get('TELEGRAM_CHAT_ID', '')
    if not token or not chat:
        raise RuntimeError('Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID repository secrets')
    data = json.dumps({'chat_id': chat, 'text': message, 'disable_web_page_preview': True}).encode()
    # Do not log request exceptions: their URL contains the bot token.
    try:
        req = Request(f'https://api.telegram.org/bot{token}/sendMessage', data=data,
                      headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=30) as response:
            result = json.load(response)
        if not result.get('ok'):
            raise ValueError('Telegram rejected message')
    except Exception:
        raise RuntimeError('Telegram delivery failed; notice remains pending') from None


def save(seen):
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps({'version': 1, 'seen': seen}, indent=2) + '\n')
    temporary.replace(STATE)


def main():
    if '--test' in sys.argv:
        send_telegram('Maharashtra NEET PG monitor: Telegram delivery test.\n' + URL)
        return
    items = parse_notices(fetch_page())
    if not STATE.exists():
        raise RuntimeError('Baseline missing; restore maharashtra_state.json before running')
    state = json.loads(STATE.read_text())
    if state.get('version') != 1 or not isinstance(state.get('seen'), dict):
        raise RuntimeError('Invalid saved state')
    seen = state['seen']
    pending = [(key, item) for key, item in items.items() if key not in seen]
    # Oldest first. Save after each successful delivery so a later error does not replay the batch.
    for key, item in reversed(pending):
        send_telegram('MAHARASHTRA NEET PG 2026\nNew / updated notice\n\n'
                      + item['title'][:1800] + '\n\n' + item['url'][:1800])
        seen[key] = item
        save(seen)
    print(f'Found {len(items)} current notices; sent {len(pending)} new / updated notices.')


if __name__ == '__main__':
    main()
