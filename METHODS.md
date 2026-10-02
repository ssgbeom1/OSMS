# Method reference

[Overview](README.md) · [Methods](METHODS.md) · [Protocol](PROTOCOL.md) · [Results](results/README.md)

Choose a method for an individual input, or use the frozen schedules in the [protocol](PROTOCOL.md) to reproduce the study.

## Available methods

| Single-case option | Recorded identifier | Meaning |
|---|---|---|
| `forest` | Forest | Exact selection for `0 <= h <= 1` |
| `global-milp` | A0 | All nonconstant naming candidates |
| `join-restricted-milp` | A0-U | Naming restricted to shared subterms, without subsequent fixing |
| `preprocessed-milp` | A1 | Safe preprocessing followed by one residual MILP |
| `component-milp` | A2 | Identical preprocessing followed by sequential component MILPs |
| `maximal-sharing` | All-U | Name all shared subterms |
| `greedy-add`, `greedy-prune` | Greedy-add, Greedy-prune | Primary whole-state greedy implementations |
| `residual-add`, `residual-prune` | RG-add, RG-prune | Greedy after the same safe preprocessing |
| `lp-presolve-on`, `lp-presolve-off` | LP-on, LP-off | Continuous residual LP diagnostics |
| `no-sharing` | No-sharing | Store the input without definitions |

Raw schemas retain these identifiers for traceability; supplementary tables use descriptive names.

## Single-input example

```sh
python -B run.py solve --case examples/small.json --method preprocessed-milp --h 3/2 --out generated/example.json
```

## New inputs

To convert a Python package directory:

```sh
python -B run.py prepare --source path/to/package --representation compact --target-nodes 100000 --out generated/input.json
python -B run.py solve --case generated/input.json --method preprocessed-milp --h 3/2 --out generated/input-result.json
```

A hand-written case needs a string `id`, a `ranks` map from symbols to child counts, and a list of `roots`. Each tree is `[symbol, [children]]`; child order matters and duplicate roots represent one tree. For example:

```json
{"id":"small", "ranks":{"a":0,"f":1}, "roots":[["f",[["a",[]]]]]}
```

---

[Overview](README.md) · [Methods](METHODS.md) · [Protocol](PROTOCOL.md) · [Results](results/README.md)
