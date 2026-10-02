# Targeted noncanonical encoding checks

## Fixed scope (before counting)

The five inputs are the article's 13-node demand example, 16-node unary chain,
and the three source examples L1, L2, L3 (13, 17, 17 nodes). They are named
fixtures, not a new exhaustive input universe. Costs are checked at
0, 1/2, 1, 3/2, 2, 32. Forest values are compared only at 0, 1/2, 1.

All nonconstant whole subterms are eligible expansions. Repeated expansions
may receive multiple names. Every output position, including its root, and
every proper body position may independently inline or reference a matching
name. Definition roots remain constructors. Dependencies strictly decrease
expanded size; aliases and constant bodies are illegal. Names are numbered
by an ordered expansion multiset, allowing redundant equal-expansion names.

For input size N and root count r, at most floor((N-r)/2) definitions are
enumerated. The targeted search additionally restricts total stored syntax
to at most N nodes. Any excluded representation costs more than the legal
unshared representation for every nonnegative charge. This size budget is
fixed from the input, not from a computed optimum. No shared-candidate
restriction, automatic reference replacement, merging of names, forest
formula or incumbent-based cutoff is used by the generator.

## Counting and execution

Preflight computes encoding counts only, without evaluating charges,
canonical selections, forest values or optimal values. It groups expression
variants by (stored size, referenced-name mask), multiplying counts through
outputs and bodies. Since dependencies decrease size, all definitions are
reachable from outputs exactly when the union of reference masks includes
all names. In a finite acyclic dependency graph, a nonempty unreachable
component would otherwise have a vertex with no incoming reference.

Each case has a 120-second preflight budget and a 2,000,000 combined source
and target encoding limit. Counts may be large integers. Full validation is
attempted only after a complete count within this cap. Each eligible case
has a 180-second validation budget. Counts and incomplete cases are retained.
The process supervisor imposes a separate 10-second timeout margin.

Validation explicitly visits each admitted encoding; dynamic programming
prunes only combinations unable to meet the size or reachability constraints.
For each visit, expansion and mapping costs are checked. Exact rational
minima from source and target enumeration are compared against canonical
subset enumeration. The latter runs only after enumeration, and is not used
to prune it. A separate tiny-case cross-check compares the optimized
generator with the previous literal generator, filtered by the same N-node
budget. Counts include equal-expansion name permutations.

## Structure and failure policy

| Input | Structure exercised |
|---|---|
| III-A | Outer naming reduces inner demand; safe inclusion |
| Chain | Adjacent optional omissions; three-vertex path |
| L1 | Two optional parents sharing a child; adjacency |
| L2 | One isolated optional vertex |
| L3 | Two isolated optional vertices; shared middle definition |

On mismatch: preserve input, witness, code hash and raw result; manually
count the witness; compare with the literal generator or independent direct
construction; then classify generator, model or theorem failure. No source
or result is overwritten to hide a failed attempt. Incomplete enumeration
does not establish an arbitrary-encoding minimum. These are internal finite
checks, not general proofs, external review, or tests of hardness reductions.
