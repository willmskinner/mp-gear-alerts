import re
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

BASE = "https://www.mountainproject.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; mp-gear-alerts/1.0)"}
REQUEST_DELAY_SECONDS = 1.0

_session = requests.Session()
_session.headers.update(HEADERS)
_last_request = 0.0


def _get(url):
    global _last_request
    wait = REQUEST_DELAY_SECONDS - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    resp = _session.get(url, timeout=20)
    _last_request = time.monotonic()
    resp.raise_for_status()
    return resp


@dataclass
class Topic:
    id: int
    title: str
    url: str
    author: str
    last_message_id: int
    sticky: bool


@dataclass
class Message:
    id: int
    topic_id: int
    author: str
    text: str

    @property
    def url(self):
        return f"{BASE}/forum/message/{self.id}"


def _id_from_href(href, kind):
    m = re.search(rf"/forum/{kind}/(\d+)", href)
    return int(m.group(1)) if m else None


def fetch_topic_list(forum_id, page=1):
    resp = _get(f"{BASE}/forum/{forum_id}?page={page}")
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.select_one("table#forum-table")
    if table is None:
        raise ValueError(f"forum {forum_id} page {page}: topic table not found (page layout changed?)")

    topics = []
    for row in table.select("tr"):
        link = row.select_one('a[href*="/forum/topic/"]')
        last_links = row.select('a[href*="/forum/message/"]')
        if not link or not last_links:
            continue
        topic_id = _id_from_href(link["href"], "topic")
        last_id = _id_from_href(last_links[-1]["href"], "message")
        author_el = link.find_next_sibling("span")
        topics.append(
            Topic(
                id=topic_id,
                title=link.get_text(" ", strip=True),
                url=link["href"],
                author=author_el.get_text(" ", strip=True).lstrip("—").strip() if author_el else "",
                last_message_id=last_id,
                sticky="Sticky:" in link.parent.get_text(),
            )
        )
    if not topics:
        raise ValueError(f"forum {forum_id} page {page}: no topics parsed (page layout changed?)")
    return topics


def _parse_messages(html, topic_id):
    soup = BeautifulSoup(html, "html.parser")
    messages = []
    for row in soup.select("tr.message-row"):
        m = re.match(r"ForumMessage-(\d+)", row.get("id", ""))
        body = row.select_one("div.fr-view")
        if not m or body is None:
            continue
        messages.append(
            Message(
                id=int(m.group(1)),
                topic_id=topic_id,
                author=row.get("data-user-name", ""),
                text=body.get_text(" ", strip=True),
            )
        )
    prev = soup.select_one('.pagination a img[alt="Previous"]')
    prev_url = prev.parent.get("href") if prev and prev.parent.name == "a" else None
    return messages, prev_url


def fetch_messages_after(topic, after_id, max_pages=3):
    """Return the topic's messages with id > after_id, oldest first.

    Starts from the page holding the topic's latest message and walks backwards.
    """
    url = f"{BASE}/forum/message/{topic.last_message_id}"
    collected = []
    for _ in range(max_pages):
        messages, prev_url = _parse_messages(_get(url).text, topic.id)
        collected.extend(msg for msg in messages if msg.id > after_id)
        if not prev_url or not messages or min(msg.id for msg in messages) <= after_id:
            break
        url = prev_url
    return sorted(collected, key=lambda msg: msg.id)
