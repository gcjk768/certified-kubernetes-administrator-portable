"""Parsers for CKA multiple-choice sources in sources/online/ (research agents, 2026-10-16) and for the MCQs generated from
the hands-on tasks by build_mcq.py (sources/mcq/generated.jsonl). Each parser calls add_mcq(domain, question, opts{L: text},
answer "B" or "B,D", explanation, source). Missing files are skipped. Personal use: nothing here is redistributed."""
import glob, hashlib, html, json, os, re

LET = "ABCDEFGH"
DOMAIN_WORDS = [("Troubleshooting", r"troubleshoot|debug|pending|crashloop|notready|logs|events|fail"),
                ("Cluster Architecture, Installation & Configuration", r"kubeadm|etcd|rbac|role|helm|kustomize|crd|certificate|upgrade|control plane|api server|install"),
                ("Services & Networking", r"service|ingress|gateway|networkpolicy|network policy|dns|coredns|nodeport|clusterip|endpoint|cni"),
                ("Storage", r"persistentvolume|pvc|pv\b|storageclass|storage class|volume"),
                ("Workloads & Scheduling", r"pod|deployment|replica|daemonset|statefulset|job|cron|taint|toler|affinity|configmap|secret|probe|hpa|resource|quota|limit")]


def guess_domain(text, default="Workloads & Scheduling"):
    t = text.lower(); best, score = default, 0
    for name, pat in DOMAIN_WORDS:
        n = len(re.findall(pat, t))
        if n > score:
            best, score = name, n
    return best


def _clean(s):
    return html.unescape(re.sub(r"<[^>]+>", " ", s)).replace("**", "").strip()


def parse_all(ON, add_mcq):
    # kube-dojo cumulative quizzes (CC BY-SA 4.0): "### Q1: Title" or "### 1. Title", options "A) ..." or "1. ...", <details><summary>Answer</summary> text
    for f in sorted(glob.glob(os.path.join(ON, "kubedojo-cka-part*.md"))):
        t = open(f, encoding="utf-8").read()
        quiz = t.split("## Quiz", 1)[1] if "## Quiz" in t else ""
        quiz = re.split(r"^## (?:Hands-On|Sources)", quiz, flags=re.M)[0]
        part = re.search(r"part(\d)-([a-z-]+)-cumulative", f)
        default = {"0": "Cluster Architecture, Installation & Configuration", "1": "Cluster Architecture, Installation & Configuration", "2": "Workloads & Scheduling",
                   "3": "Services & Networking", "4": "Storage", "5": "Troubleshooting"}.get(part.group(1) if part else "", "Workloads & Scheduling")
        for m in re.finditer(r"^### (?:Q(\d+):|(\d+)\.)\s*(.*?)\n(.*?)(?=^### (?:Q\d+:|\d+\.)|\Z)", quiz, re.M | re.S):
            body = m.group(4)
            qpart, _, apart = body.partition("<details>")
            opts = {}
            for L, text in re.findall(r"^([A-D])\)\s+(.*)$", qpart, re.M):
                opts[L] = _clean(text)
            if not opts:
                for n, text in re.findall(r"^(\d)\.\s+(.*)$", qpart, re.M):
                    opts[LET[int(n) - 1]] = _clean(text)
            stem = re.split(r"^(?:[A-D]\)|\d\.)\s", qpart, flags=re.M)[0].strip()
            expl = _clean(re.sub(r"<summary>.*?</summary>", "", apart.split("</details>")[0], flags=re.S))
            am = re.search(r"\b([A-D])\b(?: and ([A-D]))? (?:is|are) (?:correct|right)", expl)
            ans = ",".join(sorted(x for x in am.groups() if x)) if am else ""
            if not ans:                                           # numbered options: "Option 2 is correct"
                nm = re.search(r"Option (\d)(?: and (\d))? (?:is|are) correct", expl)
                ans = ",".join(sorted(LET[int(x) - 1] for x in nm.groups() if x)) if nm else ""
            if opts and ans and stem:
                add_mcq(default, stem, opts, ans, expl[:1500], "kube-dojo CKA cumulative quizzes (CC BY-SA 4.0)")

    # costudy.net sample (site terms): "### <Domain>" / stem line / "1.   text" options / "**Answer:** C — ..." / rationale paragraph
    f = os.path.join(ON, "costudy-cka-sample-24-mcq.md")
    if os.path.exists(f):
        t = open(f, encoding="utf-8").read()
        section = ""
        for chunk in re.split(r"^(### .*)$", t, flags=re.M)[1:]:
            if chunk.startswith("### "):
                section = chunk[4:].strip(); continue
            blocks = re.split(r"\n(?=\S[^\n]*\n\n1\.\s)", "\n" + chunk)
            for b in blocks:
                m = re.search(r"^(.*?)\n\n((?:\d\.\s+.*\n?)+)\n\*\*Answer:\*\*\s*([A-E](?:,\s*[A-E])*)\s*[—-]?\s*(.*?)\n\n(.*?)(?=\n\n\S|\Z)", b.strip() + "\n\n", re.S)
                if not m:
                    continue
                stem, optblock, ans, _, why = m.groups()
                opts = {LET[int(n) - 1]: _clean(x) for n, x in re.findall(r"^(\d)\.\s+(.*)$", optblock, re.M)}
                if opts and len(stem) > 15:
                    add_mcq(guess_domain(section + " " + stem, "Cluster Architecture, Installation & Configuration"), _clean(stem), opts,
                            ans.replace(" ", ""), _clean(why)[:1500], "costudy.net CKA sample (site terms)")

    # open-exam-prep.com rendered sample (no licence): "N stem" / "A.text" ... / "Explanation: ..." (answer named inside the explanation)
    f = os.path.join(ON, "open-exam-prep-cka-sample-10-mcq.md")
    if os.path.exists(f):
        t = open(f, encoding="utf-8").read()
        for m in re.finditer(r"^(\d+) (.+?)\n\n((?:[A-D]\..*\n\n)+)Explanation:\s*(.*?)(?=\n\n\d+ |\Z)", t, re.M | re.S):
            stem, optblock, expl = m.group(2), m.group(3), _clean(m.group(4))
            opts = {L: _clean(x) for L, x in re.findall(r"^([A-D])\.(.*)$", optblock, re.M)}
            am = re.search(r"\b([A-D])\b (?:is|was) (?:the )?correct", expl) or re.search(r"correct answer is ([A-D])\b", expl, re.I)
            if not am:   # fall back: the option whose text is quoted first in the explanation
                hits = [(expl.lower().find(x.lower()[:25]), L) for L, x in opts.items() if x.lower()[:25] in expl.lower()]
                am = min(hits)[1] if hits else None
            ans = am if isinstance(am, str) else (am.group(1) if am else "")
            if opts and ans:
                add_mcq(guess_domain(stem), _clean(stem), opts, ans, expl[:1500], "open-exam-prep.com CKA sample")

    # open-exam-prep raw page with the full bank (if the sister-page pattern holds): Next.js payload "initialQuestions"
    f = os.path.join(ON, "oep_cka_raw.html")
    if os.path.exists(f):
        h = open(f, encoding="utf-8", errors="replace").read()
        chunks = re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', h)
        try:
            txt = json.loads('"' + "".join(chunks) + '"')
            i = txt.find('"initialQuestions":')
            qs = json.JSONDecoder().raw_decode(txt, i + len('"initialQuestions":'))[0] if i >= 0 else []
        except Exception as exc:
            print("oep raw: payload not parsed:", exc); qs = []
        for q in qs:
            ca = q.get("correctAnswer")
            ans = ",".join(LET[k] for k in (ca if isinstance(ca, list) else [ca])) if ca is not None else ""
            opts = {LET[k]: o for k, o in enumerate(q.get("options", []))}
            if opts and ans:
                add_mcq(guess_domain(q.get("category", "") + " " + q["question"]), q["question"], opts, ans,
                        q.get("explanation", "") + (" Exam tip: " + q["examTip"] if q.get("examTip") else ""), "open-exam-prep.com CKA practice")

    # MCQs generated from the hands-on tasks (build_mcq.py): one JSON object per line
    f = os.path.join(os.path.dirname(ON), "mcq", "generated.jsonl")
    if os.path.exists(f):
        for line in open(f, encoding="utf-8"):
            try:
                q = json.loads(line)
            except Exception:
                continue
            opts = {L: q["options"].get(L, "") for L in "ABCD" if q.get("options", {}).get(L)}
            if len(opts) >= 3 and q.get("correct") and q.get("question"):
                add_mcq(q.get("domain", "Workloads & Scheduling"), q["question"], opts, q["correct"], q.get("explanation", ""),
                        "MCQ written by Claude from a hands-on scenario")
