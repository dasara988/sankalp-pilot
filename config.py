"""Every policy number the rules use, with where it comes from.

Change a number here, never inside a prompt or a rule. Each rule in agent/rules.py reads
its limit from this file, and tests/test_rules.py tests the values just below, at and
just above each limit.
"""

POLICY = "CO-POL-014 v4.2 (Trade terms and returns policy)"

# Claim windows: CO-POL-014 section 5.2, page 3
NEAR_EXPIRY_DAYS_BEFORE = 90   # near-expiry window opens 90 days before the expiry date
EXPIRED_DAYS_AFTER = 90        # no claim is accepted more than 90 days after the expiry date

# Quantity limit: CO-POL-014 section 5.5, page 3
# A stockist may not claim more packs of a batch than Pfizer invoiced to it, free packs included.

# Turnaround: CO-POL-014 section 5.6, page 4
CREDIT_NOTE_DAYS = 30          # Commercial Finance raises the credit note within 30 days of receipt

# Shelf life at dispatch: CO-POL-014 section 7.1, page 4
MIN_SHELF_LIFE_SHARE = 0.60    # stock billed must have at least 60% of its shelf life left

# C&F replenishment: SC-AGR-CF-003 Schedule 2 section 2.2
TARGET_COVER_MONTHS = 2.0      # the CDC tops each C&F up to two months of stock

# GST: CGST Act section 34(2), as amended from 1 Oct 2022 (Notification 18/2022-Central Tax)
# A credit note against a supply must be issued by 30 November after the end of the
# financial year in which the supply was made.
GST_CN_DEADLINE_MONTH = 11
GST_CN_DEADLINE_DAY = 30

# Data coverage: company overview CE-BRF-2026-07, sections 5.2 and 5.4, page 3
# Sales start on 1 Apr 2024. Batches made before Mar 2024 may have been sold earlier,
# so their supply cannot be checked from the extract and goes to a person.
SALES_VISIBLE_FROM_MFG = "2024-03-01"
