"""Count and check size-bounded arbitrary encodings of five named inputs."""
from collections import Counter
from fractions import Fraction
from functools import lru_cache
from itertools import combinations_with_replacement
from pathlib import Path
import argparse
import hashlib
import json
import time
import check as c


def fixtures():
    t = lambda s, *ch: (s, tuple(ch))
    a = t('a'); ga = t('g', a); fga = t('f', ga)
    t3 = t('f3', a); t2 = t('f2', t3); t1 = t('f1', t2)
    cd = t('c', t('d')); ac = t('a', cd); bc = t('b', cd)
    abc = t('a', t('b', t('c')))
    return {
        'demand13': (t('o', fga, fga, fga), t('w', ga)),
        'chain16': (t1, t('w1', t1), t('w2', t2), t('w3', t3)),
        'L1': (t('x', ac, ac, bc, bc),),
        'L2': (t('x', t('y', ac), t('y', ac), t('y', bc), t('y', bc)),),
        'L3': (t('s', t('x', abc), t('x', abc), t('y', abc), t('y', abc)),),
    }


def tick(deadline):
    if time.monotonic() > deadline:
        raise TimeoutError('wall-clock limit')


def configurations(roots, ordered, deadline):
    n = sum(map(c.size, roots))
    candidates = sorted({c.key(v) if not ordered else v for t in roots
                         for v in c.subterms(t) if v[1]}, key=lambda v: (c.size(v), v))
    for d in range((n-len(roots))//2+1):
        for names in combinations_with_replacement(candidates, d):
            tick(deadline)
            c.variants.cache_clear()
            terms = [(v, True) for v in names]+[(v, False) for v in roots]
            options = []
            for v, body in terms:
                variants = c.variants(v, names, ordered, body)
                options.append([(x, c.size(x), sum(1 << j for j in c.references(x)))
                                for x in variants])
            minimum = [min(z[1] for z in xs) for xs in options]
            if sum(minimum) > n:
                continue
            # Exclude an option only if the other terms' minimum sizes exceed N.
            options = [[z for z in xs if z[1]+sum(minimum)-minimum[i] <= n]
                       for i, xs in enumerate(options)]
            groups = [Counter((z[1], z[2]) for z in xs) for xs in options]
            suffix = [None]*(len(options)+1)
            suffix[-1] = {(0, 0): 1}
            for i in range(len(options)-1, -1, -1):
                tick(deadline)
                acc = Counter()
                for (s, m), k in groups[i].items():
                    for (s2, m2), k2 in suffix[i+1].items():
                        if s+s2+sum(minimum[:i]) <= n:
                            acc[s+s2, m | m2] += k*k2
                suffix[i] = acc
            full = (1 << d)-1
            count = sum(k for (s, m), k in suffix[0].items() if m == full)
            if count:
                yield d, options, suffix, count, full
    c.variants.cache_clear()


def enumerate_configuration(d, options, suffix, full, n, deadline):
    @lru_cache(None)
    def possible(i, budget, seen):
        return any(s <= budget and (m | seen) == full for s, m in suffix[i])
    def walk(i, budget, seen, chosen):
        tick(deadline)
        if i == len(options):
            if seen == full:
                yield chosen[:d], chosen[d:]
            return
        for tree, size, mask in options[i]:
            if size <= budget and possible(i+1, budget-size, seen | mask):
                yield from walk(i+1, budget-size, seen | mask, chosen+(tree,))
    yield from walk(0, n, 0, ())


def visit(enc, roots, ordered):
    bodies, outputs = enc
    assert all(c.equal(c.expand(t, bodies), v, ordered) for t, v in zip(outputs, roots))
    reached = set().union(*(c.references(t) for t in outputs))
    todo = list(reached)
    while todo:
        for j in c.references(bodies[todo.pop()]):
            if j not in reached:
                reached.add(j); todo.append(j)
    assert len(reached) == len(bodies)
    if ordered:
        back = tuple(tuple(c.erase(t) for t in part) for part in enc)
        assert c.syntax_cost(back) == c.syntax_cost(enc)
        assert all(c.equal(c.expand(t, back[0]), c.erase(v)) for t, v in zip(back[1], roots))
    else:
        mapped = tuple(tuple(c.lift(t, bodies) for t in part) for part in enc)
        assert c.syntax_cost(mapped) == c.syntax_cost(enc)
        assert all(c.expand(y, mapped[0]) == c.translate(c.expand(x, bodies))
                   for x, y in zip(bodies+outputs, mapped[0]+mapped[1]))


def run(mode, roots, seconds, cap):
    start = time.monotonic(); deadline = start+seconds
    n = sum(map(c.size, roots))
    result = dict(status='INCOMPLETE', mode=mode, N=n, roots=roots, counts=[],
                  visited=[], minima=[], charges=c.CHARGES if mode == 'run' else None)
    try:
        for ordered, language in ((False, roots), (True, tuple(c.translate(t) for t in roots))):
            result['counts'].append(0); result['visited'].append(0)
            best = [None]*len(c.CHARGES)
            for d, options, suffix, count, full in configurations(language, ordered, deadline):
                result['counts'][-1] += count
                if sum(result['counts']) > cap:
                    raise TimeoutError('combined encoding-count limit')
                if mode == 'run':
                    seen = 0
                    for enc in enumerate_configuration(d, options, suffix, full, n, deadline):
                        result['last_encoding'] = enc
                        visit(enc, language, ordered)
                        sz = c.syntax_cost(enc)
                        for j, h in enumerate(map(Fraction, c.CHARGES)):
                            val = sz+h*d
                            best[j] = val if best[j] is None else min(best[j], val)
                        seen += 1
                        result['visited'][-1] += 1
                    assert seen == count, (seen, count)
            if mode == 'run':
                result['minima'].append(list(map(str, best)))
        if mode == 'run':
            w, u, forest = c.selected_values(tuple(c.translate(t) for t in roots))
            result['canonical_all'] = list(map(str, w))
            result['canonical_shared'] = list(map(str, u))
            result['forest_low_charges'] = list(map(str, forest))
            assert result['minima'][0] == result['minima'][1] == result['canonical_all'] == result['canonical_shared']
            assert result['minima'][0][:3] == result['forest_low_charges']
        result['status'] = 'COMPLETE'
        result.pop('last_encoding', None)
    except TimeoutError as e:
        result['reason'] = str(e)
    except Exception as e:
        result['status'] = 'MISMATCH'; result['reason'] = repr(e)
    result['elapsed_seconds'] = time.monotonic()-start
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=('count', 'run'))
    ap.add_argument('case', choices=fixtures())
    ap.add_argument('out', type=Path)
    ap.add_argument('--seconds', type=float, default=120)
    ap.add_argument('--cap', type=int, default=2000000)
    args = ap.parse_args()
    if args.out.exists():raise FileExistsError(args.out)
    result = run(args.mode, fixtures()[args.case], args.seconds, args.cap)
    result['case'] = args.case
    result['sha256'] = {p: hashlib.sha256(Path(__file__).with_name(p).read_bytes()).hexdigest()
                        for p in ('targeted.py', 'check.py', 'targeted_protocol.md')}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(args.case, args.mode, result['status'], result['counts'], result['elapsed_seconds'], flush=True)
    if result['status'] == 'MISMATCH':raise SystemExit(1)


if __name__ == '__main__':main()
