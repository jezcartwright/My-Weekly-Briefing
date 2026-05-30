"""Process queued admin-send jobs from Firestore.

Runs as a GitHub Actions workflow on a schedule (every 5 min) or on
demand. Picks up jobs in `adminSends` with status='queued', sends each
recipient using senders.send_bulk, streams progress back to the same
job document so the admin UI can show live updates.

Designed to be idempotent — if a worker dies mid-send, the job stays
in status='sending' and won't be re-picked-up automatically (so we
don't double-send). An admin can manually re-queue by editing the doc.

Env vars required:
  - GMAIL_SA_JSON (service account for Firestore + Gmail)
  - UNSUBSCRIBE_SECRET (HMAC secret for unsubscribe tokens)
"""
from __future__ import annotations

import os
import sys
import json
import time
import datetime
import traceback

PROJECT_ID = "pi-briefing-38ddc"


def _build_firestore():
    """Build a Firestore client using the GMAIL_SA_JSON service account.

    The same service account that sends Gmail also has Firestore access
    via standard IAM, so we don't need a separate credential.
    """
    from google.oauth2 import service_account
    from google.cloud import firestore

    raw = os.environ.get("GMAIL_SA_JSON")
    if not raw:
        raise RuntimeError("GMAIL_SA_JSON env var not set")
    info = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(info)
    return firestore.Client(project=PROJECT_ID, credentials=creds)


def process_one_job(db, job_ref) -> bool:
    """Process a single queued job. Returns True if a job was processed."""
    from senders import send_bulk, SendResult

    snap = job_ref.get()
    if not snap.exists:
        return False
    data = snap.to_dict()
    if data.get("status") != "queued":
        return False

    print(f"Processing job {job_ref.id}: '{data.get('subject')}' to "
          f"{data.get('recipientCount')} recipients")

    # Claim the job
    job_ref.update({
        "status": "sending",
        "startedAt": datetime.datetime.utcnow().isoformat() + "Z",
    })

    recipients = data.get("recipients", [])
    subject = data.get("subject", "")
    body_html = data.get("bodyHtml", "")
    success_count = 0
    failure_count = 0
    log_entries = []

    def progress_cb(sent, total, result: "SendResult"):
        nonlocal success_count, failure_count
        if result.ok:
            success_count += 1
        else:
            failure_count += 1
        log_entries.append({
            "email": result.email,
            "ok": result.ok,
            "error": result.error,
            "at": datetime.datetime.utcnow().isoformat() + "Z",
        })
        # Stream progress back every few sends to avoid spamming Firestore writes
        if sent % 3 == 0 or sent == total:
            job_ref.update({
                "successCount": success_count,
                "failureCount": failure_count,
                "log": log_entries[-100:],  # cap log size
            })

    try:
        send_bulk(recipients, subject, body_html, progress_cb=progress_cb)
        job_ref.update({
            "status": "done",
            "completedAt": datetime.datetime.utcnow().isoformat() + "Z",
            "successCount": success_count,
            "failureCount": failure_count,
            "log": log_entries[-100:],
        })
        print(f"  ✓ Done: {success_count} sent, {failure_count} failed")
    except Exception as e:  # noqa: BLE001
        tb = traceback.format_exc()
        print(f"  ✗ Error: {e}\n{tb}", file=sys.stderr)
        job_ref.update({
            "status": "error",
            "error": f"{type(e).__name__}: {e}",
            "completedAt": datetime.datetime.utcnow().isoformat() + "Z",
            "successCount": success_count,
            "failureCount": failure_count,
            "log": log_entries[-100:],
        })
    return True


def main():
    db = _build_firestore()
    # Find queued jobs, oldest first (fair queue)
    queued = db.collection("adminSends") \
        .where("status", "==", "queued") \
        .order_by("createdAt") \
        .limit(5).stream()

    processed = 0
    for snap in queued:
        if process_one_job(db, snap.reference):
            processed += 1

    if processed == 0:
        print("No queued jobs.")
    else:
        print(f"Processed {processed} job(s).")


if __name__ == "__main__":
    main()
