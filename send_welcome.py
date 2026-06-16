#!/usr/bin/env python3
"""Send the new-subscriber welcome email.

Two modes, selected by environment variable:

  USER MODE  (WELCOME_UID set) — used by the auto-send Cloud Function
             (repository_dispatch) and the manual "Send welcome" admin button,
             both via welcome-send.yml. Looks the user up in Firestore, sends
             the welcome once, and stamps `welcomedAt`. Skips the admin account,
             unsubscribed users, users with no resolvable email, and anyone
             already welcomed (unless welcomedAt has been cleared first, which
             is exactly what the manual-resend Cloud Function does).

  TEST MODE  (TEST_EMAIL set) — used by welcome-test.yml to preview how the
             email lands. Sends to one address with no Firestore lookup and no
             welcomedAt stamp.

The body comes from build_welcome_email.build(). The send reuses senders.py so
the welcome carries the same per-recipient signed unsubscribe link and the
one-click List-Unsubscribe header as the Monday briefing — a single footer, not
two (we pass the signed link into the builder and skip senders' footer-append).

Env vars:
  GMAIL_SA_JSON              service-account JSON for Gmail domain-wide delegation
  UNSUBSCRIBE_SECRET         HMAC secret for unsubscribe tokens
  FIREBASE_SERVICE_ACCOUNT   service-account JSON for Firestore (USER MODE only)
  WELCOME_UID                user UID to (re)send to            (USER MODE)
  TEST_EMAIL / TEST_NAME     recipient + first name             (TEST MODE)

Exit codes:
  0 — sent, or deliberately skipped (admin / unsubscribed / already-welcomed)
  1 — a send was attempted and failed
  2 — fatal config error before any send (missing env, user not found)
"""
from __future__ import annotations

import datetime as dt
import html as _html
import json
import os
import sys

import build_welcome_email
import senders

ADMIN_EMAILS = {"jc@jezcartwright.com"}
SUBJECT = "Welcome to the Performance Intelligence Weekly Briefing"


def _build_firestore():
    """Build a Firestore client from FIREBASE_SERVICE_ACCOUNT (mirrors publish)."""
    from google.cloud import firestore
    from google.oauth2 import service_account

    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if not raw:
        print("FIREBASE_SERVICE_ACCOUNT env var is missing.", file=sys.stderr)
        sys.exit(2)
    info = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(info)
    return firestore.Client(project=info["project_id"], credentials=creds)


def _resolve_email(data: dict) -> str:
    return (
        (data.get("basicProfile") or {}).get("email")
        or (data.get("profile") or {}).get("email")
        or data.get("email")
        or ""
    ).strip()


def _resolve_first_name(data: dict) -> str:
    pp = data.get("profile") or {}
    bp = data.get("basicProfile") or {}
    first = (pp.get("firstName") or "").strip()
    if first:
        return first
    display = (bp.get("displayName") or pp.get("displayName") or "").strip()
    if display:
        return display.split()[0]
    return "there"


def _send(uid: str, email: str, first_name: str) -> bool:
    """Send one welcome. Single signed footer + one-click List-Unsubscribe.

    Returns True on success. Reuses senders.py helpers so the unsubscribe link
    and headers match the Monday briefing exactly.
    """
    unsub = senders.make_unsubscribe_url(uid, email)
    body_html = build_welcome_email.build(first_name, unsub)
    message = senders._build_message_with_headers(
        to=email, subject=SUBJECT, body_html=body_html,
        extra_headers={
            "List-Unsubscribe": f"<{unsub}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )
    from mailer import _build_service
    service = _build_service()
    result = service.users().messages().send(userId="me", body=message).execute()
    print(f"  sent welcome to {email} (id {result.get('id', '?')})")
    return True


def run_test() -> int:
    email = os.environ.get("TEST_EMAIL", "").strip()
    name = os.environ.get("TEST_NAME", "").strip() or "there"
    if not email:
        print("TEST_EMAIL is empty.", file=sys.stderr)
        return 2
    print(f"TEST MODE — sending welcome to {email} (greeting: {name})")
    try:
        _send("welcome-test", email, name)
    except Exception as e:  # noqa: BLE001
        print(f"  test send FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


def run_user() -> int:
    uid = os.environ.get("WELCOME_UID", "").strip()
    if not uid:
        print("WELCOME_UID is empty.", file=sys.stderr)
        return 2
    db = _build_firestore()
    snap = db.collection("users").document(uid).get()
    if not snap.exists:
        print(f"User {uid} not found in Firestore.", file=sys.stderr)
        return 2
    data = snap.to_dict() or {}

    email = _resolve_email(data)
    if not email:
        print(f"  user {uid} has no resolvable email — skipping.")
        return 0
    if email.lower() in ADMIN_EMAILS:
        print(f"  {email} is an admin address — skipping welcome.")
        return 0
    if data.get("unsubscribed") is True:
        print(f"  {email} is unsubscribed — skipping welcome.")
        return 0
    if data.get("welcomedAt"):
        print(f"  {email} already welcomed at {data.get('welcomedAt')} — skipping.")
        return 0

    first = _resolve_first_name(data)
    print(f"USER MODE — sending welcome to {email} (uid {uid})")
    try:
        _send(uid, email, first)
    except Exception as e:  # noqa: BLE001
        print(f"  send FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    db.collection("users").document(uid).set(
        {"welcomedAt": dt.datetime.now(dt.timezone.utc).isoformat()}, merge=True)
    print(f"  stamped welcomedAt for {uid}")
    return 0


def main() -> int:
    if os.environ.get("TEST_EMAIL", "").strip():
        return run_test()
    return run_user()


if __name__ == "__main__":
    sys.exit(main())
