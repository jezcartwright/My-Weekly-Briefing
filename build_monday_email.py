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
import os, sys, json, re, html as H, datetime, subprocess, tempfile

CATS = [("leadership","Leadership","#FF6600"),("markets","Markets","#0E3A7B"),
        ("psychology","Psychology","#C8243C"),("technology","Technology","#0096D6"),
        ("geopolitics","Geopolitics","#6B2DA8"),("philosophy","Philosophy","#2E7A3E")]
LIVE = "https://weeklybriefing.jezcartwright.com/"
LOGO = "https://weeklybriefing.jezcartwright.com/favicon-512x512.png"

STYLE_EXEMPLAR = """Happy Monday Everyone,
With the World Cup coming to the end of the group stages, we now enter the exciting knock out phases. For some it will be the most exciting of times, whilst for others it will be a tantalising end to the summer of sport. As an England fan I am not too hopeful, yet there is always dreams of '66!
The levels of delusion seen amongst fans is not confined to sports. The corporate world is no stranger to the realities of delusion that persist from the board room and move downwards in an organisation.
These can have catastrophic consequences and this even pervades out into the wider population that is seemingly ever more stressed in an ever changing world.
This is the thread that runs through this week's signals: the things we'd rather not look at. Senior teams are quietly editing out inconvenient information, executive stress has slipped past its pandemic peak, and the meritocratic story most leaders tell themselves about their own success is doing more damage than the markets they're trying to read. Avoidance, it turns out, is the dominant management style of late 2025.
Underneath that, the machines are wobbling in interesting ways. Frontier AI agents collapse when a tool misbehaves, large models fail basic self-control tests, and fact-checking with AI is leaving people worse at spotting fakes. Meanwhile the physical world reasserts itself through copper, heat above the silicon, and Micron's quietly extraordinary margins.
And then the slower currents: an IPO window closing, private credit meeting the retirement saver, Britain without a Prime Minister, and a 2030 deadline on the encryption holding it all together.
Twenty-four signals across six categories await. Please step inside.
Have a great week.
Cheers,
Jez"""

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
    """Defensively remove any fixed scaffolding the model echoed from the STYLE_EXEMPLAR:
    the greeting, the 'N signals \u2026 step inside' closing, and the 'Have a great week /
    Cheers, / Jez' sign-off. build() and the HTML template are the single source of truth
    for those lines, so the AI body must never contain them \u2014 otherwise they duplicate
    (two greetings) or land mid-email (a stray sign-off above the closing). The model is
    already told not to emit them; this guards against the times it does anyway."""
    out = []
    for p in paras:
        t = (p or "").strip()
        if not t:
            continue
        low = t.lower()
        # Greeting: drop the greeting clause but keep any real prose glued after it.
        if low.startswith("happy monday"):
            rest = _GREETING_RE.sub("", t, count=1).strip()
            if rest and not rest.lower().startswith("happy monday"):
                out.append(rest)
            continue
        # Closing line ("N signals across six categories await. Please step inside.")
        if "step inside" in low or "across six categories" in low:
            continue
        # Sign-off block ("Have a great week." / "Cheers," / "Jez")
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
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        prompt = (
            "You are drafting the opening of a weekly executive briefing email, in the established "
            "voice of its author, Jez. Match his voice, rhythm and structure closely.\n\n"
            "STYLE REFERENCE (a previous week's opening). Imitate the VOICE and STRUCTURE only \u2014 "
            "never reuse its content, theme, or its specific cultural references:\n---\n"
            + STYLE_EXEMPLAR +
            "\n---\n\nTHIS WEEK'S 24 TOPICS (six categories):\n"
            + "\n".join(lines) +
            "\n\nWrite ONLY the body paragraphs that sit between the greeting and the closing line. "
            "Do NOT write a greeting, a sign-off, or the 'N signals \u2026 step inside' line \u2014 those are added separately.\n\n"
            "Follow this structure (as in the reference):\n"
            "1) An opening hook: a vivid, lightly self-deprecating observation connecting a broad human "
            "theme to this week's material. The author personalises this line himself, so keep it engaging "
            "but do NOT assert specific real-world current events, scores, dates or news you cannot verify.\n"
            "2) A 'thread' paragraph naming the single idea running through this week's signals, drawn from the topics above.\n"
            "3) One or two short paragraphs narrating the categories as movements/currents (e.g. grouping the "
            "technology items as 'the machines', and the markets/geopolitics/philosophy items as 'slower currents'), "
            "evoking the real topics without listing all of them.\n\n"
            "Voice: warm, literate British English; essayistic, not a contents page; confident and a little wry; concrete. "
            "Narrate, don't enumerate.\n"
            "HARD RULES: ground every concrete claim in the topics provided \u2014 invent no facts, numbers, names, or events. "
            "No headings, no bullet points, no markdown. Avoid the words 'delve' and 'deluge'. About 230-280 words. "
            "Return only the paragraphs, separated by blank lines.")
        msg = client.messages.create(model="claude-opus-4-7", max_tokens=900,
                                     messages=[{"role":"user","content":prompt}])
        text = "".join(getattr(b,"text","") for b in msg.content if getattr(b,"type","")=="text").strip()
        paras = [p.strip() for p in text.split("\n\n") if p.strip()]
        return _strip_scaffolding(paras) or None
    except Exception as e:
        sys.stderr.write("  ! synopsis AI draft failed (%s); using fallback\n" % e)
        return None

def fallback_synopsis(data):
    picks = []
    for cid, label, _ in CATS:
        ts = data.get(cid) or []
        if ts: picks.append((label, ts[0].get("headline","").rstrip(".")))
    p1 = "There's a thread running through this week's signals worth pausing on before the detail."
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
  <tr><td style="padding:14px 32px 22px;border-top:1px solid #ece7df;font:400 11px Arial,sans-serif;color:#8E857C;text-align:center;">Performance Intelligence Weekly Briefing</td></tr>
</table></td></tr></table></body></html>""" % dict(logo=LOGO, note=note, date=date, syn=syn_html, gl=gl_html, live=LIVE)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python build_monday_email.py index.html [preview_url] > monday.html")
    sys.stdout.write(build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""))
