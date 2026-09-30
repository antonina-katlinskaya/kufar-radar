-- D1 write guards applied to bir-minsk-world-history on 2026-09-30.
-- Purpose: stay below the Workers Free D1 rows-written quota without changing cron schedules
-- or the kufar_profile_cycle_seen mechanism.
--
-- These guards suppress only redundant/noise writes:
--   * Kufar BYN-only FX recalculation updates/events when EUR and listing facts are unchanged.
--   * Bir BYN/raw HTML/raw cell noise events.
--   * Bir raw-only listing blob rewrites.
--   * Repeated missing_checks increments after an object is already absent.
--   * Match proposal updates when only computed_at would change.

CREATE TRIGGER IF NOT EXISTS opt_kufar_skip_fx_only_update
BEFORE UPDATE ON kufar_ads_live
WHEN OLD.present IS NEW.present
 AND OLD.price_eur IS NEW.price_eur
 AND OLD.area IS NEW.area
 AND OLD.rooms IS NEW.rooms
 AND OLD.floor IS NEW.floor
 AND OLD.address IS NEW.address
 AND OLD.title IS NEW.title
 AND OLD.url IS NEW.url
 AND OLD.profile_id IS NEW.profile_id
 AND OLD.list_time IS NEW.list_time
 AND OLD.price_byn IS NOT NEW.price_byn
BEGIN
  SELECT RAISE(IGNORE);
END;

CREATE TRIGGER IF NOT EXISTS opt_kufar_skip_price_byn_event
BEFORE INSERT ON kufar_bridge_events
WHEN NEW.event_type='field_changed' AND NEW.field='price_byn'
BEGIN
  SELECT RAISE(IGNORE);
END;

CREATE TRIGGER IF NOT EXISTS opt_bir_skip_noise_events
BEFORE INSERT ON bir_events
WHEN (NEW.event_type='detail_changed' AND NEW.field LIKE '%BYN')
  OR (NEW.event_type='field_changed' AND NEW.field='raw_cells_json')
  OR (NEW.event_type='listing_changed' AND NEW.field='raw_html')
BEGIN
  SELECT RAISE(IGNORE);
END;

CREATE TRIGGER IF NOT EXISTS opt_bir_skip_raw_only_listing_update
BEFORE UPDATE ON bir_objects
WHEN OLD.present=1 AND NEW.present=1
 AND OLD.missing_checks=0 AND NEW.missing_checks=0
 AND OLD.detail_json IS NEW.detail_json
 AND OLD.detail_fetched_at IS NEW.detail_fetched_at
 AND OLD.house IS NEW.house
 AND json_extract(OLD.listing_json,'$.house') IS json_extract(NEW.listing_json,'$.house')
 AND json_extract(OLD.listing_json,'$.number') IS json_extract(NEW.listing_json,'$.number')
 AND json_extract(OLD.listing_json,'$.area') IS json_extract(NEW.listing_json,'$.area')
 AND json_extract(OLD.listing_json,'$.floor') IS json_extract(NEW.listing_json,'$.floor')
 AND json_extract(OLD.listing_json,'$.rooms') IS json_extract(NEW.listing_json,'$.rooms')
 AND OLD.listing_json IS NOT NEW.listing_json
BEGIN
  SELECT RAISE(IGNORE);
END;

CREATE TRIGGER IF NOT EXISTS opt_bir_skip_repeated_missing_update
BEFORE UPDATE ON bir_objects
WHEN OLD.present=0 AND NEW.present=0
 AND NEW.missing_checks>OLD.missing_checks
 AND OLD.house IS NEW.house
 AND OLD.listing_json IS NEW.listing_json
 AND OLD.detail_json IS NEW.detail_json
 AND OLD.first_seen IS NEW.first_seen
 AND OLD.last_seen IS NEW.last_seen
 AND OLD.detail_fetched_at IS NEW.detail_fetched_at
BEGIN
  SELECT RAISE(IGNORE);
END;

CREATE TRIGGER IF NOT EXISTS opt_kufar_skip_unchanged_proposal_update
BEFORE UPDATE ON kufar_match_proposals
WHEN OLD.proposed_bir_id IS NEW.proposed_bir_id
 AND OLD.level IS NEW.level
 AND OLD.candidate_count IS NEW.candidate_count
 AND OLD.address_count IS NEW.address_count
 AND OLD.area IS NEW.area
 AND OLD.rooms IS NEW.rooms
 AND OLD.floor IS NEW.floor
 AND OLD.address IS NEW.address
BEGIN
  SELECT RAISE(IGNORE);
END;
