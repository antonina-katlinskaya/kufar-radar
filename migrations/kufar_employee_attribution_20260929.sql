-- Canonical Kufar employee attribution, 2026-09-29.
-- Non-destructive: adds a profile->employee map and a view; also normalizes
-- contact_names for dedicated v7_census profiles so existing consumers that
-- read kufar_profiles get one stable employee name.

CREATE TABLE IF NOT EXISTS kufar_employee_profile_map(
  profile_id TEXT PRIMARY KEY,
  employee_name TEXT NOT NULL,
  confidence TEXT NOT NULL,
  note TEXT,
  updated_at TEXT NOT NULL
);

INSERT INTO kufar_employee_profile_map(profile_id,employee_name,confidence,note,updated_at) VALUES
('11852045','Елена Борискина','confirmed_profile','Dedicated Kufar profile; card names: Елена / Елена Борискина',datetime('now')),
('11077002','Ирина Барашенко','confirmed_profile','Dedicated Kufar profile',datetime('now')),
('11080367','Вероника Хатковская','confirmed_profile','Dedicated Kufar profile; old cards may have empty contact person',datetime('now')),
('11093294','Алёна','confirmed_profile','Dedicated Kufar profile; dominant card name Алёна',datetime('now')),
('11162944','Анна Зенкевич','confirmed_profile','Dedicated Kufar profile',datetime('now')),
('8517496','Анастасия','confirmed_profile','Dedicated Kufar profile',datetime('now')),
('7587469','Эдуард Дусский','confirmed_profile','Dedicated Kufar profile',datetime('now')),
('11079371','Дмитрий Спиридонов','confirmed_profile','Dedicated Kufar profile',datetime('now')),
('8333991','Дарья Иванова','confirmed_profile','Dedicated Kufar profile',datetime('now')),
('7604736','Юлия Русина','confirmed_profile','Dedicated Kufar profile',datetime('now')),
('11721739','Рената Добринец','confirmed_profile','Dedicated Kufar profile',datetime('now')),
('11426419','Марина Жегало','confirmed_profile','Dedicated Kufar profile',datetime('now')),
('11571751','Валерий','confirmed_profile','Dedicated Kufar profile',datetime('now')),
('10704279','Жанна','confirmed_profile','Dedicated Kufar profile',datetime('now')),
('11465011','Татьяна','confirmed_profile','Dedicated Kufar profile',datetime('now')),
('11078751','Екатерина Матиюнас','confirmed_profile','Dedicated Kufar profile',datetime('now')),
('9408059','Ольга Михальченко','confirmed_profile','Dedicated Kufar profile',datetime('now')),
('11358242','Татьяна Булыга','confirmed_profile','Dedicated Kufar profile',datetime('now')),
('9401805','Наталья Сидорова','confirmed_profile','Dedicated Kufar profile',datetime('now')),
('10828532','Галина','confirmed_profile','Dedicated Kufar profile',datetime('now')),
('11384605','Ирина Васильевна','confirmed_profile','Dedicated Kufar profile',datetime('now')),
('11842939','Ирина Шульга','confirmed_profile','Dedicated Kufar profile',datetime('now')),
('11598501','Этажи Realt Общий','shared_profile','Shared Etagi profile used by many employees',datetime('now')),
('8931071','Этажи Realt Общий','shared_profile','Mixed profile: Дарья Иванова / Евгений / empty',datetime('now'))
ON CONFLICT(profile_id) DO UPDATE SET
  employee_name=excluded.employee_name,
  confidence=excluded.confidence,
  note=excluded.note,
  updated_at=excluded.updated_at;

UPDATE kufar_profiles
SET contact_names=(SELECT employee_name FROM kufar_employee_profile_map m WHERE m.profile_id=kufar_profiles.profile_id),
    last_seen=COALESCE(last_seen,datetime('now'))
WHERE source='v7_census'
  AND profile_id IN (SELECT profile_id FROM kufar_employee_profile_map);

DROP VIEW IF EXISTS kufar_ad_employee;
CREATE VIEW kufar_ad_employee AS
SELECT
  k.ad_id,
  k.profile_id,
  COALESCE(m.employee_name,'Сотрудник не установлен') AS employee_name,
  COALESCE(m.confidence,'unknown') AS identity_source,
  (
    SELECT json_extract(j.value,'$.v')
    FROM json_each(k.raw_json,'$.account_parameters') j
    WHERE json_extract(j.value,'$.p')='contact_person'
    LIMIT 1
  ) AS card_contact_person,
  json_extract(k.raw_json,'$.account_id') AS account_id,
  k.title,k.address,k.list_time,k.observed_at,k.present,k.url
FROM kufar_ads_live k
LEFT JOIN kufar_employee_profile_map m ON m.profile_id=k.profile_id;
