"""Build the CKA task bank (data/questions.csv) from the study notes built by build_notes.py (Killercoda scenarios
with solutions) plus any task banks in sources/tasks/*.md (format: "## <title>" / task text / ```solution``` block).
CKA is a hands-on exam, so a "question" is a task: options and correct are empty, explanation = reference solution.
Usage: python -I build_csv.py
"""
import csv, glob, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
NOTES = os.path.join(HERE, "data", "study_notes.csv")
OUT = os.path.join(HERE, "data", "questions.csv")
rows, seen = [], set()


def add(domain, task, solution, source):
    key = re.sub(r"\W+", " ", task[:120].lower()).strip()
    if key in seen or len(task) < 40 or not solution.strip():
        return
    seen.add(key)
    rows.append({"id": f"CKA-{len(rows) + 1:04d}", "domain": domain, "question": task.strip(), "options": "",
                 "correct": "", "explanation": f"Reference solution ({source}):\n{solution.strip()}"})


# 1. Scenarios from the course folder (notes with solution commands)
if os.path.exists(NOTES):
    for n in csv.DictReader(open(NOTES, encoding="utf-8")):
        if not n["labels"].strip() or n["pages"].startswith("notes/"):   # docs/concept pages are study cards, not tasks
            continue
        task = re.sub(r"(?i)^(cka:?|cka question:?)\s*", "", n["title"]).strip() + "\n\n" + n["bullets"]
        task = re.sub(r"\n(Solution|Answer)\b.*", "", task, flags=re.S)       # keep the solution out of the task text
        add(n["section"], task[:2200], n["labels"][:2500], n["pages"].split("/")[0])
else:
    print("no study_notes.csv: run build_notes.py first")

# 1b. Multiple-choice rows (sources/online/*, generated MCQs): options filled, so the portal serves them in MCQ mode
def add_mcq(domain, question, opts, answer, explanation, source):
    key = re.sub(r"\W+", " ", question[:120].lower()).strip()
    if key in seen or len(question) < 20 or not answer:
        return
    seen.add(key)
    rows.append({"id": f"CKA-{len(rows) + 1:04d}", "domain": domain, "question": question.strip(),
                 "options": "\n".join(f"{L}. {opts[L]}" for L in "ABCDEFGH" if opts.get(L)),
                 "correct": answer, "explanation": f"{explanation.strip()}\n(source: {source})"})

sys.path.insert(0, HERE)          # python -I drops the script dir from sys.path
import online_parsers, online_parsers2
online_parsers.parse_all(os.path.join(HERE, "sources", "online"), add_mcq)
online_parsers2.parse_all(os.path.join(HERE, "sources", "online"), add_mcq)   # second research batch, 11 more sources

# 2. Extra task banks: sources/tasks/*.md, "## <title>" then task text then a fenced solution block
for f in sorted(glob.glob(os.path.join(HERE, "sources", "tasks", "*.md"))):
    t = open(f, encoding="utf-8").read()
    dom = (re.search(r"^domain:\s*(.*)$", t, re.M) or [None, "Workloads & Scheduling"])[1].strip()
    for m in re.finditer(r"^## (.*?)\n(.*?)```(?:\w+)?\n(.*?)```", t, re.M | re.S):
        add(dom, m.group(1).strip() + "\n\n" + m.group(2).strip(), m.group(3), os.path.basename(f))

with open(OUT, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["id", "domain", "question", "options", "correct", "explanation"])
    w.writeheader(); w.writerows(rows)
from collections import Counter
print(Counter(r["domain"] for r in rows))
print("tasks:", sum(1 for r in rows if not r["options"]), "mcq:", sum(1 for r in rows if r["options"]), "->", OUT)
