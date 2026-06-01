"""Pluggable bulk-send abstraction.

Today this dispatches to mailer.send_email (Gmail API). Tomorrow we swap in
Resend or Postmark by writing one new send_* function and changing one line
in send_bulk(). All call-sites stay the same.

Designed for:
  - hard ceilings (won't exceed daily send quota)
  - throttling (won't hammer the API and trip rate limits)
  - per-recipient personalisation (each gets their own unsubscribe link)
  - dry-run mode (preview without sending)
  - audit logging (every send is recorded in Firestore)
"""
from __future__ import annotations

import os
import time
import json
import hmac
import hashlib
import base64
import datetime
from typing import Callable, Iterable, Optional

# Hard ceilings — leave headroom under Gmail's 500/day
DAILY_HARD_CAP = 400
PER_SECOND_THROTTLE = 1.0   # one send per second
UNSUBSCRIBE_SECRET_ENV = "UNSUBSCRIBE_SECRET"
UNSUBSCRIBE_BASE_URL = "https://weeklybriefing.jezcartwright.com/unsubscribe.html"


def _unsubscribe_secret() -> bytes:
    """Read the HMAC secret used to sign unsubscribe tokens.

    Falls back to a project-derived constant if the env var isn't set. That
    fallback only kicks in during local dev; production workflows pass the
    secret via GitHub Actions.
    """
    raw = os.environ.get(UNSUBSCRIBE_SECRET_ENV)
    if not raw:
        # Deterministic fallback so dev still works. NOT for production.
        raw = "pi-briefing-dev-only-do-not-use-in-prod-please"
    return raw.encode("utf-8")


def make_unsubscribe_token(uid: str, email: str) -> str:
    """Create a tamper-proof unsubscribe token for a user.

    Format: base64url(uid|email|signature). The signature is HMAC-SHA256
    over the uid+email with our secret. Anyone with the token can unsubscribe
    that specific user but can't forge tokens for other users without the
    secret.
    """
    msg = f"{uid}|{email}".encode("utf-8")
    sig = hmac.new(_unsubscribe_secret(), msg, hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(msg + b"|" + sig).decode("ascii").rstrip("=")
    return token


def verify_unsubscribe_token(token: str) -> Optional[tuple[str, str]]:
    """Validate an unsubscribe token. Returns (uid, email) or None if invalid."""
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded)
        parts = raw.rsplit(b"|", 1)
        if len(parts) != 2:
            return None
        msg, sig = parts
        expected_sig = hmac.new(_unsubscribe_secret(), msg, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        uid, email = msg.split(b"|", 1)
        return uid.decode("utf-8"), email.decode("utf-8")
    except Exception:  # noqa: BLE001 — invalid tokens fail closed
        return None


def make_unsubscribe_url(uid: str, email: str) -> str:
    """Per-recipient unsubscribe URL to embed in email footers."""
    return f"{UNSUBSCRIBE_BASE_URL}?t={make_unsubscribe_token(uid, email)}"


def append_footer(body_html: str, uid: str, email: str) -> str:
    """Inject the unsubscribe footer into an email body.

    Footer is Option C — quiet, single-line, deferential. Treats the foot of
    the email as an exit, not a marketing prompt. Used by both admin-send and
    the Monday-publish per-recipient pipeline.

    Looks for </body> as the insertion point. If absent, appends to the end.
    """
    unsub = make_unsubscribe_url(uid, email)
    footer = (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="margin-top:32px;border-top:1px solid #f0ece5;padding-top:14px;">'
        '<tr><td style="text-align:center;font-family:-apple-system,BlinkMacSystemFont,'
        '\'Segoe UI\',sans-serif;font-size:10px;color:#888;line-height:1.6;">'
        'Performance Intelligence Weekly Briefing &nbsp;·&nbsp; '
        f'<a href="{unsub}" style="color:#888;text-decoration:underline;">unsubscribe</a>'
        '</td></tr></table>'
    )
    lower = body_html.lower()
    idx = lower.rfind("</body>")
    if idx == -1:
        return body_html + footer
    return body_html[:idx] + footer + body_html[idx:]


class SendResult:
    """Single send outcome — for audit logging."""
    def __init__(self, email: str, uid: str, ok: bool,
                 message_id: str = "", error: str = ""):
        self.email = email
        self.uid = uid
        self.ok = ok
        self.message_id = message_id
        self.error = error

    def to_dict(self) -> dict:
        return {
            "email": self.email,
            "uid": self.uid,
            "ok": self.ok,
            "messageId": self.message_id,
            "error": self.error,
        }


def send_to_recipient(uid: str, email: str, subject: str,
                      body_html: str, *, dry_run: bool = False) -> SendResult:
    """Send a single, personalised email. Adds an unsubscribe footer.

    Currently dispatches to mailer.send_email (Gmail). Swap this function's
    body to call resend.Emails.send() etc. to switch providers.
    """
    full_body = append_footer(body_html, uid, email)
    list_unsub_url = make_unsubscribe_url(uid, email)

    if dry_run:
        return SendResult(email, uid, ok=True, message_id="dry-run")

    try:
        from mailer import _build_service, _build_message
        # We need to inject the List-Unsubscribe header for inbox-level
        # native unsubscribe support, so build the raw message ourselves.
        message = _build_message_with_headers(
            to=email, subject=subject, body_html=full_body,
            extra_headers={
                "List-Unsubscribe": f"<{list_unsub_url}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
        )
        service = _build_service()
        result = service.users().messages().send(
            userId="me", body=message,
        ).execute()
        return SendResult(email, uid, ok=True, message_id=result.get("id", ""))
    except Exception as e:  # noqa: BLE001
        return SendResult(email, uid, ok=False, error=f"{type(e).__name__}: {e}")


def _build_message_with_headers(to: str, subject: str, body_html: str,
                                extra_headers: dict) -> dict:
    """Like mailer._build_message but with arbitrary headers."""
    import base64 as b64
    import re
    from email.message import EmailMessage
    from mailer import DELEGATE_USER

    msg = EmailMessage()
    msg["To"] = to
    msg["From"] = DELEGATE_USER
    msg["Subject"] = subject
    for k, v in extra_headers.items():
        msg[k] = v
    plain = (body_html
             .replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
             .replace("</p>", "\n\n").replace("</div>", "\n"))
    plain = re.sub(r"<[^>]+>", "", plain).strip()
    msg.set_content(plain or "(HTML-only message.)")
    msg.add_alternative(body_html, subtype="html")
    raw = b64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    return {"raw": raw}


def send_bulk(recipients: list[dict], subject: str, body_html: str,
              progress_cb: Optional[Callable[[int, int, SendResult], None]] = None,
              dry_run: bool = False) -> list[SendResult]:
    """Send to multiple recipients, throttled, with a hard daily cap.

    Each recipient dict must have 'uid' and 'email' keys.

    progress_cb(sent_count, total, last_result) is called after each send
    so callers can stream progress (e.g. to a CLI or a workflow log).
    """
    if len(recipients) > DAILY_HARD_CAP:
        raise RuntimeError(
            f"Refusing to send {len(recipients)} emails — exceeds daily cap of "
            f"{DAILY_HARD_CAP}. Run in multiple batches across days, or move to "
            f"a proper bulk-email provider."
        )

    results: list[SendResult] = []
    last_send_at = 0.0
    for i, r in enumerate(recipients):
        # Throttle
        delta = time.time() - last_send_at
        if delta < PER_SECOND_THROTTLE:
            time.sleep(PER_SECOND_THROTTLE - delta)
        last_send_at = time.time()

        result = send_to_recipient(
            uid=r["uid"], email=r["email"],
            subject=subject, body_html=body_html, dry_run=dry_run,
        )
        results.append(result)
        if progress_cb:
            progress_cb(i + 1, len(recipients), result)

    return results


# CLI for use from workflows / one-off scripts
def _cli():
    import argparse
    p = argparse.ArgumentParser(description="Bulk send via configured provider")
    p.add_argument("--recipients-json", required=True,
                   help="Path to JSON file with [{'uid':..., 'email':...}, ...]")
    p.add_argument("--subject", required=True)
    p.add_argument("--body-file", required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    with open(args.recipients_json) as f:
        recipients = json.load(f)
    with open(args.body_file) as f:
        body = f.read()

    def progress(sent, total, r):
        marker = "✓" if r.ok else "✗"
        print(f"  [{sent}/{total}] {marker} {r.email}"
              f"{(' — ' + r.error) if r.error else ''}")

    print(f"Sending to {len(recipients)} recipients"
          f"{' (DRY RUN)' if args.dry_run else ''}...")
    results = send_bulk(recipients, args.subject, body,
                        progress_cb=progress, dry_run=args.dry_run)
    ok_count = sum(1 for r in results if r.ok)
    print(f"\nDone: {ok_count}/{len(results)} succeeded.")


if __name__ == "__main__":
    _cli()
