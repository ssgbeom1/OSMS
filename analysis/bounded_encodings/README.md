# Bounded encoding checks

Finite checks reported in the article subsection **Correctness checks and reproduction**. Python 3.12 and its standard library suffice. Run from the repository root:

```sh
python -B analysis/bounded_encodings/reproduce_checks.py generated/bounded_checks
```

The output directory must not exist. The command executes the small-universe check, independent input census, boundary fixtures, generator comparison, the nine- and ten-node fixtures, the five ordered examples, and the twelve-node permuted unordered fixture. It also repeats the targeted counts. All deterministic JSON fields, including minima, counts, statuses and recorded code hashes, must match the archived records; elapsed times are excluded. A failure stops the command and leaves its output and logs in place. Success produces `verification.json` with 17 passed record comparisons. This command does not rerun the large-scale timing experiments.

## Results and scope

| Check | Completed scope | Result |
|---|---|---|
| Small universe | 1,761 languages, at most five nodes; six charges | 10,566 charge comparisons; all optima equal unshared cost |
| Translation within small universe | 19,823 source/target encodings | No mapping or cost mismatch; 990 generated source encodings exercise distinct exchangeable children with references |
| Five ordered examples | 9,972 source/target encodings; 30 example–charge pairs | 23 pairs strictly improve unshared cost; all 15 eligible forest comparisons agree |
| Unordered nine-node and mixed ten-node fixtures | 420 encodings each; six charges each | Four strict-saving charges per fixture |
| Permuted unordered twelve-node fixture | 46 source and 19 target encodings; six charges | Minima 9, 9.5, 10, 10.5, 11, 12; five strict-saving charges |

The definition charge h takes values 0, 1/2, 1, 3/2, 2 and 32, in that order. Each pair is one input and one charge. Forest comparisons apply only to h=0, 1/2 and 1. A mapping check verifies expansion and stored cost through translation or reverse erasure. Encoding counts include repeated presentations and equal-expansion name permutations. The 990 qualifying encodings occur in 187 languages and are not independent inputs. The incomplete six-node preflight is retained as `count6.json` and is not counted as completed validation. The [Scope and results](notes.md) specify each scope and give the example-level minima.

Enumeration and canonical selection use different algorithms but share term, expansion and size helpers. These are internal finite implementation checks, not independent proof certification; hardness reductions are outside their scope.

## Files

| Files | Purpose |
|---|---|
| `check.py`, `PROTOCOL.md`, `count*.json`, `freeze.json`, `result001.json` | Original small universe, preflight and frozen execution |
| `census.py`, `census.json` | Alternative census of input languages |
| `fixtures.py`, `fixtures002.json`, `fixtures003.json` | Boundary checks and canonical source examples; latest record is 003 |
| `profitable_fixtures.py`, `profitable_scope.json`, `profitable_result.json` | Nine- and ten-node cases |
| `targeted.py`, `targeted_protocol.md`, `targeted_results/` | Five ordered examples, counts, frozen hashes, exact minima |
| `targeted_crosscheck.py` | Complete generated-set comparison and translation composition counts |
| `permuted_fixture.py`, `permuted_protocol.md`, `permuted_results/` | Twelve-node unordered case with opposite child orders |
| `reproduce_checks.py` | Execution and deterministic-record comparison |

The separate **repository result table S7**, `results/tables/S7_all_conditions.csv`, reports the primary execution roster. Finite encoding checks are stored here in `analysis/bounded_encodings/`.
