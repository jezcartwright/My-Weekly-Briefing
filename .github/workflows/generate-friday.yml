#!/usr/bin/env python3
"""Build the Monday 'chatty synopsis' invitation email.

The synopsis is AI-drafted from the week's actual topics (same Anthropic client
the content pipeline uses). Rendered as email-safe HTML and saved as a Gmail
draft on Friday so it can be edited over the weekend; sent Monday by the
existing publish workflow.

Usage:
    python build_monday_email.py index.html [preview_url] > monday.html

If ANTHROPIC_API_KEY is unset or the call fails, a deterministic fallback
synopsis is used so the draft always builds.
"""
from __future__ import annotations
import os, sys, json, html as H, datetime, subprocess, tempfile

CATS = [("leadership","Leadership","#FF6600"),("markets","Markets","#0E3A7B"),
        ("psychology","Psychology","#C8243C"),("technology","Technology","#0096D6"),
        ("geopolitics","Geopolitics","#6B2DA8"),("philosophy","Philosophy","#2E7A3E")]
LIVE = "https://weeklybriefing.jezcartwright.com/"
LOGO = "https://weeklybriefing.jezcartwright.com/favicon-512x512.png"

def extract_week0(path):
    src = open(path, encoding="utf-8").read()
    stmts = []
    for cat, _, _ in CATS:
        k = "D.%s=[" % cat; i = src.find(k)
        if i < 0: continue
        j = src.index("\n];", i) + 3; stmts.append(src[i:j])
    js = "var D={};\n" + "\n".join(stmts) + "\nvar o={};Object.keys(D).forEach(function(k){o[k]=D[k][0]||[]});console.log(JSON.stringify(o));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(js); tmp = f.name
    try:
        out = subprocess.check_output(["node", tmp], text=True)
    finally:
        os.unlink(tmp)
    return json.loads(out)

def ai_synopsis(data):
    lines = []
    for cid, label, _ in CATS:
        for t in (data.get(cid) or []):
            lines.append("- [%s] %s: %s" % (label, t.get("title",""), t.get("headline","")))
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        prompt = ("Below are this week's 24 topics across six categories of an executive briefing.\n\n"
                  + "\n".join(lines) +
                  "\n\nWrite the opening synopsis for the Monday email that introduces this briefing. "
                  "Voice: warm, intelligent, lightly conversational British English, like a sharp friend who reads everything. "
                  "Thread together three or four connecting themes across the topics into a short narrative; do not list every item. "
                  "Three short paragraphs, about 160 words total. A natural greeting to open is fine. "
                  "End by noting there are 24 signals across the six categories and inviting the reader into the full briefing. "
                  "No headings, no bullet points, no markdown, and do not use the word 'delve'. "
                  "Return only the paragraphs, separated by blank lines.")
        msg = client.messages.create(model="claude-opus-4-7", max_tokens=600,
                                     messages=[{"role":"user","content":prompt}])
        text = "".join(getattr(b,"text","") for b in msg.content if getattr(b,"type","")=="text").strip()
        paras = [p.strip() for p in text.split("\n\n") if p.strip()]
        return paras or None
    except Exception as e:
        sys.stderr.write("  ! synopsis AI draft failed (%s); using fallback\n" % e)
        return None

def fallback_synopsis(data):
    picks = []
    for cid, label, _ in CATS:
        ts = data.get(cid) or []
        if ts: picks.append((label, ts[0].get("headline","").rstrip(".")))
    p1 = "Morning &mdash; this week's briefing brings together twenty-four signals worth your attention."
    p2 = " ".join("In %s, %s." % (lbl, hl) for lbl, hl in picks[:3])
    p3 = "There's more across the other categories too. The full briefing is one tap away below."
    return [p1, p2, p3]

def esc(s): return H.escape(s or "")

def build(path, preview_url=""):
    data = extract_week0(path)
    syn = ai_synopsis(data) or fallback_synopsis(data)
    date = datetime.date.today().strftime("%A, %-d %B %Y")
    glance = []
    for cid, label, color in CATS:
        ts = data.get(cid) or []
        if ts: glance.append((color, label, ts[0].get("title","")))
    syn_html = "".join('<tr><td style="font:400 15px/1.65 Georgia,serif;color:#2a2a2a;padding-bottom:13px;">%s</td></tr>' % p for p in syn)
    gl_html = "".join('<tr><td valign="top" style="padding:5px 0;"><span style="display:inline-block;width:9px;height:9px;background:%s;margin-right:9px;"></span><span style="font:700 11px Arial,sans-serif;letter-spacing:1.3px;text-transform:uppercase;color:%s;">%s</span> &nbsp;<span style="font:400 13.5px Georgia,serif;color:#1a1a1a;">%s</span></td></tr>' % (c, c, l, esc(t)) for c, l, t in glance)
    note = ""
    if preview_url:
        note = ('<tr><td data-strip-on-send="true" style="padding:16px 32px 0;"><div style="background:#fff8ee;border:1px solid #f0e8d0;padding:12px 14px;font:400 12.5px Arial,sans-serif;color:#8a6d3b;line-height:1.5;">Draft for your weekend edit &mdash; tweak the synopsis below; this note won&rsquo;t be sent. Preview the site: <a href="%s" style="color:#a0530b;">%s</a></div></td></tr>' % (esc(preview_url), esc(preview_url)))
    return """<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;background:#f2efe9;">
<table width="100%%" cellpadding="0" cellspacing="0" border="0" style="background:#f2efe9;padding:24px 0;"><tr><td align="center">
<table width="100%%" cellpadding="0" cellspacing="0" border="0" style="background:#fff;max-width:600px;border:1px solid #e8e4df;">
  <tr><td style="background:#ff6600;padding:26px 28px 22px;text-align:center;">
    <img src="%(logo)s" width="42" height="42" alt="PI" style="display:block;margin:0 auto 8px;border:0;">
    <div style="font:700 21px Georgia,serif;color:#fff;letter-spacing:6px;">PERFORMANCE</div>
    <div style="font:700 21px Georgia,serif;color:#fff;letter-spacing:6px;">INTELLIGENCE</div>
    <div style="font:600 11px Georgia,serif;color:#fff;letter-spacing:5px;padding-top:6px;">WEEKLY BRIEFING</div>
  </td></tr>
  %(note)s
  <tr><td style="padding:16px 32px 2px;font:400 12px Arial,sans-serif;color:#8E857C;letter-spacing:.05em;">%(date)s</td></tr>
  <tr><td style="padding:14px 32px 4px;"><table width="100%%" cellpadding="0" cellspacing="0" border="0">%(syn)s</table></td></tr>
  <tr><td style="padding:8px 32px 0;"><table width="100%%" cellpadding="0" cellspacing="0" border="0" style="border-top:1px solid #ece7df;"><tr><td style="font:700 10px Arial,sans-serif;letter-spacing:2px;text-transform:uppercase;color:#8E857C;padding:16px 0 8px;">A taste of what&rsquo;s inside</td></tr>%(gl)s</table></td></tr>
  <tr><td style="padding:22px 32px 28px;text-align:center;"><a href="%(live)s" style="background:#ff6600;color:#fff;text-decoration:none;padding:12px 22px;border-radius:4px;font:600 14px Arial,sans-serif;display:inline-block;">Read the full briefing &rarr;</a></td></tr>
  <tr><td style="padding:14px 32px 22px;border-top:1px solid #ece7df;font:400 11px Arial,sans-serif;color:#8E857C;text-align:center;">Performance Intelligence Weekly Briefing</td></tr>
</table></td></tr></table></body></html>""" % dict(logo=LOGO, note=note, date=date, syn=syn_html, gl=gl_html, live=LIVE)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python build_monday_email.py index.html [preview_url] > monday.html")
    sys.stdout.write(build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""))
