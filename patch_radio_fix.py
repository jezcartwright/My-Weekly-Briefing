#!/usr/bin/env python3
# Fix: the Compose radios used the browser-native accent-color control, whose
# inner dot renders larger than the ring on this Chrome build (the orange dot
# spilling past the outline). Replace with a drawn radio: a 16px ring and a
# centred 8px dot that cannot exceed it.
import os, sys

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/weekly-briefing-local/test-repo/admin.html')

with open(PATH, 'r', encoding='utf-8') as f:
    s = f.read()
orig = len(s)

old = '.radio input{accent-color:var(--orange);cursor:pointer}'
new = ('.radio input{appearance:none;-webkit-appearance:none;width:16px;height:16px;'
       'margin:0;flex:0 0 auto;border:1.5px solid var(--b);border-radius:50%;'
       'background:var(--paper);cursor:pointer;display:inline-grid;place-content:center}\n'
       '.radio input:checked{border-color:var(--orange)}\n'
       '.radio input:checked::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--orange)}\n'
       '.radio input:focus-visible{outline:2px solid var(--orange);outline-offset:2px}')

if s.count(old) != 1:
    raise SystemExit('radio CSS anchor found %d times (expected 1). Aborting.' % s.count(old))
s = s.replace(old, new)

# sanity
assert s.count('.radio input:checked::before') == 1
assert 'accent-color:var(--orange)' not in s
if len(s) < orig:  # we only added text
    raise SystemExit('Result shrank unexpectedly. Aborting.')

tmp = PATH + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(s)
os.replace(tmp, PATH)
print('OK: Compose radios redrawn (16px ring, centred 8px dot). %d -> %d bytes (%+d).'
      % (orig, len(s), len(s) - orig))
