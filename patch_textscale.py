#!/usr/bin/env python3
# Complete the text-size (Aa) scaling so no readable content stays frozen.
# Adds large + x-large overrides for 7 classes that were never enrolled:
#   Notes:  .ne-title, .ne-edit-label, .ne-edit-ta
#   Topic:  .it-attr, .topic-notes-label, .topic-notes-hint
#   Liked:  .lh-cat
import os, sys

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/weekly-briefing-local/test-repo/index.html')

with open(PATH, 'r', encoding='utf-8') as f:
    s = f.read()
orig_len = len(s)

edits = [
    ("body.text-large .ng-icon{font-size:15px}",
     "body.text-large .ng-icon{font-size:15px}\n"
     "body.text-large .ne-title{font-size:16px}\n"
     "body.text-large .ne-edit-label{font-size:10px}\n"
     "body.text-large .ne-edit-ta{font-size:14px}\n"
     "body.text-large .it-attr{font-size:13px}\n"
     "body.text-large .lh-cat{font-size:12px}\n"
     "body.text-large .topic-notes-label{font-size:13px}\n"
     "body.text-large .topic-notes-hint{font-size:11px}"),
    ("body.text-xlarge .ng-icon{font-size:17px}",
     "body.text-xlarge .ng-icon{font-size:17px}\n"
     "body.text-xlarge .ne-title{font-size:20px}\n"
     "body.text-xlarge .ne-edit-label{font-size:11px}\n"
     "body.text-xlarge .ne-edit-ta{font-size:17px}\n"
     "body.text-xlarge .it-attr{font-size:15px}\n"
     "body.text-xlarge .lh-cat{font-size:14px}\n"
     "body.text-xlarge .topic-notes-label{font-size:15px}\n"
     "body.text-xlarge .topic-notes-hint{font-size:13px}"),
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
