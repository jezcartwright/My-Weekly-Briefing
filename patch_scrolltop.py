#!/usr/bin/env python3
# Fix: switching category (sc) or view (showView) re-renders content into an
# inner scroll area (.sa: #ts today, #ls library, #ks likes, #ns notes) but
# leaves that area's scrollTop where it was, so the new list opens mid-scroll.
# Reset the relevant scroll area(s) to the top on switch.
import os, sys, re

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/weekly-briefing-local/test-repo/index.html')

with open(PATH, 'r', encoding='utf-8') as f:
    s = f.read()
orig = len(s)

# Edit 1 — category switch: scroll the today area (#ts) back to top.
sc_old = ("function sc(id){ ac=CATS.find(function(c){return c.id===id;}); "
          "oc=null; rt(); rto(); rv(id); renderBannerTabs(); }")
sc_new = ("function sc(id){ ac=CATS.find(function(c){return c.id===id;}); "
          "oc=null; rt(); rto(); rv(id); renderBannerTabs(); "
          "var _ts=document.getElementById('ts'); if(_ts)_ts.scrollTop=0; }")

# Edit 2 — view switch: scroll each list area back to top when showView runs.
sv_old = "  else rt();\n  renderBannerTabs();\n}"
sv_new = ("  else rt();\n"
          "  ['ts','ls','ks','ns'].forEach(function(id){var el=document.getElementById(id); if(el)el.scrollTop=0;});\n"
          "  renderBannerTabs();\n}")

for label, old in [('sc', sc_old), ('showView', sv_old)]:
    if s.count(old) != 1:
        raise SystemExit('Anchor "%s" found %d times (expected 1). Aborting.' % (label, s.count(old)))

s = s.replace(sc_old, sc_new).replace(sv_old, sv_new)

assert s.count("if(_ts)_ts.scrollTop=0;") == 1
assert s.count("['ts','ls','ks','ns'].forEach") == 1
if len(s) < 300000:
    raise SystemExit('Result too small. Aborting.')

tmp = PATH + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(s)
os.replace(tmp, PATH)
print('OK: scroll resets to top on category/view switch. %d -> %d bytes (%+d).'
      % (orig, len(s), len(s) - orig))
