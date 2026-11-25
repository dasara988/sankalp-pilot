"""Show what the model read from data-pack emails, and every check that did not pass.

  python checks/show_read.py EML-002 EML-011

Use it when the check set reports a MISS: it separates a reading problem (the fields are wrong)
from a rule problem (the fields are right but the decision is wrong). Needs OPENROUTER_API_KEY in .env.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.data import sample_emails  # noqa: E402
from agent.graph import run_email     # noqa: E402


def main() -> None:
    emails = {e["email_id"]: e for e in sample_emails()}
    for eid in sys.argv[1:]:
        e = emails[eid.upper()]
        day = datetime.strptime(e["received_date"], "%d-%m-%Y").date().isoformat()
        r = run_email(e["body"], e["stockist_code_by_mailbox_rule"], day)
        print(f"===== {e['email_id']}  mailbox code: '{e['stockist_code_by_mailbox_rule']}'  ->  {r['decision']}")
        print("What the model read:")
        print(json.dumps(r["read"], indent=1, ensure_ascii=False))
        for ln in r.get("lines") or []:
            for c in ln["checks"]:
                if c["result"] != "pass":
                    print(f"  line {ln['line']}: {c['rule']} = {c['result']}: {c['detail']}")
        print()


if __name__ == "__main__":
    main()
