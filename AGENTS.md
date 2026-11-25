# Instructions for the coding agent

Read this file before every task. Keep it short and keep it true.

## What we are building
Commercial Finance's two claims executives (Neha Bansal's team) check about 200 near-expiry and expired claims a month by hand, so duplicates and out-of-window claims get credited and credit notes take 45 days against a 30-day policy. This pilot reads each claims-mailbox email, checks every claim line against the data and CO-POL-014, and recommends approve, reject or needs a person, with the file line and policy clause behind each check. A second screen shows Supply Chain which C&F is short or long, stock in the wrong place, and Kolkata's off-FEFO picking. The pilot recommends only; people approve.

## Architecture
```
START -> read_email (MODEL) -> route_by_intent -> check_claim_lines (code) -> write_reply (code) -> END
                                               -> look_up_status (code)   ->
                                               -> not_a_claim (code)      ->
```
- read_email: the only model call. Structured output (EmailRead, function calling). Copies fields; never decides. One retry, then a person.
- check_claim_lines: lookups in agent/data.py, rules in agent/rules.py, decision by rules.decide().
- look_up_status: claim number -> register row, or "not in the register".
- write_reply: template, no model.
- agent/stock.py: stock health, code only.

## Rules
- Facts come from agent/data.py, which reads `data/`. The model never writes a batch number, date, quantity or amount that did not come from the email or a lookup.
- Business rules live in plain Python in `agent/rules.py`, each with a pytest test at, just below and just above its limit. Limits live in `config.py` with their page reference.
- One small change per task. Run `pytest -q` and `python checks/run_checks.py --offline` after each change. Do not touch files the task does not need.
- Do not add a database, a vector store, a new framework or a new folder without asking.
- The frontend stays in `public/` as plain HTML, CSS and JavaScript.
- Secrets live only in `.env` locally and in Vercel environment variables. Never commit them.

## How to run
pip install -r requirements.txt uvicorn pytest httpx
pytest -q
python checks/run_checks.py --offline
uvicorn app:app --reload

## Current task
Pilot submitted. Next: run the check set with the model (`python checks/run_checks.py`) and on the live URL (`--url`), and record misses in this section.
