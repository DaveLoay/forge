---
status: draft            # set to approved only by the user's /forge:approve brief
approved: null           # YYYY-MM-DD, stamped by /forge:approve brief
---

# Brief: <short title>

## Goal

<One paragraph: what will exist when this is done, and for whom.>

## Non-goals

- <Something a reasonable person might expect that is deliberately out of scope.>

## Hypothesis

<The bet this work tests. What do we expect to be true, and what would show it is false?>

## Acceptance criteria

Each criterion must be testable: name the check that decides it, with a threshold where one applies.

| id | criterion | how it is tested |
|---|---|---|
| AC-1 | <observable outcome> | <test, dataset, metric and threshold> |

## Constraints

- <Language, libraries, hardware, data access, time budget, licences, cost (default: zero paid services).>

## Environment

Planning builds this environment; probes, tests and the build all run in it.

- Package manager or container: <pixi / conda / docker / venv>
- Python: <version>
- System tools: <ffmpeg, sox, ... or none>
- Hardware: <CPU only, or GPU + CUDA version>
- Data: <where the data lives, or how it gets into the project>

## Research sub-questions

One line each. `/forge:investigate` runs one search per sub-question.

| id | sub-question |
|---|---|
| SQ-1 | <what we need to learn from the literature> |

## Seed references

DOIs, arXiv IDs, URLs or PDF file names the user already knows about.

- <10.xxxx/... or 2401.01234 or paper.pdf>

## Open questions

- <Anything still undecided. An approved brief may keep open questions only if none of them blocks planning.>
