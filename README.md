# Optimal Syntactic Macro Selection

Research code, fixed inputs and reported results for optimizing acyclic, parameter-free subtree definitions. Syntax nodes and references cost one; each definition adds a rational charge `h`.

| Study inputs | Executable runs | Reported tables |
|:---|:---|:---|
| 17 distinct inputs from 4 Python packages | 6,137 across three schedules | 14 repository result tables |

[Methods](METHODS.md) · [Protocol](PROTOCOL.md) · [Results](results/README.md)

## Setup

Use Python 3.12 on Windows or Linux with CPU-affinity support. The tested environment is Windows 11 with Python 3.12.14. Run commands from the extracted package directory.

```sh
python -m venv .venv
```

Activate `.venv\Scripts\activate` on Windows or `source .venv/bin/activate` on Linux, then:

```sh
python -m pip install -r requirements.txt
python -B reproduce.py verify
python -B tests/verify.py
python -B tests/test_schedules.py
python -B tests/test_residual_summary.py
```

`verify` checks package hashes; the tests compare small solver outputs with exact oracles and check schedule membership. Expect `PASS` from package, solver and schedule checks, and `OK` from the residual-summary tests. Resolve any failure before starting the full study. Reported tables are supplied as comparison targets.

## Run one example

```sh
python -B run.py solve --case examples/small.json --method preprocessed-milp --h 3/2 --out generated/example.json
```

The output reports cost, feasibility, solver status, timings and memory. [Methods](METHODS.md) lists the other methods and the input format.

## Short scheduler check

```sh
python -B reproduce.py run --suite normalization --max-slots 3 --out generated/smoke
python -B summarize_run.py --records generated/smoke/records --out generated/smoke_summary
```

This executes three runs on a study input. `PARTIAL` means the requested prefix finished. To finish the full 1,530-run normalization suite in this directory, use `--resume` without `--max-slots`:

```sh
python -B reproduce.py run --suite normalization --resume --out generated/smoke
```

An interrupted worker without a committed supervision record requires a new output directory. Existing attempts are preserved.

## Run the full study

```sh
python -B reproduce.py run --suite all --out generated/full_run
python -B summarize_run.py --records generated/full_run/records --out generated/full_summary
python -B reproduce.py analyze --records generated/full_run/records --out generated/full_analysis
```

The primary schedule has 5,184 slots: 3,672 executions and 1,512 unexecuted aliases. Aliases are target-size requests that produced the same represented input as another request. Diagnostics add 935 executions and normalization adds 1,530. Suites run sequentially with their corresponding implementations. Individual timeouts remain in the results. Use a new output directory for each independent run; existing output directories are rejected unless the scheduler is explicitly resumed.

Allow substantial runtime and at least 60 GB of additional disk space for a full run. Avoid concurrent heavy work during timing. Per-input limits are in [Protocol](PROTOCOL.md). Each invocation receives a session identifier; comparisons across resumed sessions follow the analysis eligibility rules.

`summarize_run.py` supports both partial and complete rosters. It checks returned representations and exact costs, reports statuses, and compares available optima with the supplied results. The full `analyze` command requires all three rosters. Its detailed tables additionally require the successful forest and structural-profile returns used in those calculations; the full schedule attempts these runs but a resource limit can prevent a return. If analysis stops, inspect `runs.csv` from the run summary for unsuccessful `Forest` or `LP-on` rows and retain those failures. New times and completion rates depend on the host.

## Inspect the reported results

```sh
python -B summarize.py
```

This prints a JSON summary without modifying the reference results.

`results/` contains the reported tables and summaries for comparison, including the 935 per-run diagnostic CSV records in `results/diagnostics/runs.csv`. Historical solver logs and returned representations are not bundled. The CSV records support recalculating the reported summaries; fresh runs generate logs and representations for checking new executions. Old raw-record path columns are omitted from reference tables; costs, timings, statuses and row order are retained.

Recreate Tables S13–S14 from the 935 preserved diagnostic records, without running an optimizer:

```sh
python -B analysis/summarize_greedy.py --out generated/reported_residual_tables
```

Compare these outputs with `results/tables/S13_residual_quality_time_conditions.csv` and `results/tables/S14_residual_quality_time_by_charge.csv`. Use a new output directory for each invocation. The full `reproduce.py analyze` command also generates S13–S14 from fresh diagnostic records. Completion rates and timings in a fresh run can differ from the reported results.

Use Git or download the complete repository ZIP so that hidden files are included. The `.gitattributes` file preserves source bytes; do not convert line endings in fixed inputs or regenerate their reference hashes to bypass a failed check.

To plot freshly analyzed results:

```sh
python -m pip install -r requirements-figures.txt
python -B plot_results.py --analysis generated/full_analysis --out generated/figures
```

## Rebuild inputs

```sh
python -B reproduce.py rebuild-inputs --out generated/rebuilt_inputs
```

This converts the bundled source snapshots and checks all 17 distinct inputs and seven aliases. Source snapshots are read as text, not imported. Their comments and licenses are preserved because they form part of the fixed inputs.

## Files

| Folder | Purpose |
|:---|:---|
| `code/`, `runtime/` | Optimizers, adapters, checking and supervised execution |
| `analysis/` | Analysis of newly generated experiment records |
| `data/` | Prepared inputs, original source snapshots and hashes |
| `protocol/` | Fixed schedules and resource settings |
| `results/` | Reported reference tables and summaries |
| `examples/`, `tests/` | Example input, exact-oracle and schedule checks |
| `metadata/environment.json` | Original study environment |

The checker verifies returned representations and their costs using exact arithmetic. MILP optimality uses solver status under the stated tolerances. The forest method is exact under its model assumptions. Third-party licenses are included with the source snapshots; a license for the research code has not yet been selected.


## Finite encoding checks and result tables

| Manuscript item | Repository location |
|:---|:---|
| Article: Correctness checks and reproduction (finite encoding checks) | [Bounded encoding checks](analysis/bounded_encodings/README.md) and [scope and results](analysis/bounded_encodings/notes.md) |
| Repository result table S7 | [Primary execution schedule](results/tables/S7_all_conditions.csv) |

Run the finite encoding checks with Python 3.12: `python -B analysis/bounded_encodings/reproduce_checks.py generated/bounded_checks`. The destination must not exist. This verifies archived finite-check results; it does not rerun the large-scale timing experiments.
