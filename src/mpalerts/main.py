import argparse
import html
import logging
import sys
from dataclasses import dataclass

import requests

from . import mountainproject as mp
from .config import load_config
from .matching import any_match, snippet
from .notify import send_email
from .state import load_state, save_state

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("mpalerts")

FAILURE_ALERT_THRESHOLD = 3
MAX_LIST_PAGES = 5
MAX_NOTIFIED_PER_WATCH = 1000


@dataclass
class Hit:
    watch: str
    kind: str      # "New listing", "Updated/bumped listing", "Reply"
    title: str
    url: str
    author: str
    snippet_html: str


def highlight(text, m):
    """HTML-escaped snippet around match `m`, with the matched words bolded."""
    snip = snippet(text, m)
    matched = m.group(0)
    escaped = html.escape(snip)
    return escaped.replace(html.escape(matched), f"<b>{html.escape(matched)}</b>", 1)


def active_topics(forum_id, hwm):
    """Topics in the forum listing with a message newer than `hwm`."""
    found = {}
    for page in range(1, MAX_LIST_PAGES + 1):
        topics = mp.fetch_topic_list(forum_id, page)
        for t in topics:
            if t.last_message_id > hwm:
                found[t.id] = t
        # Listing is sorted by last post (stickies pinned on top), so stop once we reach old ones.
        regular = [t for t in topics if not t.sticky]
        if regular and min(t.last_message_id for t in regular) <= hwm:
            break
    else:
        log.info("forum %s: hit page limit (%d); some older activity may be skipped", forum_id, MAX_LIST_PAGES)
    return list(found.values())


def match_topic(topic, messages, watches, notified):
    hits = []
    op = next((m for m in messages if m.id == topic.id), None)
    replies = [m for m in messages if m.id != topic.id]

    for watch in watches:
        seen = notified.setdefault(watch.name, [])
        if topic.id in seen:
            continue  # already alerted on this listing for this watch

        listing_text = topic.title + (" — " + op.text if op else "")
        m = watch.match(listing_text)
        if m:
            hits.append(Hit(
                watch=watch.name,
                kind="New listing" if op else "Updated/bumped listing",
                title=topic.title,
                url=op.url if op else topic.url,
                author=topic.author,
                snippet_html=highlight(listing_text, m),
            ))
            seen.append(topic.id)
            continue

        for reply in replies:
            m = watch.match(reply.text)
            if m:
                hits.append(Hit(
                    watch=watch.name,
                    kind="Reply",
                    title=topic.title,
                    url=reply.url,
                    author=reply.author,
                    snippet_html=highlight(reply.text, m),
                ))
    return hits


def check_forum(forum, fstate, watches, exclude_titles, notified):
    forum_id = forum["id"]
    hwm = fstate.get("last_message_id")

    if hwm is None:
        topics = mp.fetch_topic_list(forum_id, 1)
        new_hwm = max(t.last_message_id for t in topics)
        log.info("forum %s: first run, baseline set at message %s (no alerts)", forum_id, new_hwm)
        return [], {"last_message_id": new_hwm}

    topics = active_topics(forum_id, hwm)
    hits = []
    for topic in topics:
        if any_match(exclude_titles, topic.title):
            continue
        try:
            messages = mp.fetch_messages_after(topic, hwm)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                log.info("  topic %s gone (404), skipping", topic.id)
                continue
            raise
        topic_hits = match_topic(topic, messages, watches, notified)
        for h in topic_hits:
            log.info("  MATCH [%s] %s: %s", h.watch, h.kind, h.title)
        hits.extend(topic_hits)

    new_hwm = max([hwm] + [t.last_message_id for t in topics])
    log.info("forum %s: %d active topics, %d matches", forum_id, len(topics), len(hits))
    return hits, {"last_message_id": new_hwm}


def render_email(hits, failure=None, recovered=False):
    html_parts, text_parts = [], []
    by_watch = {}
    for h in hits:
        by_watch.setdefault(h.watch, []).append(h)

    for watch, items in by_watch.items():
        html_parts.append(f"<h3>{html.escape(watch)}</h3><ul>")
        text_parts.append(f"{watch}:")
        for h in items:
            html_parts.append(
                f"<li><a href='{html.escape(h.url)}'>{html.escape(h.title)}</a>"
                f" <small>({h.kind} by {html.escape(h.author)})</small>"
                f"<br><span style='color:#555'>{h.snippet_html}</span></li>"
            )
            text_parts.append(f"  - [{h.kind}] {h.title} ({h.author}) {h.url}")
        html_parts.append("</ul>")

    if failure:
        html_parts.append(f"<h3>Scanner failing repeatedly</h3><p>{html.escape(failure)}</p>")
        text_parts.append(f"FAILING: {failure}")
    if recovered:
        html_parts.append("<h3>Scanner recovered</h3>")
        text_parts.append("RECOVERED")

    return "\n".join(html_parts), "\n".join(text_parts)


def subject_for(hits, failure, recovered):
    bits = []
    if hits:
        watches = list(dict.fromkeys(h.watch for h in hits))
        bits.append(f"{len(hits)} new — " + ", ".join(watches))
    if failure:
        bits.append("scanner failing")
    if recovered:
        bits.append("scanner recovered")
    return "MP gear alert: " + "; ".join(bits)


def run(dry_run=False):
    forums, watches, exclude_titles = load_config()
    state = load_state()
    state.setdefault("forums", {})
    notified = {k: list(v) for k, v in state.get("notified", {}).items()}
    failures = state.get("consecutive_failures", 0)

    all_hits = []
    forum_updates = {}
    try:
        for forum in forums:
            fid = str(forum["id"])
            hits, forum_updates[fid] = check_forum(
                forum, state["forums"].get(fid, {}), watches, exclude_titles, notified
            )
            all_hits.extend(hits)
    except Exception as exc:
        failures += 1
        log.exception("Scan failed (%d consecutive)", failures)
        state["consecutive_failures"] = failures
        state["last_error"] = str(exc)
        if failures == FAILURE_ALERT_THRESHOLD and not dry_run:
            html_body, text_body = render_email([], failure=str(exc))
            send_email(subject_for([], str(exc), False), html_body, text_body)
        if not dry_run:
            save_state(state)
        return

    recovered = failures >= FAILURE_ALERT_THRESHOLD

    state["forums"].update(forum_updates)
    state["consecutive_failures"] = 0
    state["last_error"] = None
    watch_names = {w.name for w in watches}
    state["notified"] = {
        name: ids[-MAX_NOTIFIED_PER_WATCH:] for name, ids in notified.items() if name in watch_names
    }

    if all_hits or recovered:
        subject = subject_for(all_hits, None, recovered)
        html_body, text_body = render_email(all_hits, recovered=recovered)
        if dry_run:
            print(f"\nSUBJECT: {subject}\n\n{text_body}")
            log.info("Dry run - not sending email, not saving state.")
            return
        send_email(subject, html_body, text_body)
        log.info("Email sent.")
    else:
        log.info("Nothing new to report.")

    if not dry_run:
        save_state(state)


def main():
    parser = argparse.ArgumentParser(description="Scan Mountain Project for-sale forums and email matching posts.")
    parser.add_argument("--test-email", action="store_true", help="Send a canned test email and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Run detection, print the email, send/save nothing.")
    args = parser.parse_args()

    if args.test_email:
        send_email("MP gear alerts - test email", "<p>This is a test email from your Mountain Project gear alerts.</p>")
        log.info("Test email sent.")
        return

    try:
        run(dry_run=args.dry_run)
    except Exception:
        log.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    main()
