#!/usr/bin/env python3
"""Render the new-subscriber welcome email as branded HTML.

Usage:
    python build_welcome_email.py "First Name" [unsubscribe_url] > welcome.html

- First name defaults to "there" if omitted (greeting becomes "Hi there,").
- Same masthead lockup (email-masthead.png, 270px) and Georgia-serif body as the
  Monday briefing, so the welcome looks of a piece with the weekly email.
- The unsubscribe URL is optional; when the auto-send Cloud Function calls this it
  will pass a per-recipient signed link. For a test send the footer falls back to a
  mailto so the email still has a working opt-out.
"""
import sys
import html

LIVE = "https://weeklybriefing.jezcartwright.com/"
MASTHEAD = "https://weeklybriefing.jezcartwright.com/email-masthead.png"


def build(first_name: str = "there", unsubscribe_url: str = "") -> str:
    fn = html.escape(first_name.strip() or "there")
    unsub = unsubscribe_url.strip() or "mailto:jc@jezcartwright.com?subject=Unsubscribe"

    # body building blocks -------------------------------------------------
    P = 'margin:0 0 14px;font:400 15px/1.65 Georgia,serif;color:#2a2a2a;'
    LBL = 'margin:0 0 8px;font:700 13px Arial,sans-serif;letter-spacing:.04em;color:#1a1a1a;'
    UL = 'margin:0 0 16px;padding-left:20px;'
    LI = 'font:400 15px/1.6 Georgia,serif;color:#2a2a2a;margin-bottom:7px;'
    LINK = 'color:#c2510a;'

    body = f"""
      <p style="{P}">Hi {fn},</p>
      <p style="{P}">Welcome &mdash; and thank you for signing up.</p>
      <p style="{P}">In today&rsquo;s hectic world that we are in, our lives seem to get busier every day. Creating the time to read widely across the subjects that move the needle &mdash; leadership, markets, psychology, technology, geopolitics, philosophy &mdash; becomes ever more impossible. And yet, there is often that one person in a meeting who is able to quote and regurgitate the latest bits of research and current thinking &mdash; annoying at best!</p>
      <p style="{P}">That is why I decided to create the Performance Intelligence Weekly Briefing. A way to help you sift through what is out there and help you with a curated brief to help you stay sharp, stay relevant, and stay the course.</p>
      <p style="{LBL}">WHAT TO EXPECT</p>
      <ul style="{UL}">
        <li style="{LI}">One briefing a week, in your inbox Monday morning.</li>
        <li style="{LI}">Six areas &mdash; Leadership, Markets, Psychology, Technology, Geopolitics, Philosophy &mdash; each distilled to what matters.</li>
        <li style="{LI}">Short enough for a coffee; sharp enough to give you an edge in the room.</li>
      </ul>
      <p style="{LBL}">GETTING THE MOST FROM IT</p>
      <ul style="{UL}">
        <li style="{LI}">Skim the synopsis, then go deep on whatever&rsquo;s relevant to your week.</li>
        <li style="{LI}">Like the pieces that land and jot notes as you read &mdash; both save to your account.</li>
        <li style="{LI}">Ask me a question at any time. I read every message, and am here to help where I can.</li>
      </ul>
      <p style="{P}">Read this week&rsquo;s briefing <a href="{LIVE}" style="{LINK}">here</a>.</p>
      <p style="{P}">Glad to have you on board.</p>
      <p style="{P}">Have a great rest of your week.</p>
      <p style="{P}">Cheers,<br>Jez</p>
    """

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><meta name="x-apple-disable-message-reformatting"></head>
<body style="margin:0;padding:0;background:#f2efe9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;-webkit-text-size-adjust:100%;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f2efe9;padding:24px 0;"><tr><td align="center">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#fff;max-width:600px;border:1px solid #e8e4df;">
  <tr><td style="background:#ff6600;padding:26px 28px 22px;text-align:center;">
    <img src="{MASTHEAD}" width="270" alt="Performance Intelligence Weekly Briefing" style="display:block;margin:0 auto;width:270px;max-width:270px;height:auto;border:0;color:#ffffff;font-family:'Cormorant Garamond',Georgia,serif;font-size:19px;font-weight:600;line-height:1.4;">
  </td></tr>
  <tr><td style="padding:24px 32px 20px;">{body}</td></tr>
  <tr><td style="padding:14px 32px 22px;border-top:1px solid #ece7df;font:400 11px Arial,sans-serif;color:#8E857C;text-align:center;">Performance Intelligence Weekly Briefing &nbsp;&middot;&nbsp; <a href="{unsub}" style="color:#8E857C;">unsubscribe</a></td></tr>
</table></td></tr></table></body></html>"""


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "there"
    unsub = sys.argv[2] if len(sys.argv) > 2 else ""
    sys.stdout.write(build(name, unsub))
