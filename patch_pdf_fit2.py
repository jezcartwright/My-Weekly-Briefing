#!/usr/bin/env python3
# Make two topics fit one PDF page even for the heaviest category (geopolitics,
# ~25-30% longer than the others this week). Main lever: widen the Why column
# (that text dominates the height), plus small type/spacing trims. The graceful
# 1-per-page fallback in pdfBuildSheets is left intact so content never clips.
import os, sys
PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/weekly-briefing-local/test-repo/index.html')
with open(PATH, 'r', encoding='utf-8') as f:
    s = f.read()
orig = len(s)

edits = [
    ('.pdf-two{display:grid;grid-template-columns:1.15fr 1fr;gap:18px;margin:0 0 9px 22px}',
     '.pdf-two{display:grid;grid-template-columns:1.6fr 1fr;gap:16px;margin:0 0 7px 22px}'),
    ('border-radius:1px;padding:14px 18px 12px;margin-bottom:18px',
     'border-radius:1px;padding:12px 16px 10px;margin-bottom:13px'),
    ('.pdf-bt{font-size:9.5px;color:var(--t);line-height:1.45}',
     '.pdf-bt{font-size:9px;color:var(--t);line-height:1.4}'),
    ('color:var(--t2);margin:0 0 9px 22px;line-height:1.4',
     'color:var(--t2);margin:0 0 7px 22px;line-height:1.35'),
    ('padding:8px 0 0 22px', 'padding:6px 0 0 22px'),
    ('margin-bottom:3px;display:flex;gap:8px;line-height:1.35',
     'margin-bottom:2px;display:flex;gap:8px;line-height:1.3'),
]
for i, (old, new) in enumerate(edits, 1):
    n = s.count(old)
    if n != 1:
        raise SystemExit('EDIT %d anchor found %d times (expected 1). Aborting.' % (i, n))
    s = s.replace(old, new)
if len(s) < 300000:
    raise SystemExit('Result too small. Aborting.')
tmp = PATH + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(s)
os.replace(tmp, PATH)
print('OK: %d edits applied. %d -> %d bytes (%+d).' % (len(edits), orig, len(s), len(s) - orig))
