# Devfolio - GitHub developer portfolio

A dashboard that turns a GitHub account into a personal branding page: contribution heatmap, repo cards, profile summary with a top-languages chart, and a job-description "stack match" score.

## Run it

```bash
pip install -r requirements.txt
python app.py            # http://127.0.0.1:5000
```

Click **Try demo data** to see everything without touching the GitHub API. Optional but recommended:

```bash
export GITHUB_TOKEN=ghp_xxx   # no scopes needed
```

| | Without token | With token |
|---|---|---|
| Rate limit | 60 requests/hour | 5,000 requests/hour |
| Contribution graph | Built from public events (last ~90 days, max 300 events) | Full 12-month calendar via GraphQL |

The token is read from the environment only and is never stored in SQLite.

## Look and feel

Dark developer-console theme: terminal-style windows, a live status bar showing where each resource came from (cache / api / stale-cache), and motion that is all CSS/JS with no libraries - typed profile name, a wave that reveals the heatmap, count-up stats, a drawn-in language donut, a scanning state on the **Run stack match** button, and an animated match ring. Everything respects `prefers-reduced-motion`.

## Features

**Required**
- **Contribution heatmap** - SVG grid, intensity from quartiles of your active days, with hover tooltips and current/longest streaks.
- **Repo cards** - stars, forks, language tag, description, topics; sort by stars/forks/recency, filter by language, hide forks. The top repo gets a wider lead card.
- **Profile header** - followers, total stars, repos, forks, and a "Top languages" donut chart (weighted by repo count and stars, forks excluded).
- **API integration** - REST for profile, repos and public events; GraphQL for the contribution calendar.
- **SQLite caching** - profile, repos, contributions, settings and saved job descriptions live in `portfolio.db`. Fresh cache is served with no API call; if GitHub rate-limits you, stale cache is served instead of an error. TTL is configurable in Settings (1-1440 min).

**Vibe check: tech stack compatibility**
Paste a job description and the backend (`matcher.py`) extracts known technologies using an alias dictionary (`golang`, `k8s`, `Node` ...), then scores them against your cached repos:
- Languages weigh 3, frameworks 2, tools 1; repeated mentions raise the weight.
- Languages: full credit if you own repos in it (scaled by your share), partial credit for related ones (TypeScript for JavaScript).
- Frameworks/tools: full credit if they appear in repo topics, names or descriptions; frameworks get 40% if you know the underlying language (Django asked, Python owned).
- Result: a **Match Percentage** badge at the top of the profile, a language-only percentage, and the matched / partial / missing breakdown. Hover a chip to see the evidence.

**Extra feature 1: skill-gap coach + developer persona.** Every missing technology comes with a concrete suggestion (a "quick win" when you already know the underlying language). The profile also gets a persona (Streak Machine, Polyglot Builder, Weekend Warrior ...) and six achievements with progress details.

**Extra feature 2: embeddable README badges.** `/badge/<user>/match.svg`, `/streak.svg` and `/stars.svg` return shields-style SVGs you can paste into any README, with copy buttons in the UI. Note: GitHub can only load them if the app is deployed at a public URL.

## Project layout

```
app.py              Flask routes, dashboard assembly, badges
github_client.py    REST + GraphQL client, cache-first reads, stale fallback
db.py               SQLite schema, cache and settings helpers
matcher.py          keyword extraction and match scoring
analytics.py        heatmap levels, streaks, language breakdown, persona, SVG badges
demo.py             deterministic sample data (username "demo")
static/             index.html, style.css, app.js (no build step, no frameworks)
tests/test_core.py  22 tests (GitHub calls are mocked)
```

## Test

```bash
python -m unittest discover -s tests -v
```

## Known limits

- Match scoring is keyword-based: it can't understand seniority, domain or soft requirements, and private repos are invisible to it.
- Repos are capped at 500 per user; languages use the primary language per repo, not byte counts.
- The Flask dev server is for local use; put it behind gunicorn for deployment.
