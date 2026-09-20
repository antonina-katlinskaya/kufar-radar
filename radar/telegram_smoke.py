import httpx
from radar.config import settings

def main():
    if not settings.telegram_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")
    base=f"https://api.telegram.org/bot{settings.telegram_token}"

    me=httpx.get(base+"/getMe",timeout=30).json()
    result=me.get("result") or {}
    print("getMe_ok", bool(me.get("ok")))
    print("bot_username", result.get("username"))

    wh=httpx.get(base+"/getWebhookInfo",timeout=30).json()
    wr=wh.get("result") or {}
    print("webhook_ok", bool(wh.get("ok")))
    print("webhook_set", bool(wr.get("url")))
    print("pending_update_count", wr.get("pending_update_count"))
    print("last_error_present", bool(wr.get("last_error_message")))

    gu=httpx.get(
        base+"/getUpdates",
        params={"timeout":0,"allowed_updates":["message","callback_query"]},
        timeout=30,
    ).json()
    print("getUpdates_ok", bool(gu.get("ok")))
    print("getUpdates_count", len(gu.get("result") or []))
    if not gu.get("ok"):
        print("getUpdates_error", gu.get("description"))

if __name__=="__main__":
    main()

# trigger health check
