"""Two predeclared larger fixtures; separate from the exhaustive universe."""
from collections import Counter
from pathlib import Path
import json
import time
import check as c


def main(out):
    out.mkdir(exist_ok=False)
    a = ('a', ())
    chain = a
    for _ in range(3):
        chain = ('u', (chain,))
    cases = [('unordered_pair', (('q', (chain, chain)),)),
             ('mixed_pair', (('m', (a, chain, chain)),))]
    (out/'scope.json').write_text(json.dumps({'cases': cases, 'charges': c.CHARGES,
        'role': 'Additional named fixtures, not expansion of bound-5 universe',
        'name_bound': 'floor((N-r)/2)', 'seconds_limit': 120}, indent=2), encoding='utf-8')
    started = time.monotonic()
    records = []
    for name, roots in cases:
        stats = Counter(languages=0, source_encodings=0, target_encodings=0, map_checks=0, charge_comparisons=0)
        c.check_language(roots, stats)
        n = sum(map(c.size, roots))
        values = c.selected_values(tuple(c.translate(t) for t in roots))[0]
        assert values[2] == n-1
        records.append({'name':name, 'N':n, 'stats':dict(stats), 'minima':list(map(str,values))})
        if time.monotonic()-started > 120:
            raise TimeoutError('Fixture limit exceeded; do not report complete')
    result = {'status':'PASS', 'records':records, 'elapsed_seconds':time.monotonic()-started}
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    import sys
    main(Path(sys.argv[1]))
