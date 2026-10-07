-- REVIEW ONLY. Target: bir-minsk-world-history. Do not execute before approval.
-- Adds lookup indexes; preserves every existing row, trigger and index.
CREATE INDEX IF NOT EXISTS opt_profiles_census_lookup
  ON kufar_profiles(enabled, source, profile_id) WHERE enabled=1 AND source='v7_census';
CREATE INDEX IF NOT EXISTS opt_bir_scans_ok_latest
  ON bir_scans(checked_at DESC, parsed_count) WHERE status='ok';
