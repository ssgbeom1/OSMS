# Permuted unordered sharing fixture

This additional named fixture is separate from the exhaustive five-node universe and the five ordered examples. It checks profitable sharing when two occurrences of an unordered subtree have distinct children presented in opposite orders.

The input is `{r1(q(g(a),k(b))), r2(q(k(b),g(a)))}`. The symbol `q` is unordered; all other constructors are ordered. There are 12 expanded nodes and two distinct output roots. Naming the shared five-node `q` subtree gives stored syntax cost 9 and one definition; the predeclared expected minimum is `min(12, 9+h)`.

The unchanged `targeted.py` enumerator permits all nonconstant subterms as expansions, duplicate definitions, position-specific inlining or references, and output-root references. Only reachable definitions are retained. Stored syntax cost is bounded by 12 and the definition count by floor((12-2)/2)=5, which retains every possible optimum for nonnegative charges. Generated presentations, including reorderings and renamed duplicates, are counted separately.

Run counting first, without charge optimization. Freeze its record and the four script/protocol hashes before running comparisons. Both phases have a 120-second limit and a combined source/target count cap of 2,000,000. If counting exceeds either limit, report incomplete and do not shrink the fixture after observing optimization values.

Compare arbitrary source, arbitrary translated, canonical all-subterm and canonical shared-subterm minima at `0, 1/2, 1, 3/2, 2, 32`. Compare the forest formula only at the first three charges. Check forward expansion commutation, reverse expansion recovery, and unchanged syntax cost for every enumerated representation. This fixture targets translation and normalization, not forest adjacency or hardness reductions.

On a mismatch, preserve the witness, calculate it by hand, compare the alternative generation path, and then identify a checker or mathematical error before changing any claim. These finite checks share helper functions and do not constitute a general proof or external review.

From the repository root:

```sh
python -B analysis/bounded_encodings/permuted_fixture.py count permuted_count.json
python -B analysis/bounded_encodings/permuted_fixture.py run permuted_run.json
```
