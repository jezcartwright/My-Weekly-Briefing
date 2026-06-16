#!/usr/bin/env python3
# Harden generate_content.py so a repeated/stale week can never auto-publish:
#  1) generate_category_content gains an `extra_avoid` list, injected into the
#     prompt on regeneration to forbid the exact topics that just clashed.
#  2) New find_category_overlaps()/_topic_clashes() compare new topics to recent
#     weeks on titles AND title+headline (catches reworded same-subject pieces).
#     recent list includes last week (index 0), so a silently-kept stale set is
#     also caught.
#  3) main() loop: per category, retry up to MAX_ATTEMPTS, regenerating when a
#     clash is found; if a category still can't go fresh, it's a HARD failure
#     and the whole run aborts WITHOUT committing (old code silently kept last
#     week's set — the bug that shipped a repeat).
import os, sys, py_compile

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/weekly-briefing-local/test-repo/generate_content.py')

with open(PATH, 'r', encoding='utf-8') as f:
    s = f.read()
orig = len(s)

edits = []

# ---- Edit A1: add extra_avoid param to generate_category_content -----------
a1_old = """    recent_topics: dict = None,
) -> list:"""
a1_new = """    recent_topics: dict = None,
    extra_avoid: list = None,
) -> list:"""
edits.append((a1_old, a1_new))

# ---- Edit A2: inject extra_avoid block into the prompt ----------------------
a2_old = '''    print(f"  Generating {cat['label']} content...")'''
a2_new = '''    if extra_avoid:
        _av = ["", "YOU JUST PROPOSED THE FOLLOWING AND THEY REPEAT RECENT "
               "WEEKS - do NOT propose them or any close variant again:"]
        for _t in extra_avoid:
            _av.append("- " + _t.get("title", "") + " - " + _t.get("headline", ""))
        _av.append("")
        prompt = prompt + "\\n" + "\\n".join(_av)

    print(f"  Generating {cat['label']} content...")'''
edits.append((a2_old, a2_new))

# ---- Edit B: add overlap helpers just before main() ------------------------
b_old = '''def main():
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")'''
b_new = '''def _topic_clashes(new_topic, recent_list):
    """Return a recent topic that a new topic repeats, else None.

    Catches near-identical titles AND same-subject pieces wearing a reworded
    headline. recent_list includes last week at set_index 0, so a category that
    silently keeps last week's set is caught here too.
    """
    nt_title = set(_normalise_for_compare(new_topic.get("title", "")).split())
    nt_full = set(_normalise_for_compare(
        new_topic.get("title", "") + " " + new_topic.get("headline", "")).split())
    if len(nt_title) < 2:
        return None
    for rt in recent_list:
        rt_title = set(_normalise_for_compare(rt.get("title", "")).split())
        rt_full = set(_normalise_for_compare(
            rt.get("title", "") + " " + rt.get("headline", "")).split())
        if rt_title:
            ratio = len(nt_title & rt_title) / min(len(nt_title), len(rt_title))
            if ratio >= 0.6:
                return rt
        if len(nt_full) >= 4 and len(rt_full) >= 4:
            ratio = len(nt_full & rt_full) / min(len(nt_full), len(rt_full))
            if ratio >= 0.5:
                return rt
    return None


def find_category_overlaps(new_topics, recent_list):
    """Return the subset of new_topics that repeat recent content."""
    clashes = []
    for nt in new_topics:
        if _topic_clashes(nt, recent_list):
            clashes.append({"title": nt.get("title", ""),
                            "headline": nt.get("headline", "")})
    return clashes


def main():
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")'''
edits.append((b_old, b_new))

for i, (old, new) in enumerate(edits, 1):
    n = s.count(old)
    if n != 1:
        raise SystemExit('Edit %s anchor found %d times (expected 1). Aborting.' % (i, n))
    s = s.replace(old, new)

# ---- Edit C: replace the generation/overlap block in main() (index splice) --
start_anchor = "    all_content = {}\n"
end_anchor = "    # 4. Update the HTML\n"
if s.count(start_anchor) != 1 or s.count(end_anchor) != 1:
    raise SystemExit('Edit C anchors not unique (%d / %d). Aborting.'
                     % (s.count(start_anchor), s.count(end_anchor)))
i0 = s.index(start_anchor)
j0 = s.index(end_anchor, i0)

new_block = '''    all_content = {}
    hard_failures = []
    MAX_ATTEMPTS = 3
    print("\\n3. Generating content (blocking anti-repetition gate)...")
    for cat in CATEGORIES:
        cat_id = cat["id"]
        recents = recent_topics.get(cat_id, [])
        extra_avoid = []
        produced = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                topics = generate_category_content(
                    client, cat, today, recent_topics, extra_avoid)
            except Exception as e:
                print("  x %s attempt %d/%d failed: %s"
                      % (cat["label"], attempt, MAX_ATTEMPTS, e))
                continue
            clashes = find_category_overlaps(topics, recents)
            if not clashes:
                produced = topics
                print("  OK %s fresh (attempt %d)" % (cat["label"], attempt))
                break
            print("  REGEN %s attempt %d: %d topic(s) repeat recent weeks:"
                  % (cat["label"], attempt, len(clashes)))
            for c in clashes:
                print("        - %s" % c["title"])
            extra_avoid.extend(clashes)
        if produced is not None:
            all_content[cat_id] = produced
        else:
            hard_failures.append(cat["label"])

    # Hard gate: every category must produce fresh, non-repeating content. If any
    # can't, abort WITHOUT committing so nothing stale or duplicated is published;
    # the outer handler emails the failure for a human re-run. (The old code
    # silently kept last week's set for a failed category - the exact path by
    # which a repeated week reached production.)
    if hard_failures or len(all_content) < len(CATEGORIES):
        missing = hard_failures or [c["label"] for c in CATEGORIES
                                    if c["id"] not in all_content]
        raise RuntimeError(
            "Could not produce fresh, non-repeating content for: "
            + ", ".join(missing)
            + ". Aborting without committing so no stale or duplicated content is "
            "published. Re-run the workflow to retry."
        )

    print("\\n4. All six categories produced fresh, non-repeating content.")

'''

s = s[:i0] + new_block + s[j0:]

if len(s) < 20000:
    raise SystemExit('Result too small. Aborting.')

tmp = PATH + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(s)
# Validate syntax before swapping in.
try:
    py_compile.compile(tmp, doraise=True)
except py_compile.PyCompileError as e:
    os.remove(tmp)
    raise SystemExit('Patched file has a syntax error, not written:\n%s' % e)
os.replace(tmp, PATH)
print('OK: generator hardened. %d -> %d bytes (%+d). Syntax valid.' % (orig, len(s), len(s) - orig))
