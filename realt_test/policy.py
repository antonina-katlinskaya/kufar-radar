"""Isolated Realt test policy: 22–25 October 2026 inclusive.

This module does not send Telegram messages. It must not be wired to the
production Kufar workflow or shared subscription list.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation

START_DATE = "2026-10-22"
END_DATE = "2026-10-25"
CONTROLLED_PEOPLE = (
    "Алёна Довгун", "Ирина Барашенко", "Хатковская",
    "Анастасия Биянова", "Анна Зенкевич", "Жанна Вакуленчик",
)


def created_in_window(value):
    """Compare the date as supplied in Realt's ISO local timestamp."""
    try:
        date = datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
        return START_DATE <= date.isoformat() <= END_DATE
    except (TypeError, ValueError):
        return False


def decimal_value(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except (ValueError, InvalidOperation):
        return None


def area_equal(realt_area, bir_area):
    """Compare published two-digit square-meter values, never tenths/integers."""
    a, b = decimal_value(realt_area), decimal_value(bir_area)
    return a is not None and b is not None and a == b


def approved_person(row, identity_map):
    """Only verified Realt userUuid -> tracked person's full name mappings.

    Ambiguous contactName values (e.g. 'Ирина') are deliberately insufficient.
    """
    user_id = str(row.get("userUuid") or "")
    return identity_map.get(user_id) if identity_map.get(user_id) in CONTROLLED_PEOPLE else None


def send_allowed(test_chat_id, target_chat_id, production_subscribers):
    """Fail closed: private test chat must be known and not a shared/group chat.

    Never broadcast to the subscriber list; caller must additionally validate
    that test_chat_id belongs to the owner before calling a Telegram API.
    """
    return (
        bool(test_chat_id)
        and str(test_chat_id).lstrip("-").isdigit()
        and not str(test_chat_id).startswith("-")
        and str(target_chat_id) == str(test_chat_id)
        and str(target_chat_id) not in {str(v) for v in production_subscribers if str(v) != str(test_chat_id)}
    )
