#!/usr/bin/env python3
# Scope the Amazon book search to the print Books department (&i=stripbooks) so
# links land on the actual book, not the Audible/audiobook edition. App-wide
# (linkify -> bookToAmazon is used by both the in-app Go Deeper links and the PDF).
import os, sys
PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/weekly-briefing-local/test-repo/index.html')
with open(PATH, 'r', encoding='utf-8') as f:
    s = f.read()
orig = len(s)
old = "return 'https://'+amazonHost()+'/s?k='+encodeURIComponent(kw);"
new = "return 'https://'+amazonHost()+'/s?k='+encodeURIComponent(kw)+'&i=stripbooks';"
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
print('OK: applied. %d -> %d bytes (%+d).' % (orig, len(s), len(s) - orig))
