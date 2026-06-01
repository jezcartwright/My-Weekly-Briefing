"""Monday-publish per-recipient send pipeline.

Reads the edited Monday teaser draft from jc@'s Gmail, strips the reviewer
block, fetches the current active subscriber list from Firestore, and sends
one personalised email per recipient (with a per-recipient unsubscribe link).

Replaces the legacy "send the draft as-is to whoever it's addressed to" flow
that publish-monday.yml previously did.

Env vars expected:
  - GMAIL_SA_JSON         (service-account JSON for Gmail domain-wide delegation)
  - FIREBASE_SERVICE_ACCOUNT (service-account JSON for Firestore)
  - UNSUBSCRIBE_SECRET    (HMAC secret for unsubscribe tokens)

Exit codes:
  0 — all sends succeeded
  1 — at least one send failed (the workflow will mark itself yellow)
  2 — fatal error before any send was attempted (no draft, no subscribers, etc.)
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from typing import Any

import mailer  # for draft find + body extract + reviewer-block strip
import senders  # for send_bulk + per-recipient footer


# --------------------------------------------------------------------------
# Firestore helpers
# --------------------------------------------------------------------------

def _build_firestore():
    """Build a Firestore client from FIREBASE_SERVICE_ACCOUNT env var."""
    from google.cloud import firestore
    from google.oauth2 import service_account

    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if not raw:
        print("FIREBASE_SERVICE_ACCOUNT env var is missing.", file=sys.stderr)
        sys.exit(2)
    info = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(info)
    return firestore.Client(project=info["project_id"], credentials=creds)


def fetch_active_subscribers(db) -> list[dict[str, str]]:
    """Pull active subscribers from Firestore users collection.

    A user is considered active if they exist AND their `unsubscribed` field
    is either missing or False. Returns a list of {uid, email} dicts.
    """
    out: list[dict[str, str]] = []
    for snap in db.collection("users").stream():
        data = snap.to_dict() or {}
        if data.get("unsubscribed") is True:
            continue
        email = data.get("email", "").strip()
        if not email:
            continue
        out.append({"uid": snap.id, "email": email})
    return out


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    # Today's subject prefix — we search for the draft by subject prefix so
    # an edit to the subject in Gmail doesn't break the lookup.
    subject_prefix = os.environ.get(
        "TEASER_SUBJECT_PREFIX",
        "Performance Intelligence Weekly Briefing",
    )

    print("=" * 70)
    print(f"Monday-publish — per-recipient pipeline")
    print(f"  Looking for draft matching subject prefix: {subject_prefix!r}")
    print("=" * 70)

    # 1) Find the draft in jc@'s Gmail
    drafts = mailer.list_drafts()
    matching = []
    for d in drafts:
        full = mailer.get_draft(d["id"])
        headers = {
            h["name"].lower(): h["value"]
            for h in full.get("message", {}).get("payload", {}).get("headers", [])
        }
        subj = headers.get("subject", "")
        if subj.startswith(subject_prefix):
            matching.append((full, subj))
    if not matching:
        print(f"No draft found matching subject prefix {subject_prefix!r}.",
              file=sys.stderr)
        sys.exit(2)
    if len(matching) > 1:
        print(f"WARNING: {len(matching)} matching drafts found. Using the most "
              f"recent (Gmail returns drafts newest-first).")
    draft, subject = matching[0]
    print(f"  Draft subject: {subject!r}")

    # 2) Extract body + strip reviewer block
    body_html, _meta = mailer._extract_html_body(draft)
    body_html, n_removed = mailer._strip_review_blocks(body_html)
    print(f"  Body extracted: {len(body_html)} bytes "
          f"({n_removed} reviewer block(s) stripped)")

    # 3) Fetch live subscriber list from Firestore
    db = _build_firestore()
    recipients = fetch_active_subscribers(db)
    print(f"  Active subscribers: {len(recipients)}")
    for r in recipients:
        print(f"    - {r['email']}")
    if not recipients:
        print("No active subscribers found. Aborting.", file=sys.stderr)
        sys.exit(2)

    # 4) Send per-recipient (throttled, footer injected by senders.append_footer)
    print()
    print(f"Sending to {len(recipients)} recipients...")
    success_count = 0
    failure_count = 0
    failures: list[dict] = []

    def progress_cb(sent: int, total: int, result: senders.SendResult):
        nonlocal success_count, failure_count
        if result.ok:
            success_count += 1
            print(f"  [{sent}/{total}] ✓ {result.email} → {result.message_id}")
        else:
            failure_count += 1
            failures.append({"email": result.email, "error": result.error})
            print(f"  [{sent}/{total}] ✗ {result.email} — {result.error}",
                  file=sys.stderr)

    senders.send_bulk(recipients, subject, body_html, progress_cb=progress_cb)

    # 5) Delete the original draft so it doesn't sit around stale
    try:
        from googleapiclient.discovery import build  # noqa: F401
        gmail = mailer._build_service()
        gmail.users().drafts().delete(
            userId="me", id=draft["id"],
        ).execute()
        print(f"\n  Original draft {draft['id']} deleted.")
    except Exception as e:  # noqa: BLE001
        print(f"\n  WARNING: failed to delete original draft: {e}",
              file=sys.stderr)

    # 6) Log summary to Firestore for audit
    try:
        db.collection("publishLog").add({
            "publishedAt": dt.datetime.utcnow().isoformat() + "Z",
            "subject": subject,
            "recipientCount": len(recipients),
            "successCount": success_count,
            "failureCount": failure_count,
            "failures": failures[:50],  # cap log size
        })
    except Exception as e:  # noqa: BLE001
        print(f"  WARNING: failed to write publishLog entry: {e}",
              file=sys.stderr)

    # 7) Final report
    print()
    print("=" * 70)
    print(f"DONE — {success_count} succeeded, {failure_count} failed")
    print("=" * 70)
    sys.exit(0 if failure_count == 0 else 1)


if __name__ == "__main__":
    main()
