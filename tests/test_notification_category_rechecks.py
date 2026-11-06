"""Regression tests: BIR recategorization is not another Kufar violation alert."""

from radar.main import notifiable_new_events


def test_bir_only_category_change_is_not_sent_again():
    # 06 Nov: existence -> area -> existence with the same Kufar card.
    for previous, next_field in [
        ("existence", "area"),
        ("area", "existence"),
        ("combination", "price"),
        ("price", "combination"),
    ]:
        new_events = [{"field_name": next_field, "ad_id": "1093110128"}]
        prior = {previous: {"id": 123, "active": 1}}
        assert notifiable_new_events(new_events, prior, kufar_changed=False) == []
        assert prior[previous]["active"] == 1  # No mutation of stored events.


def test_real_kufar_edit_still_notifies_even_when_violation_is_active():
    events = [{"field_name": "combination", "ad_id": "1093115533"}]
    prior = {"existence": {"active": 1}}
    assert notifiable_new_events(events, prior, kufar_changed=True) is events


def test_first_violation_still_notifies():
    events = [{"field_name": "existence", "ad_id": "new-card"}]
    assert notifiable_new_events(events, {}, kufar_changed=False) is events


def test_service_only_prior_state_does_not_hide_a_new_strict_violation():
    events = [{"field_name": "combination", "ad_id": "x"}]
    assert notifiable_new_events(events, {"review": {"active": 1}}, kufar_changed=False) is events


def test_no_new_event_never_creates_an_alert():
    assert notifiable_new_events([], {"existence": {"active": 1}}, False) == []
