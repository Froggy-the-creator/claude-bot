"""
Local end-to-end test for the WhatsApp bot.

Signs requests the same way Twilio does, so every code path can be
exercised without a tunnel or a deployment.

Usage:
    1. Start the app in another terminal:  python app.py
    2. Run this:                           python test_local.py

Set TEST_LIVE_API=1 to also exercise a real Claude call (costs a few cents).
"""

import os
import requests
from dotenv import load_dotenv
from twilio.request_validator import RequestValidator

load_dotenv()

URL = "http://localhost:5000/bot"
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
ADMIN = next(
    (n.strip() for n in os.getenv("ADMIN_NUMBERS", "").split(",") if n.strip()),
    None,
)
NON_ADMIN = "whatsapp:+6599999999"

validator = RequestValidator(AUTH_TOKEN)

passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


def post(params, sign=True):
    """POST to the webhook, optionally with a valid Twilio signature."""
    headers = {}
    if sign:
        # Twilio signs the full URL plus the sorted POST parameters.
        headers["X-Twilio-Signature"] = validator.compute_signature(URL, params)
    return requests.post(URL, data=params, headers=headers, timeout=60)


print("\n--- config ---")
check("TWILIO_AUTH_TOKEN is set", bool(AUTH_TOKEN), "empty token rejects everything")
check("ADMIN_NUMBERS has an entry", bool(ADMIN), "cannot test the admin path")
if ADMIN:
    check(
        "admin number has whatsapp: prefix",
        ADMIN.startswith("whatsapp:"),
        f"got {ADMIN!r} - Twilio sends whatsapp:+65...",
    )

print("\n--- webhook authentication ---")
r = post({"Body": "hello", "From": NON_ADMIN}, sign=False)
check("unsigned request is rejected", r.status_code == 403, f"got {r.status_code}")

r = requests.post(
    URL,
    data={"Body": "hello", "From": NON_ADMIN},
    headers={"X-Twilio-Signature": "obviously-wrong"},
    timeout=30,
)
check("bad signature is rejected", r.status_code == 403, f"got {r.status_code}")

r = post({"Body": "!usage", "From": NON_ADMIN})
check("valid signature is accepted", r.status_code == 200, f"got {r.status_code}")

print("\n--- admin authorisation ---")
r = post({"Body": "!all", "From": NON_ADMIN})
check("non-admin cannot run !all", "Unknown command" in r.text, r.text[:120])
check("non-admin sees no phone numbers", "whatsapp:+" not in r.text, r.text[:120])

if ADMIN:
    r = post({"Body": "!all", "From": ADMIN})
    check(
        "admin can run !all",
        "Unknown command" not in r.text,
        r.text[:120],
    )

print("\n--- commands ---")
r = post({"Body": "!usage", "From": NON_ADMIN})
check("!usage responds", r.status_code == 200 and "<Message>" in r.text, r.text[:120])

r = post({"Body": "", "From": NON_ADMIN})
check("empty message handled", "Please send a text message" in r.text, r.text[:120])

r = post({"Body": "!USAGE", "From": NON_ADMIN})
check("commands are case-insensitive", "<Message>" in r.text, r.text[:120])

if os.getenv("TEST_LIVE_API") == "1":
    print("\n--- live Claude call (costs money) ---")
    r = post({"Body": "Say the single word: pong", "From": NON_ADMIN})
    check("Claude replies", r.status_code == 200 and "<Message>" in r.text, r.text[:200])
    check(
        "no error fallback returned",
        "Something went wrong" not in r.text,
        "check the app terminal for the traceback",
    )
    print(f"    reply: {r.text[:200]}")
else:
    print("\n--- live Claude call skipped (set TEST_LIVE_API=1 to include) ---")

print(f"\n{passed} passed, {failed} failed\n")
raise SystemExit(1 if failed else 0)
