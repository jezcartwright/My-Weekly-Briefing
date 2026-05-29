"""Gmail send/draft helper using a service account with domain-wide delegation.

Reads service account credentials from the GMAIL_SA_JSON environment variable
(set in GitHub Actions from the secret of the same name). Impersonates the
DELEGATE_USER (jc@jezcartwright.com) to send mail or save drafts.

Usage from a workflow:
    python -m mailer send --to jc@jezcartwright.com \\
        --subject "Subject" --body-file body.html
    python -m mailer draft --to jc@jezcartwright.com \\
        --subject "Subject" --body-file body.html

Usage from Python:
    from mailer import send_email, save_draft
    send_email("jc@jezcartwright.com", "Subject", "<html>...</html>")

If GMAIL_SA_JSON is unset, missing, or malformed, the module raises
RuntimeError early with a clear message. Network/Google API errors propagate
as google.auth or googleapiclient exceptions — the workflow YAML decides how
to handle those (typically: log and continue, since failure-email-on-failure
is itself the mechanism that depends on this module).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from email.message import EmailMessage

DELEGATE_USER = "jc@jezcartwright.com"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
]


def _build_service():
    """Build a Gmail API service impersonating DELEGATE_USER.

    Imports are lazy so importing this module for type-checking or testing
    doesn't require google-api-python-client to be installed.
    """
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    raw = os.environ.get("GMAIL_SA_JSON")
    if not raw:
        raise RuntimeError(
            "GMAIL_SA_JSON environment variable is not set. "
            "In GitHub Actions, this should come from the secret of the same name."
        )
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"GMAIL_SA_JSON could not be parsed as JSON: {e}. "
            "Did the secret value get truncated when pasted?"
        ) from e

    creds = service_account.Credentials.from_service_account_info(
        info, scopes=SCOPES
    )
    delegated = creds.with_subject(DELEGATE_USER)
    return build("gmail", "v1", credentials=delegated, cache_discovery=False)


def _build_message(to: str, subject: str, body_html: str,
                   from_addr: str = DELEGATE_USER) -> dict:
    """Build a Gmail-API-ready message dict from a simple HTML body."""
    msg = EmailMessage()
    msg["To"] = to
    msg["From"] = from_addr
    msg["Subject"] = subject
    # Plain-text fallback derived from the HTML — very rough, but better than
    # nothing for clients that block HTML.
    plain = (body_html
             .replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
             .replace("</p>", "\n\n").replace("</div>", "\n"))
    # Strip remaining tags crudely
    import re
    plain = re.sub(r"<[^>]+>", "", plain).strip()
    msg.set_content(plain or "(HTML-only message — view in an HTML-capable client.)")
    msg.add_alternative(body_html, subtype="html")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    return {"raw": raw}


def send_email(to: str, subject: str, body_html: str) -> str:
    """Send an email immediately. Returns the Gmail message ID."""
    service = _build_service()
    message = _build_message(to, subject, body_html)
    result = service.users().messages().send(userId="me", body=message).execute()
    return result.get("id", "")


def save_draft(to: str, subject: str, body_html: str) -> str:
    """Save a draft in DELEGATE_USER's inbox. Returns the draft ID."""
    service = _build_service()
    message = _build_message(to, subject, body_html)
    result = service.users().drafts().create(
        userId="me", body={"message": message}
    ).execute()
    return result.get("id", "")


def send_draft(draft_id: str) -> str:
    """Send a previously-saved draft. Returns the resulting message ID."""
    service = _build_service()
    result = service.users().drafts().send(
        userId="me", body={"id": draft_id}
    ).execute()
    return result.get("id", "")


def list_drafts(query: str | None = None, max_results: int = 10) -> list[dict]:
    """List recent drafts, optionally filtered by query (Gmail search syntax).

    Used by the Monday workflow to find the draft created on Friday.
    """
    service = _build_service()
    params = {"userId": "me", "maxResults": max_results}
    if query:
        params["q"] = query
    return service.users().drafts().list(**params).execute().get("drafts", [])


def get_draft(draft_id: str) -> dict:
    """Fetch a draft's full content (subject/body), so we can read what the
    user actually edited before we send it Monday morning."""
    service = _build_service()
    return service.users().drafts().get(
        userId="me", id=draft_id, format="full"
    ).execute()


def _cli():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("send", "draft"):
        sp = sub.add_parser(name)
        sp.add_argument("--to", required=True)
        sp.add_argument("--subject", required=True)
        body_grp = sp.add_mutually_exclusive_group(required=True)
        body_grp.add_argument("--body", help="HTML body as inline string")
        body_grp.add_argument("--body-file", help="Path to file containing HTML body")

    sp = sub.add_parser("list-drafts")
    sp.add_argument("--query", default=None)

    sp = sub.add_parser("send-draft")
    sp.add_argument("--id", required=True)

    args = p.parse_args()

    if args.cmd in ("send", "draft"):
        if args.body_file:
            with open(args.body_file, "r", encoding="utf-8") as f:
                body = f.read()
        else:
            body = args.body
        if args.cmd == "send":
            mid = send_email(args.to, args.subject, body)
            print(f"sent message id={mid}")
        else:
            did = save_draft(args.to, args.subject, body)
            print(f"draft id={did}")
    elif args.cmd == "list-drafts":
        drafts = list_drafts(query=args.query)
        for d in drafts:
            print(d.get("id"))
    elif args.cmd == "send-draft":
        mid = send_draft(args.id)
        print(f"sent message id={mid}")


if __name__ == "__main__":
    try:
        _cli()
    except Exception as e:  # noqa: BLE001 — CLI exit code for any failure
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
