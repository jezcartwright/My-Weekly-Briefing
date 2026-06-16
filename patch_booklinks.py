#!/usr/bin/env python3
# Fix: 41 "Go Deeper" book links point at https://www.google.com/books?q=...,
# which is not a real Google page and returns nothing. bookToAmazon() already
# turns bookshop.org search links into localized Amazon book searches; extend it
# to also catch the google books pattern (www.google.com/books?q= and
# books.google.com/books?q=). Because both the in-app linkify() and the PDF
# pdfLinkLine() call bookToAmazon(), this fixes every occurrence at render time
# with no content rewrite. Non-book source URLs (publishers, journals) don't
# match and pass through untouched.
import os, sys

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/weekly-briefing-local/test-repo/index.html')

with open(PATH, 'r', encoding='utf-8') as f:
    s = f.read()
orig = len(s)

old = r'''function bookToAmazon(url){
  var m=/bookshop\.org\/beta-search\?keywords=([^&#]+)/.exec(url||'');
  if(!m)return url;
  var kw=''; try{kw=decodeURIComponent(m[1].replace(/\+/g,' '));}catch(e){kw=m[1];}
  return 'https://'+amazonHost()+'/s?k='+encodeURIComponent(kw)+'&i=stripbooks';
}'''

new = r'''function bookToAmazon(url){
  url=url||'';
  var m=/bookshop\.org\/beta-search\?keywords=([^&#]+)/.exec(url)
     || /google\.[a-z.]+\/books\?q=([^&#]+)/.exec(url);
  if(!m)return url;
  var kw=''; try{kw=decodeURIComponent(m[1].replace(/\+/g,' '));}catch(e){kw=m[1];}
  return 'https://'+amazonHost()+'/s?k='+encodeURIComponent(kw)+'&i=stripbooks';
}'''

if s.count(old) != 1:
    raise SystemExit('bookToAmazon anchor found %d times (expected 1). Aborting.' % s.count(old))
s = s.replace(old, new)

assert s.count("google\\.[a-z.]+\\/books") == 1
if len(s) < 300000:
    raise SystemExit('Result too small. Aborting.')

tmp = PATH + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(s)
os.replace(tmp, PATH)
print('OK: google.com/books links now route to localized Amazon search. %d -> %d bytes (%+d).'
      % (orig, len(s), len(s) - orig))
