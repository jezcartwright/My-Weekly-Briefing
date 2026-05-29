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


def _extract_html_body(draft: dict) -> tuple[str, dict]:
    """Pull the HTML body out of a Gmail draft's payload.

    Returns (html_string, headers_dict_keyed_by_name). The headers dict makes
    it easy to preserve subject/to/from when re-saving.
    """
    payload = draft.get("message", {}).get("payload", {})
    headers = {h["name"].lower(): h["value"]
               for h in payload.get("headers", [])
               if h.get("name") and h.get("value")}

    def walk(part):
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
        for child in part.get("parts", []) or []:
            found = walk(child)
            if found:
                return found
        return None

    html = walk(payload) or ""
    return html, headers


def _strip_review_blocks(html: str) -> tuple[str, int]:
    """Remove every element with data-strip-on-send="true" (any case, any quotes).

    Defensive parser — finds opening tag with the marker, walks balanced
    same-named tags to find its matching close, removes the entire span.
    Returns (cleaned_html, count_of_blocks_removed).

    Gmail's editor sometimes normalises attribute quoting when a draft is
    edited and re-saved, so we tolerate both single and double quotes.
    """
    import re
    cleaned = html
    removed = 0
    while True:
        # Match: < TAG ...stuff... data-strip-on-send = "true" or 'true' ... >
        # Case insensitive, both quote styles, optional whitespace around =.
        m = re.search(
            r'''<(\w+)([^>]*\bdata-strip-on-send\s*=\s*['"]true['"][^>]*)>''',
            cleaned,
            re.IGNORECASE,
        )
        if not m:
            break
        tag = m.group(1).lower()
        open_pos = m.start()
        depth = 1
        pos = m.end()
        close_pos = -1
        open_re = re.compile(rf'<{tag}\b[^>]*>', re.IGNORECASE)
        close_re = re.compile(rf'</{tag}\s*>', re.IGNORECASE)
        while pos < len(cleaned) and depth > 0:
            o = open_re.search(cleaned, pos)
            c = close_re.search(cleaned, pos)
            if not c:
                break
            if o and o.start() < c.start():
                depth += 1
                pos = o.end()
            else:
                depth -= 1
                pos = c.end()
                if depth == 0:
                    close_pos = c.end()
                    break
        if close_pos == -1:
            break
        cleaned = cleaned[:open_pos] + cleaned[close_pos:]
        removed += 1
    return cleaned, removed


def strip_and_send_draft(draft_id: str) -> tuple[str, int]:
    """Fetch a draft, strip review-only blocks, update the draft, send it.

    Returns (sent_message_id, number_of_blocks_stripped).

    This is the Monday workflow's send path. Using update-then-send rather
    than send-with-new-body so the Gmail "Sent" record reflects exactly what
    was sent — useful for audit.
    """
    service = _build_service()
    draft = service.users().drafts().get(
        userId="me", id=draft_id, format="full"
    ).execute()

    html, headers = _extract_html_body(draft)
    cleaned, removed_count = _strip_review_blocks(html)

    if removed_count > 0:
        # Re-build the message with the cleaned body, preserve subject/to
        subject = headers.get("subject", "")
        to = headers.get("to", DELEGATE_USER)
        new_message = _build_message(to, subject, cleaned)
        service.users().drafts().update(
            userId="me",
            id=draft_id,
            body={"id": draft_id, "message": new_message},
        ).execute()

    result = service.users().drafts().send(
        userId="me", body={"id": draft_id}
    ).execute()
    return result.get("id", ""), removed_count


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
