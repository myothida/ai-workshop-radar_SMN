"""Send daily digests. Called by GitHub Actions cron.

For each subscriber file in data/subscribers/:
  - load their prefs
  - build their digest (skipping already-notified items via data/notified.yaml)
  - POST to Telegram and/or Slack
  - mark the dispatched items in notified.yaml
Finally save notified.yaml so the Action can commit it back.
"""
from __future__ import annotations

import os
import sys
import time

import requests
from dotenv import load_dotenv

from src import slack, subscribers as subs
from src.data import load_venues
from src.digest import build_subscriber_digest


def send_telegram(token: str, chat_id: int, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            # "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }, timeout=15)
        if not r.ok:
            print(f"[digest] telegram {r.status_code} for {chat_id}: {r.text[:200]}")
        return r.ok
    except Exception as e:
        print(f"[digest] telegram error for {chat_id}: {e}")
        return False


def main():
    load_dotenv()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("⚠️  TELEGRAM_BOT_TOKEN missing — Telegram delivery disabled")

    venues = load_venues()
    all_subs = subs.load_all_subscribers()
    notified = subs.load_notified()

    if not all_subs:
        print("[digest] no subscribers configured")
        return

    print(f"[digest] processing {len(all_subs)} subscribers…")
    sent = 0
    for sub in all_subs:
        handle = sub["handle"]
        text, to_notify = build_subscriber_digest(sub, venues, notified)
        if not text:
            print(f"[digest] {handle}: nothing to send")
            continue

        ok_any = False
        chat_id = sub.get("telegram_chat_id") or 0
        if token and chat_id:
            if send_telegram(token, int(chat_id), text):
                ok_any = True
        if sub.get("slack_webhook"):
            if slack.send(sub["slack_webhook"], text):
                ok_any = True

        if ok_any:
            for venue_id, stage in to_notify:
                subs.mark_notified(notified, handle, venue_id, stage)
            sent += 1
            print(f"[digest] {handle}: sent ({len(to_notify)} new deadlines)")
        else:
            print(f"[digest] {handle}: failed all delivery channels")
        time.sleep(0.1)

    subs.save_notified(notified)
    print(f"[digest] done — delivered to {sent}/{len(all_subs)} subscribers")


if __name__ == "__main__":
    main()
