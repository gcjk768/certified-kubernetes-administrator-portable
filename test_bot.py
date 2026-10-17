"""Smallest check that fails if the CKA task bank or bot logic breaks: python test_bot.py"""
import os, tempfile
from datetime import datetime
os.environ["DATA_DIR"] = os.environ.get("DATA_DIR", "data")
import bot

assert len(bot.QUESTIONS) >= 100
tasks = [q for q in bot.QUESTIONS.values() if not q["letters"]]
mcqs = [q for q in bot.QUESTIONS.values() if q["letters"]]
assert len(tasks) >= 100 and len(mcqs) >= 50, (len(tasks), len(mcqs))   # both phases present
assert all(q["explanation"].startswith("Reference solution") for q in tasks)
assert all(q["answer"] <= set(q["letters"]) for q in mcqs)
assert all(len(bot.question_text(q)) < 4096 for q in bot.QUESTIONS.values())
assert {q["domain"] for q in bot.QUESTIONS.values()} <= {"Troubleshooting", "Cluster Architecture, Installation & Configuration",
                                                          "Services & Networking", "Workloads & Scheduling", "Storage"}

state = {"ok": {}, "bad": {}}
seen = {bot.pick_question(state)["id"] for _ in range(50)}
assert len(seen) > 10
state["ok"] = {i: 1 for i in bot.QUESTIONS}
state["bad"] = {"CKA-0010": 2}
assert bot.pick_question(state)["id"] == "CKA-0010"          # missed tasks come back first
assert "PROGRESS" in bot.stats_text(state)
bot.STATE_PATH = bot.Path(tempfile.mkdtemp()) / "state.json"
bot.save_state(state); assert bot.load_state() == state

now = datetime(2026, 10, 18, 22, 0)
many = [i for k, i in enumerate(bot.QUESTIONS) if k % 3]
big = {"ok": {i: 1 for i in many}, "bad": {}, "log": [{"t": "2026-10-18T09:00", "id": i, "ok": True, "first": True} for i in many]}
m = bot.metrics(big, now)
assert m["score"] == 1000 and bot.verdict(m).startswith("🟢") and bot.PASS == 660
assert bot.NOTES and all(n["labels"] or n["bullets"] for n in bot.NOTES.values())
print("ok: cka bank", len(bot.QUESTIONS), "tasks,", len(bot.NOTES), "notes")

# invented icon classes are swapped for the closest real one under the same name (no ImportError at render time)
fixed = bot.fix_icon_imports("from diagrams.aws.network import VPC, VPNGateway as GW, GwlbEndpoint\nfrom diagrams import Diagram")
assert fixed.startswith("from diagrams.aws.network import VPC, ") and " as GW" in fixed and " as GwlbEndpoint" in fixed, fixed
exec(fixed)
print("ok icon imports")


# Telegram Mermaid gets the portal's colours; the portal switches the tutor to Mermaid; the report names what to study next
t = bot.themed("flowchart LR\n  A([Start]) --> B{Ok?}\n  B --> C[(Store)]")
assert t.startswith("%%{init") and "class A term" in t and "class B dec" in t and "class C db" in t, t
assert bot.themed("sequenceDiagram\n  A->>B: hi") == "sequenceDiagram\n  A->>B: hi"
bot.PREFER_MERMAID = True
r = bot.diagram_rule('DIAGRAM: kind must be "diagrams" (x, y). Quote it.\n')
assert r.startswith('DIAGRAM: kind must be "mermaid"') and "Quote it." in r, r
assert bot.diagram_rule("").startswith('DIAGRAM: kind must be "mermaid"')
bot.PREFER_MERMAID = False
assert bot.diagram_rule("keep") == "keep"
nxt = bot.study_next({"by_dom": {"A": [1, 4], "B": [3, 3], "C": [0, 0]}})
assert "Study next" in nxt and "A · 25%" in nxt and "C · not started" in nxt and "B ·" not in nxt, nxt
print("ok diagrams + study next")
