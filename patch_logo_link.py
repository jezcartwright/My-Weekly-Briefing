#!/usr/bin/env python3
# Make the main-app masthead (logo + PERFORMANCE/INTELLIGENCE/WEEKLY BRIEFING
# wordmark) a clickable link to www.jezcartwright.com, opening in a new tab.
# Zero visual change: the <a> reproduces .identity's flex column/centre layout.
# Leaves the PDF/print header (.pdf-header .identity, deeper indent) and the
# login screen untouched.
import os, sys

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/weekly-briefing-local/test-repo/index.html')

with open(PATH, 'r', encoding='utf-8') as f:
    s = f.read()
orig = len(s)

# --- Edit 1: open the anchor right after the main-app .identity div ----------
# 4-space-indented .identity + 6-space-indented pi-logo is unique to header B
# (the PDF header uses 6/8-space indent; the login screen has no .identity).
open_old = '    <div class="identity">\n      <div class="pi-logo">'
open_new = ('    <div class="identity">\n'
            '      <a class="brand-link" href="https://www.jezcartwright.com"'
            ' target="_blank" rel="noopener noreferrer"'
            ' aria-label="Visit jezcartwright.com">\n'
            '      <div class="pi-logo">')

# --- Edit 2: close the anchor before the .identity div closes ----------------
# Only header B's wordmark is immediately followed by the #tabs container.
close_old = '      </svg>\n    </div>\n    <div id="tabs"></div>'
close_new = '      </svg>\n      </a>\n    </div>\n    <div id="tabs"></div>'

# --- Edit 3: CSS so the wrapper matches .identity exactly (no visual change) --
css_old = '.identity{display:flex;flex-direction:column;align-items:center;margin-top:0;padding-bottom:14px}'
css_new = (css_old +
           '\n.brand-link{display:flex;flex-direction:column;align-items:center;'
           'text-decoration:none;color:inherit}')

for label, old in [('open', open_old), ('close', close_old), ('css', css_old)]:
    if s.count(old) != 1:
        raise SystemExit('Anchor "%s" found %d times (expected 1). Aborting.'
                         % (label, s.count(old)))

s = s.replace(open_old, open_new).replace(close_old, close_new).replace(css_old, css_new)

# --- Safety checks -----------------------------------------------------------
if s.count('class="brand-link"') != 1:
    raise SystemExit('brand-link anchor count != 1. Aborting.')
if s.count('href="https://www.jezcartwright.com"') != 1:
    raise SystemExit('jezcartwright.com href count != 1. Aborting.')
if 'pdf-header' not in s:
    raise SystemExit('pdf-header vanished?! Aborting.')
if len(s) < 300000:
    raise SystemExit('Result too small (%d). Aborting.' % len(s))

tmp = PATH + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(s)
os.replace(tmp, PATH)
print('OK: masthead is now a link to www.jezcartwright.com. %d -> %d bytes (%+d).'
      % (orig, len(s), len(s) - orig))
