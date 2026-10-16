"""Build data/study_notes.csv for the CKA bot from the Killercoda scenario repos in the course folder.
Usage: python build_notes.py "<CKA Course>/Killercoda" [data/questions.csv]
One note per scenario: id, section (domain guessed from the title/path), title, pages (repo/scenario path),
bullets (the task text, markdown stripped), labels (the solution commands and YAML, as the study card's "commands"),
related (bank question ids by keyword overlap). Scenario repos with index.json (Killercoda layout) and plain
solution folders (one README/solution .md per task) are both handled. The course folder is private (gitignored).
"""
import csv, json, math, os, re, sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1])
BANK = Path(sys.argv[2] if len(sys.argv) > 2 else "data/questions.csv")
OUT = Path("data/study_notes.csv")
DOMAINS = [("Troubleshooting", r"troubleshoot|debug|broken|fix|issue|not (?:running|working)|crash|fail|log|event|restore"),
           ("Cluster Architecture, Installation & Configuration", r"upgrade|kubeadm|etcd|backup|cluster|node|rbac|role|service ?account|certificate|cert|helm|kustomize|crd|operator|install|cni|api"),
           ("Services & Networking", r"service|svc|ingress|gateway|network ?polic|netpol|dns|coredns|nodeport|clusterip|port|endpoint"),
           ("Storage", r"pv\b|pvc|persistent|volume|storage ?class|mount"),
           ("Workloads & Scheduling", r"pod|deploy|replica|daemon|stateful|job|cron|scale|hpa|rollout|rolling|schedul|taint|toler|affinity|configmap|secret|label|resource|quota|limit|probe|init|sidecar|multi-container")]
STOP = set("the and for with your you are can use using from into that this what how of to in on a an is be or by it its "
           "vs via not up create make should must will which when where".split())


def tokens(s):
    return [t for t in re.findall(r"[a-z0-9][a-z0-9@\-.]+", s.lower()) if t not in STOP and len(t) > 1]


def md_text(s):
    """Markdown -> plain text, keeping fenced blocks out (they go to labels)."""
    s = re.sub(r"```.*?```", " ", s, flags=re.S)
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"^\s{0,3}#+\s*", "", s, flags=re.M)
    s = re.sub(r"[*_>|]+", " ", s)
    s = re.sub(r"[\U0001F300-\U0001FAFF☀-➿⭐✅❌]", "", s)
    lines = [re.sub(r"\s+", " ", l).strip() for l in s.splitlines()]
    return "\n".join(l for l in lines if l and not re.match(r"^(click|welcome|press|start scenario|---)", l, re.I))


def code_blocks(s):
    return [b.strip() for b in re.findall(r"```(?:\w+)?\n(.*?)```", s, re.S) if b.strip()]


def domain_of(text):
    t = text.lower()
    best, score = "Workloads & Scheduling", 0
    for name, pat in DOMAINS:
        n = len(re.findall(pat, t))
        if n > score:
            best, score = name, n
    return best


def read(p):
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


notes = []
seen_titles = set()
# 1. Killercoda layout: index.json + intro/step/finish md (+ solution files, verify.sh, setup.sh)
for idx in sorted(ROOT.rglob("index.json")):
    if ".git" in idx.parts:
        continue
    d = idx.parent
    try:
        meta = json.loads(read(idx))
    except Exception:
        continue
    title = (meta.get("title") or d.name).strip()
    steps = [s.get("text") for s in meta.get("details", {}).get("steps", []) if s.get("text")]
    task = "\n".join(md_text(read(d / f)) for f in steps if (d / f).exists())
    if not task.strip():
        task = md_text(read(d / meta.get("details", {}).get("intro", {}).get("text", "intro.md")))
    sol_files = [p for p in d.iterdir() if p.is_file() and re.search(r"solution|answer|finish", p.name, re.I)]
    labels = []
    for p in sorted(sol_files):
        labels += code_blocks(read(p)) if p.suffix == ".md" else [read(p).strip()]
    for f in steps:                                   # some authors put the solution inside the step as a code block
        labels += code_blocks(read(d / f)) if (d / f).exists() else []
    labels = [l for l in labels if l and not l.startswith("#!/bin/bash\n# verify")]
    key = re.sub(r"\W+", " ", title.lower()).strip()
    if key in seen_titles or not task.strip():
        continue
    seen_titles.add(key)
    rel = d.relative_to(ROOT).as_posix()
    notes.append({"section": domain_of(title + " " + rel + " " + meta.get("description", "")), "title": title,
                  "pages": rel, "bullets": task[:2500], "labels": "\n---\n".join(labels)[:3000]})

# 2. Plain solution folders (e.g. CKA-KILLERKODA-SOLUTION/<Domain>/<Task>/*.md): one note per task folder
for md in sorted(ROOT.rglob("*.md")):
    if ".git" in md.parts or any((md.parent / x).exists() for x in ("index.json",)) or md.name.lower() in ("readme.md", "changelog.md", "contributing.md", "code_of_conduct.md", "security.md", "templates.md"):
        continue
    if "SOLUTION" not in md.as_posix().upper() and "exercises" not in md.as_posix():
        continue
    txt = read(md)
    title = (re.search(r"^#\s*(.+)$", txt, re.M) or [None, md.parent.name.replace("-", " ")])[1].strip()
    key = re.sub(r"\W+", " ", title.lower()).strip()
    if key in seen_titles:
        continue
    task, labels = md_text(txt), code_blocks(txt)
    if not labels:
        continue
    seen_titles.add(key)
    rel = md.relative_to(ROOT).as_posix()
    notes.append({"section": domain_of(title + " " + rel), "title": title, "pages": rel,
                  "bullets": task[:2500], "labels": "\n---\n".join(labels)[:3000]})

# 3. Concept notes from downloaded docs/notes pages in sources/notes/*.md (kubernetes.io via Jina, community notes):
#    one note per page: title = first heading, bullets = the page text, labels = its code blocks
NOTES_DIR = Path(__file__).resolve().parent / "sources" / "notes"
for md in sorted(NOTES_DIR.glob("*.md")) if NOTES_DIR.exists() else []:
    txt = read(md)
    title = (re.search(r"^#\s*(.+)$", txt, re.M) or [None, md.stem.replace("_", " ")])[1].strip()
    title = re.sub(r"\s*[|·].*$", "", title)[:120]
    key = re.sub(r"\W+", " ", title.lower()).strip()
    if key in seen_titles or len(txt) < 400:
        continue
    seen_titles.add(key)
    body = md_text(txt)
    body = re.sub(r"^(Title:|URL Source:|Markdown Content:).*$", "", body, flags=re.M).strip()
    notes.append({"section": domain_of(title + " " + md.stem + " " + body[:1500]) if not md.stem.startswith("bash_") else "Bash & Linux basics",
                  "title": title, "pages": f"notes/{md.name}", "bullets": body[:2500], "labels": "\n---\n".join(code_blocks(txt))[:3000]})

# related bank questions: IDF-weighted overlap of title (x3) + task tokens with question text
bank = list(csv.DictReader(BANK.open(encoding="utf-8"))) if BANK.exists() else []
qtok = {q["id"]: set(tokens(q["question"] + " " + q["options"])) for q in bank}
df = Counter(t for ts in qtok.values() for t in ts)
idf = lambda t: math.log((len(bank) + 1) / (df.get(t, 0) + 1))
for n in notes:
    tt, bt = set(tokens(n["title"])), set(tokens(n["bullets"]))
    scored = sorted(((sum(idf(t) * (3 if t in tt else 1) for t in (tt | bt) & ts), qid) for qid, ts in qtok.items()), reverse=True)
    n["related"] = ",".join(qid for s, qid in scored[:3] if s >= 6)

OUT.parent.mkdir(exist_ok=True)
with OUT.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["id", "section", "title", "pages", "bullets", "labels", "related"])
    w.writeheader()
    for k, n in enumerate(notes, 1):
        w.writerow({"id": f"N-{k:04d}", **n})
print(Counter(n["section"] for n in notes))
print("notes:", len(notes), "with commands:", sum(bool(n["labels"]) for n in notes), "with related:", sum(bool(n["related"]) for n in notes), "->", OUT)
