# Charged subtree sharing

Research code, fixed inputs and reported results for optimizing acyclic, parameter-free subtree definitions. Syntax nodes and references cost one; each definition adds a rational charge `h`.

| Study inputs | Executable runs | Reported tables |
|:---|:---|:---|
| 17 distinct inputs from 4 Python packages | 6,137 across three schedules | 12 supplementary tables |

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
```

`verify` checks package hashes; the tests compare small solver outputs with exact oracles and check schedule membership. Reported tables are supplied as comparison targets.

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

The primary schedule has 5,184 slots: 3,672 executions and 1,512 unexecuted aliases. Diagnostics add 935 executions and normalization adds 1,530. Suites run sequentially with their corresponding implementations. Individual timeouts remain in the results. Use a new output directory for each independent run.

Allow substantial runtime and at least 60 GB of additional disk space for a full run. Avoid concurrent heavy work during timing. Per-input limits are in [Protocol](PROTOCOL.md). Each invocation receives a session identifier; comparisons across resumed sessions follow the analysis eligibility rules.

`summarize_run.py` supports both partial and complete rosters. It checks returned representations and exact costs, reports statuses, and compares available optima with the supplied results. The full `analyze` command requires all three rosters. Its detailed tables additionally require the successful forest and structural-profile returns used in those calculations; the full schedule attempts these runs but a resource limit can prevent a return. If analysis stops, inspect `runs.csv` from the run summary for unsuccessful `Forest` or `LP-on` rows and retain those failures. New times and completion rates depend on the host.

## Inspect the reported results

```sh
python -B summarize.py
```

`results/` contains the reported tables and summaries for comparison. Past execution logs and returned representations are not bundled. Fresh runs write their own records under the chosen `generated/` directory. Old raw-record path columns are omitted from reference tables; costs, timings, statuses and row order are retained.

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

Feasibility and representation cost are checked exactly. MILP optimality uses solver status under the stated tolerances. The forest method is exact under its model assumptions. Third-party licenses are included with the source snapshots; a license for the research code has not yet been selected.
