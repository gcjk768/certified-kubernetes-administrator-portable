# Changelog

- 2026-10-16 — first version: task-based bank (304 Killercoda scenarios with solutions from the course folder), 370 study notes, CKA prompts (commands explained flag by flag, k8s icons), served by exam-portal with Claude grading, command playbook and a 17-task mock exam.
- 2026-10-17 — multiple-choice phase added (1,815 MCQ from 15 sources + generated), 852 tasks; the portal serves MCQ first, then scenario tasks.
- 2026-11-14 — generated questions are checked by a blind solver (`python build_mcq.py --verify`): a second model call answers from the stem and options only; questions where it disagrees or finds more than one defensible answer stay out of the bank and are listed in `sources/mcq/review.md`.
- 2026-11-14 — second opinion on flagged questions (`python build_mcq.py --verify --recheck --model sonnet`): only the flagged ones are solved again by a stronger model; agreeing with the key clears the flag. 60 flagged → 23, bank 3,158.
