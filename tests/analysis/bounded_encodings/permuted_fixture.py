"""Count and check one unordered fixture with permuted shared children."""
from pathlib import Path
import argparse
import hashlib
import json
from fractions import Fraction
import targeted


def roots():
    t = lambda s, *children: (s, tuple(children))
    ga, kb = t('g', t('a')), t('k', t('b'))
    return (t('r1', t('q', ga, kb)), t('r2', t('q', kb, ga)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=('count', 'run'))
    ap.add_argument('out', type=Path)
    args = ap.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    result = targeted.run(args.mode, roots(), seconds=120, cap=2000000)
    result['case'] = 'permuted_unordered12'
    result['sha256'] = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                        for name in ('check.py', 'targeted.py', 'permuted_fixture.py', 'permuted_protocol.md')}
    if args.mode == 'run' and result['status'] == 'COMPLETE':
        expected = [str(min(Fraction(12), 9+Fraction(h))) for h in targeted.c.CHARGES]
        assert result['minima'][0] == expected
        result['expected_minima'] = expected
        result['strict_saving_pairs'] = sum(Fraction(x) < 12 for x in expected)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(result['status'], result['counts'], result['minima'])
    if result['status'] != 'COMPLETE':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
