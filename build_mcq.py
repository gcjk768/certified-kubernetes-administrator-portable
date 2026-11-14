"""Write one multiple-choice question per hands-on task with Claude Code (claude -p), so the CKA bank has an MCQ phase to
learn the answer types before the typed-command phase. Resumable: tasks already in sources/mcq/generated.jsonl are skipped.
Usage: python build_mcq.py [--model haiku] [--workers 3] [--limit N]
       python build_mcq.py --verify [--model haiku] [--workers 3] [--limit N]
Reads the task rows of data/questions.csv (options empty, explanation = reference solution).
--verify is the blind solver: a second claude call per MCQ sees only the stem and the options and must reach the same key.
Verdicts go to sources/mcq/verified.jsonl (resumable), questions held back to sources/mcq/review.md; build_csv.py reads both."""
import csv, hashlib, json, os, random, re, shutil, subprocess, sys, tempfile, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "sources" / "mcq" / "generated.jsonl"
VERIFIED, REVIEW = OUT.with_name("verified.jsonl"), OUT.with_name("review.md")
MODEL = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else os.environ.get("CLAUDE_MODEL", "haiku")
WORKERS = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 3
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 10_000
SYSTEM = """You write multiple-choice practice questions for the Certified Kubernetes Administrator (CKA) exam from hands-on
tasks. The student is still learning bash and kubectl. Given a task and its reference solution, write ONE question that tests
the key decision of the task: which command, flag, resource kind, YAML field or approach completes it. The stem must restate
the scenario briefly (names, namespaces, numbers kept). Give exactly four options A to D: one correct (taken from the reference
solution) and three plausible wrong ones (wrong flag, wrong resource, wrong namespace, a tempting but incomplete step). The
explanation (under 120 words, plain text) explains why the correct option works, what each wrong option would do instead,
and quotes the exact command or YAML the student should remember. Return JSON only."""
SCHEMA = json.dumps({"type": "object", "required": ["question", "options", "correct", "explanation"], "additionalProperties": False,
                     "properties": {"question": {"type": "string"},
                                    "options": {"type": "object", "required": ["A", "B", "C", "D"], "additionalProperties": False,
                                                "properties": {k: {"type": "string"} for k in "ABCD"}},
                                    "correct": {"type": "string", "enum": list("ABCD")}, "explanation": {"type": "string"}}})
SOLVER = """You are sitting a multiple-choice practice exam for the Certified Kubernetes Administrator (CKA). You see one
question and four options, nothing else. Work it out from your own knowledge and pick the single best option. Set "ambiguous"
to true when more than one option is defensible as correct, when none is, or when the question cannot be answered as written.
"reason" is one line (under 30 words) that names the deciding fact, not the option letter. Return JSON only."""
SOLVER_SCHEMA = json.dumps({"type": "object", "required": ["answer", "ambiguous", "reason"], "additionalProperties": False,
                            "properties": {"answer": {"type": "string", "enum": list("ABCD")}, "ambiguous": {"type": "boolean"},
                                           "reason": {"type": "string"}}})


def key_of(task):
    return hashlib.md5(task[:300].encode()).hexdigest()[:12]


def claude(system, schema, prompt, need="options"):
    """One claude -p call (no tools) that returns (JSON object with the key `need`, cost). Shared by the generator and the solver."""
    exe = shutil.which("claude")
    work = Path(tempfile.gettempdir()) / "cka-mcq-work"; work.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != "TELEGRAM_BOT_TOKEN"}; env["DISABLE_AUTOUPDATER"] = "1"
    # Lean call: our own system prompt instead of Claude Code's, no settings, plugins, MCP servers or skills. With the
    # defaults one solver call carried ~84k tokens of context per turn on this PC (USD 0.057 a question, measured
    # 2026-11-14); like this it is ~1.2k tokens.
    cmd = [exe, "-p", "--output-format", "json", "--no-session-persistence", "--model", MODEL, "--max-turns", "4",
           "--system-prompt", system, "--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands",
           "--tools", "", "--json-schema", schema]
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=work, env=env, timeout=240)
    if p.returncode:
        raise RuntimeError(p.stderr[:200])
    data = json.loads(p.stdout)
    out = data.get("structured_output")
    if not isinstance(out, dict) or need not in out:
        text = str(data.get("result") or ""); out = json.loads(text[text.find("{"):text.rfind("}") + 1])
    return out, data.get("total_cost_usd")


def ask(task, solution):
    prompt = ("You are NOT asked to perform this task and you have no cluster. Your only job is to WRITE A QUIZ QUESTION about it.\n\n"
              f"HANDS-ON TASK (source material):\n{task}\n\nREFERENCE SOLUTION (source material):\n{solution}\n\n"
              'Reply with ONLY this JSON object and nothing else: {"question": "...", "options": {"A": "...", "B": "...", "C": "...", "D": "..."}, '
              '"correct": "A|B|C|D", "explanation": "..."}')
    out, cost = claude(SYSTEM, SCHEMA, prompt)
    opts = out.get("options") or {}
    if not (isinstance(opts, dict) and all(opts.get(k) for k in "ABCD") and out.get("correct") in list("ABCD") and out.get("question")):
        raise RuntimeError("invalid quiz JSON: " + json.dumps(out)[:120])
    return out, cost


def qkey(q):
    """Content hash of a generated MCQ: an edited stem, option or key gets a new hash, so it is checked again."""
    return hashlib.md5(json.dumps([q["question"], q["options"], q["correct"]], sort_keys=True).encode()).hexdigest()[:12]


def verified_keys():
    """qkeys the blind solver agreed with (last line per qkey wins); None when the pass has never run. Used by online_parsers.py."""
    if not VERIFIED.exists():
        return None
    status = {}
    for line in open(VERIFIED, encoding="utf-8"):
        try:
            r = json.loads(line); status[r["qkey"]] = r["status"]
        except Exception:
            pass
    return {k for k, s in status.items() if s == "verified"}


def solve(q):
    """Blind second pass: the solver sees the stem and the four options only (no key, no explanation, no source task). The
    options are shown in a shuffled order (seeded by qkey) so it cannot lean on the generator's habit of putting the answer
    in A; the reply is mapped back to the letter in generated.jsonl. Options that name other letters or "above" keep their order."""
    k = qkey(q); order = list("ABCD")
    if not re.search(r"\b(above|below|[Oo]ptions? [A-D]|[A-D] (and|or) [A-D])\b", " ".join(q["options"].values())):
        random.Random(k).shuffle(order)
    shown = dict(zip("ABCD", order))                      # letter the solver sees -> letter in generated.jsonl
    prompt = (q["question"] + "\n\n" + "\n".join(f"{s}. {q['options'][o]}" for s, o in shown.items()) +
              '\n\nReply with ONLY this JSON object: {"answer": "A|B|C|D", "ambiguous": true|false, "reason": "one line"}')
    rec = {"qkey": k, "key": q.get("key"), "status": "unverified", "generator": q["correct"], "solver": "", "ambiguous": False, "reason": ""}
    cost = 0
    for _ in range(2):                                    # unusable reply: one retry, then it stays "unverified" (never a pass)
        try:
            out, c = claude(SOLVER, SOLVER_SCHEMA, prompt, "answer"); cost += c or 0
            if out.get("answer") not in shown or not isinstance(out.get("ambiguous"), bool):
                raise RuntimeError("invalid solver JSON: " + json.dumps(out)[:120])
            solver = shown[out["answer"]]
            rec.update(status="verified" if solver == q["correct"] and not out["ambiguous"] else "flagged", solver=solver,
                       ambiguous=out["ambiguous"], reason=" ".join(str(out.get("reason") or "").split())[:300])
            break
        except Exception as exc:
            rec["reason"] = "solver reply unusable: " + " ".join(str(exc).split())[:120]
    return rec, cost


def verify():
    """python build_mcq.py --verify: solve every MCQ in generated.jsonl that has no verdict yet (resumable: verified and
    flagged ones are skipped, unverified ones are tried again), then rewrite review.md. generated.jsonl is never changed."""
    qs = {}
    for line in open(OUT, encoding="utf-8"):
        try:
            q = json.loads(line); [q["options"][L] for L in "ABCD"]; qs[qkey(q)] = q
        except Exception:
            pass
    status = {}
    if VERIFIED.exists():
        for line in open(VERIFIED, encoding="utf-8"):
            try:
                r = json.loads(line); status[r["qkey"]] = r
            except Exception:
                pass
    # --recheck: a second opinion on the flagged ones only, normally from a stronger model
    # (python build_mcq.py --verify --recheck --model sonnet). Agreement with the key clears the flag.
    recheck = "--recheck" in sys.argv
    todo = [q for k, q in qs.items() if (status.get(k, {}).get("status") == "flagged" if recheck else
                                         status.get(k, {}).get("status") not in ("verified", "flagged"))]
    print(f"{len(qs)} MCQs, {len(qs) - len(todo)} already checked, {len(todo[:LIMIT])} to solve blind with {MODEL} x{WORKERS}")
    todo = todo[:LIMIT]
    lock = threading.Lock(); cost = [0.0]; n = [0]

    def worker(chunk):
        for q in chunk:
            rec, c = solve(q)
            if recheck:
                rec["checked_by"] = MODEL
                rec["first_reason"] = status[rec["qkey"]].get("reason", "")
                if rec["status"] == "unverified":            # the second solver gave nothing usable: the flag stands
                    rec = {**status[rec["qkey"]], "recheck_failed": MODEL}
            with lock:
                with VERIFIED.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                status[rec["qkey"]] = rec; cost[0] += c; n[0] += 1
                print(f"[{n[0]}/{len(todo)}] {rec['key']} {rec['status']} ${cost[0]:.2f}", flush=True)

    threads = [threading.Thread(target=worker, args=(todo[i::WORKERS],)) for i in range(WORKERS)]
    [t.start() for t in threads]; [t.join() for t in threads]
    held = [(q, status[k]) for k, q in qs.items() if status.get(k, {}).get("status") in ("flagged", "unverified")]
    md = [f"# MCQ review · {len(held)} generated questions kept out of the bank", "",
          "Written by `python build_mcq.py --verify`, rewritten on every run. Every question below is still in `generated.jsonl`"
          " (nothing is deleted); `build_csv.py` leaves it out of the bank until it is verified.", "",
          "- **Fix:** edit its line in `generated.jsonl` (search for the key), then run `--verify` again: an edited question is checked again.",
          "- **Drop:** leave it as it is, or delete its line.",
          '- **Keep as it is:** set `"status": "verified"` on its line in `verified.jsonl` (search for the qkey).', ""]
    for q, r in held:
        why = "unverified" if r["status"] == "unverified" else "flagged: ambiguous" if r.get("ambiguous") else "flagged: solver disagrees"
        md += [f"## {r['key']} · {why}", "", f"qkey `{r['qkey']}` · generator key **{r['generator']}** · solver answer **{r['solver'] or '-'}**", "",
               q["question"], "", *[f"- {L}. {q['options'][L]}" for L in "ABCD"], "", f"Solver's reason{' (' + r['checked_by'] + ')' if r.get('checked_by') else ''}: {r['reason']}",
               *([f"First solver's reason: {r['first_reason']}"] if r.get("first_reason") else []), ""]
    REVIEW.write_text("\n".join(md), encoding="utf-8")
    count = lambda s: sum(1 for k in qs if status.get(k, {}).get("status") == s)
    print(f"done: {n[0]} solved, total ${cost[0]:.2f}, verified {count('verified')}, flagged {count('flagged')}, "
          f"unverified {count('unverified')}, not checked yet {sum(1 for k in qs if k not in status)} -> {REVIEW}")


def generate():
    rows = [r for r in csv.DictReader(open(HERE / "data" / "questions.csv", encoding="utf-8")) if not r["options"].strip()]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if OUT.exists():
        for line in open(OUT, encoding="utf-8"):
            try:
                done.add(json.loads(line)["key"])
            except Exception:
                pass
    todo = [r for r in rows if key_of(r["question"]) not in done][:LIMIT]
    print(f"{len(rows)} tasks, {len(done)} done, {len(todo)} to write with {MODEL} x{WORKERS}")
    lock = threading.Lock(); cost = [0.0]; n = [0]

    def worker(chunk):
        for r in chunk:
            try:
                out, c = ask(r["question"], r["explanation"].replace("Reference solution", "", 1))
                rec = {"key": key_of(r["question"]), "task_id": r["id"], "domain": r["domain"], **out}
                with lock:
                    with OUT.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    cost[0] += c or 0; n[0] += 1
                    print(f"[{n[0]}/{len(todo)}] {r['id']} ${cost[0]:.2f}", flush=True)
            except Exception as exc:
                print("FAILED", r["id"], str(exc)[:120], flush=True)
                time.sleep(5)

    threads = [threading.Thread(target=worker, args=(todo[i::WORKERS],)) for i in range(WORKERS)]
    [t.start() for t in threads]; [t.join() for t in threads]
    print(f"done: {n[0]} written, total ${cost[0]:.2f} -> {OUT}")
    print("next: python build_mcq.py --verify (blind solver; once it has run, build_csv.py takes only the questions it agreed with)")


if __name__ == "__main__":      # importable: test_build_mcq.py and the bank builder use the functions above
    verify() if "--verify" in sys.argv else generate()
