"""The API answers without a real model: a fake reader stands in. No key, no cost."""
from fastapi.testclient import TestClient

import agent.llm
from agent.graph import EmailRead
from app import app

client = TestClient(app)


class FakeReader:
    """Pretends to be the model: returns fields as if it had read the email."""

    def with_structured_output(self, schema, **kwargs):
        return self

    def invoke(self, messages):
        return EmailRead(intent="claim", lines=[{"product": "Linezolid", "batch_no": "L2400579", "quantity": 38,
                                                 "unit": "strip", "invoice_ref": "INV/S01/2507/044588"}])


def test_health():
    assert client.get("/api/health").json()["ok"] is True


def test_claim_runs_the_graph(monkeypatch):
    monkeypatch.setattr(agent.llm, "get_llm", lambda: FakeReader())
    r = client.post("/api/claim", json={"email_text": "Linezolid batch L2400579 38 strips",
                                        "sender_code": "STK0117", "claim_date": "2026-10-16"})
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "Approve" and body["model_calls"] == 1


def test_empty_email_is_refused():
    assert client.post("/api/claim", json={"email_text": "  "}).status_code == 400


def test_samples_and_stock():
    assert len(client.get("/api/samples").json()) == 30
    s = client.get("/api/stock").json()
    kolkata = next(c for c in s["cfas"] if c["cnf_code"] == "CF-E01")
    assert kolkata["off_fefo_pct"] > 50 and s["national_cover_months"] > 1
