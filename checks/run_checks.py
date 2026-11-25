"""Run the check set and print how many emails get the expected decision.

  python checks/run_checks.py --offline         fields read by hand: tests rules and routing, no key needed
  python checks/run_checks.py                   the model reads each email (needs OPENROUTER_API_KEY in .env)
  python checks/run_checks.py --url https://your-app.vercel.app      same, against the live deployment
"""
import argparse
import csv
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.data import sample_emails  # noqa: E402
from agent.graph import run_email     # noqa: E402


def outcome(result: dict) -> str:
    """Claim emails: the decision of each line, joined. Anything else: the overall decision."""
    lines = result.get("lines") or []
    return ";".join(ln["decision"] for ln in lines) if lines else result["decision"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use fields read by hand instead of the model")
    ap.add_argument("--url", help="run against a deployed URL instead of local code")
    args = ap.parse_args()

    emails = {e["email_id"]: e for e in sample_emails()}
    by_hand = json.loads((ROOT / "checks" / "read_by_hand.json").read_text())
    rows = list(csv.DictReader(open(ROOT / "checks" / "check_set.csv", newline="")))
    passed = 0
    for row in rows:
        e = emails[row["email_id"]]
        day = datetime.strptime(e["received_date"], "%d-%m-%Y").date().isoformat()
        if args.url:
            body = json.dumps({"email_text": e["body"], "sender_code": e["stockist_code_by_mailbox_rule"],
                               "claim_date": day}).encode()
            req = urllib.request.Request(args.url.rstrip("/") + "/api/claim", data=body,
                                         headers={"Content-Type": "application/json"})
            result = json.load(urllib.request.urlopen(req, timeout=120))
        else:
            result = run_email(e["body"], e["stockist_code_by_mailbox_rule"], day,
                               read=by_hand[row["email_id"]] if args.offline else None)
        got = outcome(result)
        ok = got == row["expected"]
        passed += ok
        print(f"{'PASS' if ok else 'MISS'}  {row['email_id']}  expected {row['expected']:<32} got {got}")
    print(f"\n{passed} of {len(rows)} as expected")


if __name__ == "__main__":
    main()
