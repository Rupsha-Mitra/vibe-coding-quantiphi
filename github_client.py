"""GitHub REST + GraphQL client with cache-first reads.

Flow for every resource: fresh cache -> return it; otherwise hit the API and
store the result; if the API fails (rate limit / network) and we have *stale*
cache, return that instead of an error.
"""
import os
from datetime import date, datetime, timedelta, timezone

import requests

import db
import demo

API = "https://api.github.com"
TIMEOUT = 15


class GitHubError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


class RateLimited(GitHubError):
    pass


def _headers():
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "gh-portfolio"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def has_token():
    return bool(os.environ.get("GITHUB_TOKEN"))


def _get(path, params=None):
    try:
        r = requests.get(f"{API}{path}", headers=_headers(), params=params, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise GitHubError(f"Could not reach GitHub: {e.__class__.__name__}")
    if r.status_code == 404:
        raise GitHubError("GitHub user not found", 404)
    if r.status_code in (403, 429) and r.headers.get("X-RateLimit-Remaining") == "0":
        reset = int(r.headers.get("X-RateLimit-Reset", 0))
        mins = max(1, int((reset - datetime.now().timestamp()) / 60))
        raise RateLimited(f"GitHub rate limit hit; resets in ~{mins} min. Set GITHUB_TOKEN for 5,000 req/hr.", 429)
    if not r.ok:
        raise GitHubError(f"GitHub API error {r.status_code}", 502)
    return r.json()


def _graphql(query, variables):
    try:
        r = requests.post(
            f"{API}/graphql", json={"query": query, "variables": variables}, headers=_headers(), timeout=TIMEOUT
        )
    except requests.RequestException as e:
        raise GitHubError(f"Could not reach GitHub: {e.__class__.__name__}")
    if r.status_code in (401, 403):
        raise GitHubError("GraphQL needs a valid GITHUB_TOKEN", r.status_code)
    data = r.json()
    if data.get("errors"):
        raise GitHubError(data["errors"][0].get("message", "GraphQL error"))
    return data["data"]


# ---------- normalisers ----------
def _norm_profile(u):
    return {
        "login": u["login"],
        "name": u.get("name") or u["login"],
        "avatar_url": u.get("avatar_url"),
        "bio": u.get("bio") or "",
        "company": u.get("company") or "",
        "location": u.get("location") or "",
        "blog": u.get("blog") or "",
        "html_url": u.get("html_url"),
        "followers": u.get("followers", 0),
        "following": u.get("following", 0),
        "public_repos": u.get("public_repos", 0),
        "created_at": u.get("created_at"),
    }


def _norm_repo(r):
    return {
        "name": r["name"],
        "description": r.get("description") or "",
        "html_url": r.get("html_url"),
        "language": r.get("language"),
        "stars": r.get("stargazers_count", 0),
        "forks": r.get("forks_count", 0),
        "topics": r.get("topics", []),
        "size": r.get("size", 0),
        "fork": r.get("fork", False),
        "archived": r.get("archived", False),
        "updated_at": r.get("pushed_at") or r.get("updated_at"),
    }


# ---------- public API ----------
def get_profile(login, force=False):
    if demo.is_demo(login):
        return demo.profile(), "demo"
    cached, ts = db.get_profile(login)
    if cached and not force and db.is_fresh(ts):
        return cached, "cache"
    try:
        prof = _norm_profile(_get(f"/users/{login}"))
    except GitHubError:
        if cached:
            return cached, "stale-cache"
        raise
    db.put_profile(login, prof)
    return prof, "api"


def get_repos(login, force=False):
    if demo.is_demo(login):
        return demo.repos(), "demo"
    cached, ts = db.get_repos(login)
    if cached is not None and not force and db.is_fresh(ts):
        return cached, "cache"
    try:
        repos, page = [], 1
        while page <= 5:  # cap at 500 repos
            batch = _get(f"/users/{login}/repos", {"per_page": 100, "page": page, "sort": "pushed"})
            repos += [_norm_repo(r) for r in batch]
            if len(batch) < 100:
                break
            page += 1
    except GitHubError:
        if cached is not None:
            return cached, "stale-cache"
        raise
    db.put_repos(login, repos)
    return repos, "api"


CAL_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}"""


def _contributions_graphql(login):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=364)
    d = _graphql(CAL_QUERY, {"login": login, "from": start.isoformat(), "to": end.isoformat()})
    if not d.get("user"):
        raise GitHubError("GitHub user not found", 404)
    weeks = d["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [{"date": x["date"], "count": x["contributionCount"]} for w in weeks for x in w["contributionDays"]]


def _contributions_events(login):
    """Token-less fallback: public events cover only ~90 days / 300 events."""
    counts = {}
    for page in (1, 2, 3):
        events = _get(f"/users/{login}/events/public", {"per_page": 100, "page": page})
        for e in events:
            day = e["created_at"][:10]
            n = e.get("payload", {}).get("size", 1) if e["type"] == "PushEvent" else 1
            counts[day] = counts.get(day, 0) + max(1, n)
        if len(events) < 100:
            break
    return _fill_year(counts)


def _fill_year(counts):
    today = date.today()
    days = []
    for i in range(364, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        days.append({"date": d, "count": counts.get(d, 0)})
    return days


def get_contributions(login, force=False):
    """Returns (days, source, origin). source: graphql | events | demo."""
    if demo.is_demo(login):
        return demo.contributions(), "demo", "demo"
    cached, source, ts = db.get_contributions(login)
    if cached and not force and db.is_fresh(ts):
        return cached, source, "cache"
    try:
        if has_token():
            days, source = _contributions_graphql(login), "graphql"
        else:
            days, source = _contributions_events(login), "events"
    except GitHubError:
        if cached:
            return cached, source, "stale-cache"
        raise
    db.put_contributions(login, days, source)
    return days, source, "api"


def rate_limit():
    try:
        r = requests.get(f"{API}/rate_limit", headers=_headers(), timeout=8)
        core = r.json()["resources"]["core"]
        return {"remaining": core["remaining"], "limit": core["limit"], "authenticated": has_token()}
    except Exception:
        return {"remaining": None, "limit": None, "authenticated": has_token()}
