"""Business rules as plain Python. No model, no data loading: values in, a result out.

Every rule returns a Check: which rule, the result, a one-line reason, and the policy
source. Results:
    pass    the rule is met
    fail    the rule is broken: the claim line is rejected
    person  the data cannot settle it: a person must decide
    warn    allowed, but Finance should know (does not change the decision)
"""
from dataclasses import asdict, dataclass
from datetime import date, timedelta

import config


@dataclass
class Check:
    rule: str
    result: str
    detail: str
    source: str

    def to_dict(self) -> dict:
        return asdict(self)


def fmt(d: date) -> str:
    return d.strftime("%d %b %Y")


def check_batch(batch_no: str, batch: dict | None) -> Check:
    """The batch must exist in the batch master. A miss is never guessed or corrected."""
    if not batch_no:
        return Check("Batch found", "person", "No batch number in the claim", "CO-POL-014 s5.3, p3")
    if batch is None:
        return Check("Batch found", "person",
                     f"Batch {batch_no} is not in the batch master (a typo, or a batch made before Oct 2023)",
                     "batch_master.csv")
    return Check("Batch found", "pass",
                 f"{batch_no} is {batch['product_description']} ({batch['sku_code']}), expiry {fmt(batch['expiry_date'])}",
                 f"batch_master.csv line {batch['row_id']}")


def check_expiry_written(expiry_month: str, expiry: date) -> Check:
    """The expiry the stockist wrote should match the batch master. The batch master wins."""
    master = expiry.strftime("%Y-%m")
    if expiry_month.strip() != master:
        return Check("Expiry as written", "warn",
                     f"Email says {expiry_month}, batch master says {master}; the batch master date is used",
                     "batch_master.csv")
    return Check("Expiry as written", "pass", f"Matches the batch master ({master})", "batch_master.csv")


def check_window(claim_date: date, expiry: date) -> Check:
    """CO-POL-014 s5.2: from 90 days before expiry to 90 days after expiry."""
    opens = expiry - timedelta(days=config.NEAR_EXPIRY_DAYS_BEFORE)
    closes = expiry + timedelta(days=config.EXPIRED_DAYS_AFTER)
    source = "CO-POL-014 s5.2, p3"
    if claim_date < opens:
        return Check("Claim window", "fail", f"Too early: the window opens on {fmt(opens)}", source)
    if claim_date > closes:
        return Check("Claim window", "fail", f"Too late: the window closed on {fmt(closes)}", source)
    return Check("Claim window", "pass", f"Inside the window {fmt(opens)} to {fmt(closes)}", source)


def check_quantity(qty: float, already_claimed: float, supplied: float, supply_visible: bool) -> Check:
    """CO-POL-014 s5.5: claims on a batch may not exceed what Pfizer invoiced, free packs included."""
    source = "CO-POL-014 s5.5, p3"
    if not supply_visible:
        return Check("Quantity vs supplied", "person",
                     "Batch made before Mar 2024: its supply may predate the sales extract", source)
    if supplied <= 0:
        return Check("Quantity vs supplied", "fail", "Pfizer never invoiced this batch to this stockist", source)
    total = qty + already_claimed
    if total > supplied:
        return Check("Quantity vs supplied", "fail",
                     f"{total:g} claimed in all ({already_claimed:g} earlier + {qty:g} now) but only {supplied:g} supplied",
                     source)
    return Check("Quantity vs supplied", "pass",
                 f"{total:g} claimed in all ({already_claimed:g} earlier + {qty:g} now), {supplied:g} supplied", source)


def check_duplicate(qty: float, earlier: list[dict]) -> Check:
    """CO-POL-014 s5.6: check for an earlier claim on the same stockist and batch."""
    source = "CO-POL-014 s5.6, p4"
    same = [c for c in earlier if float(c["qty"]) == float(qty)]
    if same:
        c = same[0]
        return Check("Not a duplicate", "fail",
                     f"Same stockist, batch and quantity already claimed: {c['label']}", source)
    return Check("Not a duplicate", "pass", "No earlier claim with this stockist, batch and quantity", source)


def check_invoice(invoice_ref: str, found_rows: int, matching_rows: int, supplied: float) -> Check:
    """CO-POL-014 s5.3 and s5.4: quote the original invoice, or the C&F verifies with Area Manager approval."""
    if not invoice_ref:
        if supplied > 0:
            return Check("Invoice reference", "person",
                         "No invoice quoted. The batch was supplied to this stockist; s5.4 needs Area Manager approval",
                         "CO-POL-014 s5.4, p3")
        return Check("Invoice reference", "person", "No invoice quoted", "CO-POL-014 s5.3, p3")
    if found_rows == 0:
        return Check("Invoice reference", "person", f"Invoice {invoice_ref} is not in the sales extract",
                     "primary_sales.csv")
    if matching_rows == 0:
        return Check("Invoice reference", "fail",
                     f"Invoice {invoice_ref} exists but does not carry this batch for this stockist", "primary_sales.csv")
    return Check("Invoice reference", "pass", f"Invoice {invoice_ref} carries this batch for this stockist",
                 "primary_sales.csv")


def gst_deadline(supply_date: date) -> date:
    """CGST s34(2): 30 November after the end of the financial year (April to March) of the supply."""
    fy_end_year = supply_date.year + 1 if supply_date.month >= 4 else supply_date.year
    return date(fy_end_year, config.GST_CN_DEADLINE_MONTH, config.GST_CN_DEADLINE_DAY)


def check_gst(first_supply: date | None, today: date) -> Check:
    source = "CGST Act s34(2)"
    if first_supply is None:
        return Check("GST credit-note date", "pass", "No supply date to check", source)
    limit = gst_deadline(first_supply)
    if today > limit:
        return Check("GST credit-note date", "warn",
                     f"Supplied {fmt(first_supply)}: the s34(2) date was {fmt(limit)}. Finance to decide the GST treatment",
                     source)
    return Check("GST credit-note date", "pass", f"Credit note can still be issued with GST until {fmt(limit)}", source)


def decide(checks: list[Check]) -> tuple[str, str]:
    """Any fail -> Reject. Otherwise any person -> Needs a person. Otherwise Approve."""
    fails = [c for c in checks if c.result == "fail"]
    if fails:
        return "Reject", fails[0].detail
    people = [c for c in checks if c.result == "person"]
    if people:
        return "Needs a person", people[0].detail
    return "Approve", "Every rule is met"
