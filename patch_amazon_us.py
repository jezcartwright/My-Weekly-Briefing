#!/usr/bin/env python3
# Fix: amazonHost() had no US timezones in its map, so a US phone fell through
# to navigator.language; a UK-language US phone (en-GB) then resolved to
# amazon.co.uk. Add the US IANA zones -> 'com' so timezone (the real location
# signal) wins for the US too. Canada/Mexico/Brazil entries are matched before
# these, so they're unaffected.
import os, sys

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/weekly-briefing-local/test-repo/index.html')

with open(PATH, 'r', encoding='utf-8') as f:
    s = f.read()
orig = len(s)

old = "var tzMap={'Europe/London':'co.uk',"
us = ("'America/New_York':'com','America/Detroit':'com','America/Chicago':'com',"
      "'America/Denver':'com','America/Boise':'com','America/Phoenix':'com',"
      "'America/Los_Angeles':'com','America/Anchorage':'com','America/Adak':'com',"
      "'America/Juneau':'com','America/Nome':'com','America/Sitka':'com',"
      "'America/Indiana/Indianapolis':'com','America/Kentucky/Louisville':'com',"
      "'America/Menominee':'com','Pacific/Honolulu':'com',")
new = "var tzMap={" + us + "'Europe/London':'co.uk',"

if s.count(old) != 1:
    raise SystemExit('tzMap anchor found %d times (expected 1). Aborting.' % s.count(old))
s = s.replace(old, new)

assert s.count("'America/Los_Angeles':'com'") == 1
assert s.count("'America/Toronto':'ca'") == 1  # Canada entry still intact
if len(s) < 300000:
    raise SystemExit('Result too small. Aborting.')

tmp = PATH + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(s)
os.replace(tmp, PATH)
print('OK: US timezones added to amazonHost. %d -> %d bytes (%+d).'
      % (orig, len(s), len(s) - orig))
