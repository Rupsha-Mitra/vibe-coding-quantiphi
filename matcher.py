"""Tech Stack Compatibility ("Vibe Check").

Pipeline:
  1. Extract known technologies from the job description (alias dictionary,
     so "golang", "Node", "k8s" are understood).
  2. Build evidence from the user's *cached repos*: primary languages
     (weighted by stars) plus topics / repo names / descriptions.
  3. Score each JD term: languages are weighted heaviest, then frameworks,
     then tools. Full credit needs direct evidence; framework terms get
     partial credit when the user only knows the underlying language
     (e.g. Django asked, Python owned).
"""
import math
import re

# canonical -> (category, aliases, github_language_name, implied_languages)
# Aliases are case-insensitive unless listed in CASE_SENSITIVE.
TECH = {
    # languages
    "Python": ("language", ["python", "python3"], "Python", []),
    "JavaScript": ("language", ["javascript", "js", "ecmascript", "es6"], "JavaScript", []),
    "TypeScript": ("language", ["typescript", "ts"], "TypeScript", []),
    "Java": ("language", ["java"], "Java", []),
    "Go": ("language", ["golang", "Go"], "Go", []),
    "Rust": ("language", ["rust"], "Rust", []),
    "C++": ("language", ["c++", "cpp"], "C++", []),
    "C": ("language", ["c/c++", "c programming", "c language"], "C", []),
    "C#": ("language", ["c#", "csharp"], "C#", []),
    "Ruby": ("language", ["ruby"], "Ruby", []),
    "PHP": ("language", ["php"], "PHP", []),
    "Swift": ("language", ["swift"], "Swift", []),
    "Kotlin": ("language", ["kotlin"], "Kotlin", []),
    "Scala": ("language", ["scala"], "Scala", []),
    "Shell": ("language", ["bash", "shell scripting", "shell"], "Shell", []),
    "HTML": ("language", ["html", "html5"], "HTML", []),
    "CSS": ("language", ["css", "css3", "sass", "scss"], "CSS", []),
    "R": ("language", ["r programming", "r language"], "R", []),
    "Dart": ("language", ["dart"], "Dart", []),
    # frameworks / libraries
    "React": ("framework", ["react", "react.js", "reactjs"], None, ["JavaScript", "TypeScript"]),
    "Angular": ("framework", ["angular", "angularjs"], None, ["TypeScript", "JavaScript"]),
    "Vue": ("framework", ["vue", "vue.js", "vuejs"], None, ["JavaScript", "TypeScript"]),
    "Next.js": ("framework", ["next.js", "nextjs"], None, ["JavaScript", "TypeScript"]),
    "Node.js": ("framework", ["node", "node.js", "nodejs"], None, ["JavaScript", "TypeScript"]),
    "Express": ("framework", ["express", "express.js", "expressjs"], None, ["JavaScript", "TypeScript"]),
    "Django": ("framework", ["django"], None, ["Python"]),
    "Flask": ("framework", ["flask"], None, ["Python"]),
    "FastAPI": ("framework", ["fastapi"], None, ["Python"]),
    "Spring": ("framework", ["spring", "spring boot", "springboot"], None, ["Java", "Kotlin"]),
    "Rails": ("framework", ["rails", "ruby on rails"], None, ["Ruby"]),
    "Laravel": ("framework", ["laravel"], None, ["PHP"]),
    ".NET": ("framework", [".net", "dotnet", "asp.net"], None, ["C#"]),
    "PyTorch": ("framework", ["pytorch"], None, ["Python", "Jupyter Notebook"]),
    "TensorFlow": ("framework", ["tensorflow"], None, ["Python", "Jupyter Notebook"]),
    "Pandas": ("framework", ["pandas"], None, ["Python", "Jupyter Notebook"]),
    # tools / platforms / concepts
    "Docker": ("tool", ["docker", "containers", "containerization"], None, []),
    "Kubernetes": ("tool", ["kubernetes", "k8s", "helm"], None, []),
    "AWS": ("tool", ["aws", "amazon web services"], None, []),
    "GCP": ("tool", ["gcp", "google cloud"], None, []),
    "Azure": ("tool", ["azure"], None, []),
    "PostgreSQL": ("tool", ["postgresql", "postgres"], None, []),
    "MySQL": ("tool", ["mysql", "mariadb"], None, []),
    "MongoDB": ("tool", ["mongodb", "mongo"], None, []),
    "Redis": ("tool", ["redis"], None, []),
    "SQL": ("tool", ["sql", "sqlite"], None, []),
    "Kafka": ("tool", ["kafka"], None, []),
    "GraphQL": ("tool", ["graphql"], None, []),
    "REST": ("tool", ["rest", "restful", "rest api", "rest apis"], None, []),
    "Terraform": ("tool", ["terraform"], None, []),
    "CI/CD": ("tool", ["ci/cd", "cicd", "github actions", "jenkins", "continuous integration"], None, []),
    "Microservices": ("tool", ["microservices", "microservice"], None, []),
    "Machine Learning": ("tool", ["machine learning", "ml", "deep learning"], None, ["Jupyter Notebook"]),
    "Git": ("tool", ["git", "github"], None, []),
}

CASE_SENSITIVE = {"Go", "R"}
# Words after "Go" that mean it's English, not the language ("go to market").
GO_ENGLISH = r"(?!\s+(?:to|beyond|above|the|ahead|live|forward|getter|with|for|through|into|out)\b)"

BASE_WEIGHT = {"language": 3.0, "framework": 2.0, "tool": 1.0}
RELATED_LANG = {  # asked -> {owned: partial credit}
    "JavaScript": {"TypeScript": 0.6},
    "TypeScript": {"JavaScript": 0.5},
    "C": {"C++": 0.5},
    "C++": {"C": 0.5},
    "Java": {"Kotlin": 0.5, "Scala": 0.4},
    "Kotlin": {"Java": 0.5},
    "CSS": {},
}
ALWAYS_HAVE = {"Git"}  # anyone with a GitHub profile


def _alias_regex(alias, case_sensitive=False):
    esc = re.escape(alias)
    pat = rf"(?<![A-Za-z0-9+#.]){esc}(?![A-Za-z0-9+#])"
    if alias == "Go":
        pat = rf"(?<![A-Za-z0-9+#.]){esc}(?![A-Za-z0-9+#]){GO_ENGLISH}"
    return re.compile(pat, 0 if case_sensitive else re.IGNORECASE)


_COMPILED = {
    name: [(a, _alias_regex(a, a in CASE_SENSITIVE)) for a in info[1]] for name, info in TECH.items()
}


def _count(text, name):
    total = 0
    for _alias, rx in _COMPILED[name]:
        total += len(rx.findall(text))
    return total


def extract_terms(jd_text):
    """-> {canonical_name: occurrence_count} for every known tech in the JD."""
    found = {}
    for name in TECH:
        c = _count(jd_text, name)
        if c:
            found[name] = c
    # "C/C++" mentions both C and C++
    if re.search(r"c/c\+\+", jd_text, re.IGNORECASE):
        found.setdefault("C++", 1)
        found.setdefault("C", 1)
    return found


def _language_shares(repos):
    weights = {}
    for r in repos:
        lang = r.get("language")
        if not lang or r.get("fork"):
            continue
        weights[lang] = weights.get(lang, 0) + 1 + math.log2(1 + r.get("stars", 0))
    total = sum(weights.values()) or 1
    return {k: v / total for k, v in weights.items()}


def _evidence_blob(repos):
    parts = []
    for r in repos:
        parts += [r.get("name", "").replace("-", " ").replace("_", " "), r.get("description", "")]
        parts += r.get("topics", [])
        if r.get("language"):
            parts.append(r["language"])
    return " \n ".join(parts)


def _evidence_for(name, blob):
    return _count(blob, name) > 0


def _label(pct):
    if pct >= 80:
        return "Strong match"
    if pct >= 60:
        return "Good match"
    if pct >= 40:
        return "Partial match"
    return "Stretch role"


def _suggestion(name, category, owned_langs):
    if category == "language":
        return f"Ship a small project in {name} and keep it public - even one repo makes the language visible on your profile."
    if category == "framework":
        implied = TECH[name][3]
        known = [l for l in implied if l in owned_langs]
        if known:
            return f"Quick win: you already write {known[0]}. Build a small {name} app and add the '{name.lower()}' topic to the repo."
        return f"Build a small {name} project; it's a bigger jump since none of its usual languages appear in your repos."
    return f"Add a {name} component to an existing project (and mention it in the README/topics) so recruiters can see it."


def compute_match(jd_text, repos):
    terms = extract_terms(jd_text or "")
    if not terms:
        return {
            "percent": None, "label": "No tech keywords found",
            "message": "I couldn't find any known technologies in that text. Paste the full job description.",
            "matched": [], "partial": [], "missing": [], "language_percent": None, "terms_found": 0,
        }
    shares = _language_shares(repos)
    blob = _evidence_blob(repos)
    owned = set(shares)

    earned = total = lang_earned = lang_total = 0.0
    matched, partial, missing = [], [], []

    for name, count in terms.items():
        cat = TECH[name][0]
        weight = BASE_WEIGHT[cat] * (1 + 0.5 * min(count - 1, 3))
        credit, why = 0.0, ""

        if cat == "language":
            gh = TECH[name][2]
            if gh in shares:
                s = shares[gh]
                credit = 1.0 if s >= 0.10 else 0.85 if s >= 0.03 else 0.6
                why = f"{round(s * 100)}% of your repo weight"
            else:
                for other, c in RELATED_LANG.get(name, {}).items():
                    if other in shares and c > credit:
                        credit, why = c, f"related to your {other}"
        elif name in ALWAYS_HAVE:
            credit, why = 1.0, "you're on GitHub"
        else:
            if _evidence_for(name, blob):
                credit, why = 1.0, "found in your repo topics/descriptions"
            elif cat == "framework" and any(l in owned for l in TECH[name][3]):
                credit, why = 0.4, "you know the underlying language"
            elif name == "SQL" and owned & {"PLpgSQL", "TSQL", "PLSQL"}:
                credit, why = 1.0, "SQL dialect repos"

        earned += weight * credit
        total += weight
        if cat == "language":
            lang_earned += weight * credit
            lang_total += weight

        entry = {"term": name, "category": cat, "mentions": count, "credit": round(credit, 2), "evidence": why}
        if credit >= 0.85:
            matched.append(entry)
        elif credit > 0:
            partial.append(entry)
        else:
            entry["suggestion"] = _suggestion(name, cat, owned)
            missing.append(entry)

    pct = round(100 * earned / total)
    return {
        "percent": pct,
        "label": _label(pct),
        "language_percent": round(100 * lang_earned / lang_total) if lang_total else None,
        "matched": sorted(matched, key=lambda e: -e["mentions"]),
        "partial": sorted(partial, key=lambda e: -e["credit"]),
        "missing": sorted(missing, key=lambda e: -e["mentions"]),
        "terms_found": len(terms),
        "message": "",
    }
