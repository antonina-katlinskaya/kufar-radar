-- Apply to bir-minsk-world-history together with the updated BIR collector.
-- The previous raw-only guard ignored real EUR price changes and repeatedly
-- pushed the same unchanged stored rows to the front of the detail queue.
DROP TRIGGER IF EXISTS opt_bir_skip_raw_only_listing_update;
CREATE TRIGGER opt_bir_skip_raw_only_listing_update
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
 -- Missing metadata must allow writes from the previous deployed collector too.
 AND json_type(OLD.listing_json,'$.prices_eur')='array'
 AND json_type(NEW.listing_json,'$.prices_eur')='array'
 AND json_extract(OLD.listing_json,'$.prices_eur') IS json_extract(NEW.listing_json,'$.prices_eur')
 AND OLD.listing_json IS NOT NEW.listing_json
BEGIN
 SELECT RAISE(IGNORE);
END;
