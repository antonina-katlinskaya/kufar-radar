CREATE TABLE IF NOT EXISTS state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kufar_ads (
  ad_id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL,
  url TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  price_eur REAL,
  price_byn REAL,
  area REAL,
  rooms INTEGER,
  floor INTEGER,
  address TEXT,
  title TEXT,
  fingerprint TEXT,
  raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_kufar_active ON kufar_ads(active, profile_id);

CREATE TABLE IF NOT EXISTS kufar_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ad_id TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  price_eur REAL,
  price_byn REAL,
  area REAL,
  rooms INTEGER,
  floor INTEGER,
  address TEXT,
  title TEXT,
  fingerprint TEXT NOT NULL,
  raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_kufar_versions_ad ON kufar_versions(ad_id, id DESC);

CREATE TABLE IF NOT EXISTS bir_objects (
  object_key TEXT PRIMARY KEY,
  building_name TEXT,
  official_address TEXT,
  unit_no TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  price_regular_eur REAL,
  price_fast_eur REAL,
  area REAL,
  rooms INTEGER,
  floor INTEGER,
  raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_bir_active ON bir_objects(active);
CREATE INDEX IF NOT EXISTS idx_bir_identity ON bir_objects(building_name, unit_no, floor, area);

CREATE TABLE IF NOT EXISTS bir_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  object_key TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  price_regular_eur REAL,
  price_fast_eur REAL,
  area REAL,
  rooms INTEGER,
  floor INTEGER,
  official_address TEXT,
  raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_bir_versions_object ON bir_versions(object_key, id DESC);

CREATE TABLE IF NOT EXISTS matches (
  ad_id TEXT PRIMARY KEY,
  object_key TEXT NOT NULL,
  confidence TEXT NOT NULL,
  reason TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ad_id TEXT NOT NULL,
  object_key TEXT,
  event_type TEXT NOT NULL,
  field_name TEXT NOT NULL,
  old_value TEXT,
  new_value TEXT,
  bir_value TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  occurred_at TEXT NOT NULL,
  resolved_at TEXT,
  signature TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_active ON events(active, ad_id);
CREATE INDEX IF NOT EXISTS idx_events_signature ON events(signature);

CREATE TABLE IF NOT EXISTS unmatched_state (
  ad_id TEXT PRIMARY KEY,
  consecutive_count INTEGER NOT NULL DEFAULT 0,
  first_seen_at TEXT,
  last_seen_at TEXT
);

CREATE TABLE IF NOT EXISTS source_diagnostics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  url TEXT,
  method TEXT,
  status INTEGER,
  content_type TEXT,
  note TEXT
);
