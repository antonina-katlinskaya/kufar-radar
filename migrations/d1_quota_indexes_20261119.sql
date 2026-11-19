-- D1 free-tier quota fix, 2026-11-19.
-- Matches the exact hot predicates reported by D1 Insights.
CREATE INDEX IF NOT EXISTS idx_bir_objects_active_object_key
  ON bir_objects(active, object_key);

CREATE INDEX IF NOT EXISTS idx_kufar_ads_profile_active_adid
  ON kufar_ads(profile_id, active, ad_id);

CREATE INDEX IF NOT EXISTS idx_kufar_ads_active_adid
  ON kufar_ads(active, ad_id);

CREATE INDEX IF NOT EXISTS idx_events_active_occurred_adid
  ON events(active, occurred_at, ad_id);
