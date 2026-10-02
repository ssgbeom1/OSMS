# Reported reference results

The primary study uses four Python packages, 17 distinct represented inputs and five charges above one, giving 85 conditions. Its `h=1` roster is separate. The normalization and LP/residual-greedy batches are retrospective diagnostics on the same inputs.

| Files | Content |
|---|---|
| `tables/S1_h1_times.csv` | All 17 inputs at `h=1` |
| `tables/S2_candidate_reduction.csv` | Candidate and model sizes for all 85 conditions |
| `tables/S3_paired_times.csv` | Eligible and ineligible primary comparisons |
| `tables/S4_high_h_phases.csv` | Phase times and memory by condition |
| `tables/S5_lp_comparison.csv` | Continuous LP bounds and fractionality |
| `tables/S6_residual_ablation.csv` | Residual-greedy costs and quality-matched timing |
| `tables/S7_all_conditions.csv` | Planned roster, aliases, statuses and sessions |
| `tables/S8_normalization_conditions.csv` | All 85 normalization-ablation conditions |
| `tables/S9_normalization_runs.csv` | All 1,530 normalization-ablation runs |
| `tables/S10_normalization_pairs.csv` | Within-batch paired comparisons |
| `tables/S11_normalization_failures.csv` | Failure stages and reasons |
| `tables/S12_normalization_source_summary.csv` | Source-specific ablation summaries |
| `tables/S13_residual_quality_time_conditions.csv` | Full and residual cost gaps and timing for all 170 residual-greedy method-condition pairs |
| `tables/S14_residual_quality_time_by_charge.csv` | Charge-specific and pooled summaries of the 168 completed pairs |
| `primary/all_slots.csv` | All 5,184 planned primary slots, including 1,512 aliases not executed |
| `primary/quality.csv` | Primary quality comparisons |
| `primary/completion.csv` | Completion for charges above one |
| `primary/incomplete_conditions.csv` | Conditions without optimal completion |
| `primary/maximal_sharing_gap_by_charge.csv` | Matched-input cost gaps by charge |
| `primary/timing_by_source.csv` | Source-specific primary timing |
| `diagnostics/runs.csv` | All 935 LP/residual-greedy diagnostic slots |
| `diagnostics/root_solver_statistics.csv` | Reported root-node solver statistics |
| `normalization/paired_summary.csv` | Aggregate normalization-ablation comparisons |

The primary study has 3,672 executed slots. It completed 64/85 conditions for the global MILP and 84/85 for the preprocessed global MILP. The separate normalization batch completed 65, 80 and 84 conditions for global, join-restricted and preprocessed MILP, respectively. Do not combine the batches' runtime observations.

A condition is complete only if all six repetitions return within the relevant limits, pass representation checks and meet solver optimality. Primary timing comparisons additionally require matched sessions and equal costs. The 6.019 median speedup uses 63 eligible primary conditions. Conditions within a source are dependent.

Times are seconds unless a column says otherwise. RSS is sampled, not an instantaneous peak. MILP bounds and gaps are floating-point solver quantities. Exact cost columns use integers or rational strings. Empty fields indicate unavailable values. A last observed phase identifies where the supervisor last sampled a run; it does not establish the causal source of a failure.

These are the reported reference results. Historical raw-record locations and hashes are omitted because the corresponding records are not included. Scientific values, statuses and row order are preserved. New executions produce their own records; `summarize_run.py` checks and summarizes them, and `reproduce.py analyze --records ...` analyzes a completed set of all three rosters.

Tables S13–S14 can be regenerated from `diagnostics/runs.csv` using `python -B analysis/summarize_greedy.py --out generated/reported_residual_tables` from the package root. This reuses the existing diagnostic batch. Its full-roster timing summaries differ from S6, whose timing ratios retain only equal-quality pairs. In S13, completion requires all three exact and three greedy runs to return valid representations; the exact runs must have matching solver-optimal costs. Fixed offsets and residual-model signatures must agree before gaps are calculated.
