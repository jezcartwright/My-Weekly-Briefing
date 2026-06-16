#!/usr/bin/env python3
# 1) linkify now rewrites Bookshop search links -> Amazon search in the user's
#    country (best-guess from timezone/locale, .com fallback). App-wide: used by
#    both the in-app "Go Deeper" links and the PDF.
# 2) PDF deeper links (.pdf-di a) use the category colour (var --link) instead of
#    the hard-coded brown, matching the in-app links and the topic colour.
import os, sys

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/weekly-briefing-local/test-repo/index.html')

with open(PATH, 'r', encoding='utf-8') as f:
    s = f.read()
orig_len = len(s)

old_linkify = """function linkify(text,url){ if(url)return'<a href="'+url+'" target="_blank" rel="noopener">'+text+'</a>'; return text; }"""

new_linkify = """function amazonHost(){
  var tz=''; try{tz=Intl.DateTimeFormat().resolvedOptions().timeZone||'';}catch(e){}
  var tzMap={'Europe/London':'co.uk','Europe/Dublin':'co.uk','Europe/Berlin':'de','Europe/Vienna':'de','Europe/Zurich':'de','Europe/Paris':'fr','Europe/Brussels':'fr','Europe/Luxembourg':'fr','Europe/Madrid':'es','Europe/Rome':'it','Europe/Amsterdam':'nl','Europe/Stockholm':'se','Europe/Warsaw':'pl','Asia/Tokyo':'co.jp','Asia/Kolkata':'in','Asia/Calcutta':'in','Asia/Singapore':'sg','Asia/Dubai':'ae','Australia/Sydney':'com.au','Australia/Melbourne':'com.au','Australia/Perth':'com.au','Australia/Brisbane':'com.au','America/Toronto':'ca','America/Vancouver':'ca','America/Edmonton':'ca','America/Winnipeg':'ca','America/Halifax':'ca','America/Mexico_City':'com.mx','America/Sao_Paulo':'com.br'};
  if(tzMap[tz])return'www.amazon.'+tzMap[tz];
  if(tz.indexOf('Australia/')===0)return'www.amazon.com.au';
  var loc=''; try{loc=(navigator.language||navigator.userLanguage||'');}catch(e){}
  var reg=(loc.split('-')[1]||'').toUpperCase();
  var regMap={GB:'co.uk',IE:'co.uk',US:'com',CA:'ca',DE:'de',AT:'de',CH:'de',FR:'fr',BE:'fr',ES:'es',IT:'it',NL:'nl',SE:'se',PL:'pl',JP:'co.jp',IN:'in',SG:'sg',AE:'ae',AU:'com.au',MX:'com.mx',BR:'com.br',TR:'com.tr'};
  if(regMap[reg])return'www.amazon.'+regMap[reg];
  return'www.amazon.com';
}
function bookToAmazon(url){
  var m=/bookshop\\.org\\/beta-search\\?keywords=([^&#]+)/.exec(url||'');
  if(!m)return url;
  var kw=''; try{kw=decodeURIComponent(m[1].replace(/\\+/g,' '));}catch(e){kw=m[1];}
  return 'https://'+amazonHost()+'/s?k='+encodeURIComponent(kw);
}
function linkify(text,url){ url=bookToAmazon(url); if(url)return'<a href="'+url+'" target="_blank" rel="noopener">'+text+'</a>'; return text; }"""

old_pdf_di_a = ".pdf-di a{color:#A0530B;text-decoration:underline;text-underline-offset:2px;text-decoration-thickness:0.5px}"
new_pdf_di_a = ".pdf-di a{color:var(--link,#A0530B);text-decoration:underline;text-underline-offset:2px;text-decoration-thickness:0.5px}"

edits = [(old_linkify, new_linkify), (old_pdf_di_a, new_pdf_di_a)]

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
