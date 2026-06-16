#!/usr/bin/env python3
# Add vertical separation between the two topics on a PDF page.
# .pdf-topic gets a bottom margin; .pdf-topic:last-child already resets it to 0,
# so there's a gap between the pair but no extra space above the footer.
import os, sys
PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/weekly-briefing-local/test-repo/index.html')
with open(PATH, 'r', encoding='utf-8') as f:
    s = f.read()
orig = len(s)
old = 'padding:14px 18px 12px;margin-bottom:0}'
new = 'padding:14px 18px 12px;margin-bottom:18px}'
n = s.count(old)
if n != 1:
    raise SystemExit('anchor found %d times (expected 1). Aborting.' % n)
s = s.replace(old, new)
if len(s) < 300000:
    raise SystemExit('Result too small. Aborting.')
tmp = PATH + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(s)
os.replace(tmp, PATH)
print('OK: topic gap added. %d -> %d bytes (%+d).' % (orig, len(s), len(s) - orig))
