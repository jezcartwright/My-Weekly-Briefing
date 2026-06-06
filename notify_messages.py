"""Email the admin when subscribers send new in-app messages.

Polls the `threads` collection for docs flagged pendingNotify == True
(set by the web app when a subscriber sends a message), emails a
summary to the admin, then clears the flag. Reuses the GMAIL_SA_JSON
service account (Firestore + Gmail), same as the other workers.

Env: GMAIL_SA_JSON
"""
from __future__ import annotations
import os, json, html, datetime

PROJECT_ID = "pi-briefing-38ddc"
ADMIN_EMAIL = "jc@jezcartwright.com"
APP_URL = "https://weeklybriefing.jezcartwright.com"


def _build_firestore():
    from google.oauth2 import service_account
    from google.cloud import firestore
    raw = os.environ.get("GMAIL_SA_JSON")
    if not raw:
        raise RuntimeError("GMAIL_SA_JSON env var not set")
    info = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(info)
    return firestore.Client(project=PROJECT_ID, credentials=creds)


def _email_html(name, email, text):
    e = lambda s: html.escape(s or "")
    return (
        '<html><body style="font-family:Georgia,serif;font-size:15px;line-height:1.55;color:#1a1a1a;margin:0;">'
        '<div style="background:#ff6600;padding:16px 20px;color:#fff;font-family:Arial,sans-serif;font-weight:700;letter-spacing:.04em;">'
        'New message &mdash; Performance Intelligence</div>'
        '<div style="padding:20px;">'
        '<p style="margin:0 0 2px;"><strong>' + (e(name) or "A subscriber") + '</strong></p>'
        '<p style="margin:0 0 16px;color:#666;font-size:13px;font-family:Arial,sans-serif;">' + e(email) + '</p>'
        '<div style="background:#faf8f5;border-left:3px solid #ff6600;padding:12px 16px;border-radius:4px;">' + e(text) + '</div>'
        '<p style="margin:20px 0 0;font-family:Arial,sans-serif;font-size:13px;">'
        '<a href="' + APP_URL + '" style="color:#ff6600;">Open the app to reply &rarr;</a></p>'
        '</div></body></html>'
    )


def main():
    import mailer
    db = _build_firestore()
    pending = list(db.collection("threads").where("pendingNotify", "==", True).stream())
    if not pending:
        print("No pending notifications.")
        return
    sent = 0
    for snap in pending:
        t = snap.to_dict() or {}
        name, email, text = t.get("name"), t.get("email"), t.get("lastText") or ""
        subject = "[PI Briefing] New message from " + (name or email or "a subscriber")
        try:
            mailer.send_email(ADMIN_EMAIL, subject, _email_html(name, email, text))
            snap.reference.update({
                "pendingNotify": False,
                "notifiedAt": datetime.datetime.utcnow().isoformat() + "Z",
            })
            sent += 1
            print("Notified:", snap.id, email)
        except Exception as ex:
            print("Failed for", snap.id, "->", ex)
    print("Done. Sent", sent, "notification(s).")


if __name__ == "__main__":
    main()
