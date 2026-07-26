#!/usr/bin/env python3
"""Build the Monday 'chatty synopsis' invitation email.

The synopsis is AI-drafted from the week's actual topics (same Anthropic client
the content pipeline uses). Rendered as email-safe HTML and saved as a Gmail
draft on Friday so it can be edited over the weekend; sent Monday by the
existing publish workflow.

The intro is written FROM SCRATCH each week: ai_synopsis() invents a fresh
structure and is forbidden from reusing any structure recorded in the intro
history file, so no two weeks share a shape. The greeting, the closing line and
the sign-off are fixed furniture owned by build()/the template - the AI only
ever writes the middle.

Usage:
    python build_monday_email.py index.html [preview_url] > monday.html

If ANTHROPIC_API_KEY is unset or the call fails, a deterministic fallback
synopsis is used so the draft always builds.
"""
from __future__ import annotations
import os, sys, json, re, html as H, datetime, subprocess, tempfile

CATS = [("leadership","Leadership","#FF6600"),("markets","Markets","#0E3A7B"),
        ("psychology","Psychology","#C8243C"),("technology","Technology","#0096D6"),
        ("geopolitics","Geopolitics","#6B2DA8"),("philosophy","Philosophy","#2E7A3E")]
LIVE = "https://weeklybriefing.jezcartwright.com/"
LOGO = "https://weeklybriefing.jezcartwright.com/favicon-512x512.png"

# "Add to home screen" card. Uses hosted PNGs (Gmail strips inline SVG), so upload
# icon-app-tile.png (your pi mark), icon-share-ios.png and icon-share-android.png to
# ICON_BASE alongside the masthead before this ships.
ICON_BASE = "https://weeklybriefing.jezcartwright.com"
HOMESCREEN_CARD = (
    '<tr><td style="padding:6px 32px 20px;">'
      '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#fff8ee;border:1px solid #f0e8d0;border-radius:6px;">'
        '<tr><td style="padding:16px 18px 13px;">'
          '<table cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td valign="middle" style="padding-right:14px;"><img src="{ICON_BASE}/icon-app-tile.png" width="46" height="46" alt="Performance Intelligence" style="display:block;width:46px;height:46px;border:0;"></td>'
            '<td valign="middle">'
              '<div style="font:600 15px Georgia,serif;color:#a0530b;padding-bottom:2px;">Add the briefing to your home screen</div>'
              '<div style="font:400 12.5px/1.5 Georgia,serif;color:#8a6d3b;">One tap to each week&rsquo;s briefing &mdash; no searching your inbox.</div>'
            '</td>'
          '</tr></table>'
        '</td></tr>'
        '<tr><td style="padding:0 18px 16px;">'
          '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-top:1px solid #f0e4cd;"><tr><td style="padding-top:12px;">'
            '<table cellpadding="0" cellspacing="0" border="0" style="margin-bottom:9px;"><tr>'
              f'<td width="26" valign="middle"><img src="{ICON_BASE}/icon-share-ios.png" width="18" height="18" alt="Share" style="display:block;width:18px;height:18px;border:0;"></td>'
              '<td valign="middle" style="font:400 12.5px/1.5 Georgia,serif;color:#8a6d3b;"><span style="font-weight:600;color:#6f5327;">iPhone</span> &mdash; tap Share, then &lsquo;Add to Home Screen&rsquo;</td>'
            '</tr></table>'
            '<table cellpadding="0" cellspacing="0" border="0"><tr>'
              f'<td width="26" valign="middle"><img src="{ICON_BASE}/icon-share-android.png" width="18" height="18" alt="Share" style="display:block;width:18px;height:18px;border:0;"></td>'
              '<td valign="middle" style="font:400 12.5px/1.5 Georgia,serif;color:#8a6d3b;"><span style="font-weight:600;color:#6f5327;">Android</span> &mdash; tap Share, then &lsquo;Add to Home screen&rsquo;</td>'
            '</tr></table>'
          '</td></tr></table>'
        '</td></tr>'
      '</table>'
    '</td></tr>'
)

# Voice reference ONLY. Short fragments in deliberately different shapes so the model
# picks up Jez's register (warm, wry, concrete, first-person British English) without
# a full opening to copy the structure from. NEVER put a whole exemplar intro here
# again - a single exemplar is what made every week read the same.
VOICE_REFERENCE = """- "I spent Tuesday certain I'd read the room. The room, it turned out, had read me."
- "Every decision looks inevitable in hindsight and reckless at the time; the job is telling which is which beforehand."
- "Copper does not care about your quarterly narrative. Neither, lately, does the weather.\""""

# Phrases past intros over-used. The AI body must contain none of them, in any form,
# so each week reads new. Extend this list whenever a new tic starts to creep in.
BANNED_TICS = [
    "a particular kind of self", "particular kind of", "self-deception", "self-flattery",
    "the thread that runs through", "the thread running through", "this week's thread",
    "runs through this week", "that gap", "the gap between",
    "the machines, meanwhile", "the machines are", "meanwhile, the machines",
    "slower currents", "the slower currents", "underneath that", "underneath,", "beneath that",
    "step inside", "twenty-four signals", "across six categories", "signals await",
    "delve", "deluge", "in a world where", "in today's world", "now more than ever",
]

# Record of every intro structure used, so none is ever reused. This file MUST persist
# between weekly runs for the guarantee to hold: it has to be committed back to the repo
# by the workflow (exactly as the topic pipeline persists its content history) or pointed
# at a durable path via the INTRO_HISTORY env var. If it cannot be persisted the intro is
# still written from scratch each week - it simply loses its cross-week memory.
INTRO_HISTORY = os.environ.get("INTRO_HISTORY", "intro_history.json")
HISTORY_KEEP = 60  # forbid this many past structures: over a year with no structural repeat

def _load_history():
    try:
        with open(INTRO_HISTORY, encoding="utf-8") as f:
            h = json.load(f)
        return [str(x).strip() for x in h if str(x).strip()] if isinstance(h, list) else []
    except Exception:
        return []

def _save_history(hist):
    try:
        with open(INTRO_HISTORY, "w", encoding="utf-8") as f:
            json.dump(hist[-HISTORY_KEEP:], f, ensure_ascii=False, indent=0)
    except Exception as e:
        sys.stderr.write("  ! could not persist intro history (%s)\n" % e)

def _parse_json_obj(text):
    """Pull the first JSON object from the model reply, tolerating ``` fences and trailing prose."""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        return None
    frag = t[i:j+1]
    try:
        return json.loads(frag)
    except Exception:
        try:  # last-ditch: escape raw newlines that slipped inside string values
            return json.loads(frag.replace("\r", "").replace("\n", "\\n"))
        except Exception:
            return None

_ONES = ["zero","one","two","three","four","five","six","seven","eight","nine","ten",
         "eleven","twelve","thirteen","fourteen","fifteen","sixteen","seventeen","eighteen","nineteen"]
_TENS = ["","","twenty","thirty","forty","fifty","sixty","seventy","eighty","ninety"]
def num_word(n):
    """Spell a small count (0-99) like the author does ('Twenty-four'); fall back to digits."""
    if n < 20: return _ONES[n]
    if n < 100:
        t, o = divmod(n, 10)
        return _TENS[t] + ("-" + _ONES[o] if o else "")
    return str(n)

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

# The greeting is a single line ending at its first comma ("Happy Monday Everyone,").
_GREETING_RE = re.compile(r"(?is)^\s*happy\s+monday[^,\n]*,\s*")

def _strip_scaffolding(paras):
    """Defensively remove any fixed scaffolding the model echoed: the greeting, the
    'N signals \u2026 step inside' closing, and the 'Have a great week / Cheers, / Jez'
    sign-off. build() and the HTML template are the single source of truth for those
    lines, so the AI body must never contain them \u2014 otherwise they duplicate (two
    greetings) or land mid-email (a stray sign-off above the closing). The model is told
    not to emit them; this guards against the times it does anyway."""
    out = []
    for p in paras:
        t = (p or "").strip()
        if not t:
            continue
        low = t.lower()
        if low.startswith("happy monday"):
            rest = _GREETING_RE.sub("", t, count=1).strip()
            if rest and not rest.lower().startswith("happy monday"):
                out.append(rest)
            continue
        if "step inside" in low or "across six categories" in low:
            continue
        if "have a great week" in low or low.startswith("cheers") or low.rstrip(".") == "jez":
            continue
        out.append(t)
    return out

def ai_synopsis(data):
    lines = []
    for cid, label, _ in CATS:
        for t in (data.get(cid) or []):
            lines.append("- [%s] %s: %s" % (label, t.get("title",""), t.get("headline","")))
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    history = _load_history()
    forbidden = "\n".join("- " + h for h in history) if history else "(nothing yet - a clean slate)"
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        prompt = (
            "You are drafting the opening body of Jez's weekly executive briefing email. It sits between a fixed "
            "greeting (\"Happy Monday Everyone,\") and a fixed closing line, both added separately \u2014 so write "
            "ONLY the middle paragraphs. Do NOT write a greeting, a sign-off, or any 'N signals / six categories / "
            "step inside' line.\n\n"
            "INVENT A COMPLETELY FRESH STRUCTURE from scratch this week. There is NO house template and you must not "
            "reach for one. How it opens, how it moves, and how it ends must all be materially different from every "
            "structure listed below \u2014 each has already been used in a previous week and must never recur:\n"
            "ALREADY USED \u2014 your shape must not resemble any of these:\n" + forbidden + "\n\n"
            "VOICE \u2014 imitate the TONE ONLY, never the structure or content. Warm, literate British English; "
            "essayistic and a little wry; concrete over abstract; first person; comfortable being self-deprecating. "
            "Fragments that show the register:\n" + VOICE_REFERENCE + "\n\n"
            "Choose a handful of the topics below and weave them into your fresh structure in whatever order serves "
            "it; you need not use all of them. Do NOT organise the piece by category, and do NOT narrate the "
            "technology items collectively as 'the machines' or sweep the rest into 'currents' \u2014 that grouping "
            "IS the old formula.\n\n"
            "THIS WEEK'S 24 TOPICS (six categories):\n" + "\n".join(lines) + "\n\n"
            "BANNED \u2014 never use any of these words or phrases, in any form or tense:\n"
            + "; ".join(BANNED_TICS) + "\n\n"
            "HARD RULES: ground every concrete claim in the topics above \u2014 invent no facts, numbers, names, "
            "dates, scores or events (the author adds any personal or real-world specifics himself, so leave room for "
            "that and never assert current events you cannot verify). No headings, no bullet points, no markdown. "
            "About 230-280 words.\n\n"
            "Return ONE JSON object and nothing else \u2014 no code fences, no commentary:\n"
            "{\"approach\": \"a concrete description, 18 words or fewer, of the structure you used (opening move + "
            "organising idea), specific enough that a future writer could deliberately avoid repeating it\", "
            "\"body\": \"the paragraphs, separated by \\n\\n\"}")
        msg = client.messages.create(model="claude-opus-4-7", max_tokens=1200, temperature=1.0,
                                     messages=[{"role":"user","content":prompt}])
        text = "".join(getattr(b,"text","") for b in msg.content if getattr(b,"type","")=="text").strip()
        obj = _parse_json_obj(text)
        if not obj:
            sys.stderr.write("  ! synopsis JSON parse failed; using fallback\n")
            return None
        approach = str(obj.get("approach","")).strip()
        paras = _strip_scaffolding([p.strip() for p in str(obj.get("body","")).split("\n\n") if p.strip()])
        if not paras:
            return None
        if approach:
            _save_history(history + [approach])
        return paras
    except Exception as e:
        sys.stderr.write("  ! synopsis AI draft failed (%s); using fallback\n" % e)
        return None

def fallback_synopsis(data):
    picks = []
    for cid, label, _ in CATS:
        ts = data.get(cid) or []
        if ts: picks.append((label, ts[0].get("headline","").rstrip(".")))
    p1 = "A few of this week's signals are worth pausing on before the detail."
    p2 = " ".join("In %s, %s." % (lbl, hl) for lbl, hl in picks[:3])
    p3 = "More runs through the other categories \u2014 the through-lines are easier to feel than to summarise."
    return [p1, p2, p3]

def esc(s): return H.escape(s or "")

def build(path, preview_url=""):
    data = extract_week0(path)
    body = ai_synopsis(data) or fallback_synopsis(data)
    n = sum(len(data.get(cid) or []) for cid, _, _ in CATS)
    greeting = "Happy Monday Everyone,"
    closing = "%s signals across six categories await. Please step inside." % num_word(n).capitalize()
    syn = [greeting] + body + [closing]
    # The draft is built on Friday but SENT on Monday, so stamp the send day, not the
    # build day (which is why it used to read "Saturday, 4 July"). Use the soonest Monday
    # that is today-or-later: a Friday build -> the coming Monday; a Monday rebuild -> today.
    today = datetime.date.today()
    send_date = today + datetime.timedelta(days=(0 - today.weekday()) % 7)
    date = send_date.strftime("%A, %-d %B %Y")
    glance = []
    for cid, label, color in CATS:
        ts = data.get(cid) or []
        if ts: glance.append((color, label, ts[0].get("title","")))
    syn_html = "".join('<tr><td style="font:400 15px/1.65 Georgia,serif;color:#2a2a2a;padding-bottom:13px;">%s</td></tr>' % p for p in syn)
    gl_html = "".join('<tr><td valign="top" style="padding:5px 0;"><span style="display:inline-block;width:9px;height:9px;background:%s;margin-right:9px;"></span><span style="font:700 11px Arial,sans-serif;letter-spacing:1.3px;text-transform:uppercase;color:%s;">%s</span> &nbsp;<span style="font:400 13.5px Georgia,serif;color:#1a1a1a;">%s</span></td></tr>' % (c, c, l, esc(t)) for c, l, t in glance)
    note = ""
    if preview_url:
        note = ('<tr><td data-strip-on-send="true" style="padding:16px 32px 0;"><div style="background:#fff8ee;border:1px solid #f0e8d0;padding:12px 14px;font:400 12.5px Arial,sans-serif;color:#8a6d3b;line-height:1.5;">Draft for your weekend edit &mdash; tweak the synopsis below; this note won&rsquo;t be sent. Preview the site: <a href="%s" style="color:#a0530b;">%s</a></div></td></tr>' % (esc(preview_url), esc(preview_url)))
    return """<!DOCTYPE html><html><head><meta charset="utf-8"><style>@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600;700&display=swap');</style></head>
<body style="margin:0;background:#f2efe9;">
<table width="100%%" cellpadding="0" cellspacing="0" border="0" style="background:#f2efe9;padding:24px 0;"><tr><td align="center">
<table width="100%%" cellpadding="0" cellspacing="0" border="0" style="background:#fff;max-width:600px;border:1px solid #e8e4df;">
  <tr><td style="background:#ff6600;padding:26px 28px 22px;text-align:center;">
    <img src="https://weeklybriefing.jezcartwright.com/email-masthead.png" width="270" alt="Performance Intelligence Weekly Briefing" style="display:block;margin:0 auto;width:270px;max-width:270px;height:auto;border:0;color:#ffffff;font-family:'Cormorant Garamond',Georgia,serif;font-size:19px;font-weight:600;line-height:1.4;">
  </td></tr>
  %(note)s
  <tr><td style="padding:16px 32px 2px;font:400 12px Arial,sans-serif;color:#8E857C;letter-spacing:.05em;">%(date)s</td></tr>
  <tr><td style="padding:14px 32px 4px;"><table width="100%%" cellpadding="0" cellspacing="0" border="0">%(syn)s</table></td></tr>
  <tr><td style="padding:6px 32px 22px;font:400 15px/1.65 Georgia,serif;color:#2a2a2a;">Have a great week.<br><br>Cheers,<br>Jez</td></tr>
  <tr><td style="padding:8px 32px 0;"><table width="100%%" cellpadding="0" cellspacing="0" border="0" style="border-top:1px solid #ece7df;"><tr><td style="font:700 10px Arial,sans-serif;letter-spacing:2px;text-transform:uppercase;color:#8E857C;padding:16px 0 8px;">A taste of what&rsquo;s inside</td></tr>%(gl)s</table></td></tr>
  <tr><td style="padding:22px 32px 24px;text-align:center;"><a href="%(live)s" style="background:#ff6600;color:#fff;text-decoration:none;padding:12px 22px;border-radius:4px;font:600 14px Arial,sans-serif;display:inline-block;">Read the full briefing &rarr;</a></td></tr>
  %(homescreen)s
  <tr><td style="padding:14px 32px 22px;border-top:1px solid #ece7df;font:400 11px Arial,sans-serif;color:#8E857C;text-align:center;">Performance Intelligence Weekly Briefing</td></tr>
</table></td></tr></table></body></html>""" % dict(logo=LOGO, note=note, date=date, syn=syn_html, gl=gl_html, live=LIVE, homescreen=HOMESCREEN_CARD)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python build_monday_email.py index.html [preview_url] > monday.html")
    sys.stdout.write(build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""))
