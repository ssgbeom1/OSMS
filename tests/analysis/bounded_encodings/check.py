"""Bounded enumeration of noncanonical macro encodings; standard library only."""
from collections import Counter
from fractions import Fraction
from functools import lru_cache
from itertools import combinations, combinations_with_replacement, permutations, product
from pathlib import Path
import argparse
import hashlib
import json
import time

HERE = Path(__file__).resolve().parent
CHARGES = ('0', '1/2', '1', '3/2', '2', '32')
SYMBOLS = ('a', 'b', 'u', 'v', 'q', 'm')


def size(t):
    return 1 + sum(size(c) for c in t[1])


def subterms(t):
    yield t
    for c in t[1]:
        yield from subterms(c)


def key(t):
    s, children = t
    ch = tuple(key(c) for c in children)
    if s == 'q':
        ch = tuple(sorted(ch))
    elif s == 'm':
        ch = ch[:1] + tuple(sorted(ch[1:]))
    return s, ch


def equal(a, b, ordered=False):
    """Compare source trees by matching children, without canonical sorting."""
    if a[0] != b[0] or len(a[1]) != len(b[1]):
        return False
    prefix = len(a[1]) if ordered or a[0] not in ('q', 'm') else int(a[0] == 'm')
    if not all(equal(x, y, ordered) for x, y in zip(a[1][:prefix], b[1][:prefix])):
        return False
    left, right = a[1][prefix:], b[1][prefix:]
    return any(all(equal(x, y, ordered) for x, y in zip(left, perm))
               for perm in permutations(right))


def compositions(n, k):
    if k == 0:
        if n == 0:
            yield ()
    elif k == 1:
        if n >= 1:
            yield (n,)
    else:
        for i in range(1, n-k+2):
            for tail in compositions(n-i, k-1):
                yield (i,) + tail


def universe(bound):
    levels = {1: {('a', ()), ('b', ())}}
    for n in range(2, bound+1):
        level = set()
        for s in SYMBOLS[2:]:
            arities = (1,) if s == 'u' else (2,) if s == 'v' else range(1, n)
            for arity in arities:
                for parts in compositions(n-1, arity):
                    for children in product(*(levels[p] for p in parts)):
                        level.add(key((s, children)))
        levels[n] = level
    terms = sorted(set.union(*levels.values()), key=lambda t: (size(t), t))
    yield ()
    def extend(start, budget, roots):
        for j in range(start, len(terms)):
            t = terms[j]
            if size(t) > budget:
                break
            new = roots + (t,)
            yield new
            yield from extend(j+1, budget-size(t), new)
    yield from extend(0, bound, ())


@lru_cache(None)
def variants(t, names, ordered, body=False):
    out = set()
    if not body:
        out.update(('@'+str(i), ()) for i, expansion in enumerate(names)
                   if equal(t, expansion, ordered))
    for children in product(*(variants(c, names, ordered) for c in t[1])):
        if not ordered and t[0] in ('q', 'm'):
            p = int(t[0] == 'm')
            for suffix in set(permutations(children[p:])):
                out.add((t[0], children[:p]+suffix))
        else:
            out.add((t[0], children))
    return tuple(sorted(out))


def references(t):
    return {int(v[0][1:]) for v in subterms(t) if v[0].startswith('@')}


def encodings(roots, ordered=False):
    """Enumerate all reference/inline choices up to the cost-derived name bound."""
    n, r = sum(map(size, roots)), len(roots)
    candidates = sorted({key(v) if not ordered else v for t in roots for v in subterms(t) if v[1]},
                        key=lambda t: (size(t), t))
    for d in range((n-r)//2+1):
        for names in combinations_with_replacement(candidates, d):
            body_options = []
            for t in names:
                # Only proper-subterm expansions can occur below a definition root.
                body_options.append(variants(t, names, ordered, True))
            options = body_options + [variants(t, names, ordered) for t in roots]
            for chosen in product(*options):
                bodies, outputs = chosen[:d], chosen[d:]
                reached = set().union(*(references(t) for t in outputs)) if outputs else set()
                todo = list(reached)
                while todo:
                    for j in references(bodies[todo.pop()]):
                        if j not in reached:
                            reached.add(j)
                            todo.append(j)
                if len(reached) == d:
                    yield bodies, outputs


def expand(t, bodies):
    if t[0].startswith('@'):
        return expand(bodies[int(t[0][1:])], bodies)
    return t[0], tuple(expand(c, bodies) for c in t[1])


def syntax_cost(enc):
    return sum(size(t) for part in enc for t in part)


def translate(t):
    s, ch = t
    mapped = [translate(c) for c in ch]
    if s == 'q':
        mapped.sort()
    elif s == 'm':
        mapped[1:] = sorted(mapped[1:])
    return s+'#'+str(len(ch)), tuple(mapped)


def lift(t, bodies):
    if t[0].startswith('@'):
        return t
    ch = list(t[1])
    if t[0] == 'q':
        ch.sort(key=lambda c: translate(expand(c, bodies)))
    elif t[0] == 'm':
        ch[1:] = sorted(ch[1:], key=lambda c: translate(expand(c, bodies)))
    return t[0]+'#'+str(len(ch)), tuple(lift(c, bodies) for c in ch)


def erase(t):
    return t[0].split('#')[0], tuple(erase(c) for c in t[1])


def selected_values(roots):
    vertices = {v for t in roots for v in subterms(t)}
    W = sorted((v for v in vertices if v[1]), key=lambda t: (size(t), t))
    inc = Counter(roots)
    for v in vertices:
        inc.update(v[1])
    U = {v for v in W if inc[v] >= 2}
    def render(t, S, body=False):
        if t in S and not body:
            return ('@ref', ())
        return t[0], tuple(render(c, S) for c in t[1])
    def stored(S):
        return sum(size(render(t, S)) for t in roots)+sum(size(render(t, S, True)) for t in S)
    def minimum(pool):
        values = [None]*len(CHARGES)
        for k in range(len(pool)+1):
            for subset in combinations(pool, k):
                b = stored(set(subset))
                for j, h in enumerate(map(Fraction, CHARGES)):
                    v = b+h*k
                    values[j] = v if values[j] is None else min(values[j], v)
        return values
    def edges(t):
        return len(t[1])+sum(edges(c) for c in t[1] if c not in U)
    J = sorted(v for v in U if edges(v) == 1 and inc[v] == 2)
    alpha = 0
    for k in range(len(J)+1):
        for subset in combinations(J, k):
            I = set(subset)
            if not any(c in I for v in I for c in v[1]):
                alpha = max(alpha, k)
    forest = [Fraction(stored(U))+Fraction(h)*(len(U)-alpha) for h in CHARGES[:3]]
    return minimum(W), minimum(sorted(U)), forest


def check_language(roots, stats):
    target = tuple(translate(t) for t in roots)
    minima = []
    for ordered, language in ((False, roots), (True, target)):
        best = [None]*len(CHARGES)
        for enc in encodings(language, ordered):
            bodies, outputs = enc
            stats['target_encodings' if ordered else 'source_encodings'] += 1
            assert len(outputs) == len(language)
            assert all(equal(expand(t, bodies), original, ordered) for t, original in zip(outputs, language))
            count = syntax_cost(enc)
            for j, h in enumerate(map(Fraction, CHARGES)):
                val = count+h*len(bodies)
                best[j] = val if best[j] is None else min(best[j], val)
            if ordered:
                back = tuple(tuple(erase(t) for t in part) for part in enc)
                assert syntax_cost(back) == count
                assert all(equal(expand(t, back[0]), original) for t, original in zip(back[1], roots))
            else:
                mapped = tuple(tuple(lift(t, bodies) for t in part) for part in enc)
                assert syntax_cost(mapped) == count
                for t, mapped_t in zip(bodies+outputs, mapped[0]+mapped[1]):
                    assert expand(mapped_t, mapped[0]) == translate(expand(t, bodies))
            stats['map_checks'] += 1
        minima.append(best)
    w, u, forest = selected_values(target)
    assert minima[0] == minima[1] == w == u, (roots, minima, w, u)
    assert u[:3] == forest, (roots, u, forest)
    stats['languages'] += 1
    stats['charge_comparisons'] += len(CHARGES)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=('count', 'run'))
    ap.add_argument('--bound', type=int, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--seconds', type=float, default=120)
    ap.add_argument('--cap', type=int, default=200000)
    args = ap.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    started = time.monotonic()
    stats = Counter(languages=0, source_encodings=0, target_encodings=0, map_checks=0, charge_comparisons=0)
    status = 'COMPLETE'
    current = None
    try:
        for roots in universe(args.bound):
            current = roots
            if args.mode == 'count':
                for ordered, lang in ((False, roots), (True, tuple(translate(t) for t in roots))):
                    for enc in encodings(lang, ordered):
                        stats['target_encodings' if ordered else 'source_encodings'] += 1
                        if sum(stats[k] for k in ('source_encodings', 'target_encodings')) > args.cap or time.monotonic()-started > args.seconds:
                            raise TimeoutError('preflight cap')
                stats['languages'] += 1
            else:
                check_language(roots, stats)
            if time.monotonic()-started > args.seconds:
                raise TimeoutError('wall cap')
    except TimeoutError as e:
        status = 'INCOMPLETE'
        stats['reason'] = str(e)
    except Exception as e:
        status = 'MISMATCH'
        stats['reason'] = repr(e)
        stats['input'] = current
    result = dict(mode=args.mode, bound=args.bound, charges=CHARGES if args.mode == 'run' else None,
                  status=status, stats=dict(stats), elapsed_seconds=time.monotonic()-started,
                  code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    if status == 'MISMATCH':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
