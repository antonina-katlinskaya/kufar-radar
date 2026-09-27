-- Indexes for the new Bir.by -> Kufar monitoring database.
-- Safe to run repeatedly: every statement uses IF NOT EXISTS.

CREATE INDEX IF NOT EXISTS kufar_bridge_events_time_ad
  ON kufar_bridge_events(observed_at, ad_id);

CREATE INDEX IF NOT EXISTS bir_events_time_object
  ON bir_events(observed_at, object_id);

CREATE INDEX IF NOT EXISTS kufar_proposals_bir
  ON kufar_match_proposals(proposed_bir_id, ad_id);

CREATE INDEX IF NOT EXISTS kufar_proposals_computed_ad
  ON kufar_match_proposals(computed_at, ad_id);

CREATE INDEX IF NOT EXISTS kufar_proposals_ad_level
  ON kufar_match_proposals(ad_id, level, proposed_bir_id);

CREATE INDEX IF NOT EXISTS price_alert_queue_status_id
  ON kufar_price_alert_queue(status, id);

CREATE INDEX IF NOT EXISTS price_alert_state_ad
  ON kufar_price_alert_state(ad_id);
