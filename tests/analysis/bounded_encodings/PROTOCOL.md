# Bounded encoding checks

This internal check targets canonicalization, restriction to shared subterms,
the forest formula, and the source-syntax translation. It does not check the
hardness reductions or constitute an external mathematical proof review.

The finite signature has two constants `a,b`, ordered unary `u`, ordered binary
`v`, unordered unranked `q` of positive arity, and mixed-arity `m` of positive
arity with one ordered prefix position and an exchangeable suffix. Inputs are
finite sets of source-equality classes, including the empty set. The size bound
is the sum of expanded node counts of distinct roots.

Before computing any minima, count inputs and generated encodings at bounds
4, 5, and 6. Each preflight has a 120-second / 200,000 combined-encoding cap.
Choose the largest completely counted bound. Preserve incomplete count records.
The validation run has a 600-second limit. Do not decrease the frozen bound
after inspecting a comparison. A timed-out validation remains incomplete.

Reachable macro expansions are input subterms by nullary substitution. Allow
all nonconstant subterms, repeated names for the same expansion, and independent
reference/inline choices at every position, including output roots. A definition
retains its constructor root; dependencies go to strictly smaller subterms.
With N input nodes and r distinct roots, enumerate up to floor((N-r)/2) names.
Every better-than-unshared encoding is included because its stored cost is at
least r+2d for d definitions and h>=0. Unreachable definitions and duplicate
expanded output roots may be discarded independently of canonicalization:
deletion preserves the expanded language and reduces stored cost. Names are
numbered in nondecreasing expansion size and structural order; permutations of
equal-expansion names may still be counted more than once. Counts are generated
encodings, not isomorphism-class counts. No incumbent-cost pruning is used.

Compare exact rational minima for h=0,1/2,1,3/2,2,32. Compute arbitrary-encoding
minima independently for the source language and its ordered-ranked translation;
compare with all-subterm canonical minima, shared-subterm canonical minima, and
(for the first three charges) the forest formula. Every generated encoding also
undergoes expansion, forward commutation or reverse recovery, and stored-cost
checks. Source equality uses recursive child matching, not the translation's
sorting function. Source presentations include exchangeable-child permutations.

Targeted fixtures additionally cover equivalent permuted roots, an inline child
beside an equivalent reference, full-root references, duplicate definitions,
and the three published unary examples. Fixtures beyond the frozen size bound
are labeled separately and do not enlarge the exhaustive-universe claim.

On mismatch preserve the input and original result; manually expand and count
the offending witness, compare with a separate calculation, then identify the
generator, equality checker, translation, or mathematical claim responsible.
Preserve failed attempts and rerun affected checks after repairs. Never report
finite checks as proof of the unrestricted theorems or all rational charges.
