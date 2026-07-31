import json, os, sys, base64

repo_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(repo_root, "bin", "upload"))
sys.path.insert(0, os.path.join(repo_root, "bin", "core"))

from upload_youtube import build_title, system_title_tag, content_profile
from title_lint import lint as title_lint

with open(os.path.join(repo_root, "_tmp_backfill_candidates.json"), encoding="utf-8") as f:
    candidates = json.load(f)

results = []
for c in candidates:
    os.environ["BIZZAL_SYSTEM_ID"] = c["sys"]
    atom = {
        "fact": {"name": c["fact_name"]},
        "category": c["category"],
        "script": {"hook": c["hook"]},
    }
    title = build_title(atom, c["day"])
    title, issues, ok = title_lint(title)
    _tag = system_title_tag(content_profile(atom))
    if _tag.lstrip("#").lower() not in title.lower():
        _candidate = f"{title} {_tag}"
        if len(_candidate) <= 100:
            title = _candidate
        else:
            budget = 100 - len(_tag) - 1
            trimmed = title[:budget].rsplit(" ", 1)[0].rstrip(".!,;: ")
            title = f"{trimmed} {_tag}"
    results.append({"sys": c["sys"], "vid": c["vid"], "correct_title": title, "lint_issues": issues})

with open(os.path.join(repo_root, "_tmp_recomputed_titles.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"wrote {len(results)} recomputed titles")
