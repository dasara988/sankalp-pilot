# Decision log

Each design decision in this pilot, the evidence behind it, and the option it rules out. The project brief asks for this log ("A decision log: the panel will ask why you skipped the obvious", brief p5).

**Sources used**

| Short name | Document |
|---|---|
| Brief | Project 1 brief (FDE Academy), pages 1–8 |
| Guide | Build and deploy guide (FDE Academy), pages 1–7 |
| Overview | Company and channel overview CE-BRF-2026-07, pages 1–5 |
| Policy | CO-POL-014 v4.2 Trade terms and returns policy, pages 1–6 |
| C&F agreement | SC-AGR-CF-003 C&F agreement and SOP |
| Interviews | Stakeholder interview notes CE-SNK-NOTE-01 |
| QBR | QBR finance and MIS pack, with minutes |
| Data | The seven CSVs in `data/`. The figures come from `sankalp_discovery.py` (discovery work) or from this repo's code |
| CGST s34 | CGST Act 2017, section 34, on the CBIC tax information portal (taxinformation.cbic.gov.in), read 22 Nov 2026 |

**Type** says what a decision rests on: **Data** (a figure from the CSVs), **Policy** (a numbered clause), **Brief** (a rule of the assignment), or **Judgement** (a design choice where the sources leave room). Judgement calls are labelled so the panel can challenge them.

---

## A. What to build, and for whom

### D01 · The first user is the claims desk in Commercial Finance
- **Type:** Data + Interviews
- **Decision:** The claims checker serves Neha Bansal's two claims executives. Their weekly decision: credit, reject or send each claim to a person.
- **Evidence:**
  - Two people settle every claim, using a spreadsheet register (Interviews, #4 Neha Bansal).
  - They cannot check claims against sales history (QBR minutes, item 2).
  - 61 duplicate credits worth ₹11.1 lakh: same stockist, batch and quantity credited again (Data, `expiry_claims.csv`).
  - 64 claims worth ₹10.7 lakh credited more than 90 days after expiry, which Policy s5.2 forbids.
  - Claim to credit note takes 45 days on average against a 30-day limit (Policy s5.6); 76% are late.
  - 360 claims worth ₹95.9 lakh were pending on 30 Sep 2026.
  - 30 real claim emails are in `claim_emails.csv`, so the pilot can be tested on real inputs.
- **Not chosen:** "Management" as the user. Brief p5: "'Management' is not a user."

### D02 · The second user is supply-chain planning
- **Type:** Data + Interviews
- **Decision:** The stock health page serves Kavita Rao's planners and the Kolkata regional manager (Subhajit Banerjee).
- **Evidence:**
  - Kavita Rao wants "not another forecast. I need to know where the stock is going to expire before it does" (Interviews, #2).
  - Kolkata dispatched 52–92% of value each month from a newer batch while an older one sat in stock (Data, from Mar 2026). Every other C&F was at 0%.
  - Kolkata stock below 60% shelf life grew from ₹6.1 lakh (Dec 2025) to ₹117.9 lakh (Sep 2026).
  - On 30 Sep 2026, Lucknow had 23 of 36 SKUs at zero stock.
- **Not chosen:** a separate app. Brief p2: "One LangGraph workflow can serve more than one problem and more than one user."

### D03 · Do not build the AI forecasting tool the CFO asked for
- **Type:** Data + Brief
- **Decision:** Recommend against buying or building a forecasting tool now.
- **Evidence:**
  - SKUs without a scheme sell evenly across the quarter (33/33/34% by month) and come back at about 0.45% of sales (Data).
  - Scheme SKUs book 52% of the quarter in month 3, and their claims rose to 5.71% of sales (Tier A, H1 FY27).
  - National stock cover is 1.74 months, inside the 2-month norm (C&F agreement Sch 2 s2.2). The shortage is in the split between C&Fs, not the national total.
  - Brief p5 lists "Training your own ML models" as out of scope unless argued with evidence. The evidence points away from it.
- **Not chosen:** a demand-sensing pilot.

### D04 · The pilot covers problem 5 (claims) and supports 3 and 4 (stock); problems 1 and 2 stay as recommendations
- **Type:** Brief + Judgement
- **Decision:** Problems 1 (scheme incentives) and 2 (free goods against the circular) are bigger in rupees, but they are fixed in the sales incentive plan and in SAP billing. They are in the discovery note and deck, not in the pilot.
- **Evidence:**
  - Brief p5 lists "Writing to the client's systems" as out of scope; free goods are granted in SAP billing.
  - Brief p5 asks for "a named role and a weekly decision". The claims desk has one every week; the incentive plan changes once a year.
- **Judgement:** choosing the claims workflow is a scoping call, made because the pack holds real claim emails to test on and a person can act on the output the same day.

---

## B. Where the model is used, and where it is not

### D05 · The model only reads the email into fields; code makes every decision
- **Type:** Brief
- **Decision:** One model step (`read_email`). Every rule, lookup, decision and reply is plain Python.
- **Evidence:** Brief p4 table: code does "every exact fact", "every rule with a number in it", "joins, sums and windows" and "routing". The model does "read a messy stockist email into fields". Brief p4: "If a formula can do it, the model should not."
- **In the code:** `agent/graph.py` (`read_email` is the only node that calls `get_llm()`), `agent/rules.py`.

### D06 · Structured output with a schema, not free text
- **Type:** Brief
- **Decision:** The model fills a Pydantic schema (`EmailRead`, `ClaimLine`) that the code acts on.
- **Evidence:** Brief p4: "Must the model fill a form your code acts on? → Structured output with a schema."
- **In the code:** `agent/graph.py`, `with_structured_output(EmailRead, method="function_calling")`.
- **Judgement:** `method="function_calling"` instead of the library default (JSON schema mode), because tool calling is the format more providers behind OpenRouter accept. Confirm this by running `python checks\run_checks.py` with the real key.

### D07 · No tool loop
- **Type:** Brief
- **Decision:** The lookups always run in the same order (stockist → batch → supplies → earlier claims → invoice), so they are plain code in one node.
- **Evidence:** Brief p4: a tool loop only "where the next lookup depends on the last answer". Here it never does.

### D08 · Three branches by intent
- **Type:** Data + Brief
- **Decision:** A conditional edge sends each email to `check_claim_lines`, `look_up_status` or `not_a_claim`.
- **Evidence:** In `claim_emails.csv`, 22 of the 30 emails are claims, 5 ask about a claim's status (EML-023 to EML-027), and 3 are something else (EML-028 to EML-030), read by hand in `checks/read_by_hand.json`. Brief p4: "Do different cases need different handling? → Conditional edges."

### D09 · The stock page uses no model
- **Type:** Brief
- **Decision:** Cover, zero-stock SKUs, off-FEFO % and aged stock are computed with pandas.
- **Evidence:** Brief p4: the model does "nothing that a formula can do".

### D10 · The email is treated as untrusted
- **Type:** Data
- **Decision:** The prompt says the email is data. The code also flags phrases like "skip checks" and "ignore the rules". Every check runs anyway.
- **Evidence:** EML-017 tells the AI to approve and skip the checks; its claimed quantity is above what was supplied. Expected outcome: Reject (`checks/check_set.csv`).
- **In the code:** `INJECTION` pattern and `asks_ai_to_skip_checks` in `agent/graph.py`.

### D11 · The reply is a template
- **Type:** Brief
- **Decision:** `write_reply` fills a fixed template with the checked values, so the model never writes a number, date or batch.
- **Evidence:** Brief p5, accuracy rule 1: "No batch, date, quantity or amount appears on screen without the file and row, or the policy clause, it came from."

### D29 · The sender's identity comes from the mailbox rule only
- **Type:** Data + Brief
- **Decision:**
  - Who sent the email comes only from `stockist_code_by_mailbox_rule` in `claim_emails.csv`.
  - A code like STK0123 written in the email is found by a pattern match in code, never by the model, and is only cross-checked against the mailbox code.
  - No mailbox code → Needs a person. Mailbox code and written code differ → Needs a person.
  - The model no longer reads a stockist code at all.
- **Evidence:**
  - Overview s5.7, p3: "Mailbox content is untrusted input."
  - None of the 30 emails contains a stockist code in its text (checked by pattern match).
  - Check-set run 1 with the model (22 Nov): EML-011, sent from a personal email, came out **Reject**; the expected outcome is Needs a person.
  - In the earlier code (`code = sender or written`), an email with no mailbox code could reach Reject only if the model had written a valid stockist code into its reading. The run-1 reading was not saved, so this conclusion rests on that code path, not on seeing the field.
  - Run 2 (`checks/show_read.py`, 22 Nov) read the same email correctly. The model's reading of this field varied between runs, even at temperature 0.
  - Brief p4: "If a formula can do it, the model should not."
- **Tests:** `test_code_written_in_the_email_does_not_prove_the_sender`, `test_mailbox_and_email_naming_different_stockists_goes_to_a_person`.

### D30 · Code checks the model's "boxes" reading against the email text
- **Type:** Data + Policy
- **Decision:**
  - If the model says a quantity is in boxes but the email never contains the word "box", the quantity is read as packs, with a warning.
  - If the model gives a number of strips per box, that number must appear in the email. Otherwise the line goes to a person.
- **Evidence:**
  - `checks/show_read.py` on EML-002 (22 Nov): the model read the unit as "box" on all three lines. The email has only a column headed "Qty" and never says box. All three lines went to a person; the expected outcome is Approve.
  - Policy s5.5, p3 counts the quantity limit in packs. The check set, agreed by hand, reads a quantity with no unit as packs with a warning.
  - Replay: that exact model reading, run through the new code, gives Approve, Approve, Approve.
- **Risk:** an email that says "boxes" only in another language would be read as packs: a lower quantity, with a warning. None of the 30 emails does this. EML-005 is Hindi written in Roman script and says "strip".
- **Tests:** `test_model_says_boxes_but_email_never_says_box`, `test_strips_per_box_not_written_goes_to_a_person`.

---

## C. The rules

Every limit lives in `config.py` with its page. `tests/test_rules.py` tests each one just below, at and just above the limit.

| # | Rule | Limit | Source | Result if broken |
|---|---|---|---|---|
| D12 | Claim window | 90 days before expiry to 90 days after | Policy s5.2, p3 | Reject |
| D13 | Quantity | Total claimed ≤ invoiced + free to that stockist for that batch | Policy s5.5, p3 | Reject |
| D14 | Duplicate | Same stockist, batch and quantity already Pending or Credited, or earlier in the same email | Policy s5.6, p4 ("check for an earlier claim on the same stockist and batch") | Reject |
| D15 | Invoice reference | The quoted invoice must carry that batch for that stockist. No invoice quoted → written Area Manager approval needed | Policy s5.3, s5.4 (added in v4.2), p3 | Reject if wrong; Needs a person if missing |
| D16 | Claim value | Quantity × PTS from `sku_master.csv` | Policy s5.7, p4; Overview s5.1, p3: "All valuation for Project Sankalp uses these PTS and MRP values" | — |

### D17 · A batch is never guessed or corrected
- **Type:** Brief + Data
- **Decision:** Batch numbers must match `batch_master.csv` exactly. A batch that isn't found goes to a person.
- **Evidence:**
  - Brief p2: "An invented invoice or batch makes it wrong on paper."
  - Brief p5, accuracy rule 2: "A guess counts as a failure, even when it happens to be right."
  - EML-007 writes K23O0830, with the letter O in place of a zero. Expected outcome: Needs a person.

### D18 · Batches made before Mar 2024 go to a person
- **Type:** Data
- **Decision:** For older batches, the quantity check can't be done, so the line goes to a person.
- **Evidence:**
  - Sales data starts on 1 Apr 2024 (Overview s5.4, p3; `primary_sales.csv` runs 2024-04-01 to 2026-09-30).
  - The batch master covers batches made from Oct 2023 (Overview s5.2, p3).
  - 971 claim rows name batches that aren't in the batch master.
- **In the code:** `SALES_VISIBLE_FROM_MFG = "2024-03-01"` in `config.py`.

### D19 · A wrongly written expiry is a warning, not a rejection
- **Type:** Data + Judgement
- **Decision:** If the email's expiry differs from the batch master, the batch master date is used and the line carries a warning.
- **Evidence:** `batch_master.csv` is the system record (Overview s5.2). EML-012 writes Mar 2027 for a batch the master dates Sep 2026. Expected outcome: Approve with a warning.
- **Judgement:** warning rather than reject, because the batch number already identifies the expiry exactly.

### D20 · The GST date is a warning for Finance, not a rejection
- **Type:** Policy + Law
- **Decision:** If today is past the CGST s34(2) date for the original supply, the line says so and leaves the GST treatment to Finance.
- **Evidence:**
  - CGST s34(2): the credit note must be declared by 30 November after the end of the financial year of supply, or by the annual return date if earlier. "November" replaced "September" by Finance Act 2022, s102, effective 1 Oct 2022 (Notification 18/2022-CT, 28 Sep 2022). Read on the CBIC portal, 22 Nov 2026.
  - CO-POL-014 doesn't make this a reason to reject a claim. It is a tax question, not a claim-validity rule.
- **Limit:** the pilot uses 30 November only. The annual return filing date isn't in the data pack, so the "whichever is earlier" part can't be checked.

### D21 · How a decision is reached
- **Type:** Brief
- **Decision:** Any **fail** → Reject. Otherwise any **person** → Needs a person. Otherwise → Approve. A **warn** never blocks.
- **Evidence:**
  - Brief p5, accuracy rule 2: "If the data cannot answer, the tool says 'not found' or 'needs a person'."
  - Brief p4: "Does the outcome move money or stock? → A named person decides." So Approve is a recommendation; a claims executive still approves every credit note.

---

## D. Data handling

### D22 · Clean the extracts before using them
- **Type:** Data
- **Decision:**
  - Remove exactly repeated rows: 746 in `primary_sales.csv`, leaving 93,063; 23 in `expiry_claims.csv`, leaving 4,503.
  - Sum stock rows per C&F and batch, because one batch can sit in several storage locations.
  - Read three date formats, strip spaces, and upper-case codes.
- **Evidence:** After this cleaning, primary sales, free goods %, claims % and C&F inventory match the QBR scorecard (`sankalp_discovery.py`, section F1).
- **In the code:** `agent/data.py`. Each row keeps its CSV line number (`row_id`), so every figure on screen links to its row.

### D23 · Load the CSVs once, in memory
- **Type:** Brief
- **Decision:** pandas loads the seven files once per process (`lru_cache`). No CSV goes into a prompt.
- **Evidence:** Brief p5: "Load CSVs once. Use pandas in memory. Never paste a CSV into a prompt." Brief p5 lists retrieval and vector stores as out of scope.

---

## E. Stack and deployment

### D24 · LangGraph, FastAPI, plain HTML, Vercel
- **Type:** Brief + Guide
- **Decision:** The workflow is a LangGraph `StateGraph`. The API is one FastAPI app, the page is plain HTML/CSS/JS, and it is hosted on Vercel Hobby.
- **Evidence:**
  - Brief p3: "One fixed requirement: the workflow is a LangGraph graph."
  - Brief p3: the recommended path is "starter: FastAPI, plain HTML", deployed on Vercel. "No marks for a fancier stack."

### D25 · Model `openai/gpt-4o-mini` through OpenRouter
- **Type:** Guide
- **Decision:** Use the model the guide sets, through the provider in the starter (`agent/llm.py`).
- **Evidence:**
  - Guide p5 sets `MODEL = openai/gpt-4o-mini`.
  - Price on OpenRouter's model page: $0.15 per million input tokens and $0.60 per million output tokens. At about 1,500 input and 300 output tokens, an email costs about $0.0004.

### D26 · Function region Mumbai (bom1)
- **Type:** Guide
- **Decision:** After the first deploy, set the function region to bom1.
- **Evidence:** Guide p6, step 6: "Move the function to Mumbai."
- **Done:** set in Vercel Settings, Functions, 25 Nov 2026.

### D27 · No `Send` and no `interrupt()`
- **Type:** Brief + Judgement
- **Decision:** These LangGraph features are not used.
- **Evidence:** Brief p3: they "earn credit only when your design needs them".
- **Judgement:** One request handles one email, so there are no parallel items for `Send`. The person's approval happens on the screen after the graph returns, so nothing needs to pause mid-graph.

---

## F. Testing

### D28 · A check set of 20 real emails, with outcomes agreed by hand
- **Type:** Brief
- **Decision:** `checks/check_set.csv` lists 20 emails from `claim_emails.csv`, each with its expected outcome and what it tests. `checks/run_checks.py` runs them three ways: offline (fields read by hand), with the model, and against the live URL.
- **Evidence:** Brief p5, accuracy rule 3: "10 to 20 real records with the right output agreed by hand."
- **Results so far:**
  - 46 unit tests pass.
  - Offline, fields read by hand: 20 of 20.
  - With the model, run 1 (before D29 and D30): 18 of 20. Misses: EML-002 and EML-011.
  - With the model, after D29 and D30: 20 of 20 (25 Nov 2026).
  - Live URL https://sankalp-pilot-iota.vercel.app: 20 of 20 (25 Nov 2026).

---

## G. Known gaps (said openly)

- The pilot doesn't compute fill rate, lost sales or free-goods eligibility. Those are in the discovery note.
- PTS is the current price from `sku_master.csv`, as Overview s5.1 instructs. Price changes over time are not modelled.
- The GST check ignores the annual-return date (see D20).
- The model's reading can vary between runs (EML-011, D29), so run the check set more than once. Checks in code (D29, D30) limit what a misreading can do. The unit tests use a fake model.
- Fictional data. Pfizer Limited is not involved.
