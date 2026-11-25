"""FastAPI entrypoint: routes only, no business logic. Vercel finds the FastAPI instance named `app` here.

Run locally:   uvicorn app:app --reload        then open http://127.0.0.1:8000
On Vercel:     files in public/ are served from the CDN; /api/* reaches this app.
"""
import os
from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from agent.data import sample_emails
from agent.graph import run_email
from agent.stock import stock_health

app = FastAPI(title="Project Sankalp pilot: claims checker and stock health")
ROOT = Path(__file__).resolve().parent


class ClaimRequest(BaseModel):
    email_text: str
    sender_code: str = ""          # stockist code from the mailbox rule; empty if the sender is unknown
    claim_date: str | None = None  # date the email was received, YYYY-MM-DD; today if empty


@app.get("/api/health")
def health():
    """Quick check that the deployment is alive and the key is configured."""
    return {"ok": True, "model_key_set": bool(os.getenv("OPENROUTER_API_KEY"))}


@app.get("/api/samples")
def samples():
    """The 30 emails from the claims mailbox (claim_emails.csv), to try on the page."""
    return sample_emails()


@app.post("/api/claim")
def claim(body: ClaimRequest):
    """Run one email through the LangGraph workflow and return the decision with its evidence."""
    if not body.email_text.strip():
        return JSONResponse({"error": "Paste an email first."}, status_code=400)
    try:
        date.fromisoformat(body.claim_date) if body.claim_date else None
    except ValueError:
        return JSONResponse({"error": "Claim date must look like 2026-10-16."}, status_code=400)
    try:
        return run_email(body.email_text, body.sender_code, body.claim_date)
    except ValueError as err:        # missing key: say so instead of a bare 500
        return JSONResponse({"error": str(err)}, status_code=503)


@app.get("/api/stock")
def stock():
    """Stock health by C&F at the latest month-end (code only, no model)."""
    return stock_health()


@app.get("/")
def index():
    return FileResponse(ROOT / "public" / "index.html")


# On Vercel the public/ folder is served by the platform. Locally nothing serves it, so mount it.
if not os.getenv("VERCEL"):
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=ROOT / "public"), name="public")
