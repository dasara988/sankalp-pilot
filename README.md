# Project Sankalp pilot: claims checker and stock health

A pilot for Pfizer Limited's General Medicines trade channel (fictional teaching case, FDE Academy Project 1).

| Screen | Used by | Weekly decision it supports |
|---|---|---|
| **Claims checker** | Neha Bansal's claims executives, Commercial Finance | Credit, reject or review each near-expiry or expired claim from the claims mailbox |
| **Stock health** | Kavita Rao's planners; Subhajit Banerjee (Kolkata) | Which C&F is short or long, which stock to move, which old lots Kolkata must pick first |

The pilot **recommends only**. A named person approves every credit note and stock transfer, and nothing is written back to SAP.

## How a claim email flows (LangGraph)

```
START -> read_email (model) -> route by intent -> check_claim_lines (code)  -> write_reply (code) -> END
                                               -> look_up_status (code)    ->
                                               -> not_a_claim (code)       ->
```

- **read_email** is the only model step. It copies the email into fields (batch, quantity, unit, invoice, expiry) and never decides. The email is treated as untrusted data.
- **check_claim_lines** finds the stockist, batch and supplies in the data, then runs every rule in `agent/rules.py`.
- **write_reply** builds the reply to the stockist from a template, so the model never writes a number, date or batch.

## Rules and where each comes from

| Rule | Limit | Source |
|---|---|---|
| Sender is a registered stockist | mailbox rule + stockist master | `stockist_master.csv` |
| Batch exists (never guessed or corrected) | exact match | `batch_master.csv` |
| Expiry as written matches the batch master | warning only | `batch_master.csv` |
| Claim window | 90 days before to 90 days after expiry | CO-POL-014 s5.2, p3 |
| Quantity vs supplied | claimed in total ≤ invoiced + free to that stockist | CO-POL-014 s5.5, p3 |
| Not a duplicate | same stockist, batch and quantity not already claimed | CO-POL-014 s5.6, p4 |
| Invoice reference | invoice carries the batch for the stockist; none quoted → Area Manager approval | CO-POL-014 s5.3, s5.4, p3 |
| GST credit-note date | warn after 30 Nov following the FY of supply | CGST Act s34(2) |
| Claim value | quantity × PTS | CO-POL-014 s5.7, p4 |

Every number lives in `config.py` with its page reference. Every design decision and its evidence is in [`DECISIONS.md`](DECISIONS.md). Decision order: any **fail** → Reject; else any **person** → Needs a person; else Approve.

## Run it on your laptop (Windows PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt uvicorn pytest httpx
copy .env.example .env        # then open .env and paste your OpenRouter key
pytest -q                     # 46 tests, no key needed
python checks\run_checks.py --offline   # check set, fields read by hand: 20 of 20
python checks\run_checks.py             # check set with the model reading each email (uses the key)
python checks\show_read.py EML-002      # what the model read from one email, and every check that did not pass
uvicorn app:app --reload      # open http://127.0.0.1:8000
```

## Deploy (Vercel Hobby)

1. Push this folder to a **private** GitHub repository under your own account.
2. On vercel.com: **Add New → Project → Import** the repository. Framework preset: **FastAPI**.
3. Add environment variables `OPENROUTER_API_KEY` and `MODEL` = `openai/gpt-4o-mini`, then **Deploy**.
4. Open `https://<your-app>.vercel.app/api/health`: you want `"ok": true` and `"model_key_set": true`.
5. Settings → Functions → Function Region → **bom1 (Mumbai)**, then redeploy.
6. Run the check set against the live URL: `python checks\run_checks.py --url https://<your-app>.vercel.app`

## Folder

```
DECISIONS.md        every design decision, with its evidence
app.py              API routes only: /api/health, /api/samples, /api/claim, /api/stock
config.py           every policy number, with its page reference
agent/llm.py        the model provider (OpenRouter), in one place
agent/data.py       loads and cleans the 7 CSVs once; exact lookups with CSV line numbers
agent/rules.py      the rules as plain Python, each tested
agent/graph.py      LangGraph state, nodes and edges
agent/stock.py      stock health by C&F (code only)
agent/prompts.py    the one prompt
data/               the 7 CSVs from the data pack
public/             index.html, app.js, style.css (no frameworks)
tests/              test_rules.py, test_data.py, test_graph.py, test_api.py
checks/             check_set.csv, read_by_hand.json, run_checks.py
```

## Cost per run

One model call per email (about 1,500 tokens in, 300 out with `openai/gpt-4o-mini`); a retry only if the call fails. Everything else is code. The stock page uses no model.

## Known limits

- Batches made before Mar 2024 may have been supplied before the sales extract starts (Apr 2024), so quantity can't be checked and the line goes to a person.
- Fill rate and lost sales are in the discovery note, not in this pilot.
- Fictional data. Pfizer Limited is not involved.
