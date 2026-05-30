"""Build the Monday teaser email body from the latest staging index.html.

Extracts the 6 categories x 4 topic titles + headlines from the live D[catId]
data in index.html and renders them as a clean HTML email. Designed to be
called from the Friday workflow after generate_content.py has updated the
staging branch.

Usage:
    python build_teaser.py path/to/index.html > teaser.html
"""
from __future__ import annotations

import re
import sys
import datetime

# Mirror of the category palette in index.html so colours match the site.
CATEGORIES = [
    ("leadership",  "Leadership",   "#FF6600"),
    ("markets",     "Markets",      "#0E3A7B"),
    ("psychology",  "Psychology",   "#C8243C"),
    ("technology",  "Technology",   "#0096D6"),
    ("geopolitics", "Geopolitics",  "#6B2DA8"),
    ("philosophy",  "Philosophy",   "#2E7A3E"),
]


def _extract_this_week(html: str) -> dict:
    """Pull set 0 (most recent) for each category: list of {title, headline}.

    Reuses the same string-aware bracket-walking approach as
    generate_content.extract_recent_topics, but only returns set 0.
    """
    out = {}
    for m in re.finditer(r'D\.(\w+)\s*=\s*\[', html):
        cat = m.group(1)
        start = m.end() - 1
        depth = 0
        in_str = False
        quote = ''
        esc = False
        end = -1
        for i in range(start, len(html)):
            ch = html[i]
            if esc:
                esc = False
                continue
            if in_str:
                if ch == '\\':
                    esc = True
                elif ch == quote:
                    in_str = False
                continue
            if ch in ('"', "'"):
                in_str = True
                quote = ch
                continue
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end == -1:
            continue
        block = html[start + 1:end]
        # First top-level [ ... ] is set 0
        d = 0
        in_str = False
        quote = ''
        esc = False
        set_start = None
        first_set = None
        for i, ch in enumerate(block):
            if esc:
                esc = False
                continue
            if in_str:
                if ch == '\\':
                    esc = True
                elif ch == quote:
                    in_str = False
                continue
            if ch in ('"', "'"):
                in_str = True
                quote = ch
                continue
            if ch == '[':
                d += 1
                if d == 1:
                    set_start = i
            elif ch == ']':
                d -= 1
                if d == 0 and set_start is not None:
                    first_set = block[set_start:i + 1]
                    break
        if not first_set:
            continue
        topics = []
        for tm in re.finditer(
            r'\{title:"((?:[^"\\]|\\.)*)",headline:"((?:[^"\\]|\\.)*)"',
            first_set,
        ):
            topics.append({
                'title': tm.group(1).replace('\\"', '"').replace('\\\\', '\\'),
                'headline': tm.group(2).replace('\\"', '"').replace('\\\\', '\\'),
            })
        out[cat] = topics
    return out


def build_teaser_html(html: str, preview_url: str = "",
                      live_url: str = "https://weeklybriefing.jezcartwright.com/") -> str:
    """Render the teaser email body from the freshly-generated index.html.

    If preview_url is provided, a clearly-marked reviewer block is included
    at the top of the email body. The block is wrapped with
    data-strip-on-send="true" so the Monday workflow can surgically remove
    it before the email is sent to subscribers — even if the user forgot to
    delete it manually.
    """
    data = _extract_this_week(html)
    today = datetime.date.today()
    week = today.isocalendar()[1]
    date_str = today.strftime("%-d %B %Y")

    sections = []
    for cat_id, label, colour in CATEGORIES:
        topics = data.get(cat_id, [])
        if not topics:
            continue
        items = "".join(
            f'<li style="margin:0 0 14px 0;padding:0;">'
            f'<div style="font-weight:600;color:#1a1a1a;font-size:15px;">{t["title"]}</div>'
            f'<div style="color:#1a1a1a;font-size:13.5px;margin-top:2px;">{t["headline"]}</div>'
            f'</li>'
            for t in topics
        )
        sections.append(f'''
<div style="margin:28px 0 0;">
  <div style="font-size:11px;font-weight:700;letter-spacing:0.18em;text-transform:uppercase;color:{colour};margin-bottom:10px;border-bottom:2px solid {colour};padding-bottom:6px;">{label}</div>
  <ul style="list-style:none;padding:0;margin:0;">{items}</ul>
</div>''')

    review_block = ""
    if preview_url:
        review_block = f'''
<div data-strip-on-send="true" class="review-only" style="background:#fff3cd;border:2px solid #c9a84c;border-radius:6px;padding:14px 16px;margin:0 0 24px 0;font-size:13px;color:#664d03;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<div style="font-weight:700;letter-spacing:0.15em;text-transform:uppercase;color:#8a6d12;font-size:11px;margin-bottom:6px;">⚠ Reviewer note — auto-removed before send</div>
<div style="color:#664d03;line-height:1.55;">
This block only appears in your draft. The Monday workflow will strip it automatically before sending to subscribers.<br><br>
<strong>Preview next week's full briefing:</strong> <a href="{preview_url}" style="color:#a0530b;font-weight:600;">{preview_url}</a><br>
<span style="color:#7a5f12;font-size:12px;">Edit the rest of this draft as you like — anything outside this yellow block goes out as-is on Monday 06:17 GMT.</span>
</div>
</div>'''

    return f'''<!DOCTYPE html>
<html><head>
<style>@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600&family=IBM+Plex+Serif:wght@600&display=swap');</style>
</head><body style="margin:0;padding:0;background:#faf8f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#faf8f5;padding:24px 0;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" border="0" style="background:#fff;max-width:640px;border:1px solid #e8e4df;">
<tr><td style="background:#ff6600;padding:28px 32px;color:#fff;">
  <table cellpadding="0" cellspacing="0" border="0" width="100%"><tr>
  <td valign="middle" width="72" style="padding-right:18px;color:#fff;">
    <img src="https://weeklybriefing.jezcartwright.com/favicon-512x512.png" width="56" height="56" alt="PI" style="display:block;width:56px;height:56px;border:0;">
  </td>
  <td valign="middle" style="color:#fff;">
    <div style="font-family:'Cormorant Garamond',Georgia,'Times New Roman',serif;font-size:13px;letter-spacing:0.35em;text-transform:uppercase;color:#ffffff;margin-bottom:4px;font-weight:600;">Performance Intelligence</div>
    <div style="font-family:'IBM Plex Serif',Georgia,serif;font-size:28px;font-weight:600;letter-spacing:-0.01em;line-height:1;color:#ffffff;">Weekly Briefing</div>
    <div style="font-size:13px;color:#ffffff;opacity:0.88;margin-top:4px;">Week {week} · {date_str}</div>
  </td>
  </tr></table>
</td></tr>
<tr><td style="padding:24px 32px 32px;">
{review_block}
<p style="font-size:14px;color:#222;line-height:1.55;">
This week's briefing is live. Six categories, four topics each, twenty-four signals worth your attention.
</p>
<p style="font-size:14px;color:#222;line-height:1.55;">
<a href="{live_url}" style="background:#ff6600;color:#fff;text-decoration:none;padding:10px 18px;border-radius:4px;font-weight:600;display:inline-block;">Read the full briefing →</a>
</p>
{"".join(sections)}
<hr style="margin:32px 0 16px;border:none;border-top:1px solid #e8e4df;">
<p style="font-size:11px;color:#1a1a1a;line-height:1.6;">
Performance Intelligence Weekly Briefing · helping you win.<br>
Sent automatically Monday morning from jc@jezcartwright.com.
</p>
</td></tr>
</table>
</td></tr>
</table>
</body></html>'''


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python build_teaser.py path/to/index.html [preview_url]",
              file=sys.stderr)
        sys.exit(1)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        html_in = f.read()
    preview = sys.argv[2] if len(sys.argv) > 2 else ""
    print(build_teaser_html(html_in, preview_url=preview))
