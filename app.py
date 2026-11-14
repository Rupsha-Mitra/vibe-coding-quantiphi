"""GitHub Developer Portfolio - Flask backend.

Run:  python app.py        (then open http://localhost:5000, try username "demo")
Optional: export GITHUB_TOKEN=ghp_...  -> GraphQL contribution calendar + 5,000 req/hr
"""
import os
import re
import time

from flask import Flask, Response, jsonify, request, send_from_directory

import analytics
import db
import github_client as gh
import matcher

app = Flask(__name__, static_folder="static", static_url_path="/static")
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
MAX_JD_CHARS = 20000


def valid_login(login):
    if not LOGIN_RE.match(login or ""):
        raise gh.GitHubError("That doesn't look like a valid GitHub username", 400)
    return login


@app.errorhandler(gh.GitHubError)
def handle_github_error(e):
    return jsonify({"error": str(e), "rate_limited": isinstance(e, gh.RateLimited)}), e.status


def build_dashboard(login, force=False):
    valid_login(login)
    profile, p_src = gh.get_profile(login, force)
    repos, r_src = gh.get_repos(login, force)
    days, c_src, c_origin = gh.get_contributions(login, force)

    leveled = analytics.add_levels(days)
    cstats = analytics.contribution_stats(days)
    st = analytics.streaks(days)
    totals = analytics.repo_totals(repos)
    persona, achievements = analytics.persona_and_achievements(totals, cstats, st)

    jd = db.get_jd(login)
    match = matcher.compute_match(jd, repos) if jd else None

    _, cached_at = db.get_profile(login)
    return {
        "profile": profile,
        "totals": totals,
        "languages": analytics.language_breakdown(repos),
        "contributions": {"days": leveled, "source": c_src, "stats": cstats, "streaks": st},
        "repos": repos,
        "persona": persona,
        "achievements": achievements,
        "job_description": jd,
        "match": match,
        "meta": {
            "origins": {"profile": p_src, "repos": r_src, "contributions": c_origin},
            "cached_at": cached_at,
            "authenticated": gh.has_token(),
            "ttl_minutes": db.get_settings()["cache_ttl_minutes"],
        },
    }


# ---------- pages ----------
@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ---------- API ----------
@app.get("/api/dashboard/<login>")
def api_dashboard(login):
    force = request.args.get("refresh") == "1"
    return jsonify(build_dashboard(login, force))


@app.post("/api/match/<login>")
def api_match(login):
    valid_login(login)
    text = ((request.get_json(silent=True) or {}).get("job_description") or "").strip()
    if len(text) > MAX_JD_CHARS:
        return jsonify({"error": f"Job description too long (max {MAX_JD_CHARS} characters)"}), 400
    db.put_jd(login, text)
    if not text:
        return jsonify({"match": None})
    repos, _ = gh.get_repos(login)  # served from the SQLite cache when fresh
    return jsonify({"match": matcher.compute_match(text, repos)})


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        return jsonify(db.save_settings(request.get_json(silent=True) or {}))
    return jsonify(db.get_settings())


@app.delete("/api/cache")
@app.delete("/api/cache/<login>")
def api_clear_cache(login=None):
    db.clear_cache(login)
    return jsonify({"cleared": login or "all"})


@app.get("/api/status")
def api_status():
    return jsonify({"ok": True, "time": time.time(), **gh.rate_limit()})


# ---------- embeddable badges (extra feature 2) ----------
def _svg(body):
    return Response(body, mimetype="image/svg+xml", headers={"Cache-Control": "public, max-age=900"})


@app.get("/badge/<login>/<kind>.svg")
def badge(login, kind):
    try:
        valid_login(login)
        days, _, _ = gh.get_contributions(login)
        repos, _ = gh.get_repos(login)
        if kind == "streak":
            s = analytics.streaks(days)
            return _svg(analytics.make_badge("streak", f"{s['current']} days (best {s['longest']})", "#f0883e"))
        if kind == "stars":
            return _svg(analytics.make_badge("total stars", str(analytics.repo_totals(repos)["total_stars"]), "#dfb317"))
        if kind == "match":
            jd = db.get_jd(login)
            if not jd:
                return _svg(analytics.make_badge("stack match", "no job set", "#8b949e"))
            m = matcher.compute_match(jd, repos)
            pct = m["percent"]
            return _svg(analytics.make_badge("stack match", f"{pct}%" if pct is not None else "n/a", analytics.match_color(pct)))
        return _svg(analytics.make_badge("badge", "unknown kind", "#8b949e")), 404
    except gh.GitHubError:
        return _svg(analytics.make_badge("github", "unavailable", "#8b949e"))


if __name__ == "__main__":
    db.init_db()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("DEBUG") == "1")
else:
    db.init_db()
