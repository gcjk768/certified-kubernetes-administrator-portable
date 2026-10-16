"""Second batch of CKA multiple-choice parsers for sources/online/ (research agents, 2026-10-16). Same contract as
online_parsers.py: parse_all(ON, add_mcq) calls add_mcq(domain, question, opts{L: text}, answer "B"/"B,D", explanation, source).
Each source parser is isolated: a failure prints one WARN line and the rest continue. Personal use: nothing is redistributed."""
import glob, json, os, re

from online_parsers import guess_domain, _clean

LET = "ABCDEFGHIJ"
T, A, N, S, W = ("Troubleshooting", "Cluster Architecture, Installation & Configuration", "Services & Networking", "Storage",
                 "Workloads & Scheduling")
_DOM = {"ARCH": A, "WORK": W, "NET": N, "STO": S, "TRBL": T}
SKIPPED = []   # (source, reason, stem[:60]) for the __main__ report


def _md(s):   # markdown/plain text: drop bold + backticks, collapse whitespace (keeps literal <ns>/<pod> placeholders)
    return re.sub(r"\s+", " ", (s or "").replace("**", "").replace("`", "")).strip()


def _ht(s):   # HTML: strip tags/entities, collapse whitespace
    return re.sub(r"\s+", " ", _clean(s or "")).strip()


def _domain(label, text):
    """Map a labelled domain/category onto the five CKA names; fall back to guess_domain on the text."""
    l = (label or "").lower()
    for key, name in (("troubleshoot", T), ("architecture", A), ("install", A), ("network", N), ("service", N), ("storage", S),
                      ("workload", W), ("schedul", W)):
        if key in l:
            return name
    return guess_domain(text)


def _emit(add, domain, stem, opts, ans, expl, source):
    stem = (stem or "").strip()
    opts = {L: v for L, v in opts.items() if v}
    ans = ",".join(x for x in ans.split(",") if x) if isinstance(ans, str) else ",".join(ans)
    reason = ("<2 options" if len(opts) < 2 else "no answer" if not ans or any(a not in opts for a in ans.split(","))
              else "stem <15 chars" if len(stem) < 15 else "")
    if reason:
        SKIPPED.append((source, reason, stem[:60])); return
    add(domain, stem, opts, ans, (expl or "")[:1500], source)


# 1. examcert.app: {"questions":[{questionText html, options[{text,isCorrect}], explanation "<!-- DOMAIN: x -->html"}]}
def p_examcert(ON, add):
    src = "examcert.app free CKA practice test"
    for q in json.load(open(os.path.join(ON, "examcert_cka_free_practice_test_100.json"), encoding="utf-8"))["questions"]:
        dm = re.search(r"<!--\s*DOMAIN:\s*(.*?)\s*(?:\(~\d+%\))?\s*-->", q.get("explanation", ""))
        stem = _ht(q["questionText"])
        opts = {LET[i]: _ht(o["text"]) for i, o in enumerate(q["options"])}
        ans = ",".join(LET[i] for i, o in enumerate(q["options"]) if o.get("isCorrect"))
        expl = _ht(re.sub(r"<!--.*?-->", "", q.get("explanation", ""), flags=re.S))
        _emit(add, _domain(dm.group(1) if dm else " ".join(q.get("tags", [])), stem), stem, opts, ans, expl, src)


# 2. certland.net: <article>; <h2><span>Q1.</span> stem</h2>; <li class="...bg-green-500/10..."> = correct; <p class="mt-1 text-sm text-subtle">expl
def p_certland(ON, add):
    src = "certland.net CKA samples"
    h = open(os.path.join(ON, "certland_cka_practice_raw.html"), encoding="utf-8", errors="replace").read()
    for art in re.findall(r"<article.*?</article>", h, re.S):
        m = re.search(r"<h2[^>]*>(.*?)</h2>", art, re.S)
        stem = _ht(re.sub(r"<span[^>]*>Q\d+\.</span>", "", m.group(1))) if m else ""
        opts, ans = {}, []
        for i, (cls, body) in enumerate(re.findall(r'<li class="([^"]*)">(.*?)</li>', art, re.S)):
            spans = re.findall(r"<span[^>]*>(.*?)</span>", body, re.S)
            opts[LET[i]] = _ht(spans[-1] if spans else body)
            if "bg-green-500/10" in cls:
                ans.append(LET[i])
        em = re.search(r'<p class="mt-1 text-sm text-subtle">(.*?)</p>', art, re.S)
        _emit(add, guess_domain(stem), stem, opts, ans, _ht(em.group(1)) if em else "", src)


# 3. techpracticeexams.com blog: <h2 id="question-N">; <p><strong>stem</strong></p>; <li>A) ..; <p><strong>Answer: B — ..</strong></p>; expl <p>s
def p_techpractice(ON, add):
    src = "techpracticeexams.com blog"
    h = open(os.path.join(ON, "techpracticeexams_blog_cka_practice_questions_1_raw.html"), encoding="utf-8", errors="replace").read()
    parts = re.split(r'<h2 id="question-\d+">', h)[1:]
    for part in parts:
        part = part.split("<h2", 1)[0]
        sm = re.search(r"<p><strong>(.*?)</strong></p>", part, re.S)
        opts = {L: _ht(x) for L, x in re.findall(r"<li>([A-F])\)\s*(.*?)</li>", part, re.S)}
        am = re.search(r"<p><strong>Answer:\s*([A-F](?:\s*,\s*[A-F])*)\b(.*?)</strong></p>(.*?)(?:&lt;/details&gt;|\Z)", part, re.S)
        if not sm or not am:
            _emit(add, W, _ht(sm.group(1)) if sm else "", opts, "", "", src); continue
        expl = _ht(am.group(2).strip(" —-") + ". " + am.group(3))
        stem = _ht(sm.group(1))
        _emit(add, guess_domain(stem), stem, opts, re.sub(r"\s", "", am.group(1)), expl, src)


# 4. ZiyadAli00/training-ops: "## QN [DOM] [EXAMx]" / stem / "- a) .." / "Answer: a. explanation"
def p_ziyadali(ON, add):
    src = "ZiyadAli00/training-ops quiz bank (GitHub, no licence, AI-generated)"
    t = open(os.path.join(ON, "gh_ziyadali00_training_ops_cka_quiz_bank.md"), encoding="utf-8").read()
    for m in re.finditer(r"^## Q\d+ \[([A-Z]+)\][^\n]*\n([^\n]+)\n((?:- [a-f]\) [^\n]*\n)+)Answer:\s*([a-f](?:\s*,\s*[a-f])*)\.\s*(.*?)(?=\n## Q|\Z)",
                         t, re.M | re.S):
        dom, stem, optblock, ans, expl = m.groups()
        opts = {L.upper(): _md(x) for L, x in re.findall(r"^- ([a-f])\) (.*)$", optblock, re.M)}
        _emit(add, _DOM.get(dom, guess_domain(stem)), _md(stem), opts, re.sub(r"\s", "", ans).upper(), _md(expl), src)


# 5. yassine-eluharani/QuizzApp: [{question, choices[], correct_answer_indices[0-based], explanation_html}]
def p_yassine(ON, add):
    src = "yassine-eluharani/QuizzApp (GitHub)"
    for q in json.load(open(os.path.join(ON, "gh_yassine_quizzapp_cka_ckad_quiz1.json"), encoding="utf-8")):
        stem = re.sub(r"^Note:.*?\[SCENARIO\]\s*", "", q["question"], count=1, flags=re.S)   # drop the "Note: real exam is hands-on" boilerplate
        opts = {LET[i]: _md(c) for i, c in enumerate(q["choices"])}
        ans = ",".join(LET[i] for i in sorted(q["correct_answer_indices"]))
        _emit(add, guess_domain(stem), _md(stem), opts, ans, _ht(q.get("explanation_html", "")), src)


# 6. slauger/kubestronaut: [{category, question, answers[], correct int|[ints] (0-based: id 3 correct=3 -> "etcdctl snapshot save"), explanation}]
def p_slauger(ON, add):
    src = "slauger/kubestronaut CKA quiz (GitHub)"
    for q in json.load(open(os.path.join(ON, "gh_slauger_kubestronaut_questions_cka.json"), encoding="utf-8")):
        c = q["correct"]; c = c if isinstance(c, list) else [c]
        opts = {LET[i]: _md(a) for i, a in enumerate(q["answers"])}
        _emit(add, _domain(q.get("category"), q["question"]), _md(q["question"]), opts, ",".join(LET[i] for i in sorted(c)), _md(q.get("explanation")), src)


# 7. vinayydv3695: "N. stem" / "   A) .." (one line lacks its letter: letters assigned by position) / "**Correct Answer(s): B**" / "**Explanation:** .."
def p_vinay(ON, add):
    src = "vinayydv3695 Kubernetes MCQ (GitHub)"
    for f in ("gh_vinayydv3695_k8s_mcq_single_correct.md", "gh_vinayydv3695_k8s_mcq_multiple_correct.md"):
        t = open(os.path.join(ON, f), encoding="utf-8").read()
        for block in re.split(r"^(?=\d+\. )", t, flags=re.M)[1:]:
            sm = re.match(r"\d+\.\s+(.*)", block)
            optlines = re.findall(r"^[ \t]+[A-F]?\)\s*(.*)$", block, re.M)
            opts = {LET[i]: _md(x) for i, x in enumerate(optlines)}
            am = re.search(r"\*\*Correct Answers?:\s*([A-F](?:\s*,\s*[A-F])*)\*\*", block)
            em = re.search(r"\*\*Explanation:\*\*\s*(.*)", block)
            stem = _md(sm.group(1)) if sm else ""
            _emit(add, guess_domain(stem + " " + " ".join(opts.values())), stem, opts, re.sub(r"\s", "", am.group(1)) if am else "", _md(em.group(1)) if em else "", src)


# 8. nurudeen19/quizsphere: [{question, options[4], answer[0-based ints], explanation}]
def p_quizsphere(ON, add):
    src = "nurudeen19/quizsphere Kubernetes (GitHub)"
    for q in json.load(open(os.path.join(ON, "gh_nurudeen19_quizsphere_kubernetes.json"), encoding="utf-8")):
        opts = {LET[i]: _md(o) for i, o in enumerate(q["options"])}
        a = q["answer"]; a = a if isinstance(a, list) else [a]
        _emit(add, guess_domain(q["question"] + " " + " ".join(opts.values())), _md(q["question"]), opts, ",".join(LET[i] for i in sorted(a)), _md(q.get("explanation")), src)


# 9. rajdyp/rdocs: Hugo pages "{{< quiz >}} {json} {{< /quiz >}}"; keep mcq / multiple-select / true-false / code-output only
_RAJ_DEFAULT = {"networking": N, "services": N, "ingress": N, "storage": S, "observability": T, "pods": W, "pod-lifecycle": W,
                "workload-controllers": W, "autoscaling": W, "introduction": W}


def p_rajdyp(ON, add):
    src = "rajdyp/rdocs Kubernetes quizzes (GitHub)"
    for f in sorted(glob.glob(os.path.join(ON, "gh_rajdyp_rdocs_k8s_quiz", "*.md"))):
        topic = re.sub(r"^\d+-", "", os.path.basename(f)[:-3])
        default = _RAJ_DEFAULT.get(topic, A)
        t = open(f, encoding="utf-8").read()
        for m in re.finditer(r"\{\{<\s*quiz[^>]*>\}\}(.*?)\{\{<\s*/quiz\s*>\}\}", t, re.S):
            for q in json.loads(m.group(1)).get("questions", []):
                typ, stem = q.get("type"), _md(q.get("question", ""))
                if typ in ("mcq", "code-output"):
                    opts = {LET[i]: _md(o) for i, o in enumerate(q.get("options", []))}; ans = LET[q["answer"]]
                    if typ == "code-output" and q.get("code"):
                        stem = stem + "\n" + q["code"]
                elif typ == "multiple-select":
                    opts = {LET[i]: _md(o) for i, o in enumerate(q.get("options", []))}; ans = ",".join(LET[i] for i in sorted(q["answers"]))
                elif typ == "true-false":
                    opts = {"A": "True", "B": "False"}; ans = "A" if q["answer"] else "B"
                else:
                    continue   # fill-blank, code-completion, flashcard, drag-drop, ordered-recall: no options
                _emit(add, guess_domain(topic.replace("-", " ") + " " + stem, default), stem, opts, ans, _md(q.get("explanation")), src)


# 10. PlatformRelay/Kubernetes-Workshop (0BSD): {"questions":[{id "S03-Q-..", section, prompt, options[{id,text,rationale}], answer "<id>", explanation}]}
def p_platformrelay(ON, add):
    src = "PlatformRelay/Kubernetes-Workshop quiz (GitHub, 0BSD)"
    for q in json.load(open(os.path.join(ON, "gh_platformrelay_k8s_workshop_quiz.json"), encoding="utf-8"))["questions"]:
        if q.get("section") == "S00":
            continue
        ids = [o["id"] for o in q["options"]]
        opts = {LET[i]: _md(o["text"]) for i, o in enumerate(q["options"])}
        ans = ",".join(LET[ids.index(a)] for a in (q["answer"] if isinstance(q["answer"], list) else [q["answer"]]) if a in ids)
        expl = _md(q.get("explanation", "")) + " " + " ".join(f"{LET[i]}: {_md(o['rationale'])}" for i, o in enumerate(q["options"]) if o.get("rationale"))
        _emit(add, guess_domain(q["prompt"] + " " + " ".join(opts.values())), _md(q["prompt"]), opts, ans, expl.strip(), src)


# 11. The-DevOps-Daily (MIT): {"questions":[{description, situation, codeExample, options[], correctAnswer 0-based, explanation}]}
def p_devopsdaily(ON, add):
    src = "The-DevOps-Daily quizzes (GitHub, MIT)"
    for f, default in (("gh_devopsdaily_kubernetes_quiz.json", W), ("gh_devopsdaily_helm_charts_quiz.json", A), ("gh_devopsdaily_kubernetes_operators_quiz.json", A)):
        for q in json.load(open(os.path.join(ON, f), encoding="utf-8"))["questions"]:
            stem = " ".join(_md(q.get(k)) for k in ("description", "situation") if q.get(k))
            if q.get("codeExample"):
                stem += "\n" + q["codeExample"].strip()
            opts = {LET[i]: o.strip() for i, o in enumerate(q["options"])}
            c = q["correctAnswer"]; c = c if isinstance(c, list) else [c]
            _emit(add, guess_domain(stem, default), stem, opts, ",".join(LET[i] for i in sorted(c)), _md(q.get("explanation")), src)


PARSERS = [p_examcert, p_certland, p_techpractice, p_ziyadali, p_yassine, p_slauger, p_vinay, p_quizsphere, p_rajdyp, p_platformrelay, p_devopsdaily]


def parse_all(ON, add_mcq):
    for p in PARSERS:
        try:
            p(ON, add_mcq)
        except Exception as exc:
            print(f"WARN {p.__name__}: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    from collections import Counter
    items = []
    parse_all(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources", "online"), lambda *a: items.append(a))
    counts = Counter(i[5] for i in items)
    for s, n in counts.items():
        print(f"{n:4d}  {s}")
    print("TOTAL", len(items))
    for d, q, o, a, e, s in items:
        assert len(o) >= 2, (s, q[:60])
        assert all(L in o for L in a.split(",")), (s, q[:60], a, list(o))
        assert d in (T, A, N, S, W), (s, d)
    seen = set()
    for d, q, o, a, e, s in items:
        if s not in seen:
            seen.add(s); print(f"  [{s}] {d} | {q[:80]!r} | {a}")
    print("SKIPPED", len(SKIPPED), Counter((s, r) for s, r, _ in SKIPPED))
    for s, r, st in SKIPPED:
        print("   -", s, "|", r, "|", st)
