# Certified Kubernetes Administrator — Portable

A self-hosted study bot for the **CKA** exam, built for someone who is still learning bash and kubectl. The bank has two phases. First **multiple choice** (about 1,800 questions from fifteen open sources plus one question written from every hands-on task) to learn the kind of answer the exam wants. Then, once the MCQ bank has been seen, **scenario tasks** like the real exam: you read a scenario, type the commands or YAML you would run, and Claude grades them against the reference solution, explains what was missing, and prints the command guideline flag by flag. Study cards do the same for every scenario in your course folder. Served on the web by [Exam Portal](https://github.com/gcjk768/exam-portal) (quiz, timed 17-task mock exam, playbook of "which command for which problem").

> Unofficial and independent. Not affiliated with the Linux Foundation or CNCF. The tasks are practice scenarios from open-source Killercoda repositories, not exam content.

## The exam (checked 2026-10-16)

About 15 to 20 performance-based tasks on live clusters, 120 minutes, pass 66%, USD 445, two attempts, two killer.sh simulator sessions included. Domains: Troubleshooting 30%, Cluster Architecture, Installation and Configuration 25%, Services and Networking 20%, Workloads and Scheduling 15%, Storage 10%.

## What you get

| | |
|---|---|
| **Task bank** | `build_notes.py` reads a folder of Killercoda scenario repos (index.json + step/solution markdown) and plain solution folders into `data/study_notes.csv`; `build_csv.py` turns every scenario that has a solution into a task (`data/questions.csv`, options empty, explanation = reference solution). Extra task banks go in `sources/tasks/*.md`. |
| **Grading** | On the web: type your commands, *Check with Claude* (score 0 to 100, feedback, command guideline, reference solution) or *Reveal solution* and self-mark for free. Score 70 or more counts as done; missed tasks come back first. |
| **Study cards** | Claude rewrites a scenario as a card: what the task asks, the exact commands, what every flag does in plain words, the examiner's trap, plus a diagram of the Kubernetes objects with official icons. |
| **Mock exam** | 17 tasks in 120 minutes at the real pace (or 8 or 3), every task graded by Claude at submit, pass at 660 on the 1000 scale. |
| **Telegram** | Same bot code as the other exams (`bot.py`); needs a bot token. Tasks arrive as text; grading happens on the web. |

## Build

```sh
python build_notes.py "<course folder>/Killercoda"   # scenarios -> data/study_notes.csv (also sources/notes/*.md concept pages)
python -I build_csv.py                               # notes with solutions -> data/questions.csv
python test_bot.py
```

Nothing from the course folder is committed (`sources/`, `data/`, `*.pdf` are gitignored).

## Files

`bot.py` the bot · `build_notes.py` scenarios and docs pages to notes · `build_csv.py` notes to tasks · `test_bot.py` self-check · `Dockerfile`, `compose.yaml`, `run.ps1`, `bot.env.example`.

## License

MIT for the code. Scenario text belongs to its repositories (mostly MIT); see each repo.
