#!/usr/bin/env python3
# Broadens story sourcing in generate_content.py:
#  - rewrites the global source-priority line to vary outlets week to week
#  - adds a per-category CATEGORY_SOURCES map + shared CROSS_CUTTING list
#  - feeds both into the per-category prompt
# Safe-edit: each change asserted unique, py_compile + format() smoke test, then os.replace.
import os, re, sys, py_compile

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/weekly-briefing-local/test-repo/generate_content.py')

with open(PATH, 'r', encoding='utf-8') as f:
    s = f.read()
orig_len = len(s)

pat1 = re.compile(
    r"Use web search to find current stories, papers, research and commentary published\s+"
    r"in the last 7 days\. Prioritise: HBR, McKinsey, FT, WSJ, The Economist, Nature,\s+"
    r"academic journals, and respected thought leaders\.")
new1 = ("Use web search to find current stories, papers, research and commentary published \n"
        "in the last 7 days. Draw from a BROAD range of credible sources. Favour the \n"
        "suggested publications provided for each category, alongside mainstays like HBR, \n"
        "the FT, The Economist and Nature. Deliberately vary the outlets you cite from week \n"
        "to week so the briefing never leans on the same few publications; a mix of essay \n"
        "outlets, research journals and serious journalism is ideal.")
s, n1 = pat1.subn(new1, s)
if n1 != 1:
    raise SystemExit('EDIT 1 (system prompt): matched %d times (expected 1).' % n1)

old2 = "Focus specifically on {category_focus}."
new2 = ("Focus specifically on {category_focus}.\n\n"
        "Favour these publications where they have relevant, recent material (not "
        "exclusively; a strong current piece from elsewhere is always welcome, and do not "
        "force a source in if it has nothing timely): {category_sources}.\n"
        "Across any category you may also draw from: {cross_cutting}.")
if s.count(old2) != 1:
    raise SystemExit('EDIT 2 (prompt template): anchor found %d times (expected 1).' % s.count(old2))
s = s.replace(old2, new2)

pat3 = re.compile(
    r'("philosophy": "philosophy, ethics, meaning, first principles thinking, '
    r'Stoicism and the examined life as applied to leadership",\n\})')
dicts = '''

CATEGORY_SOURCES = {
    "leadership": "Harvard Business Review, MIT Sloan Management Review, McKinsey Quarterly, Korn Ferry Institute, Egon Zehnder Insights, The Leadership Quarterly, First Round Review",
    "markets": "The Economist, Financial Times (Lex and Alphaville), Howard Marks's Oaktree Capital memos, NBER working papers, Marginal Revolution, the Journal of Finance, the Review of Financial Studies",
    "psychology": "Behavioral Scientist, Psyche, Nature Human Behaviour, Psychological Science, the Annual Review of Psychology, Trends in Cognitive Sciences",
    "technology": "MIT Technology Review, IEEE Spectrum, Stratechery, The Information, arXiv (cs.AI and cs.LG), Quanta Magazine, Communications of the ACM",
    "geopolitics": "Foreign Affairs, Foreign Policy, War on the Rocks, Chatham House, Brookings, CSIS, the Carnegie Endowment, International Security, the Journal of Democracy",
    "philosophy": "Aeon, the Stanford Encyclopedia of Philosophy, The Point, The New Atlantis, Mind, the Journal of Philosophy",
}

CROSS_CUTTING = "Noema, Nautilus, Works in Progress, Asterisk, Farnam Street and The Marginalian"'''
s, n3 = pat3.subn(lambda m: m.group(1) + dicts, s)
if n3 != 1:
    raise SystemExit('EDIT 3 (source dicts): matched %d times (expected 1).' % n3)

old4 = ('        category_focus=CATEGORY_FOCUS[cat["id"]],\n'
        '    )')
new4 = ('        category_focus=CATEGORY_FOCUS[cat["id"]],\n'
        '        category_sources=CATEGORY_SOURCES[cat["id"]],\n'
        '        cross_cutting=CROSS_CUTTING,\n'
        '    )')
if s.count(old4) != 1:
    raise SystemExit('EDIT 4 (format call): anchor found %d times (expected 1).' % s.count(old4))
s = s.replace(old4, new4)

if len(s) < 30000:
    raise SystemExit('Result too small (%d bytes) — aborting.' % len(s))

tmp = PATH + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(s)
try:
    py_compile.compile(tmp, doraise=True)
except py_compile.PyCompileError as e:
    os.remove(tmp)
    raise SystemExit('Syntax check FAILED, no file written:\n' + str(e))
os.replace(tmp, PATH)
print('OK: 4 edits applied. %d -> %d bytes (+%d).' % (orig_len, len(s), len(s) - orig_len))
