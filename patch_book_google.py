#!/usr/bin/env python3
# Change book "Go Deeper" links from an Amazon product search (which returns
# "no results" for niche, mis-classified, or non-existent titles) to a plain
# Google search of the title/author. A web search never dead-ends and Google
# localises results by region. The matching logic (bookshop + google.com/books
# patterns) is unchanged; only the target URL changes. Real source URLs
# (publishers, journals) still pass straight through.
import os, sys

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/weekly-briefing-local/test-repo/index.html')

with open(PATH, 'r', encoding='utf-8') as f:
    s = f.read()
orig = len(s)

hdr_old = "function bookToAmazon(url){"
hdr_new = ('// Book "Go Deeper" links -> a Google search of the title/author. A search\n'
           '// never dead-ends on a "no results" page the way an Amazon book search\n'
           '// can (niche, mis-classified, or non-existent titles), and Google\n'
           '// localises results by the reader\'s region. Name kept for call sites.\n'
           'function bookToAmazon(url){')
if s.count(hdr_old) != 1:
    raise SystemExit('function header anchor found %d times (expected 1).' % s.count(hdr_old))
s = s.replace(hdr_old, hdr_new)

ret_old = "  return 'https://'+amazonHost()+'/s?k='+encodeURIComponent(kw)+'&i=stripbooks';"
ret_new = "  return 'https://www.google.com/search?q='+encodeURIComponent(kw);"
if s.count(ret_old) != 1:
    raise SystemExit('return-line anchor found %d times (expected 1).' % s.count(ret_old))
s = s.replace(ret_old, ret_new)

assert s.count("www.google.com/search?q=") == 1
assert "/s?k='+encodeURIComponent(kw)+'&i=stripbooks'" not in s
if len(s) < 300000:
    raise SystemExit('Result too small. Aborting.')

tmp = PATH + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(s)
os.replace(tmp, PATH)
print('OK: book links now go to a Google search. %d -> %d bytes (%+d).'
      % (orig, len(s), len(s) - orig))
