#!/usr/bin/env python3
# Two small notes UI fixes in index.html:
#  1. .has-note-pill -> orange tint (uses existing --orange tokens, replaces gold)
#  2. topic note label "My Notes on this topic" -> singular "My note on this topic"
import os, sys

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/weekly-briefing-local/test-repo/index.html')

with open(PATH, 'r', encoding='utf-8') as f:
    s = f.read()
orig_len = len(s)

edits = [
    ("""\
.has-note-pill{font-family:'Inter',sans-serif;display:inline-flex;align-items:center;gap:3px;background:#fff8ee;border:1px solid #f0e8d0;border-radius:10px;padding:2px 7px;font-size:9px;color:#C9A84C;font-weight:700;margin-top:6px}""",
     """\
.has-note-pill{font-family:'Inter',sans-serif;display:inline-flex;align-items:center;gap:3px;background:var(--orange-light);border:1px solid var(--orange-mid);border-radius:10px;padding:2px 7px;font-size:9px;color:var(--orange);font-weight:700;margin-top:6px}"""),
    ("""My Notes on this topic""",
     """My note on this topic"""),
]

for i, (old, new) in enumerate(edits, 1):
    n = s.count(old)
    if n != 1:
        raise SystemExit('EDIT %d: anchor found %d times (expected 1). Aborting, no file written.' % (i, n))
    s = s.replace(old, new)

if len(s) < 300000:
    raise SystemExit('Result too small (%d bytes) — aborting.' % len(s))

tmp = PATH + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(s)
os.replace(tmp, PATH)
print('OK: %d edits applied. %d -> %d bytes (%+d).' % (len(edits), orig_len, len(s), len(s) - orig_len))
