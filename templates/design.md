---
round: 0                 # last council round that changed this file
status: draft            # draft | final (set when the stop rule triggers)
---

# Design: <short title>

For the human gate. Keep it under ~200 lines: this is the solution, not the code.

## Goal

<Restate the brief's goal in one paragraph, and list the acceptance criteria it must meet (AC-ids).>

## Key decisions

Each decision cites its evidence: an `index.md` row or a reference key.

| id | decision | why | evidence |
|---|---|---|---|
| D-1 | <choice made> | <reason, and the main alternative rejected> | <[[key]] or index row> |

## Solution

```
<ASCII diagram of the data flow / components. Boxes and arrows, no code.>
```

<Short prose walking through the diagram.>

## Risks

| risk | likelihood | impact | mitigation or early signal |
|---|---|---|---|
| <what could go wrong> | low/med/high | low/med/high | <how we notice and what we do> |

## Out of scope

- <Carried from the brief's non-goals, plus anything the council cut.>
