"""Verified year values from the original Kufar and BIR records."""
import json

def _raw(value):
    if isinstance(value,dict):
        return value
    try:
        result=json.loads(value or '{}')
        return result if isinstance(result,dict) else {}
    except (ValueError,TypeError):
        return {}

def normalize_year(value):
    if isinstance(value,list):
        value=value[0] if len(value)==1 else None
    try:
        n=int(str(value).strip())
        return n if 1900<=n<=2100 else None
    except (ValueError,TypeError):
        return None

def kufar_year(raw):
    rows=_raw(raw).get('ad_parameters') or []
    if isinstance(rows,dict):
        row=rows.get('year_built')
        return normalize_year(row.get('v') if isinstance(row,dict) else row)
    values={normalize_year(row.get('v')) for row in rows if isinstance(row,dict) and row.get('p')=='year_built'}
    return next(iter(values)) if len(values)==1 else None

def bir_year(raw):
    return normalize_year(_raw(raw).get('god'))

def verified_bir_year(raw):
    raw=_raw(raw)
    year=bir_year(raw)
    deadline=normalize_year(str(raw.get('deadline') or '')[:4])
    # A disagreement between BIR's two fields requires manual verification.
    return year if year is not None and (deadline is None or deadline==year) else None


def house_year_index(candidates):
    from .house_directory import HOUSE_DIRECTORY, _building_number
    from .matcher import norm_address
    addresses = {}
    for number, address in HOUSE_DIRECTORY.items():
        addresses.setdefault(tuple(norm_address(address)), set()).add(number)
    years = {}
    for obj in candidates:
        number = _building_number(obj.building_name)
        if number in HOUSE_DIRECTORY:
            raw = _raw(obj.raw)
            if raw.get('god') is not None:
                years.setdefault(number, set()).add(verified_bir_year(raw))
    return {address: next(iter(years[number]))
            for address, numbers in addresses.items() if len(numbers) == 1
            for number in numbers if len(years.get(number, ())) == 1}
