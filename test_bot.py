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
