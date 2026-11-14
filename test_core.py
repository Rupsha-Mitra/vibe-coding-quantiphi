import os
import sys
import tempfile
import time
import unittest
from datetime import date, timedelta
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import analytics  # noqa: E402
import db  # noqa: E402
import github_client as gh  # noqa: E402
import matcher  # noqa: E402


def make_repos():
    return [
        {"name": "api", "description": "REST API with Flask", "language": "Python", "stars": 40, "forks": 2, "topics": ["flask", "docker"], "fork": False},
        {"name": "web", "description": "UI", "language": "TypeScript", "stars": 5, "forks": 0, "topics": ["react"], "fork": False},
        {"name": "clone", "description": "", "language": "Rust", "stars": 900, "forks": 0, "topics": [], "fork": True},
    ]


class TempDBCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self._old = db.DB_PATH
        db.DB_PATH = self.tmp.name
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self._old
        os.unlink(self.tmp.name)


class MatcherTests(unittest.TestCase):
    def test_alias_extraction(self):
        t = matcher.extract_terms("We use golang, Node.js, k8s, C++ and C# daily.")
        for name in ("Go", "Node.js", "Kubernetes", "C++", "C#"):
            self.assertIn(name, t)

    def test_go_english_not_language(self):
        self.assertNotIn("Go", matcher.extract_terms("A go to market role"))
        self.assertIn("Go", matcher.extract_terms("Experience with Go and Rust"))

    def test_full_and_partial_credit(self):
        m = matcher.compute_match("Python, Django, Docker, Java", make_repos())
        by = {e["term"]: e for e in m["matched"] + m["partial"] + m["missing"]}
        self.assertEqual(by["Python"]["credit"], 1.0)
        self.assertEqual(by["Docker"]["credit"], 1.0)      # topic evidence
        self.assertEqual(by["Django"]["credit"], 0.4)      # knows Python only
        self.assertEqual(by["Java"]["credit"], 0.0)
        self.assertEqual([e["term"] for e in m["missing"]], ["Java"])
        self.assertTrue(0 < m["percent"] < 100)

    def test_forks_ignored_for_language_ownership(self):
        m = matcher.compute_match("Rust", make_repos())
        self.assertEqual(m["percent"], 0)

    def test_js_ts_related(self):
        m = matcher.compute_match("JavaScript", make_repos())
        self.assertEqual(m["partial"][0]["credit"], 0.6)

    def test_no_terms(self):
        m = matcher.compute_match("We value kindness and curiosity.", make_repos())
        self.assertIsNone(m["percent"])


class AnalyticsTests(unittest.TestCase):
    def days(self, counts):
        today = date.today()
        n = len(counts)
        return [{"date": (today - timedelta(days=n - 1 - i)).isoformat(), "count": c} for i, c in enumerate(counts)]

    def test_streaks_with_empty_today(self):
        s = analytics.streaks(self.days([0, 1, 1, 0, 2, 3, 0]))
        self.assertEqual(s["current"], 2)   # today empty, streak through yesterday
        self.assertEqual(s["longest"], 2)

    def test_current_streak_includes_today(self):
        self.assertEqual(analytics.streaks(self.days([0, 0, 4, 5, 6]))["current"], 3)

    def test_levels(self):
        lv = analytics.add_levels(self.days([0, 1, 2, 3, 4, 100]))
        self.assertEqual(lv[0]["level"], 0)
        self.assertEqual(lv[-1]["level"], 4)
        self.assertTrue(all(0 <= d["level"] <= 4 for d in lv))

    def test_language_breakdown_skips_forks(self):
        langs = analytics.language_breakdown(make_repos())
        self.assertEqual({l["language"] for l in langs}, {"Python", "TypeScript"})
        self.assertAlmostEqual(sum(l["percent"] for l in langs), 100, delta=0.2)

    def test_badge_escapes(self):
        self.assertNotIn("<script>", analytics.make_badge("a", "<script>"))


class CacheTests(TempDBCase):
    def raw_repo(self, name="r"):
        return {"name": name, "description": "d", "stargazers_count": 3, "forks_count": 1, "language": "Go", "topics": []}

    def fake_get(self, payload, status=200, headers=None):
        r = mock.Mock(status_code=status, headers=headers or {}, ok=status < 400)
        r.json.return_value = payload
        return r

    def test_fresh_cache_skips_api(self):
        with mock.patch.object(gh.requests, "get", return_value=self.fake_get([self.raw_repo()])) as g:
            _, src1 = gh.get_repos("alice")
            _, src2 = gh.get_repos("alice")
        self.assertEqual((src1, src2), ("api", "cache"))
        self.assertEqual(g.call_count, 1)

    def test_stale_cache_served_on_rate_limit(self):
        db.put_repos("alice", [{"name": "old", "language": "Go", "stars": 1, "forks": 0, "topics": []}])
        db.save_settings({"cache_ttl_minutes": 1})
        with db.connect() as c:
            c.execute("UPDATE repos SET fetched_at = ?", (time.time() - 7200,))
        limited = self.fake_get({}, 403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(int(time.time()) + 600)})
        with mock.patch.object(gh.requests, "get", return_value=limited):
            repos, src = gh.get_repos("alice")
        self.assertEqual(src, "stale-cache")
        self.assertEqual(repos[0]["name"], "old")

    def test_rate_limit_without_cache_raises(self):
        limited = self.fake_get({}, 403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(int(time.time()) + 600)})
        with mock.patch.object(gh.requests, "get", return_value=limited):
            with self.assertRaises(gh.RateLimited):
                gh.get_repos("bob")

    def test_events_fallback_builds_year(self):
        events = [{"type": "PushEvent", "created_at": date.today().isoformat() + "T10:00:00Z", "payload": {"size": 4}}]
        with mock.patch.object(gh.requests, "get", return_value=self.fake_get(events)), \
             mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GITHUB_TOKEN", None)
            days, source, _ = gh.get_contributions("carol")
        self.assertEqual(source, "events")
        self.assertEqual(len(days), 365)
        self.assertEqual(days[-1]["count"], 4)

    def test_graphql_path_with_token(self):
        payload = {"data": {"user": {"contributionsCollection": {"contributionCalendar": {"weeks": [
            {"contributionDays": [{"date": "2026-11-13", "contributionCount": 2}, {"date": "2026-11-14", "contributionCount": 5}]}]}}}}}
        resp = mock.Mock(status_code=200)
        resp.json.return_value = payload
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "x"}), mock.patch.object(gh.requests, "post", return_value=resp):
            days, source, _ = gh.get_contributions("dave")
        self.assertEqual((source, days[-1]["count"]), ("graphql", 5))

    def test_settings_validation(self):
        s = db.save_settings({"cache_ttl_minutes": 99999, "theme": "neon", "bogus": 1})
        self.assertEqual(s["cache_ttl_minutes"], 1440)
        self.assertEqual(s["theme"], "dark")
        self.assertNotIn("bogus", s)


class AppTests(TempDBCase):
    def setUp(self):
        super().setUp()
        import app as appmod
        self.c = appmod.app.test_client()

    def test_demo_dashboard_and_match_persist(self):
        d = self.c.get("/api/dashboard/demo").get_json()
        self.assertEqual(d["profile"]["login"], "demo")
        self.assertEqual(len(d["contributions"]["days"]), 365)
        self.assertIsNone(d["match"])
        r = self.c.post("/api/match/demo", json={"job_description": "Python and Go engineer"}).get_json()
        self.assertEqual(r["match"]["percent"], 100)
        self.assertIsNotNone(self.c.get("/api/dashboard/demo").get_json()["match"])  # saved JD

    def test_badges(self):
        for kind in ("streak", "stars", "match"):
            r = self.c.get(f"/badge/demo/{kind}.svg")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.mimetype, "image/svg+xml")

    def test_invalid_login_rejected(self):
        self.assertEqual(self.c.get("/api/dashboard/-bad-").status_code, 400)

    def test_settings_roundtrip(self):
        self.c.post("/api/settings", json={"theme": "dark", "cache_ttl_minutes": 5})
        s = self.c.get("/api/settings").get_json()
        self.assertEqual((s["theme"], s["cache_ttl_minutes"]), ("dark", 5))

    def test_jd_too_long(self):
        r = self.c.post("/api/match/demo", json={"job_description": "x" * 20001})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
