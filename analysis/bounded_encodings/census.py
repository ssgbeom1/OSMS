"""Independent raw-presentation census using isomorphism matching and a generating polynomial."""
from itertools import product
from math import comb
from pathlib import Path
import json
import check


def main(out):
    if out.exists():
        raise FileExistsError(out)
    limit = 5
    raw = {1: [('a', ()), ('b', ())]}
    counts = {}
    raw_counts = {}
    def lists(total, prefix=()):
        if total == 0:
            yield prefix
        for k in range(1, total+1):
            for t in raw[k]:
                yield from lists(total-k, prefix+(t,))
    for n in range(1, limit+1):
        if n > 1:
            raw[n] = []
            for children in lists(n-1):
                if len(children) == 1:
                    raw[n].append(('u', children))
                if len(children) == 2:
                    raw[n].append(('v', children))
                raw[n].extend((s, children) for s in ('q', 'm'))
        representatives = []
        for term in raw[n]:
            if not any(check.equal(term, r) for r in representatives):
                representatives.append(term)
        counts[n] = len(representatives)
        raw_counts[n] = len(raw[n])
    polynomial = [1]+[0]*limit
    for n, count in counts.items():
        nxt = [0]*(limit+1)
        for i, value in enumerate(polynomial):
            for k in range(min(count, (limit-i)//n)+1):
                nxt[i+k*n] += value*comb(count, k)
        polynomial = nxt
    observed = [0]*(limit+1)
    for language in check.universe(limit):
        observed[sum(map(check.size, language))] += 1
    assert polynomial == observed
    result = dict(status='PASS', bound=limit, raw_terms_by_size=raw_counts,
                  source_classes_by_size=counts, languages_by_total_size=polynomial,
                  total_languages=sum(polynomial))
    out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    import sys
    main(Path(sys.argv[1]))
