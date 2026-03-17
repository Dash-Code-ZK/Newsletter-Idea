#!/usr/bin/env python3
"""
Morning AI & Tech Newsletter Generator
Fetches the latest AI/tech news and uses Claude to craft a curated morning brief.
"""

import os
import json
import re
import calendar
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic
import feedparser
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# RSS feed sources — mix of broad tech and AI-focused outlets
# ---------------------------------------------------------------------------
RSS_FEEDS = [
    ("TechCrunch",              "https://techcrunch.com/feed/"),
    ("The Verge",               "https://www.theverge.com/rss/index.xml"),
    ("Ars Technica",            "http://feeds.arstechnica.com/arstechnica/technology-lab"),
    ("VentureBeat AI",          "https://venturebeat.com/ai/feed/"),
    ("MIT Technology Review",   "https://www.technologyreview.com/feed/"),
    ("Wired",                   "https://www.wired.com/feed/rss"),
    ("AI News",                 "https://artificialintelligence-news.com/feed/"),
    ("ZDNet",                   "https://www.zdnet.com/news/rss.xml"),
    ("9to5Google",              "https://9to5google.com/feed/"),
    ("The Register Tech",       "https://www.theregister.com/emergent_tech/headlines.atom"),
]


# ---------------------------------------------------------------------------
# Step 1 — Fetch recent articles from RSS feeds
# ---------------------------------------------------------------------------
def fetch_recent_articles(hours: int = 24) -> list[dict]:
    """Return articles published within the last `hours` hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    articles = []

    for source, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url, request_headers={"User-Agent": "MorningBriefBot/1.0"})
            for entry in feed.entries:
                pub_date = None
                for attr in ("published_parsed", "updated_parsed"):
                    val = getattr(entry, attr, None)
                    if val:
                        pub_date = datetime.fromtimestamp(calendar.timegm(val), tz=timezone.utc)
                        break

                if pub_date and pub_date >= cutoff:
                    raw_summary = getattr(entry, "summary", "")
                    clean_summary = re.sub(r"<[^>]+>", "", raw_summary)[:600].strip()

                    articles.append({
                        "source":    source,
                        "title":     entry.get("title", "").strip(),
                        "url":       entry.get("link", "").strip(),
                        "summary":   clean_summary,
                        "published": pub_date.strftime("%Y-%m-%d %H:%M UTC"),
                    })
        except Exception as exc:
            print(f"  [warn] Could not fetch {source}: {exc}")

    # Deduplicate by URL
    seen = set()
    unique = []
    for a in articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)

    return unique


# ---------------------------------------------------------------------------
# Step 2 — Ask Claude to curate & write the newsletter
# ---------------------------------------------------------------------------
def generate_newsletter(articles: list[dict], date_str: str) -> dict:
    """Send articles to Claude Opus and receive a structured newsletter dict."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    articles_text = json.dumps(articles, ensure_ascii=False, indent=2)

    system_prompt = (
        "You are a sharp, insightful tech journalist who writes a concise morning brief "
        "for busy professionals. Your writing is clear, direct, and free of hype. "
        "You always respond with valid JSON only — no markdown fences, no preamble."
    )

    user_prompt = f"""Today is {date_str}. Below are raw articles scraped from AI and tech news RSS feeds in the last 24 hours.

ARTICLES:
{articles_text}

Create a morning brief newsletter. Return a single JSON object with EXACTLY this structure:

{{
  "date": "{date_str}",
  "greeting": "A warm, personalized good-morning greeting (2 sentences max).",
  "top_stories": [
    {{
      "rank": 1,
      "title": "Exact article title",
      "url": "Exact URL from the articles list — never fabricate",
      "source": "Publication name",
      "summary": "2–3 sentence factual summary of what happened.",
      "why_it_matters": "2–3 sentences on the significance for tech/AI professionals."
    }},
    {{ "rank": 2, ... }},
    {{ "rank": 3, ... }},
    {{ "rank": 4, ... }},
    {{ "rank": 5, ... }}
  ],
  "quote": {{
    "text": "A thought-provoking or inspiring quote relevant to today's themes.",
    "author": "Full name (and context if helpful, e.g. 'Alan Turing, Computing Pioneer')"
  }},
  "thought_provoking_article": {{
    "title": "Title of an article from the list that deserves deeper reflection",
    "url": "Exact URL from the articles list",
    "source": "Publication name",
    "why_read": "2–3 sentences explaining why this piece rewards careful reading."
  }},
  "claude_pick": {{
    "title": "A trend, observation, or additional article you find fascinating today",
    "url": "Exact URL if referencing an article from the list, else empty string",
    "description": "2–3 sentences on why this is interesting and what it signals."
  }}
}}

Rules:
- top_stories must contain EXACTLY 5 items, focused on AI and technology.
- All URLs must be copied verbatim from the articles list — do NOT invent URLs.
- If the list is thin, use the best available stories even if broader tech.
- The quote should feel relevant to today's news themes, not generic.
- claude_pick can be a pattern you noticed across articles, a meta-observation, or a story from the list not already covered.
- Return only the JSON object — no other text."""

    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        response = stream.get_final_message()

    text = next((b.text for b in response.content if b.type == "text"), "{}")

    # Strip any accidental markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())

    return json.loads(text)


# ---------------------------------------------------------------------------
# Step 3 — Render beautiful HTML with clickable links
# ---------------------------------------------------------------------------
def render_html(data: dict) -> str:
    date        = data.get("date", datetime.now().strftime("%B %d, %Y"))
    greeting    = data.get("greeting", "Good morning!")
    stories     = data.get("top_stories", [])
    quote       = data.get("quote", {})
    thought     = data.get("thought_provoking_article", {})
    pick        = data.get("claude_pick", {})

    # --- Top stories ---
    stories_html = ""
    for story in stories:
        url = story.get("url", "#") or "#"
        stories_html += f"""
        <div class="story">
          <span class="rank">#{story.get('rank', '?')}</span>
          <div class="story-body">
            <p class="source-tag">{story.get('source', '')}</p>
            <h2><a href="{url}" target="_blank" rel="noopener noreferrer">{story.get('title', '')}</a></h2>
            <p class="summary">{story.get('summary', '')}</p>
            <div class="matters">
              <strong>Why it matters:</strong> {story.get('why_it_matters', '')}
            </div>
          </div>
        </div>"""

    # --- Quote ---
    quote_html = ""
    if quote.get("text"):
        quote_html = f"""
    <div class="quote-block">
      <blockquote>"{quote['text']}"</blockquote>
      <cite>— {quote.get('author', '')}</cite>
    </div>"""

    # --- Thought-provoking article ---
    thought_html = ""
    if thought.get("title"):
        t_url = thought.get("url", "#") or "#"
        thought_html = f"""
    <div class="card card-thought">
      <h3 class="card-label">🧠 Thought-Provoking Read</h3>
      <p class="source-tag">{thought.get('source', '')}</p>
      <h2><a href="{t_url}" target="_blank" rel="noopener noreferrer">{thought['title']}</a></h2>
      <p>{thought.get('why_read', '')}</p>
    </div>"""

    # --- Claude's pick ---
    pick_html = ""
    if pick.get("title"):
        p_url = pick.get("url", "") or ""
        if p_url:
            pick_title_html = f'<h2><a href="{p_url}" target="_blank" rel="noopener noreferrer">{pick["title"]}</a></h2>'
        else:
            pick_title_html = f'<h2>{pick["title"]}</h2>'
        pick_html = f"""
    <div class="card card-pick">
      <h3 class="card-label">✨ Claude's Pick</h3>
      {pick_title_html}
      <p>{pick.get('description', '')}</p>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Morning Brief — {date}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Georgia, serif;
      background: #f0ede8;
      color: #1c1c1c;
      line-height: 1.65;
      padding: 24px 16px 48px;
    }}
    .wrapper {{ max-width: 660px; margin: 0 auto; }}

    /* Header */
    .header {{
      background: linear-gradient(145deg, #0d1b2a, #1b4965);
      color: #fff;
      border-radius: 16px;
      padding: 40px 32px 36px;
      text-align: center;
      margin-bottom: 20px;
    }}
    .header .eyebrow {{
      font-size: 10px;
      letter-spacing: 4px;
      text-transform: uppercase;
      opacity: 0.65;
      margin-bottom: 10px;
    }}
    .header h1 {{
      font-size: 30px;
      font-weight: 800;
      letter-spacing: -0.5px;
      margin-bottom: 6px;
    }}
    .header .sub {{
      font-size: 13px;
      opacity: 0.7;
    }}

    /* Greeting */
    .greeting {{
      background: #fff;
      border-left: 4px solid #e63946;
      border-radius: 10px;
      padding: 16px 20px;
      font-size: 15px;
      color: #444;
      margin-bottom: 24px;
    }}

    /* Section divider */
    .divider {{
      display: flex;
      align-items: center;
      gap: 12px;
      margin: 28px 0 16px;
    }}
    .divider span {{
      font-size: 10px;
      letter-spacing: 3px;
      text-transform: uppercase;
      color: #999;
      white-space: nowrap;
      font-weight: 600;
    }}
    .divider hr {{ flex: 1; border: none; border-top: 1px solid #ddd; }}

    /* Story cards */
    .story {{
      background: #fff;
      border-radius: 12px;
      padding: 20px 22px;
      margin-bottom: 14px;
      display: flex;
      gap: 16px;
      transition: box-shadow .15s ease;
    }}
    .story:hover {{ box-shadow: 0 4px 24px rgba(0,0,0,.09); }}
    .rank {{
      font-size: 26px;
      font-weight: 900;
      color: #e0dbd4;
      line-height: 1;
      min-width: 34px;
      padding-top: 4px;
    }}
    .story-body {{ flex: 1; min-width: 0; }}
    .source-tag {{
      font-size: 10px;
      letter-spacing: 2px;
      text-transform: uppercase;
      color: #e63946;
      font-weight: 700;
      margin-bottom: 5px;
    }}
    .story-body h2 {{ font-size: 16px; font-weight: 700; line-height: 1.35; margin-bottom: 8px; }}
    .story-body h2 a {{ color: #1c1c1c; text-decoration: none; }}
    .story-body h2 a:hover {{ color: #1b4965; text-decoration: underline; }}
    .summary {{ font-size: 13.5px; color: #555; margin-bottom: 10px; }}
    .matters {{
      font-size: 12.5px;
      color: #555;
      background: #f7f4f0;
      border-left: 3px solid #1b4965;
      padding: 9px 13px;
      border-radius: 6px;
    }}
    .matters strong {{ color: #1b4965; }}

    /* Quote */
    .quote-block {{
      background: linear-gradient(135deg, #6a0572, #a84293);
      color: #fff;
      border-radius: 14px;
      padding: 30px 32px;
      text-align: center;
      margin: 24px 0;
    }}
    blockquote {{
      font-size: 17px;
      font-style: italic;
      line-height: 1.6;
      margin-bottom: 14px;
    }}
    cite {{ font-size: 12.5px; opacity: .8; font-style: normal; }}

    /* Generic card */
    .card {{
      background: #fff;
      border-radius: 12px;
      padding: 20px 22px;
      margin-bottom: 14px;
    }}
    .card-label {{
      font-size: 14px;
      font-weight: 700;
      margin-bottom: 6px;
      color: #1c1c1c;
    }}
    .card h2 {{ font-size: 15px; font-weight: 700; margin-bottom: 8px; line-height: 1.35; }}
    .card h2 a {{ color: #1c1c1c; text-decoration: none; }}
    .card h2 a:hover {{ color: #1b4965; text-decoration: underline; }}
    .card p {{ font-size: 13.5px; color: #555; }}
    .card-thought {{ border-top: 3px solid #6a0572; }}
    .card-pick {{ border-top: 3px solid #e63946; }}

    /* Footer */
    footer {{
      text-align: center;
      margin-top: 40px;
      font-size: 11.5px;
      color: #aaa;
    }}
    footer a {{ color: #aaa; }}
  </style>
</head>
<body>
  <div class="wrapper">

    <div class="header">
      <p class="eyebrow">Your Daily Digest</p>
      <h1>Morning Brief</h1>
      <p class="sub">{date} &nbsp;·&nbsp; AI &amp; Technology</p>
    </div>

    <div class="greeting">{greeting}</div>

    {quote_html}

    <div class="divider"><span>Top Stories</span><hr></div>

    {stories_html}

    <div class="divider"><span>Going Deeper</span><hr></div>

    {thought_html}
    {pick_html}

    <footer>
      Generated by Claude Opus &nbsp;·&nbsp; {date}<br>
      <a href="https://anthropic.com" target="_blank" rel="noopener">Powered by Anthropic</a>
    </footer>

  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    date_str = datetime.now().strftime("%B %d, %Y")
    print(f"\n📰  Generating Morning Brief for {date_str}...")

    # 1. Fetch
    print("🌐  Fetching articles from RSS feeds...")
    articles = fetch_recent_articles(hours=24)
    print(f"    Found {len(articles)} articles in the past 24 hours.")

    if not articles:
        print("    ⚠️  No fresh articles — Claude will draw on its own knowledge.")
        articles = [{
            "note": (
                "No articles were retrieved from RSS feeds today. "
                "Please curate the newsletter based on your knowledge of recent AI and tech events."
            )
        }]

    # 2. Generate with Claude
    print("🤖  Asking Claude to curate and write the newsletter...")
    newsletter_data = generate_newsletter(articles, date_str)

    # 3. Render
    print("🎨  Rendering HTML...")
    html = render_html(newsletter_data)

    # 4. Save
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    dated_file = output_dir / f"morning-brief-{datetime.now().strftime('%Y-%m-%d')}.html"
    latest_file = output_dir / "latest.html"

    dated_file.write_text(html, encoding="utf-8")
    latest_file.write_text(html, encoding="utf-8")

    print(f"\n✅  Done!")
    print(f"    Saved: {dated_file}")
    print(f"    Latest: {latest_file}")
    print(f"\n    Open in browser: file://{latest_file.resolve()}")


if __name__ == "__main__":
    main()
