#!/usr/bin/env python3
# Generator fixes for book "Go Deeper" links:
#  G1 _book_search_url -> Google search (was bookshop, which the client turned
#     into an Amazon product search that can return "no results").
#  G2 update that docstring line accordingly.
#  G3 ALWAYS override a book-like item's URL with our search link (was: only
#     when the model left it null). The model emits broken google.com/books
#     links and links to books that don't exist, so we never trust its book URL.
#  G4 fix the now-inaccurate comment.
#  G5 strengthen the prompt: only recommend books that really exist, never
#     invent a title or pair a real author with a title they didn't write, and
#     never output a google.com/books / guessed link (url=null for books).
import os, sys, py_compile

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/weekly-briefing-local/test-repo/generate_content.py')

with open(PATH, 'r', encoding='utf-8') as f:
    s = f.read()
orig = len(s)

edits = [
    ("    return 'https://bookshop.org/beta-search?keywords=' + urllib.parse.quote(q)",
     "    return 'https://www.google.com/search?q=' + urllib.parse.quote(q)"),
    ("    title/author. Bookshop.org is used as a reputable, non-Amazon\n"
     "    default appropriate for a professional briefing.",
     "    title/author. A web search is used so the link can never dead-end on a\n"
     "    \"no results\" page the way a product search can."),
    ("            if not d_url and _looks_like_book(d_text):",
     "            if _looks_like_book(d_text):"),
    ("            # (item 1), and never overwrite a real URL the model supplied.",
     "            # (item 1). For books we deliberately override any model URL."),
]
for i, (old, new) in enumerate(edits, 1):
    if s.count(old) != 1:
        raise SystemExit('Edit G%d anchor found %d times (expected 1). Aborting.' % (i, s.count(old)))
    s = s.replace(old, new)

start_anchor = "  - For Items 2 and 3: if it is a BOOK, set url to null UNLESS you are"
end_anchor = "    bookshop search link automatically for books left without a URL."
if s.count(start_anchor) != 1 or s.count(end_anchor) != 1:
    raise SystemExit('G5 anchors not unique (%d / %d).' % (s.count(start_anchor), s.count(end_anchor)))
i0 = s.index(start_anchor)
j0 = s.index(end_anchor, i0) + len(end_anchor)
g5_new = (
    "  - For Items 2 and 3: recommend only books and resources that genuinely\n"
    "    EXIST. Make sure the title and author are real and that the author\n"
    "    actually wrote that title. Do not invent a title, and do not attach a\n"
    "    real author to a book they did not write. If you are not confident a\n"
    "    book is real, cite a different verifiable book or a reputable article.\n"
    "  - For any BOOK, set url to null. Do NOT output a google.com/books,\n"
    "    books.google.com or any guessed link; the system adds a reliable search\n"
    "    link for the title and author."
)
s = s[:i0] + g5_new + s[j0:]

assert "https://www.google.com/search?q=' + urllib.parse.quote(q)" in s
assert "if not d_url and _looks_like_book" not in s
assert "Do NOT output a google.com/books" in s

tmp = PATH + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(s)
try:
    py_compile.compile(tmp, doraise=True)
except py_compile.PyCompileError as e:
    os.remove(tmp)
    raise SystemExit('Syntax error, not written:\n%s' % e)
os.replace(tmp, PATH)
print('OK: generator book-link handling fixed. %d -> %d bytes (%+d). Syntax valid.'
      % (orig, len(s), len(s) - orig))
