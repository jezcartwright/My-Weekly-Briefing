#!/usr/bin/env python3
# Notes panel category header ("LEADERSHIP / 1 note") was tiny and didn't scale
# with the text-size setting. Bump base sizes and add large/x-large overrides.
import os, sys

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/weekly-briefing-local/test-repo/index.html')

with open(PATH, 'r', encoding='utf-8') as f:
    s = f.read()
orig_len = len(s)

edits = [
    (".ng-icon{font-size:12px}",
     ".ng-icon{font-size:13px}"),
    (".ng-name{font-size:9px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;font-family:'Inter',sans-serif}",
     ".ng-name{font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;font-family:'Inter',sans-serif}"),
    (".ng-count{font-size:10px;color:var(--t3);margin-left:auto;font-family:'Inter',sans-serif}",
     ".ng-count{font-size:11px;color:var(--t3);margin-left:auto;font-family:'Inter',sans-serif}"),
    ("body.text-large .ne-preview{font-size:12px}",
     "body.text-large .ne-preview{font-size:12px}\n"
     "body.text-large .ng-name{font-size:13px}\n"
     "body.text-large .ng-count{font-size:13px}\n"
     "body.text-large .ng-icon{font-size:15px}"),
    ("body.text-xlarge .ne-preview{font-size:15px}",
     "body.text-xlarge .ne-preview{font-size:15px}\n"
     "body.text-xlarge .ng-name{font-size:15px}\n"
     "body.text-xlarge .ng-count{font-size:15px}\n"
     "body.text-xlarge .ng-icon{font-size:17px}"),
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
