"""Blind-solver check of build_mcq.py with a fake claude (no real calls, temp files only): python test_build_mcq.py"""
import json, re, tempfile
from pathlib import Path
import build_mcq as b

tmp = Path(tempfile.mkdtemp())
b.OUT, b.VERIFIED, b.REVIEW = tmp / "generated.jsonl", tmp / "verified.jsonl", tmp / "review.md"


def mcq(name, correct="B"):
    return {"key": name, "question": f"Stem {name}?", "correct": correct, "explanation": f"SECRET-EXPLANATION {name}",
            "options": {L: f"{name} option {L}" for L in "ABCD"}}


def write(qs):
    b.OUT.write_text("".join(json.dumps(q) + "\n" for q in qs), encoding="utf-8")


calls = []


def fake(system, schema, prompt, need="options"):
    """Answers by option text, so the test fails if the builder maps the shuffled letter back wrongly."""
    name = re.search(r"Stem (\w+)\?", prompt).group(1); calls.append(name)
    assert system == b.SOLVER and need == "answer" and "SECRET" not in prompt and "correct" not in prompt, prompt
    letter = lambda orig: re.search(rf"^([A-D])\. {name} option {orig}$", prompt, re.M).group(1)
    if name == "agree":
        return {"answer": letter("B"), "ambiguous": False, "reason": "matches"}, 0.01
    if name == "disagree":
        return {"answer": letter("C"), "ambiguous": False, "reason": "C is the only\nvalid flag"}, 0.01
    if name == "ambiguous":
        return {"answer": letter("B"), "ambiguous": True, "reason": "B and D both work"}, 0.01
    if name == "retry" and calls.count("retry") == 1:
        return {"answer": "E"}, 0.01                                  # malformed once, good on the retry
    if name == "retry":
        return {"answer": letter("B"), "ambiguous": False, "reason": "ok"}, 0.01
    raise ValueError("not JSON at all")                               # "malformed": every time


b.claude = fake
names = ["agree", "disagree", "ambiguous", "malformed", "retry"]
write([mcq(n) for n in names])
assert b.verified_keys() is None                                      # pass never run
b.verify()
st = {r["key"]: r for r in map(json.loads, b.VERIFIED.read_text(encoding="utf-8").splitlines())}
assert {k: r["status"] for k, r in st.items()} == {"agree": "verified", "disagree": "flagged", "ambiguous": "flagged",
                                                   "malformed": "unverified", "retry": "verified"}, st
assert st["disagree"]["generator"] == "B" and st["disagree"]["solver"] == "C" and st["disagree"]["reason"] == "C is the only valid flag"
assert st["ambiguous"]["solver"] == "B" and st["ambiguous"]["ambiguous"] is True
assert calls.count("malformed") == 2 and calls.count("retry") == 2 and len(calls) == 7      # one retry, no more
assert b.verified_keys() == {b.qkey(mcq("agree")), b.qkey(mcq("retry"))}                    # only these reach the bank
review = b.REVIEW.read_text(encoding="utf-8")
assert "3 generated questions" in review and "disagree · flagged: solver disagrees" in review and "generator key **B** · solver answer **C**" in review
assert "ambiguous · flagged: ambiguous" in review and "malformed · unverified" in review and "Stem agree?" not in review
assert len(b.OUT.read_text(encoding="utf-8").splitlines()) == 5      # flagged questions stay in generated.jsonl
print("ok agree, disagree, ambiguous, malformed -> unverified, retry")

# resume: verified and flagged are skipped, only the unverified one is tried again; the review file comes out the same
calls.clear(); b.verify()
assert calls == ["malformed", "malformed"], calls
assert b.REVIEW.read_text(encoding="utf-8") == review
print("ok resume skips done")

# an edited question (one option reworded) has a new content hash: it is checked again, the others are still skipped
edited = mcq("agree"); edited["options"]["D"] = "agree option D reworded"
calls.clear(); write([edited] + [mcq(n) for n in names[1:]]); b.verify()
assert sorted(calls) == ["agree", "malformed", "malformed"], calls
assert b.verified_keys() == {b.qkey(mcq("agree")), b.qkey(edited), b.qkey(mcq("retry"))}
print("ok edited question is re-checked")

# --recheck: a second, stronger solver looks at the flagged questions only; agreeing with the key clears the flag
import sys


def stronger(system, schema, prompt, need="options"):
    name = re.search(r"Stem (\w+)\?", prompt).group(1); calls.append(name)
    letter = lambda orig: re.search(rf"^([A-D])\. {name} option {orig}$", prompt, re.M).group(1)
    if name == "disagree":
        return {"answer": letter("B"), "ambiguous": False, "reason": "B is right after all"}, 0.02
    return {"answer": letter("B"), "ambiguous": True, "reason": "still two answers"}, 0.02


b.claude = stronger
flagged_before = sorted(r["key"] for r in map(json.loads, b.VERIFIED.read_text(encoding="utf-8").splitlines()) if r["status"] == "flagged")
calls.clear(); sys.argv.append("--recheck"); b.verify(); sys.argv.remove("--recheck")
last = {}
for r in map(json.loads, b.VERIFIED.read_text(encoding="utf-8").splitlines()):
    last[r["key"]] = r
assert sorted(set(calls)) == sorted(set(flagged_before)) and "agree" not in calls, calls       # only the flagged ones are asked
assert last["disagree"]["status"] == "verified" and last["disagree"]["checked_by"] == b.MODEL
assert last["ambiguous"]["status"] == "flagged" and last["ambiguous"]["first_reason"] == "B and D both work"
assert "First solver's reason: B and D both work" in b.REVIEW.read_text(encoding="utf-8")
print("ok recheck clears a flag the stronger solver disagrees with, keeps the rest")
