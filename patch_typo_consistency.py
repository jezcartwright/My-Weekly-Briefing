#!/usr/bin/env python3
# Make Notes + Liked typography match the home topic card:
#  - titles  -> IBM Plex Serif 15/18/24 w600  (= .tt)
#  - headline -> IBM Plex Serif 12/14/18 w500 (= .thl)
#  - "My note" label -> orange (was gold #C9A84C), 11/13/15 (= .topic-notes-label)
#  - user note text stays Inter (the font it's typed in)
import os, sys

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/weekly-briefing-local/test-repo/index.html')

with open(PATH, 'r', encoding='utf-8') as f:
    s = f.read()
orig_len = len(s)

SERIF = "'IBM Plex Serif',Georgia,'Times New Roman',serif"

edits = [
    (".ne-title{font-family:'Inter',sans-serif;font-size:13px;font-weight:700;color:var(--t);margin-bottom:2px}",
     ".ne-title{font-family:" + SERIF + ";font-size:15px;font-weight:600;color:var(--t);margin-bottom:2px;line-height:1.2;letter-spacing:-0.005em}"),
    (".ne-hl{font-size:8px;color:var(--t2);margin-bottom:4px;line-height:1.4}",
     ".ne-hl{font-family:" + SERIF + ";font-size:12px;font-weight:500;color:var(--t2);margin-bottom:4px;line-height:1.45}"),
    (".ne-preview{font-size:8.5px;color:var(--t2);line-height:1.6;padding:8px 12px;background:#fffdf9;border-top:1px solid #f0e8d0}",
     ".ne-preview{font-family:'Inter',sans-serif;font-size:8.5px;color:var(--t2);line-height:1.6;padding:8px 12px;background:#fffdf9;border-top:1px solid #f0e8d0}"),
    (".ne-edit-label{font-size:8px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:#C9A84C;margin-bottom:5px;font-family:'Inter',sans-serif}",
     ".ne-edit-label{font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:var(--orange);margin-bottom:5px;font-family:'Inter',sans-serif}"),
    (".lh-title{font-family:'Inter',sans-serif;font-size:13px;font-weight:600;color:var(--t);margin-bottom:3px;line-height:1.25;letter-spacing:-0.005em}",
     ".lh-title{font-family:" + SERIF + ";font-size:15px;font-weight:600;color:var(--t);margin-bottom:3px;line-height:1.25;letter-spacing:-0.005em}"),
    ("body.text-large .ne-title{font-size:16px}",  "body.text-large .ne-title{font-size:18px}"),
    ("body.text-xlarge .ne-title{font-size:20px}", "body.text-xlarge .ne-title{font-size:24px}"),
    ("body.text-large .ne-hl{font-size:11px}",     "body.text-large .ne-hl{font-size:14px}"),
    ("body.text-xlarge .ne-hl{font-size:14px}",    "body.text-xlarge .ne-hl{font-size:18px}"),
    ("body.text-large .ne-edit-label{font-size:10px}",  "body.text-large .ne-edit-label{font-size:13px}"),
    ("body.text-xlarge .ne-edit-label{font-size:11px}", "body.text-xlarge .ne-edit-label{font-size:15px}"),
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
