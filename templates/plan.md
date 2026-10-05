---
round: 0
status: draft            # draft | final
---

# Plan: <short title>

The builder's contract. MF-CODE implements one slice at a time and may not change `tests/`.

## File tree

```
src/
  <module>.py        # <one-line purpose>
tests/
  test_<module>.py   # <which slices it checks>
```

## Interfaces

Full signatures with types, and what each function guarantees.

```python
def name(arg: Type, ...) -> ReturnType:
    """<contract: inputs, outputs, errors raised, invariants>"""
```

## Data paths

| data | location | format | produced by | consumed by |
|---|---|---|---|---|
| <dataset or artefact> | <path> | <format, shape, dtype> | <step> | <step> |

## Test specs

Unit tests check the interfaces. Conceptual tests check that the method works at all:
known-answer synthetic data, a shuffled-label control that must score at chance,
invariants, and overfitting a tiny dataset.

| id | kind | what it checks | pass condition | covers |
|---|---|---|---|---|
| T-1 | unit / known-answer / shuffled-label / invariant / tiny-overfit | <behaviour> | <exact condition or threshold> | AC-1 |

## Slices

Each slice is vertical (it runs end to end) and ends at a test checkpoint.

### Slice 1: <name>

- Build: <files and functions>
- Checkpoint: `<test command>` passes T-1, T-2
- Done when: <observable result>

## To-do

- [ ] Slice 1: <name>
