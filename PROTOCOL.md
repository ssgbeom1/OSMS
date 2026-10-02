# Experimental protocol

[Overview](README.md) · [Methods](METHODS.md) · [Protocol](PROTOCOL.md) · [Results](results/README.md)

The input rules, execution budgets and comparison criteria used by the distributed schedules.

[Inputs](#inputs) · [Primary schedule](#primary-schedule) · [Resources](#resources-and-timing) · [Diagnostics](#retrospective-diagnostics) · [Reporting](#checks-and-reporting)

## Inputs

| Source snapshot | Version |
|:---|:---|
| matplotlib | 3.10.5 |
| pydantic | 2.13.4 |
| aiohttp | 3.14.1 |
| jsonschema | 4.26.0 |

Compact and fielded ASTs are evaluated at requested sizes 100,000, 1,000,000 and 10,000,000 nodes. Whole files are included before checking the size target. Undersized packages remain; identical prefix root sets are aliases. There are 17 distinct inputs among 24 planned prefixes. Requested size differs from actual size. Conditions within a package are dependent.

Files are traversed in sorted relative POSIX-path order, excluding hidden paths and `__pycache__`, including tests. The adapter checks AST roundtrips, rejects rank collisions and paths escaping the source root, and deduplicates roots by exact equality. The representation does not preserve source formatting or comments as a byte archive.

Syntax and reference nodes cost one; definitions add `h`. Charges are `1`, `11/10`, `5/4`, `3/2`, `2` and `32`. Exact rational abstract cost measures quality; serialized bytes are not the objective.

## Primary schedule

At `h=1`, the methods are unshared representation, maximal sharing, greedy addition, greedy pruning, forest selection and global MILP. At `h>1`, they are global MILP, preprocessed global MILP, preprocessed component MILP, maximal sharing, greedy addition and greedy pruning. Each condition has six repeats. `protocol/primary.json` gives all slots, including aliases: target size, charge, representation and source; method rotation depends on condition and repeat.

The distributed reference results combine the completed study batches. New executions follow the full fixed roster without the original aggregate cutoff. A timing pair requires six valid optimal returns per method, equal cost and one execution session; interrupted attempts are excluded.

## Resources and timing

Common modules load before preparation. Solver options and tolerances are in each frozen `engine.py`.

| Resource or phase | Limit / setting |
|:---|---:|
| Preparation | 120 s |
| Method, including reconstruction | 30 s |
| Expression checking | 60 s |
| Entire process | 220 s |
| Process-tree RSS | 4,096 MiB |
| RSS sampling interval | 50 ms |
| CPU affinity / solver threads | 1 / 1 |

Primary time includes method-specific preprocessing, model construction, all solver calls, interpretation and reconstruction. Expression checking uses the separate checking budget. Component solves share the remaining method budget. Search reserves `min(5 seconds, 10% of the method budget)` for reconstruction and bookkeeping. The recorded failure phase is the last observed phase, not an exact instruction. Nested telemetry intervals may overlap.

## Retrospective diagnostics

`protocol/diagnostics.json` gives 935 runs on the same 85 conditions with `h>1`: LP with and without presolve, then three rotated repeats of preprocessed global MILP and both residual greedy methods. LP values are numerical. Greedy timing comparisons require convergence, three valid repeats and equal reference cost.

`protocol/normalization.json` gives 85 conditions × three methods × six repeats = 1,530 runs. Global, shared-subterm-restricted and preprocessed global MILP use one builder within the batch. All six method permutations are balanced. Comparisons are within this diagnostic batch. Both diagnostic rosters use exposed inputs, not new holdouts.

## Checks and reporting

Valid returns must pass expansion and exact rational cost checks. Optimal MILP completion additionally requires `optimal_numerical`; forest uses `THEOREM_EXACT`. Greedy convergence is `FEASIBLE`; limited incumbents have a separate status. Failures and aliases remain in tables.

For reference times A and comparison times B, improvement requires median(A)/median(B) > 1.05 and max(B) < min(A). Regression requires a ratio below 1/1.05 and max(A) < min(B); other comparisons are unresolved. Comparisons are descriptive, with dependent conditions grouped by source. Fresh measurements are reported separately.

---

[Overview](README.md) · [Methods](METHODS.md) · [Protocol](PROTOCOL.md) · [Results](results/README.md)
