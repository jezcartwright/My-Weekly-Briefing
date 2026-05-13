#!/usr/bin/env python3
"""
Performance Intelligence Weekly Briefing — Content Generator
Runs every Monday via GitHub Actions.
Calls Claude API with web search to generate fresh weekly content,
then updates index.html in the repo.
"""

import os
import re
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
  - Item 1: A reflective question or personal challenge
  - Item 2: A specific book, article or resource with real URL if available  
  - Item 3: A specific book, article or resource with real URL if available

Quality standards:
- WHY IT MATTERS must cite specific studies, data points or named research
- Quotes must be real, accurately attributed
- Topics should feel CURRENT — referencing this week's news/research where possible
- Write for intelligent executives who read broadly
- British spelling throughout (organisation, behaviour, recognise etc.)

Return ONLY valid JSON — no markdown, no explanation, no backticks."""

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


def generate_category_content(client: anthropic.Anthropic, cat: dict, today: str) -> list:
    """Call Claude API with web search to generate content for one category."""
    
    prompt = USER_PROMPT_TEMPLATE.format(
        today=today,
        category=cat["label"],
        category_focus=CATEGORY_FOCUS[cat["id"]],
    )
    
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
    # Strip any markdown fences if present
    clean = re.sub(r'```json\s*|\s*```', '', text_content).strip()
    
    # Find JSON array
    start = clean.find('[')
    end = clean.rfind(']') + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON array found in response for {cat['label']}: {clean[:200]}")
    
    topics = json.loads(clean[start:end])
    
    if len(topics) != 4:
        raise ValueError(f"Expected 4 topics for {cat['label']}, got {len(topics)}")
    
    print(f"    ✓ {cat['label']}: {len(topics)} topics generated")
    for t in topics:
        print(f"      - {t['title']}")
    
    return topics


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


def update_html(html: str, all_content: dict) -> str:
    """Prepend new content set to each category — keeps last 4 weeks of content."""
    MAX_SETS = 4  # Keep up to 4 weeks of content per category
    
    for cat_id, topics in all_content.items():
        js_content = topics_to_js(topics)
        
        # Find D.catId=[ and get the entire existing block
        marker = f'D.{cat_id}=['
        start = html.index(marker)
        
        # Find the matching closing bracket of the outer array
        pos = start + len(marker) - 1
        depth = 0
        for i in range(pos, len(html)):
            if html[i] == '[':
                depth += 1
            elif html[i] == ']':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        
        # Extract existing sets from current block
        existing_block = html[start+len(marker):end-1].strip()
        
        # Count existing sets by finding top-level arrays
        # Each set is a [...] at depth 1
        existing_sets = []
        d = 0
        set_start = None
        for i, ch in enumerate(existing_block):
            if ch == '[':
                d += 1
                if d == 1:
                    set_start = i
            elif ch == ']':
                d -= 1
                if d == 0 and set_start is not None:
                    existing_sets.append(existing_block[set_start:i+1])
                    set_start = None
        
        # Prepend new set, keep up to MAX_SETS
        all_sets = [js_content] + existing_sets[:MAX_SETS-1]
        new_block = f'D.{cat_id}=[\n' + ',\n'.join(all_sets) + '\n]'
        html = html[:start] + new_block + html[end:]
        print(f"  ✓ Updated D.{cat_id} in HTML ({len(all_sets)} sets, newest first)")
    
    return html


def get_current_file(token: str) -> tuple[str, str]:
    """Get current index.html content and SHA from GitHub API."""
    import requests
    
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
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


def commit_file(token: str, content: str, sha: str, message: str) -> None:
    """Commit updated index.html to GitHub."""
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
        "branch": "main",
    }
    resp = requests.put(url, headers=headers, json=payload)
    resp.raise_for_status()
    result = resp.json()
    print(f"  ✓ Committed: {result['commit']['html_url']}")


def main():
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    github_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    
    if not anthropic_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")
    if not github_token:
        raise ValueError("GH_TOKEN environment variable not set")
    
    today = datetime.date.today().strftime("%A, %d %B %Y")
    week = datetime.date.today().isocalendar()[1]
    
    print(f"Performance Intelligence Weekly Briefing Generator")
    print(f"Date: {today} | Week: {week}")
    print("=" * 60)
    
    client = anthropic.Anthropic(api_key=anthropic_key)
    
    # Generate content for all 6 categories
    all_content = {}
    print("\n1. Generating content via Claude API with web search...")
    for cat in CATEGORIES:
        topics = generate_category_content(client, cat, today)
        all_content[cat["id"]] = topics
    
    # Get current HTML from GitHub
    print("\n2. Fetching current index.html from GitHub...")
    html_content, file_sha = get_current_file(github_token)
    print(f"  ✓ Got file ({len(html_content)//1024}KB, SHA: {file_sha[:8]}...)")
    
    # Update the HTML
    print("\n3. Updating content in index.html...")
    updated_html = update_html(html_content, all_content)
    
    # Commit back to GitHub
    print("\n4. Committing to GitHub...")
    commit_message = f"Weekly briefing content update — Week {week}, {today}"
    commit_file(github_token, updated_html, file_sha, commit_message)
    
    print(f"\n✅ Done! Week {week} briefing published.")


if __name__ == "__main__":
    main()
