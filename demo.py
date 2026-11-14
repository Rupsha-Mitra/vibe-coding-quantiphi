"""Deterministic sample data so the dashboard works offline (username: demo)."""
import random
from datetime import date, timedelta

DEMO_LOGIN = "demo"


def is_demo(login):
    return login.lower() == DEMO_LOGIN


def profile():
    return {
        "login": "demo", "name": "Demo Developer", "avatar_url": "",
        "bio": "Full-stack engineer. Sample data - type any GitHub username to see the real thing.",
        "company": "Acme Labs", "location": "Remote", "blog": "", "html_url": "https://github.com",
        "followers": 482, "following": 61, "public_repos": 12, "created_at": "2018-03-02T00:00:00Z",
    }


_REPOS = [
    ("stream-etl", "Fault-tolerant ETL pipeline for event streams", "Python", 412, 58, ["etl", "kafka", "docker", "postgresql"]),
    ("react-dash-kit", "Composable React dashboard components", "TypeScript", 389, 44, ["react", "typescript", "frontend"]),
    ("go-ratelimiter", "Token-bucket rate limiter with Redis backend", "Go", 301, 27, ["redis", "microservices", "api"]),
    ("rust-kv", "Tiny log-structured key-value store", "Rust", 220, 19, ["database", "storage"]),
    ("flask-auth-starter", "Flask REST API starter with JWT auth", "Python", 148, 33, ["flask", "rest", "jwt", "sqlite"]),
    ("k8s-playground", "Helm charts and manifests for local clusters", "Shell", 96, 12, ["kubernetes", "devops", "aws"]),
    ("sql-lint", "Opinionated SQL linter", "JavaScript", 74, 8, ["sql", "nodejs", "cli"]),
    ("ml-notes", "Notebooks on gradient boosting and embeddings", "Jupyter Notebook", 61, 9, ["machine-learning", "pytorch"]),
    ("dotfiles", "My terminal setup", "Shell", 22, 3, []),
    ("css-tricks-lab", "Tiny CSS experiments", "CSS", 15, 2, ["css"]),
    ("java-spring-shop", "Spring Boot demo shop with PostgreSQL", "Java", 12, 4, ["spring", "postgresql", "rest"]),
    ("typed-fetch", "Type-safe fetch wrapper", "TypeScript", 9, 1, ["typescript", "graphql"]),
]


def repos():
    out = []
    for i, (name, desc, lang, stars, forks, topics) in enumerate(_REPOS):
        out.append({
            "name": name, "description": desc, "html_url": f"https://github.com/demo/{name}",
            "language": lang, "stars": stars, "forks": forks, "topics": topics, "size": 200 + i * 90,
            "fork": False, "archived": False, "updated_at": (date.today() - timedelta(days=i * 17)).isoformat(),
        })
    return out


def contributions():
    rng = random.Random(42)
    today = date.today()
    days = []
    streak_burst_start = 60  # a deliberate recent streak so streak UI has something to show
    for i in range(364, -1, -1):
        d = today - timedelta(days=i)
        weekend = d.weekday() >= 5
        base = rng.random()
        if i < streak_burst_start:
            count = rng.randint(1, 9)
        elif base < (0.55 if weekend else 0.25):
            count = 0
        else:
            count = rng.choice([1, 1, 2, 3, 4, 6, 9, 12])
        days.append({"date": d.isoformat(), "count": count})
    return days
