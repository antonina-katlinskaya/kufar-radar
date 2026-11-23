"""Independent GitHub Actions watchdog for public BIR radar and EUR price health.

Stores only alert-delivery state in the existing operational D1 state table.
Never modifies inventory, apartment identities, price events, or radar history.
"""
import json
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from notifications.bir_refresh_failure import d1_query, owner_chat_id, send_message

MINSK = ZoneInfo("Europe/Minsk")
BASE = "https://bir-radar-diagnostic.an-katlinskaya.workers.dev"
SERVICES = {
    "inventory": ("/status/public", "BIR — новинки и возвращения"),
    "eur_prices": ("/status/price/public", "BIR — история цен в евро"),
}
KEY_PREFIX = "bir_external_health_watchdog_20261123_"


def public_status(path):
    try:
        req = urllib.request.Request(
            BASE + path,
            headers={"Accept": "application/json", "User-Agent": "BIR-GitHub-independent-watchdog/1.0"},
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.load(response)
        if not isinstance(payload, dict):
            raise ValueError("Health response was not a JSON object")
        return payload
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError, TimeoutError, OSError) as exc:
        return {"ok": False, "reason": f"cannot_read_public_health: {type(exc).__name__}"}


def get_state(key):
    rows = d1_query("SELECT value FROM state WHERE key=?", [KEY_PREFIX + key])
    if not rows:
        return {"active": False, "failures": 0, "lastAlertAt": ""}
    try:
        value = json.loads(rows[0]["value"])
        return value if isinstance(value, dict) else {"active": False, "failures": 0}
    except (TypeError, ValueError, KeyError):
        return {"active": False, "failures": 0}


def set_state(key, value):
    now = datetime.now(MINSK).isoformat()
    d1_query(
        "INSERT INTO state(key,value,updated_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
        [KEY_PREFIX + key, json.dumps(value, ensure_ascii=False), now],
    )


def check_service(key, path, label, now):
    health = public_status(path)
    active = bool(health.get("ok")) is False
    prev = get_state(key)
    if active:
        failures = int(prev.get("failures", 0)) + 1
        last = prev.get("lastAlertAt") or ""
        try:
            since = (now - datetime.fromisoformat(last)).total_seconds()
        except (ValueError, TypeError):
            since = 10 ** 9
        should_alert = failures >= 2 and (not prev.get("active") or since >= 4 * 3600)
        if should_alert:
            reason = str(health.get("reason") or "данные устарели")
            source_time = str(health.get("lastAt") or health.get("lastSuccessAt") or "неизвестно")
            message = (
                f"🚨 Независимая проверка BIR: {label}\n"
                f"Причина: {reason}\n"
                f"Последняя успешная проверка: {source_time}\n"
                f"Повторный сбой при двух проверках подряд.\n"
                "Проверьте радар: https://github.com/antonina-katlinskaya/kufar-radar/actions"
            )
            send_message(owner_chat_id(), message)
        set_state(key, {
            "active": bool(prev.get("active") or should_alert),
            "failures": min(failures, 1000),
            "lastAlertAt": now.isoformat() if should_alert else last,
            "lastCheckedAt": now.isoformat(),
            "lastReason": str(health.get("reason") or "unhealthy")[:250],
        })
        print(f"{key}: unhealthy, consecutive_failures={failures}, alert_sent={should_alert}")
        return

    if prev.get("active"):
        message = f"✅ BIR: {label} снова обновляется. Независимая проверка подтверждена."
        send_message(owner_chat_id(), message)
        print(f"{key}: recovery alert sent")
    if prev.get("active") or prev.get("failures"):
        set_state(key, {
            "active": False,
            "failures": 0,
            "lastAlertAt": prev.get("lastAlertAt", ""),
            "recoveredAt": now.isoformat(),
        })
    else:
        print(f"{key}: healthy")


def main():
    now = datetime.now(MINSK)
    if not 8 <= now.hour < 22:
        print("Quiet hours: no BIR watchdog alerts")
        return
    for key, (path, label) in SERVICES.items():
        if key == "eur_prices" and now.hour == 8 and now.minute < 45:
            print("EUR price morning grace period")
            continue
        check_service(key, path, label, now)


if __name__ == "__main__":
    main()
