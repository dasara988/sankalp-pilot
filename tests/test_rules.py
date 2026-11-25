"""Every rule in agent/rules.py, tested just below, at and just above its limit. No data, no model."""
from datetime import date, timedelta

import config
from agent import rules

EXPIRY = date(2026, 9, 30)


# ---- claim window: CO-POL-014 s5.2 (90 days before to 90 days after expiry)
def test_window_opens_exactly_90_days_before():
    assert rules.check_window(EXPIRY - timedelta(days=config.NEAR_EXPIRY_DAYS_BEFORE), EXPIRY).result == "pass"


def test_window_one_day_too_early():
    c = rules.check_window(EXPIRY - timedelta(days=config.NEAR_EXPIRY_DAYS_BEFORE + 1), EXPIRY)
    assert c.result == "fail" and "Too early" in c.detail


def test_window_closes_exactly_90_days_after():
    assert rules.check_window(EXPIRY + timedelta(days=config.EXPIRED_DAYS_AFTER), EXPIRY).result == "pass"


def test_window_one_day_too_late():
    c = rules.check_window(EXPIRY + timedelta(days=config.EXPIRED_DAYS_AFTER + 1), EXPIRY)
    assert c.result == "fail" and "Too late" in c.detail


def test_window_feb_2027_is_too_late_for_a_sep_2026_batch():
    assert rules.check_window(date(2027, 2, 15), EXPIRY).result == "fail"


# ---- quantity: CO-POL-014 s5.5 (never more than invoiced, free packs included)
def test_quantity_at_the_limit_passes():
    assert rules.check_quantity(100, 50, 150, True).result == "pass"


def test_quantity_one_over_the_limit_fails():
    assert rules.check_quantity(101, 50, 150, True).result == "fail"


def test_quantity_never_supplied_fails():
    assert rules.check_quantity(10, 0, 0, True).result == "fail"


def test_quantity_old_batch_goes_to_a_person():
    assert rules.check_quantity(10, 0, 0, False).result == "person"


# ---- duplicate: CO-POL-014 s5.6 (same stockist, batch and quantity claimed before)
def test_same_quantity_is_a_duplicate():
    c = rules.check_duplicate(61, [{"qty": 61, "label": "line 1 of this same email"}])
    assert c.result == "fail" and "line 1" in c.detail


def test_different_quantity_is_not_a_duplicate():
    assert rules.check_duplicate(79, [{"qty": 76, "label": "CLM-1"}]).result == "pass"


def test_no_earlier_claim_is_not_a_duplicate():
    assert rules.check_duplicate(10, []).result == "pass"


# ---- invoice reference: CO-POL-014 s5.3 and s5.4
def test_invoice_matching_passes():
    assert rules.check_invoice("INV/S01/2507/044588", 3, 1, 276).result == "pass"


def test_invoice_without_this_batch_fails():
    assert rules.check_invoice("INV/S01/2507/044588", 3, 0, 276).result == "fail"


def test_invoice_not_in_extract_goes_to_a_person():
    assert rules.check_invoice("INV/X/1", 0, 0, 276).result == "person"


def test_no_invoice_goes_to_a_person_for_area_manager_approval():
    c = rules.check_invoice("", 0, 0, 276)
    assert c.result == "person" and "Area Manager" in c.detail


# ---- GST credit-note date: CGST s34(2)
def test_gst_deadline_for_a_march_supply_is_30_nov_same_year():
    assert rules.gst_deadline(date(2025, 3, 30)) == date(2025, 11, 30)


def test_gst_deadline_for_an_april_supply_is_30_nov_next_year():
    assert rules.gst_deadline(date(2025, 4, 1)) == date(2026, 11, 30)


def test_gst_on_the_deadline_passes_and_a_day_later_warns():
    assert rules.check_gst(date(2025, 4, 1), date(2026, 11, 30)).result == "pass"
    assert rules.check_gst(date(2025, 4, 1), date(2026, 12, 1)).result == "warn"


# ---- decision order
def test_any_fail_rejects_even_with_people_and_warnings():
    checks = [rules.Check("a", "pass", "", ""), rules.Check("b", "person", "x", ""),
              rules.Check("c", "fail", "broken", ""), rules.Check("d", "warn", "", "")]
    assert rules.decide(checks) == ("Reject", "broken")


def test_person_beats_approve():
    assert rules.decide([rules.Check("a", "pass", "", ""), rules.Check("b", "person", "why", "")])[0] == "Needs a person"


def test_warnings_alone_still_approve():
    assert rules.decide([rules.Check("a", "pass", "", ""), rules.Check("b", "warn", "", "")])[0] == "Approve"


# ---- expiry as written vs batch master (warning only; the batch master date is used)
def test_expiry_written_matches():
    assert rules.check_expiry_written("2026-09", EXPIRY).result == "pass"


def test_expiry_written_differs_is_a_warning():
    c = rules.check_expiry_written("2027-03", EXPIRY)
    assert c.result == "warn" and "2027-03" in c.detail
