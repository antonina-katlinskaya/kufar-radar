"""Isolated archive audit. Production modules and source state are read-only."""
import csv
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from realt_test.policy import area_equal, decimal_value
from realt_test.sources import TRACKED, load_realt

OUT = Path('realt_test/results.json')


def candidate_record(b):
    return {
        'id': b.object_key, 'house': b.building_name, 'unit': b.unit_no,
        'rooms': b.rooms, 'area': b.area, 'floor': b.floor,
        'special_price_eur': b.price_fast_eur, 'regular_price_eur': b.price_regular_eur,
    }


def audit(rows, bir, bir_checked, source):
    items = []
    for row in rows:
        rooms, area, price = [decimal_value(row.get(k)) for k in ('rooms', 'areaTotal', 'price')]
        candidates = [b for b in bir if rooms is not None and decimal_value(b.rooms) == rooms and area_equal(area, b.area)]
        price_confirmed = str(row.get('priceCurrency')) in {'978', 'EUR'} and price is not None
        exact = [b for b in candidates if price_confirmed and decimal_value(b.price_fast_eur) == price]
        if exact:
            status, reason = 'OK', 'Совпали комнаты, точная площадь и специальная стоимость Bir при быстрой оплате'
        elif not price_confirmed:
            status, reason = 'SKIP', 'Цена Realt не в евро; ценовое сравнение не производится'
        elif candidates:
            status, reason = 'REVIEW', 'Комнаты и точная площадь найдены, но специальная стоимость Bir отличается'
        else:
            status, reason = 'REVIEW', 'Нет сочетания комнат и точной площади в текущем наличии Bir'
        edits = row.get('material_edits') or []
        if edits:
            status = 'BACKDATED'
            reason = 'Существенные параметры старого объявления изменены без новой даты публикации'
        same_rooms = [b for b in bir if rooms is not None and decimal_value(b.rooms) == rooms and decimal_value(b.area) is not None]
        nearest = sorted(same_rooms, key=lambda b: (abs(decimal_value(b.area) - area), str(b.object_key)))[:3] if area is not None and not candidates else []
        items.append({
            'code': str(row.get('code') or ''), 'uuid': row['uuid'], 'person': row['person'],
            'url': f"https://realt.by/sale-flats/object/{row['code']}/",
            'created_at': row.get('createdAt'), 'updated_at': row.get('updatedAt'), 'radar_checked_at': datetime.now(timezone.utc).isoformat(),
            'first_seen_at': row.get('first_seen_at'), 'last_seen_at': row.get('last_seen_at'),
            'present_in_latest_snapshot': row.get('present_in_latest_snapshot'),
            'rooms': row.get('rooms'), 'area': row.get('areaTotal'), 'floor': row.get('storey'),
            'address': row.get('address'), 'street': row.get('streetName'), 'house_number': row.get('houseNumber'), 'quarter': row.get('quarter'), 'title': row.get('title'),
            'price': row.get('price'), 'currency': row.get('priceCurrency'),
            'status': status, 'reason': reason, 'material_edits': edits,
            'matching_bir_keys': [b.object_key for b in exact],
            'bir_room_area_candidates': [candidate_record(b) for b in candidates],
            'nearest_area_hints_not_matches': [candidate_record(b) for b in nearest],
        })
    counts = {p: dict(Counter(x['status'] for x in items if x['person'] == p)) for p in TRACKED.values()}
    return {
        'scope': ('2026-10-23..ongoing' if os.getenv('REALT_CONTINUOUS') == '1' else '2026-10-23..2026-10-26'), 'checked_at': datetime.now(timezone.utc).isoformat(),
        'bir_checked_at': bir_checked, 'bir_objects': len(bir), 'source': source,
        'checked': len(items), 'status_counts': dict(Counter(x['status'] for x in items)),
        'person_status_counts': counts, 'tracked_people': list(TRACKED.values()),
        'coverage_warning': 'Объединены доступные архивные снимки и последний список. Объявления между обходами могли не попасть в архив. Сверка с наличием Bir на момент проверки, не на дату публикации. REVIEW не является доказанным нарушением. Этаж и адрес не входят в первичный фильтр.',
        'notification_sent': False, 'items': items,
    }


def write_reports(result):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.with_name('diagnostics.json').write_text(json.dumps({k:result.get(k) for k in ('checked_at','checked','bir_checked_at','status_counts','source','notification_paused')},ensure_ascii=False),encoding='utf-8')
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    fields = ['person', 'code', 'created_at', 'area', 'rooms', 'price', 'currency', 'status', 'reason', 'address', 'floor', 'url', 'present_in_latest_snapshot', 'first_seen_at', 'last_seen_at']
    with OUT.with_suffix('.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(result['items'])
    period = 'Объявления с 23 октября 2026.' if os.getenv('REALT_CONTINUOUS') == '1' else 'Объявления 23–26 октября 2026 включительно.'
    lines = ['# Realt — тест', '', period, '',
             f"Проверено: {result['checked']}. Bir: {result['bir_checked_at']}.", '', result['coverage_warning'], '',
             '| Сотрудник | Всего | Совпали | Проверить |', '|---|---:|---:|---:|']
    for person, counts in result['person_status_counts'].items():
        lines.append(f"| {person} | {sum(counts.values())} | {counts.get('OK', 0)} | {counts.get('REVIEW', 0)} |")
    lines += ['', '## Требуют проверки', '']
    for item in result['items']:
        if item['status'] not in ('REVIEW', 'BACKDATED'):
            continue
        lines += [f"### {item['person']} · [{item['code']}]({item['url']})", '',
                  f"{item['rooms']} комн. · {item['area']} м² · {item['price']} (валюта {item['currency']}). {item['address']}", '', item['reason'], '']
        candidates = item['bir_room_area_candidates']
        if candidates:
            lines.append('Bir, точные комнаты и площадь: ' + '; '.join(
                f"{b['house']}, кв. {b['unit']}, {b['area']} м², спеццена {b['special_price_eur']} EUR, ID {b['id']}" for b in candidates))
        else:
            lines.append('Ближайшие площади — только подсказки, не соответствия: ' + '; '.join(
                f"{b['house']}, {b['area']} м², спеццена {b['special_price_eur']} EUR" for b in item['nearest_area_hints_not_matches']))
        lines.append('')
    OUT.with_suffix('.md').write_text('\n'.join(lines), encoding='utf-8')
    summary = os.getenv('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as f:
            f.write('\n'.join(lines))


def run():
    from realt_test.github_store import GitHubState
    from realt_test.bir_snapshot import load as load_bir_snapshot
    checkpoint=None;checkpoint_db=None
    if os.getenv('REALT_CONTINUOUS') == '1':
        from realt_test.incremental import load, source as incremental_source, BudgetPause
        checkpoint_db=GitHubState()
        previous=load(checkpoint_db)
        try:
            checkpoint,source=incremental_source(previous)
        except BudgetPause as pause:
            result={'items':[],'tracked_people':list(TRACKED.values()),'person_status_counts':{},
                    'checked':0,'coverage_warning':str(pause),'bir_checked_at':'','status_counts':{},
                    'source':{},'budget_paused':pause.budget,'checked_at':datetime.now(timezone.utc).isoformat()}
            write_reports(result)
            print(json.dumps({'budget_paused':pause.budget},ensure_ascii=False))
            return
        if source['unchanged']:
            if previous.get('pending_result'):
                write_reports(previous['pending_result'])
            else:
                write_reports({'items':[],'tracked_people':list(TRACKED.values()),'person_status_counts':{},
                    'checked':0,'coverage_warning':'Этот снимок уже обработан','bir_checked_at':'',
                    'status_counts':{},'source':source})
            print(json.dumps({'source_unchanged':True,'new_snapshot_processed':False}))
            return
        rows=list(checkpoint['rows'].values())
        from realt_test.policy import created_in_window
        from realt_test.sources import created_since_baseline
        rows=[r for r in rows if created_since_baseline(r.get('createdAt')) or r.get('material_edits')]
    else:
        rows, source = load_realt()
    bir, checked = load_bir_snapshot()
    if not bir:
        raise RuntimeError('Bir snapshot is empty; audit aborted')
    result = audit(rows, bir, checked, source)
    result["notification_paused"]=bool(source.get("baseline_only"))
    if checkpoint is not None:
        old_status=previous.get('last_status',{})
        for item in result['items']:
            if item['status']=='OK' and old_status.get(item['uuid'])=='REVIEW' and item.get('present_in_latest_snapshot'):
                item['status']='RESOLVED'
                item['reason']='Предыдущее расхождение устранено: комнаты, точная площадь и спеццена совпали'
        result['status_counts']=dict(Counter(x['status'] for x in result['items']))
        result['person_status_counts']={p:dict(Counter(x['status'] for x in result['items'] if x['person']==p)) for p in TRACKED.values()}
        checkpoint['last_status']={x['uuid']:x['status'] for x in result['items']}
        checkpoint['pending_result']=result
        from realt_test.incremental import save
        save(checkpoint_db,checkpoint)
    write_reports(result)
    print(json.dumps({k: v for k, v in result.items() if k not in {'items', 'source'}}, ensure_ascii=False))


if __name__ == '__main__':
    run()
