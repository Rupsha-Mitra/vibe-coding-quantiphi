"""Pure functions turning raw cached data into dashboard stats."""
import hashlib
import math
from datetime import date, timedelta
from html import escape

LANG_COLORS = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6", "Java": "#b07219",
    "Go": "#00ADD8", "Rust": "#dea584", "C++": "#f34b7d", "C": "#555555", "C#": "#178600",
    "Ruby": "#701516", "PHP": "#4F5D95", "Swift": "#F05138", "Kotlin": "#A97BFF", "Shell": "#89e051",
    "HTML": "#e34c26", "CSS": "#563d7c", "Jupyter Notebook": "#DA5B0B", "Dart": "#00B4AB",
    "Scala": "#c22d40", "Vue": "#41b883", "Other": "#8b949e",
}


def lang_color(lang):
    if lang in LANG_COLORS:
        return LANG_COLORS[lang]
    h = hashlib.md5(lang.encode()).hexdigest()
    return f"#{h[:6]}"


# ---------- contribution heatmap ----------
def add_levels(days):
    """Attach a 0-4 intensity level to each day using quartiles of active days."""
    nz = sorted(d["count"] for d in days if d["count"] > 0)
    if not nz:
        return [{**d, "level": 0} for d in days]

    def q(p):
        return nz[min(len(nz) - 1, int(p * len(nz)))]

    q1, q2, q3 = q(0.25), q(0.5), q(0.75)
    out = []
    for d in days:
        c = d["count"]
        lvl = 0 if c == 0 else 1 if c <= q1 else 2 if c <= q2 else 3 if c <= q3 else 4
        out.append({**d, "level": lvl})
    return out


def streaks(days, today=None):
    today = today or date.today()
    by_date = {d["date"]: d["count"] for d in days}
    ordered = sorted(by_date)

    longest = run = 0
    longest_end = None
    prev = None
    for ds in ordered:
        d = date.fromisoformat(ds)
        if by_date[ds] > 0:
            run = run + 1 if prev and (d - prev).days == 1 else 1
            prev = d
            if run > longest:
                longest, longest_end = run, ds
        else:
            run, prev = 0, None

    # current streak: allow today to still be empty (day isn't over)
    cur = 0
    cursor = today
    if by_date.get(cursor.isoformat(), 0) == 0:
        cursor -= timedelta(days=1)
    while by_date.get(cursor.isoformat(), 0) > 0:
        cur += 1
        cursor -= timedelta(days=1)
    return {"current": cur, "longest": longest, "longest_ended": longest_end}


def contribution_stats(days):
    total = sum(d["count"] for d in days)
    active = [d for d in days if d["count"] > 0]
    weekday_totals = [0] * 7
    for d in days:
        weekday_totals[date.fromisoformat(d["date"]).weekday()] += d["count"]
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    best = max(days, key=lambda d: d["count"]) if days else None
    weekend_share = (weekday_totals[5] + weekday_totals[6]) / total if total else 0
    return {
        "total": total,
        "active_days": len(active),
        "avg_per_active_day": round(total / len(active), 1) if active else 0,
        "best_day": best if best and best["count"] else None,
        "busiest_weekday": names[weekday_totals.index(max(weekday_totals))] if total else None,
        "weekday_totals": weekday_totals,
        "weekend_share": round(weekend_share, 2),
        "last_30_days": sum(d["count"] for d in days[-30:]),
    }


# ---------- repos / languages ----------
def language_breakdown(repos, top=6):
    weights, counts = {}, {}
    for r in repos:
        lang = r.get("language")
        if not lang or r.get("fork"):
            continue
        weights[lang] = weights.get(lang, 0) + 1 + math.log2(1 + r.get("stars", 0))
        counts[lang] = counts.get(lang, 0) + 1
    total = sum(weights.values())
    if not total:
        return []
    ranked = sorted(weights, key=weights.get, reverse=True)
    out = [
        {"language": l, "repos": counts[l], "percent": round(100 * weights[l] / total, 1), "color": lang_color(l)}
        for l in ranked[:top]
    ]
    rest = ranked[top:]
    if rest:
        pct = round(100 * sum(weights[l] for l in rest) / total, 1)
        out.append({"language": "Other", "repos": sum(counts[l] for l in rest), "percent": pct, "color": LANG_COLORS["Other"]})
    return out


def repo_totals(repos):
    own = [r for r in repos if not r.get("fork")]
    return {
        "total_stars": sum(r.get("stars", 0) for r in repos),
        "total_forks": sum(r.get("forks", 0) for r in repos),
        "repo_count": len(repos),
        "original_repo_count": len(own),
        "language_count": len({r["language"] for r in own if r.get("language")}),
        "top_repo": max(own, key=lambda r: r.get("stars", 0))["name"] if own else None,
    }


# ---------- extra feature 1: persona & achievements ----------
def persona_and_achievements(totals, cstats, st):
    ach = [
        ("Century Club", "Earn 100+ total stars", totals["total_stars"] >= 100, f"{totals['total_stars']} stars"),
        ("Polyglot", "Ship repos in 5+ languages", totals["language_count"] >= 5, f"{totals['language_count']} languages"),
        ("Streak Master", "Hit a 30-day contribution streak", st["longest"] >= 30, f"best {st['longest']} days"),
        ("Consistency", "Be active on 200+ days in a year", cstats["active_days"] >= 200, f"{cstats['active_days']} active days"),
        ("Community Magnet", "Get 25+ forks across repos", totals["total_forks"] >= 25, f"{totals['total_forks']} forks"),
        ("Prolific", "Make 1,000+ contributions in a year", cstats["total"] >= 1000, f"{cstats['total']} contributions"),
    ]
    achievements = [{"name": n, "goal": g, "unlocked": u, "detail": d} for n, g, u, d in ach]

    if totals["total_stars"] >= 500:
        persona = ("Open Source Star", "Your work is widely used and starred - a strong public track record.")
    elif st["longest"] >= 30:
        persona = ("Streak Machine", "You show up day after day. Consistency is your superpower.")
    elif totals["language_count"] >= 5:
        persona = ("Polyglot Builder", "You move comfortably across languages and stacks.")
    elif cstats["weekend_share"] >= 0.35:
        persona = ("Weekend Warrior", "A big share of your commits land on weekends - a true side-project builder.")
    elif cstats["total"] == 0:
        persona = ("Getting Started", "No public activity in the last year yet - your first commit is the next milestone.")
    else:
        persona = ("Rising Builder", "Steady activity with room to grow - keep shipping.")
    return {"title": persona[0], "blurb": persona[1]}, achievements


# ---------- extra feature 2: embeddable SVG badges ----------
def make_badge(label, value, color="#2ea043"):
    lw = int(len(label) * 6.6 + 14)
    vw = int(len(value) * 6.6 + 14)
    w = lw + vw
    label, value = escape(label), escape(value)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="20" role="img" aria-label="{label}: {value}">'
        f'<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>'
        f'<clipPath id="r"><rect width="{w}" height="20" rx="3" fill="#fff"/></clipPath>'
        f'<g clip-path="url(#r)"><rect width="{lw}" height="20" fill="#555"/><rect x="{lw}" width="{vw}" height="20" fill="{color}"/>'
        f'<rect width="{w}" height="20" fill="url(#s)"/></g>'
        f'<g fill="#fff" text-anchor="middle" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11">'
        f'<text x="{lw / 2}" y="14">{label}</text><text x="{lw + vw / 2}" y="14">{value}</text></g></svg>'
    )


def match_color(pct):
    if pct is None:
        return "#8b949e"
    return "#2ea043" if pct >= 80 else "#97ca00" if pct >= 60 else "#dfb317" if pct >= 40 else "#e05d44"
