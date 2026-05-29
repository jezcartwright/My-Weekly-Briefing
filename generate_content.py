#!/usr/bin/env python3
"""
Performance Intelligence Weekly Briefing — Content Generator
Runs every Monday via GitHub Actions.
Calls Claude API with web search to generate fresh weekly content,
then updates index.html in the repo.
"""

import os
import re
import sys
import json
import base64
import datetime
import anthropic

REPO = "jezcartwright/My-Weekly-Briefing"
FILE_PATH = "index.html"

CATEGORIES = [
    {"id": "leadership",   "label": "Leadership",   "color": "#C9A84C"},
    {"id": "markets",      "label": "Markets",      "color": "#7EB8A4"},
    {"id": "psychology",   "label": "Psychology",   "color": "#C47F6B"},
    {"id": "technology",   "label": "Technology",   "color": "#7A9CC4"},
    {"id": "geopolitics",  "label": "Geopolitics",  "color": "#9B7EC4"},
    {"id": "philosophy",   "label": "Philosophy",   "color": "#A4B87E"},
]

SYSTEM_PROMPT = """You are an expert editor for Performance Intelligence Weekly Briefing — 
a high-quality executive briefing read by senior leaders, coaches and executives.

Your task: generate 4 topics per category based on the most relevant, timely and 
intellectually rich content from the past week across business, science, psychology 
and global affairs.

Use web search to find current stories, papers, research and commentary published 
in the last 7 days. Prioritise: HBR, McKinsey, FT, WSJ, The Economist, Nature, 
academic journals, and respected thought leaders.

Each topic must have:
- title: Short compelling title (4-7 words)
- headline: One powerful sentence that is the key insight (not a question)
- why: 2-3 sentences of substantive explanation with specific data/research
- ref: {text: "Author/Source (Year). 'Title.' Publication.", url: "real URL or null"}
- insight: A real attributed quote relevant to the topic
- attribution: "Full name, role/context"
- deeper: Array of 3 items [{text: "...", url: "real URL or null"}]
  - Item 1: A reflective question or personal challenge (url MUST be null)
  - Item 2: A specific book, article or resource with real URL if available
  - Item 3: A specific book, article or resource with real URL if available
  - For Items 2 and 3: if it is a BOOK, set url to null UNLESS you are
    certain of the real publisher/source page. Do NOT invent or guess a
    URL — a fabricated link is worse than none. The system will add a safe
    bookshop search link automatically for books left without a URL.
  - When an item is a book, phrase its text as: Title - Author(s)
    (so the title and author can be reliably detected).

Quality standards:
- WHY IT MATTERS must cite specific studies, data points or named research
- Quotes must be real, accurately attributed
- Topics should feel CURRENT — referencing this week's news/research where possible
- Write for intelligent executives who read broadly
- British spelling throughout (organisation, behaviour, recognise etc.)

Return ONLY valid JSON — no markdown, no explanation, no backticks.

CRITICAL JSON RULES:
- Any double-quote character inside a string value MUST be escaped as \\".
  Prefer single quotes for quotations within text (e.g. 'as Seneca put it').
- Do not use smart/curly quotes; use straight ' and ". Do not use em dashes; use a hyphen.
- No trailing commas. Output must parse with a strict JSON parser on the first attempt.
- Output the JSON array EXACTLY ONCE. Do not repeat it. Do not write any preamble
  such as "Here is the final JSON:" and do not write anything after the closing ].
- Do not include citation markers, footnote tags, or any <...> tags inside string
  values. Write plain prose only. The very first character of your response must be
  [ and the very last character must be ]."""

USER_PROMPT_TEMPLATE = """Today is {today}. 

Search the web for the most relevant, timely and high-signal content published in the 
last 7 days in the area of {category}.

Generate exactly 4 topics for the {category} section of this week's Performance 
Intelligence Weekly Briefing.

Return a JSON array of exactly 4 topic objects:
[
  {{
    "title": "...",
    "headline": "...",
    "why": "...",
    "ref": {{"text": "...", "url": "...or null"}},
    "insight": "...",
    "attribution": "...",
    "deeper": [
      {{"text": "...", "url": "...or null"}},
      {{"text": "...", "url": "...or null"}},
      {{"text": "...", "url": "...or null"}}
    ]
  }},
  ...
]

Focus specifically on {category_focus}."""

CATEGORY_FOCUS = {
    "leadership": "leadership, management, organisational behaviour, executive performance, team dynamics, strategy and decision-making",
    "markets": "financial markets, economics, business strategy, investment, pricing, corporate finance and global commerce",
    "psychology": "behavioural science, cognitive psychology, performance psychology, coaching, motivation and human behaviour",
    "technology": "AI, emerging technology, digital transformation, cybersecurity, platforms and the future of work",
    "geopolitics": "global affairs, international relations, supply chains, geopolitical risk, trade and government policy",
    "philosophy": "philosophy, ethics, meaning, first principles thinking, Stoicism and the examined life as applied to leadership",
}


def parse_topics_json(raw: str, label: str) -> list:
    """Parse the model's JSON array tolerantly.

    The model occasionally emits JSON with an unescaped quote or apostrophe
    inside a string value, or a trailing comma, or smart quotes. A single
    strict json.loads() turns any of those into a hard failure for the whole
    run. This tries strict first (the common case), then applies a series of
    safe repairs and retries before giving up.
    """
    # Fast path — most weeks the JSON is clean.
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"    ! {label}: strict JSON parse failed ({e}); attempting repair...")

    repaired = raw

    # 1. Normalise smart quotes / unicode punctuation that breaks JSON.
    replacements = {
        '\u201c': '"', '\u201d': '"',   # curly double quotes
        '\u2018': "'", '\u2019': "'",   # curly single quotes / apostrophes
        '\u2013': '-', '\u2014': '-',   # en / em dash (safe inside strings)
        '\u00a0': ' ',                  # non-breaking space
    }
    for bad, good in replacements.items():
        repaired = repaired.replace(bad, good)

    # 2. Remove trailing commas before } or ]  (e.g.  "x": 1, }  ->  "x": 1 }).
    repaired = re.sub(r',(\s*[}\]])', r'\1', repaired)

    try:
        result = json.loads(repaired)
        print(f"    ! {label}: recovered after light repair.")
        return result
    except json.JSONDecodeError as e:
        print(f"    ! {label}: still invalid after light repair ({e}); trying strict-strings repair...")

    # 3. Last resort: try Python's more permissive literal parser. It accepts
    #    single-quoted strings and is more forgiving of stray quotes. We only
    #    use its result if it yields a list of dicts shaped like topics.
    #    NOTE: literal_eval can raise more than ValueError/SyntaxError on
    #    pathological input (RecursionError, MemoryError, TypeError, etc.).
    #    We must catch broadly here so a failure CANNOT bypass the diagnostic
    #    block below.
    try:
        import ast
        candidate = ast.literal_eval(repaired)
        if isinstance(candidate, list) and all(isinstance(x, dict) for x in candidate):
            print(f"    ! {label}: recovered via permissive literal parse.")
            return candidate
    except Exception as e:  # noqa: BLE001 - intentional broad catch
        print(f"    ! {label}: permissive literal parse failed ({type(e).__name__}: {e}).")

    # Could not recover. Before giving up, dump the raw text so we can see
    # EXACTLY what the model produced and fix the real cause — no guessing.
    # The whole diagnostic is wrapped defensively: it must NEVER be the thing
    # that fails silently. If anything here breaks, we still print the raw
    # text in the crudest possible way.
    try:
        print(f"    ===== UNRECOVERABLE JSON DIAGNOSTIC: {label} =====")

        # Re-run a strict parse purely to capture the precise error position.
        err_pos = None
        try:
            json.loads(raw)
        except json.JSONDecodeError as e:
            err_pos = e.pos
            print(f"    strict error: {e.msg} at line {e.lineno} col {e.colno} (char {e.pos})")

        # Focused window: ~400 chars either side of the failure point so the
        # log stays readable but shows the actual offending region.
        if err_pos is not None:
            lo = max(0, err_pos - 400)
            hi = min(len(raw), err_pos + 400)
            print(f"    --- raw text around char {err_pos} (showing {lo}..{hi}) ---")
            window = raw[lo:hi]
            rel = err_pos - lo
            print("    " + window[:rel].replace("\n", "\n    "))
            print("    >>>>>>>>>> FAILURE POINT >>>>>>>>>>")
            print("    " + window[rel:].replace("\n", "\n    "))
        else:
            head = raw[:1200]
            tail = raw[-1200:] if len(raw) > 2400 else ""
            print("    --- raw text (head, first 1200 chars) ---")
            print("    " + head.replace("\n", "\n    "))
            if tail:
                print("    --- raw text (tail, last 1200 chars) ---")
                print("    " + tail.replace("\n", "\n    "))

        print(f"    --- raw length: {len(raw)} chars ---")
        print(f"    ===== END DIAGNOSTIC: {label} =====")
    except Exception as diag_err:  # noqa: BLE001 - diagnostic must never fail silently
        print(f"    !! diagnostic itself errored ({type(diag_err).__name__}: {diag_err})")
        print(f"    !! crude raw dump for {label} (repr, first 3000 chars):")
        try:
            print("    " + repr(raw)[:3000])
        except Exception:
            print("    !! could not even repr the raw text")

    # Raise so the caller can skip THIS category only.
    raise ValueError(f"Unrecoverable JSON for {label}")


def extract_recent_topics(html_content: str, max_sets_back: int = 4) -> dict:
    """Pull recently-published topic titles + headlines from index.html.

    Used to give the model an explicit "do not repeat" list so each week's
    content stays distinct from the previous 4 weeks. The state IS the data
    in the live file — no separate state.json to drift out of sync.

    Returns {cat_id: [{title, headline, set_index}, ...]} where set_index 0
    is the most recently published set. If parsing fails for any reason,
    returns {} — generation continues without anti-repetition rather than
    crashing the whole run.
    """
    out = {}
    try:
        for m in re.finditer(r'D\.(\w+)\s*=\s*\[', html_content):
            cat = m.group(1)
            start = m.end() - 1
            # String-aware walk to matching ]
            depth = 0
            in_str = False
            quote = ''
            esc = False
            end = -1
            for i in range(start, len(html_content)):
                ch = html_content[i]
                if esc:
                    esc = False
                    continue
                if in_str:
                    if ch == '\\':
                        esc = True
                    elif ch == quote:
                        in_str = False
                    continue
                if ch in ('"', "'"):
                    in_str = True
                    quote = ch
                    continue
                if ch == '[':
                    depth += 1
                elif ch == ']':
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end == -1:
                continue
            block = html_content[start + 1:end]
            # Extract each top-level set within this block
            sets = []
            d = 0
            in_str = False
            quote = ''
            esc = False
            set_start = None
            for i, ch in enumerate(block):
                if esc:
                    esc = False
                    continue
                if in_str:
                    if ch == '\\':
                        esc = True
                    elif ch == quote:
                        in_str = False
                    continue
                if ch in ('"', "'"):
                    in_str = True
                    quote = ch
                    continue
                if ch == '[':
                    d += 1
                    if d == 1:
                        set_start = i
                elif ch == ']':
                    d -= 1
                    if d == 0 and set_start is not None:
                        sets.append(block[set_start:i + 1])
                        set_start = None
            cat_topics = []
            for si, s in enumerate(sets[:max_sets_back]):
                for tm in re.finditer(
                    r'\{title:"((?:[^"\\]|\\.)*)",headline:"((?:[^"\\]|\\.)*)"',
                    s,
                ):
                    title = tm.group(1).replace('\\"', '"').replace('\\\\', '\\')
                    headline = tm.group(2).replace('\\"', '"').replace('\\\\', '\\')
                    cat_topics.append({
                        'title': title,
                        'headline': headline,
                        'set_index': si,
                    })
            out[cat] = cat_topics
    except Exception as e:  # noqa: BLE001 — never fail the run on extraction
        print(f"  ! extract_recent_topics: parsing failed ({e}); "
              f"continuing without anti-repetition list")
        return {}
    return out


def format_recent_for_prompt(cat_id: str, recent_topics: dict) -> str:
    """Format the recent-topics list for inclusion in the user prompt.

    Returns an empty string if no recent topics exist for this category,
    so first-time runs (or post-reset runs) don't get a confusing empty
    'avoid these' block.
    """
    topics = recent_topics.get(cat_id, [])
    if not topics:
        return ""
    lines = ["", "RECENTLY PUBLISHED IN THIS CATEGORY (DO NOT REPEAT):"]
    # Group by week for readability and weight: set 0 = most recent
    for t in topics:
        age = ("last week" if t['set_index'] == 0
               else f"{t['set_index']+1} weeks ago")
        lines.append(f"- [{age}] {t['title']} — {t['headline']}")
    lines.append("")
    lines.append(
        "Generate 4 topics that are GENUINELY DIFFERENT from the above. "
        "Different angle, different research, different argument. "
        "Same broad theme is acceptable (e.g. another AI story) but the "
        "specific insight, headline and evidence base must be fresh."
    )
    lines.append("")
    return "\n".join(lines)


def generate_category_content(
    client: anthropic.Anthropic,
    cat: dict,
    today: str,
    recent_topics: dict = None,
) -> list:
    """Call Claude API with web search to generate content for one category."""

    prompt = USER_PROMPT_TEMPLATE.format(
        today=today,
        category=cat["label"],
        category_focus=CATEGORY_FOCUS[cat["id"]],
    )

    # Append the anti-repetition block if we have history for this category.
    if recent_topics:
        avoid_block = format_recent_for_prompt(cat["id"], recent_topics)
        if avoid_block:
            prompt = prompt + "\n" + avoid_block
    
    print(f"  Generating {cat['label']} content...")
    
    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )
    
    # Extract text content from response
    text_content = ""
    for block in response.content:
        if block.type == "text":
            text_content += block.text
    
    # Parse JSON
    # 1. Strip any markdown fences if present.
    clean = re.sub(r'```json\s*|\s*```', '', text_content).strip()

    # 2. Strip web-search citation markers that leak into the model output
    #    (e.g. <cite index="54-5,54-6">...</cite>). These otherwise end up
    #    embedded inside the JSON string values and pollute the briefing text.
    clean = re.sub(r'</?cite[^>]*>', '', clean)

    # 3. Extract ONLY the first complete top-level JSON array.
    #    The model sometimes emits the array, then prose like
    #    "Here is the final JSON:", then a SECOND array. A naive
    #    "first [ ... last ]" grab swallows the prose and the duplicate,
    #    which guarantees a parse failure ("Extra data"). Instead we walk
    #    the string tracking bracket depth (ignoring brackets inside
    #    strings) and stop the instant the first top-level array closes.
    start = clean.find('[')
    if start == -1:
        raise ValueError(f"No JSON array found in response for {cat['label']}: {clean[:200]}")

    depth = 0
    end = -1
    in_string = False
    escape = False
    for i in range(start, len(clean)):
        ch = clean[i]
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == -1:
        # Never closed — fall back to last ] so the diagnostic can still
        # show us what happened.
        end = clean.rfind(']') + 1
        if end == 0:
            raise ValueError(f"Unterminated JSON array for {cat['label']}: {clean[:200]}")

    raw = clean[start:end]
    topics = parse_topics_json(raw, cat["label"])

    if len(topics) != 4:
        raise ValueError(f"Expected 4 topics for {cat['label']}, got {len(topics)}")
    
    print(f"    ✓ {cat['label']}: {len(topics)} topics generated")
    for t in topics:
        print(f"      - {t['title']}")
    
    return topics


def _looks_like_book(text: str) -> bool:
    """Heuristic: does this deeper-item text describe a book?

    We keep this deliberately conservative — false positives (treating a
    non-book as a book) only cost a harmless extra search link; we avoid
    matching reflective questions (which end in '?') or obvious article/
    podcast/episode references.
    """
    if not text:
        return False
    t = text.strip()
    low = t.lower()
    # Never treat the reflective question / prompt as a book.
    if t.endswith('?'):
        return False
    # Strong negative signals — these are articles, papers, podcasts.
    negative = ('hbr.org', 'http://', 'https://', 'ideacast', 'podcast',
                'episode', 'working paper', 'journal of', 'review (',
                'nber', 'arxiv', '.com', '.org')
    if any(n in low for n in negative):
        return False
    # Positive signals for a book reference.
    positive = (' - ', ' by ', '(press)', 'publishing', 'wiley', 'penguin',
                'harpercollins', 'random house', 'press)', 'hbr press',
                'harvard business review press')
    return any(p in low for p in positive)


def _book_search_url(text: str) -> str:
    """Build a safe bookshop SEARCH url from a book-like deeper item.

    Uses a search query (not a guessed product page) so it can never
    404 in an embarrassing way — it always lands on results for the
    title/author. Bookshop.org is used as a reputable, non-Amazon
    default appropriate for a professional briefing.
    """
    import urllib.parse
    # Strip a trailing parenthetical like "(Wiley, 2026)" and tidy dashes
    # so the search query is just title + author.
    q = re.sub(r'\([^)]*\)\s*$', '', text).strip()
    q = q.replace(' - ', ' ').strip(' .')
    return 'https://bookshop.org/beta-search?keywords=' + urllib.parse.quote(q)


def topics_to_js(topics: list) -> str:
    """Convert topic list to JavaScript object array string."""
    lines = []
    for t in topics:
        # Escape quotes in strings
        def esc(s):
            if s is None:
                return "null"
            return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ').strip() + '"'
        
        ref_url = t.get('ref', {}).get('url')
        ref_text = t.get('ref', {}).get('text', '')

        deeper_items = []
        for d in t.get('deeper', []):
            d_text = d.get('text', '') if isinstance(d, dict) else str(d)
            d_url = d.get('url') if isinstance(d, dict) else None

            # Safety net (Option 1): if a deeper item looks like a BOOK and
            # has no URL, attach a deterministic bookshop SEARCH url. A search
            # URL can't 404 embarrassingly the way a guessed publisher link
            # can — worst case it shows results for the right title. We only
            # do this for book-like items, never for the reflective question
            # (item 1), and never overwrite a real URL the model supplied.
            if not d_url and _looks_like_book(d_text):
                d_url = _book_search_url(d_text)

            deeper_items.append(
                '{text:' + esc(d_text) + ',url:' + (esc(d_url) if d_url else 'null') + '}'
            )
        
        topic_js = (
            '{title:' + esc(t.get('title', '')) + ','
            'headline:' + esc(t.get('headline', '')) + ','
            'why:' + esc(t.get('why', '')) + ','
            'ref:{text:' + esc(ref_text) + ',url:' + (esc(ref_url) if ref_url else 'null') + '},'
            'insight:' + esc(t.get('insight', '')) + ','
            'attribution:' + esc(t.get('attribution', '')) + ','
            'deeper:[' + ','.join(deeper_items) + ']}'
        )
        lines.append('  ' + topic_js)
    
    return '[\n' + ',\n'.join(lines) + '\n]'


def _find_matching_bracket(s: str, open_pos: int) -> int:
    """Return index of the ] that closes the [ at open_pos.

    CRITICAL: ignores brackets that appear inside JS string literals.
    The previous implementation counted every [ and ] including those
    inside topic text (citations like [1], names, etc.), which made it
    splice new content at the wrong boundary and silently corrupt the
    file while still printing success. This walks the string tracking
    quote state so brackets inside strings are never counted.
    """
    depth = 0
    in_string = False
    quote = ''
    escape = False
    for i in range(open_pos, len(s)):
        ch = s[i]
        if escape:
            escape = False
            continue
        if in_string:
            if ch == '\\':
                escape = True
            elif ch == quote:
                in_string = False
            continue
        if ch in ('"', "'"):
            in_string = True
            quote = ch
            continue
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                return i
    return -1


def update_html(html: str, all_content: dict) -> str:
    """Prepend new content set to each category — keeps last 4 weeks of content."""
    MAX_SETS = 4  # Keep up to 4 weeks of content per category
    
    for cat_id, topics in all_content.items():
        js_content = topics_to_js(topics)
        
        # Find D.catId=[ and get the entire existing block
        marker = f'D.{cat_id}=['
        start = html.index(marker)
        
        # Find the matching closing bracket of the outer array.
        # String-aware: brackets inside topic text are ignored.
        outer_open = start + len(marker) - 1
        end_idx = _find_matching_bracket(html, outer_open)
        if end_idx == -1:
            raise ValueError(
                f"Could not find matching ] for D.{cat_id} — refusing to "
                f"splice (would corrupt the file). Aborting so existing "
                f"content is preserved."
            )
        end = end_idx + 1
        
        # Extract existing sets from current block
        existing_block = html[start+len(marker):end-1].strip()
        
        # Count existing sets by finding top-level arrays.
        # Also string-aware for the same reason as above.
        existing_sets = []
        d = 0
        set_start = None
        in_string = False
        quote = ''
        escape = False
        for i, ch in enumerate(existing_block):
            if escape:
                escape = False
                continue
            if in_string:
                if ch == '\\':
                    escape = True
                elif ch == quote:
                    in_string = False
                continue
            if ch in ('"', "'"):
                in_string = True
                quote = ch
                continue
            if ch == '[':
                d += 1
                if d == 1:
                    set_start = i
            elif ch == ']':
                d -= 1
                if d == 0 and set_start is not None:
                    existing_sets.append(existing_block[set_start:i+1])
                    set_start = None
        
        # Sanity check: the new content must actually appear in the new
        # block, otherwise we have spliced wrong. Fail loudly rather than
        # commit a file that looks updated but isn't.
        all_sets = [js_content] + existing_sets[:MAX_SETS-1]
        new_block = f'D.{cat_id}=[\n' + ',\n'.join(all_sets) + '\n]'

        # Verify a distinctive piece of the new content is present.
        first_title = topics[0].get('title', '') if topics else ''
        if first_title and first_title.replace('"', '\\"') not in new_block:
            raise ValueError(
                f"Post-splice check failed for D.{cat_id}: new topic "
                f"'{first_title}' not found in rebuilt block. Aborting "
                f"to avoid committing corrupted content."
            )

        html = html[:start] + new_block + html[end:]
        print(f"  ✓ Updated D.{cat_id} in HTML ({len(all_sets)} sets, newest first)")
    
    return html


def get_current_file(token: str, branch: str = "main") -> tuple[str, str]:
    """Get current index.html content and SHA from a given branch.

    Defaults to main so the existing Monday workflow keeps working unchanged.
    The Friday workflow passes branch='staging' to stage content for review.
    """
    import requests

    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}?ref={branch}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "PI-Weekly-Briefing-Bot",
    }
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()

    file_content = base64.b64decode(data['content']).decode('utf-8')
    sha = data['sha']
    return file_content, sha


def commit_file(token: str, content: str, sha: str, message: str,
                branch: str = "main") -> None:
    """Commit updated index.html to GitHub on the given branch."""
    import requests

    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "PI-Weekly-Briefing-Bot",
    }
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode('utf-8')).decode('ascii'),
        "sha": sha,
        "branch": branch,
    }
    resp = requests.put(url, headers=headers, json=payload)
    resp.raise_for_status()
    result = resp.json()
    print(f"  ✓ Committed to {branch}: {result['commit']['html_url']}")


def _normalise_for_compare(text: str) -> str:
    """Lowercase, strip punctuation/articles for loose title comparison."""
    if not text:
        return ""
    s = text.lower()
    # Strip everything that isn't a letter, digit or space
    s = re.sub(r'[^a-z0-9\s]', ' ', s)
    # Drop noise words
    stopwords = {'the', 'a', 'an', 'of', 'and', 'or', 'to', 'for',
                 'in', 'on', 'is', 'are', 'as', 'how', 'why'}
    tokens = [t for t in s.split() if t and t not in stopwords]
    return ' '.join(tokens)


def check_for_overlap(new_content: dict, recent_topics: dict) -> list:
    """Compare each new topic against recent ones in the same category.

    Returns a list of human-readable overlap warnings. A "warning" fires when
    a new title shares >=60% of significant tokens with any recent title.
    This is intentionally lenient — false positives are fine (we just log
    them), false negatives are what we're trying to catch.
    """
    warnings = []
    for cat_id, new_topics in new_content.items():
        recents = recent_topics.get(cat_id, [])
        if not recents:
            continue
        for nt in new_topics:
            new_norm = _normalise_for_compare(nt.get('title', ''))
            if not new_norm:
                continue
            new_tokens = set(new_norm.split())
            if len(new_tokens) < 2:
                continue
            for rt in recents:
                old_norm = _normalise_for_compare(rt.get('title', ''))
                old_tokens = set(old_norm.split())
                if not old_tokens:
                    continue
                overlap = new_tokens & old_tokens
                # Ratio against the SMALLER set so a 3-word title vs 5-word
                # title can still flag if all 3 overlap.
                ratio = len(overlap) / min(len(new_tokens), len(old_tokens))
                if ratio >= 0.6:
                    warnings.append(
                        f"{cat_id}: new '{nt['title']}' overlaps with "
                        f"recent '{rt['title']}' (set {rt['set_index']}, "
                        f"{int(ratio*100)}% token overlap)"
                    )
                    break  # one warning per new topic is enough
    return warnings


def main():
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    github_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    target_branch = os.environ.get("TARGET_BRANCH", "main").strip() or "main"

    if not anthropic_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")
    if not github_token:
        raise ValueError("GH_TOKEN environment variable not set")

    today = datetime.date.today().strftime("%A, %d %B %Y")
    week = datetime.date.today().isocalendar()[1]

    print(f"Performance Intelligence Weekly Briefing Generator")
    print(f"Date: {today} | Week: {week} | Target branch: {target_branch}")
    print("=" * 60)

    client = anthropic.Anthropic(api_key=anthropic_key)

    # 1. Fetch current HTML FIRST so we know what's been published recently.
    # The anti-repetition list is built from the live file — single source of
    # truth, no separate state file to drift out of sync.
    print(f"\n1. Fetching current index.html from {target_branch}...")
    html_content, file_sha = get_current_file(github_token, branch=target_branch)
    print(f"  ✓ Got file ({len(html_content)//1024}KB, SHA: {file_sha[:8]}...)")

    print("\n2. Extracting recently-published topics for anti-repetition...")
    recent_topics = extract_recent_topics(html_content, max_sets_back=4)
    total_recent = sum(len(v) for v in recent_topics.values())
    if total_recent:
        print(f"  ✓ Found {total_recent} recent topics across "
              f"{len(recent_topics)} categories (last 4 weeks)")
    else:
        print("  ! No recent topics found — first run or empty file. "
              "Generation will proceed without anti-repetition list.")

    # 2. Generate content for all 6 categories.
    # If one category fails (bad JSON from the model, etc.) we skip THAT
    # category and keep the rest, rather than losing the entire week.
    all_content = {}
    failures = []
    print("\n3. Generating content via Claude API with web search...")
    for cat in CATEGORIES:
        try:
            topics = generate_category_content(client, cat, today, recent_topics)
            all_content[cat["id"]] = topics
        except Exception as e:
            print(f"  ✗ {cat['label']} FAILED: {e}")
            print(f"    Skipping {cat['label']} this week, continuing with the others.")
            failures.append(cat["label"])

    # Safety floor: if too few categories succeeded, abort rather than
    # publish a gutted briefing that would also push good older content
    # down the 4-week history.
    MIN_CATEGORIES = 4
    if len(all_content) < MIN_CATEGORIES:
        raise RuntimeError(
            f"Only {len(all_content)} of {len(CATEGORIES)} categories succeeded "
            f"(failed: {', '.join(failures) or 'none'}). "
            f"Below the safety floor of {MIN_CATEGORIES}; aborting without committing "
            f"so existing content is preserved. Re-run the workflow to try again."
        )

    if failures:
        print(f"\n  Note: proceeding with {len(all_content)} categories; "
              f"{len(failures)} skipped this week ({', '.join(failures)}).")

    # 3. Post-generation overlap check — warn (not fail) if any new title
    # closely matches a recent one. This is a tripwire, not a hard gate;
    # Claude is usually obedient with the "do not repeat" instruction, but
    # if it slips we want to know so the prompt can be tightened.
    print("\n4. Checking new content against recent for overlap...")
    overlaps = check_for_overlap(all_content, recent_topics)
    if overlaps:
        print(f"  ! {len(overlaps)} possible overlap(s) detected:")
        for o in overlaps:
            print(f"    - {o}")
        print("  (continuing — review on staging before Monday merge)")
    else:
        print("  ✓ No overlaps with recent content")

    # 4. Update the HTML
    print("\n5. Updating content in index.html...")
    updated_html = update_html(html_content, all_content)

    # 5. Commit back to GitHub
    print("\n6. Committing to GitHub...")
    commit_message = f"Weekly briefing content update — Week {week}, {today}"
    commit_file(github_token, updated_html, file_sha, commit_message,
                branch=target_branch)

    print(f"\n✅ Done! Week {week} briefing published.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 — outermost catch by design
        import traceback
        tb = traceback.format_exc()
        print(f"\n❌ FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        print(tb, file=sys.stderr)

        # Best-effort failure notification. If mailer itself is broken we
        # don't compound the problem — just log and exit with the original
        # failure code so the workflow shows red.
        try:
            from mailer import send_email
            run_url = ""
            server = os.environ.get("GITHUB_SERVER_URL", "")
            repo = os.environ.get("GITHUB_REPOSITORY", "")
            run_id = os.environ.get("GITHUB_RUN_ID", "")
            if server and repo and run_id:
                run_url = f"{server}/{repo}/actions/runs/{run_id}"
            workflow = os.environ.get("GITHUB_WORKFLOW", "(unknown workflow)")
            body = f"""<html><body style="font-family:system-ui,sans-serif;font-size:14px;color:#222;">
<h2 style="color:#c00;">PI Briefing: content generation failed</h2>
<p><strong>Workflow:</strong> {workflow}</p>
<p><strong>Error:</strong> {type(e).__name__}: {e}</p>
{f'<p><strong>Run:</strong> <a href="{run_url}">{run_url}</a></p>' if run_url else ''}
<h3>Traceback</h3>
<pre style="background:#f5f5f5;padding:12px;border:1px solid #ddd;white-space:pre-wrap;font-size:12px;">{tb}</pre>
<p style="color:#666;font-size:12px;">Sent automatically by mailer.py from the failed run.
The repo state has NOT been modified — re-run the workflow to retry.</p>
</body></html>"""
            send_email(
                to="jc@jezcartwright.com",
                subject=f"[PI Briefing] {workflow} failed: {type(e).__name__}",
                body_html=body,
            )
            print("(failure notification email sent to jc@jezcartwright.com)",
                  file=sys.stderr)
        except Exception as mail_err:  # noqa: BLE001
            print(f"(also could not send failure email: {mail_err})",
                  file=sys.stderr)

        sys.exit(1)
