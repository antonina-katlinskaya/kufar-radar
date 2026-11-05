"""Notify the radar owner about nightly BIR refresh failures, during Minsk daytime only.

Failures detected between 22:00 and 08:00 are persisted in the existing D1
state table, then delivered by the dedicated morning-flush workflow.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MINSK = ZoneInfo("Europe/Minsk")
OUTBOX_KEY = "bir_refresh_failure_outbox_v1"
DATABASE_ID = "43422bcb-fce7-4ddc-adc7-e9bf457f2837"


def delivery_allowed(now=None):
    local = (now or datetime.now(MINSK)).astimezone(MINSK)
    return 8 <= local.hour < 22


def request(url, body, headers=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def d1_query(sql, params=None):
    account = os.environ["CF_ACCOUNT_ID"]
    token = os.environ["CF_D1_API_TOKEN"]
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{DATABASE_ID}/query"
    data = request(
        url,
        {"sql": sql, "params": params or []},
        {"Authorization": "Bearer " + token},
    )
    if not data.get("success") or not data.get("result") or not data["result"][0].get("success", True):
        raise RuntimeError("D1 request failed: " + str(data.get("errors") or data.get("result")))
    return data["result"][0].get("results", [])


def owner_chat_id():
    explicit = os.getenv("BIR_OWNER_CHAT_ID")
    if explicit:
        return str(int(explicit))
    rows = d1_query("SELECT value FROM state WHERE key='telegram_chat_id'")
    if len(rows) != 1:
        raise RuntimeError("Owner chat is not configured")
    return str(int(rows[0]["value"]))


def read_pending():
    rows = d1_query("SELECT value FROM state WHERE key=?", [OUTBOX_KEY])
    if not rows:
        return []
    value = json.loads(rows[0]["value"])
    if not isinstance(value, list):
        raise RuntimeError("BIR failure outbox has invalid format")
    return [str(message) for message in value]


def save_pending(messages):
    if messages:
        d1_query(
            "INSERT INTO state(key,value,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
            [OUTBOX_KEY, json.dumps(messages, ensure_ascii=False), datetime.now(timezone.utc).isoformat()],
        )
    else:
        d1_query("DELETE FROM state WHERE key=?", [OUTBOX_KEY])


def send_message(chat, message):
    result = request(
        "https://api.telegram.org/bot" + os.environ["TELEGRAM_BOT_TOKEN"] + "/sendMessage",
        {"chat_id": chat, "text": message, "disable_web_page_preview": True},
    )
    if not result.get("ok"):
        raise RuntimeError("Telegram did not confirm delivery")


def main():
    chat = owner_chat_id()

    if "--prepare" in sys.argv:
        with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as handle:
            handle.write("BIR_OWNER_CHAT_ID=" + chat + "\n")
        return

    if "--flush" in sys.argv:
        if not delivery_allowed():
            print("BIR_FAILURE_OUTBOX: quiet hours; not sending")
            return
        pending = read_pending()
        sent = 0
        while pending and delivery_allowed():
            send_message(chat, pending[0])
            pending.pop(0)
            save_pending(pending)
            sent += 1
        print(f"BIR_FAILURE_OUTBOX: delivered={sent}, remaining={len(pending)}")
        return

    text = (
        "⚠️ Ночная задача BIR завершилась ошибкой: обновление карточек или очистка хранилища. "
        "Результат и полнота обновления указаны в журнале: "
        "https://github.com/" + os.environ["GITHUB_REPOSITORY"] + "/actions/runs/"
        + os.environ["GITHUB_RUN_ID"]
    )
    if delivery_allowed():
        send_message(chat, text)
        print("BIR_REFRESH_FAILURE: daytime notification delivered")
    else:
        pending = read_pending()
        if text not in pending:
            pending.append(text)
            save_pending(pending)
        print(f"BIR_REFRESH_FAILURE: queued until after 08:00 Minsk; pending={len(pending)}")


if __name__ == "__main__":
    main()
