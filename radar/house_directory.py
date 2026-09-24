import re
from urllib.parse import urlparse


# Only verified official addresses belong here. The BIR house slug is the primary
# key because it is stable even when the visible building name changes slightly.
OFFICIAL_ADDRESS_BY_HOUSE_SLUG = {
    'dom-mediteranian': 'Игоря Лученка ул, 22, Минск',
}

# Building numbers are a fallback for stored/diagnostic rows that do not contain
# house_href. Keep this mapping explicit: numbers can repeat outside Minsk World.
OFFICIAL_ADDRESS_BY_BUILDING_NUMBER = {
    '11.2': 'Игоря Лученка ул, 22, Минск',
}


def _house_slug(house_href: str | None) -> str | None:
    if not house_href:
        return None
    path=urlparse(str(house_href)).path
    parts=[part.casefold() for part in path.split('/') if part]
    return parts[-1] if parts else None


def _building_number(building_name: str | None) -> str | None:
    if not building_name:
        return None
    match=re.search(r'\d+(?:[.,]\d+)?',str(building_name))
    return match.group(0).replace(',','.') if match else None


def directory_address(building_name: str | None, house_href: str | None=None) -> str | None:
    slug=_house_slug(house_href)
    if slug and slug in OFFICIAL_ADDRESS_BY_HOUSE_SLUG:
        return OFFICIAL_ADDRESS_BY_HOUSE_SLUG[slug]
    number=_building_number(building_name)
    return OFFICIAL_ADDRESS_BY_BUILDING_NUMBER.get(number) if number else None


def resolved_bir_address(bir) -> str | None:
    """Return BIR's own address or a verified address from the house directory."""
    if bir.official_address:
        return bir.official_address
    return directory_address(
        bir.building_name,
        (bir.raw or {}).get('house_href'),
    )
