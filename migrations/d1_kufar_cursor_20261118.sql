-- Additive, non-unique read-cost index; existing records and audit policy remain unchanged.
CREATE INDEX IF NOT EXISTS idx_kufar_profile_adid_cursor ON kufar_ads(profile_id,ad_id);
