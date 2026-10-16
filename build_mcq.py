"""Write one multiple-choice question per hands-on task with Claude Code (claude -p), so the CKA bank has an MCQ phase to
learn the answer types before the typed-command phase. Resumable: tasks already in sources/mcq/generated.jsonl are skipped.
Usage: python build_mcq.py [--model haiku] [--workers 3] [--limit N]
Reads the task rows of data/questions.csv (options empty, explanation = reference solution)."""
import csv, hashlib, json, os, shutil, subprocess, sys, tempfile, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "sources" / "mcq" / "generated.jsonl"
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


def key_of(task):
    return hashlib.md5(task[:300].encode()).hexdigest()[:12]


def ask(task, solution):
    exe = shutil.which("claude")
    work = Path(tempfile.gettempdir()) / "cka-mcq-work"; work.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != "TELEGRAM_BOT_TOKEN"}; env["DISABLE_AUTOUPDATER"] = "1"
    cmd = [exe, "-p", "--output-format", "json", "--no-session-persistence", "--permission-mode", "dontAsk", "--model", MODEL,
           "--tools", "", "--max-turns", "4", "--append-system-prompt", SYSTEM, "--json-schema", SCHEMA]
    prompt = ("You are NOT asked to perform this task and you have no cluster. Your only job is to WRITE A QUIZ QUESTION about it.\n\n"
              f"HANDS-ON TASK (source material):\n{task}\n\nREFERENCE SOLUTION (source material):\n{solution}\n\n"
              'Reply with ONLY this JSON object and nothing else: {"question": "...", "options": {"A": "...", "B": "...", "C": "...", "D": "..."}, '
              '"correct": "A|B|C|D", "explanation": "..."}')
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=work, env=env, timeout=240)
    if p.returncode:
        raise RuntimeError(p.stderr[:200])
    data = json.loads(p.stdout)
    out = data.get("structured_output")
    if not isinstance(out, dict) or "options" not in out:
        text = str(data.get("result") or ""); out = json.loads(text[text.find("{"):text.rfind("}") + 1])
    opts = out.get("options") or {}
    if not (isinstance(opts, dict) and all(opts.get(k) for k in "ABCD") and out.get("correct") in list("ABCD") and out.get("question")):
        raise RuntimeError("invalid quiz JSON: " + json.dumps(out)[:120])
    return out, data.get("total_cost_usd")


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
