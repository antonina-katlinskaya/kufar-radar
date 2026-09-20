from collections.abc import Mapping, Sequence

def walk_json(x):
    if isinstance(x, Mapping):
        yield x
        for v in x.values(): yield from walk_json(v)
    elif isinstance(x, Sequence) and not isinstance(x,(str,bytes,bytearray)):
        for v in x: yield from walk_json(v)

def first_value(d, keys):
    for k in keys:
        if k in d and d[k] not in (None,''): return d[k]
    # common nested property arrays
    for key in ('parameters','params','properties','ad_parameters'):
        arr=d.get(key)
        if isinstance(arr,list):
            for p in arr:
                if not isinstance(p,dict): continue
                name=str(p.get('p') or p.get('name') or p.get('key') or p.get('id') or '').lower()
                for k in keys:
                    if k.lower() in name:
                        return p.get('v') or p.get('value') or p.get('vl')
    return None
