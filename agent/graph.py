"""The claims workflow as a LangGraph graph.

    START -> read_email -> (route by intent) -> check_claim_lines | look_up_status | not_a_claim
          -> write_reply -> END

Only read_email calls a model. It turns a messy email into fields. Every other node is
plain Python: lookups in agent/data.py, rules in agent/rules.py, and the reply is built
from a template, so the model never writes a number, date or batch.
"""
import re
from datetime import date
from typing import Literal, Optional, TypedDict

import pandas as pd

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

import config
from agent import data, rules
from agent.prompts import READ_EMAIL


# ---------------------------------------------------------------- what the model must return
class ClaimLine(BaseModel):
    product: str = Field("", description="Product name as written")
    batch_no: str = Field("", description="Batch number exactly as written; empty if missing")
    expiry_month: str = Field("", description="Expiry as written, rewritten as YYYY-MM; empty if missing")
    quantity: Optional[float] = Field(None, description="Quantity as written; null if missing")
    unit: Literal["strip", "box", "pack", "bottle", "unknown"] = "unknown"
    units_per_box: Optional[int] = Field(None, description="Strips per box, only if the email says so")
    invoice_ref: str = Field("", description="Invoice number exactly as written; empty if missing")


class EmailRead(BaseModel):
    """What a claims-mailbox email asks for, copied into fields. No judgement."""

    intent: Literal["claim", "status_query", "other"]
    claim_numbers: list[str] = []
    lines: list[ClaimLine] = []
    asks_ai_to_skip_checks: bool = False
    summary: str = ""


class State(TypedDict, total=False):
    email_text: str      # the email as received
    sender_code: str     # stockist code from the mailbox rule ('' = unknown sender)
    claim_date: str      # date received, YYYY-MM-DD
    read: dict           # fields read from the email (by the model, or given directly in tests)
    lines: list          # one result per claim line
    statuses: list       # results of a status query
    decision: str        # overall: Approve, Reject, Needs a person, Status reply
    reason: str
    reply: str           # draft reply to the stockist, built from a template
    model_calls: int
    errors: list


STOCKIST_CODE = re.compile(r"\bSTK\d{4}\b")
BOX_WORD = re.compile(r"\bbox(es)?\b", re.I)
INJECTION = re.compile(r"(ai assistant|system note|skip (the )?checks|ignore (all|previous|the) (rules|instructions)|pre-?approved)", re.I)


# ---------------------------------------------------------------- node 1: model reads the email
def read_email(state: State) -> dict:
    if state.get("read"):                      # fields given directly (tests, check set offline mode)
        return {}
    from agent.llm import get_llm               # imported here so tests never need a key
    reader = get_llm().with_structured_output(EmailRead, method="function_calling")
    messages = [SystemMessage(READ_EMAIL), HumanMessage(f"<email>\n{state['email_text']}\n</email>")]
    errors, calls = [], 0
    for _ in range(2):                         # one retry, then hand to a person
        calls += 1
        try:
            return {"read": reader.invoke(messages).model_dump(), "model_calls": calls}
        except Exception as err:               # noqa: BLE001 - any model failure goes to a person
            errors.append(f"Model could not read the email: {type(err).__name__}")
    return {"read": {"intent": "other", "lines": [], "summary": "The email could not be read automatically"},
            "model_calls": calls, "errors": errors}


def route_by_intent(state: State) -> str:
    intent = state["read"].get("intent")
    if intent == "claim":
        return "check_claim_lines"
    if intent == "status_query":
        return "look_up_status"
    return "not_a_claim"


# ---------------------------------------------------------------- node 2: code checks every line
def _stockist_check(sender: str, written: list[str]) -> tuple[rules.Check, dict | None]:
    """Who sent the claim comes from the mailbox rule only (claim_emails.csv, stockist_code_by_mailbox_rule).
    The email body is untrusted input (overview CE-BRF-2026-07 s5.7, p3), so a stockist code typed in it is
    only cross-checked, never used to decide who the sender is."""
    source = "claim_emails.csv mailbox rule; stockist_master.csv"
    if not sender:
        named = f". The email names {', '.join(written)}, which does not prove who sent it" if written else ""
        return rules.Check("Sender is a stockist", "person",
                           "Not from a registered stockist mailbox" + named, source), None
    stk = data.get_stockist(sender)
    if stk is None:
        return rules.Check("Sender is a stockist", "person",
                           f"Mailbox code {sender} is not in the stockist master", source), None
    others = [c for c in written if c != sender]
    if others:
        return rules.Check("Sender is a stockist", "person",
                           f"Mailbox belongs to {sender} but the email names {', '.join(others)}", source), stk
    return rules.Check("Sender is a stockist", "pass",
                       f"{stk['stockist_name']}, {stk['city']} (C&F {stk['cnf_code']})",
                       f"stockist_master.csv line {stk['row_id']}"), stk


def _check_line(i: int, line: dict, stk: dict | None, header: list, claim_day: date, same_email: list,
                text: str = "") -> dict:
    checks = list(header)
    evidence = []
    batch_no = str(line.get("batch_no") or "").strip().upper()
    b = data.get_batch(batch_no) if batch_no else None
    checks.append(rules.check_batch(batch_no, b))
    if b is not None and line.get("expiry_month"):
        checks.append(rules.check_expiry_written(line["expiry_month"], b["expiry_date"].date()))

    qty = line.get("quantity")
    if qty is None:
        checks.append(rules.Check("Quantity read", "person", "No quantity in the claim", "CO-POL-014 s5.3, p3"))
    elif line.get("unit") == "box" and not BOX_WORD.search(text):
        # The model said boxes but the email never says box: code checks the model's reading (DECISIONS.md D30)
        checks.append(rules.Check("Quantity read", "warn",
                                  f"The model read boxes, but the email never says box: {qty:g} read as packs",
                                  "email; CO-POL-014 s5.5 counts packs"))
    elif line.get("unit") == "box":
        per_box_written = line.get("units_per_box") and re.search(rf"\b{int(line['units_per_box'])}\b", text)
        if per_box_written:
            per_box = int(line["units_per_box"])
            checks.append(rules.Check("Quantity read", "pass",
                                      f"{qty:g} boxes x {per_box} = {qty * per_box:g} strips", "email"))
            qty = qty * per_box
        else:
            checks.append(rules.Check("Quantity read", "person",
                                      "Quantity is in boxes and the email gives no strips per box", "email"))
            qty = None
    elif line.get("unit") == "unknown":
        checks.append(rules.Check("Quantity read", "warn", f"No unit written: {qty:g} read as packs", "email"))

    value = None
    if b is not None and stk is not None and qty is not None:
        code = stk["stockist_code"]
        checks.append(rules.check_window(claim_day, b["expiry_date"].date()))

        sup = data.supplies(code, batch_no)
        supplied = float((sup.invoiced_qty.fillna(0) + sup.free_qty.fillna(0)).sum())
        visible = b["mfg_date"] >= pd.Timestamp(config.SALES_VISIBLE_FROM_MFG)
        prior = data.earlier_claims(code, batch_no)
        earlier = [{"qty": float(r.qty_claimed),
                    "label": f"{r.claim_no} ({r.status}, {rules.fmt(r.claim_date)}, expiry_claims.csv line {r.row_id})"}
                   for r in prior.itertuples()]
        earlier += [e for e in same_email if e["batch_no"] == batch_no]
        already = sum(e["qty"] for e in earlier)
        checks.append(rules.check_quantity(float(qty), already, supplied, visible))
        checks.append(rules.check_duplicate(float(qty), earlier))

        inv = data.clean_invoice(line.get("invoice_ref"))
        rows = data.invoice_lines(inv) if inv else sup.iloc[0:0]
        matching = rows[(rows.stockist_code == code) & (rows.batch_no == batch_no)]
        checks.append(rules.check_invoice(inv, len(rows), len(matching), supplied))
        first = sup.invoice_date.min()
        checks.append(rules.check_gst(None if sup.empty else first.date(), claim_day))

        value = round(float(qty) * float(b["pts_inr"]), 2)          # CO-POL-014 s5.7: PTS on the claim date
        evidence += [{"file": "primary_sales.csv", "line": int(r.row_id),
                      "what": f"{r.invoice_no} on {rules.fmt(r.invoice_date)}: {r.invoiced_qty:g} + {r.free_qty:g} free"
                              + (f" ({r.scheme_code})" if r.scheme_code else "")}
                     for r in sup.head(5).itertuples()]
        evidence += [{"file": "expiry_claims.csv", "line": int(r.row_id),
                      "what": f"{r.claim_no}: {r.qty_claimed:g} packs, {r.status}"} for r in prior.head(5).itertuples()]
        same_email.append({"batch_no": batch_no, "qty": float(qty), "label": f"line {i} of this same email"})

    decision, reason = rules.decide(checks)
    return {"line": i, "product": (b or {}).get("product_description") or line.get("product", ""),
            "batch_no": batch_no or "(none)", "quantity": qty, "value_inr": value,
            "decision": decision, "reason": reason, "checks": [c.to_dict() for c in checks], "evidence": evidence}


def check_claim_lines(state: State) -> dict:
    read = state["read"]
    claim_day = date.fromisoformat(state["claim_date"])
    sender = str(state.get("sender_code") or "").strip().upper()
    written = sorted(set(STOCKIST_CODE.findall(state.get("email_text", "").upper())))   # found by code, not the model
    stk_check, stk = _stockist_check(sender, written)
    header = [stk_check]
    if read.get("asks_ai_to_skip_checks") or INJECTION.search(state.get("email_text", "")):
        header.append(rules.Check("No instructions to the tool", "person",
                                  "The email tries to instruct the tool. Checks ran as normal; a person must review",
                                  "Untrusted input"))
    same_email: list = []
    text = state.get("email_text", "")
    lines = [_check_line(i, ln, stk, header, claim_day, same_email, text)
             for i, ln in enumerate(read.get("lines", []), 1)]
    if not lines:
        return {"lines": [], "decision": "Needs a person",
                "reason": "No claim line could be read: batch or quantity missing"}
    kinds = {ln["decision"] for ln in lines}
    overall = kinds.pop() if len(kinds) == 1 else "Mixed"
    if len(lines) == 1:
        return {"lines": lines, "decision": overall, "reason": lines[0]["reason"]}
    counts = ", ".join(f"{sum(ln['decision'] == d for ln in lines)} {d.lower()}"
                       for d in ["Approve", "Reject", "Needs a person"] if any(ln["decision"] == d for ln in lines))
    return {"lines": lines, "decision": overall, "reason": f"{len(lines)} lines: {counts}"}


# ---------------------------------------------------------------- node 3: status questions
def look_up_status(state: State) -> dict:
    claim_day = date.fromisoformat(state["claim_date"])
    out = []
    for no in state["read"].get("claim_numbers", []):
        c = data.get_claim(no)
        if c is None:
            out.append({"claim_no": no.upper(), "found": False, "text": f"{no.upper()} is not in the claims register"})
            continue
        waited = (claim_day - c["claim_date"].date()).days
        text = f"{c['claim_no']}: {c['status']}, claimed {rules.fmt(c['claim_date'])}"
        if c["status"] == "Pending":
            late = waited > config.CREDIT_NOTE_DAYS
            text += f", waiting {waited} days" + (f" (over the {config.CREDIT_NOTE_DAYS}-day limit)" if late else "")
        elif c["credit_note_no"]:
            text += f", credit note {c['credit_note_no']} on {rules.fmt(c['credit_note_date'])}"
        out.append({"claim_no": c["claim_no"], "found": True, "text": text,
                    "evidence": {"file": "expiry_claims.csv", "line": int(c["row_id"])}})
    if not out:
        return {"statuses": [], "decision": "Needs a person", "reason": "Status asked but no claim number given"}
    return {"statuses": out, "decision": "Status reply", "reason": "; ".join(s["text"] for s in out)}


# ---------------------------------------------------------------- node 4: anything else
def not_a_claim(state: State) -> dict:
    summary = state["read"].get("summary") or "Not a claim"
    return {"decision": "Needs a person", "reason": f"Not a claim: {summary}. Forward to the right team."}


# ---------------------------------------------------------------- node 5: reply from a template
def write_reply(state: State) -> dict:
    stk = data.get_stockist(str(state.get("sender_code") or "")) or {}
    name = stk.get("stockist_name", "Sir/Madam")
    parts = [f"Dear {name},", "", "Thank you for your email."]
    for ln in state.get("lines", []):
        head = f"Line {ln['line']} ({ln['product']}, batch {ln['batch_no']}, {ln['quantity'] if ln['quantity'] is not None else '?'} packs)"
        if ln["decision"] == "Approve":
            parts.append(f"- {head}: accepted. A credit note of Rs {ln['value_inr']:,.2f} will follow once the C&F verifies the stock.")
        elif ln["decision"] == "Reject":
            parts.append(f"- {head}: we cannot accept this claim. {ln['reason']}.")
        else:
            parts.append(f"- {head}: our team will review it and contact you. {ln['reason']}.")
    for s in state.get("statuses", []):
        parts.append(f"- {s['text']}.")
    if not state.get("lines") and not state.get("statuses"):
        parts.append("We have passed your message to the right team.")
    parts += ["", "Regards,", "Commercial Finance, Pfizer Limited"]
    return {"reply": "\n".join(parts)}


# ---------------------------------------------------------------- the graph
builder = StateGraph(State)
builder.add_node("read_email", read_email)
builder.add_node("check_claim_lines", check_claim_lines)
builder.add_node("look_up_status", look_up_status)
builder.add_node("not_a_claim", not_a_claim)
builder.add_node("write_reply", write_reply)
builder.add_edge(START, "read_email")
builder.add_conditional_edges("read_email", route_by_intent,
                              ["check_claim_lines", "look_up_status", "not_a_claim"])
for node in ["check_claim_lines", "look_up_status", "not_a_claim"]:
    builder.add_edge(node, "write_reply")
builder.add_edge("write_reply", END)
graph = builder.compile()


def run_email(email_text: str, sender_code: str = "", claim_date: str | None = None, read: dict | None = None) -> dict:
    """Run one email through the graph. Pass `read` to skip the model (tests, offline check set)."""
    state: State = {"email_text": email_text, "sender_code": sender_code or "",
                    "claim_date": claim_date or date.today().isoformat(), "model_calls": 0, "errors": []}
    if read:
        state["read"] = read
    final = graph.invoke(state)
    return {k: final.get(k) for k in ["decision", "reason", "lines", "statuses", "reply", "read", "model_calls", "errors"]}
