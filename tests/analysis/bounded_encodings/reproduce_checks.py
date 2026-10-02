"""Rerun the bounded checks and compare deterministic archived fields."""
from pathlib import Path
import argparse
import json
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def stable(value):
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items() if k != 'elapsed_seconds'}
    if isinstance(value, list):
        return list(map(stable, value))
    return value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out', type=Path)
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    checks = []

    def run(script, arguments, actual, archived):
        with (out/(actual.replace('/', '_')+'.log')).open('w', encoding='utf-8') as log:
            subprocess.run([sys.executable, '-B', str(HERE/script), *arguments],
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=700)
        observed = json.loads((out/actual).read_text(encoding='utf-8'))
        expected = json.loads((HERE/archived).read_text(encoding='utf-8'))
        if stable(observed) != stable(expected):
            raise ValueError('Deterministic result differs: '+actual)
        checks.append({'result': actual, 'archive': archived, 'status': 'PASS'})
        print(actual, 'PASS', flush=True)

    run('check.py', ['run', '--bound', '5', '--seconds', '600', '--out', str(out/'universe.json')],
        'universe.json', 'result001.json')
    for script, name, archive in (
        ('census.py', 'census.json', 'census.json'),
        ('fixtures.py', 'fixtures.json', 'fixtures003.json'),
        ('targeted_crosscheck.py', 'crosscheck.json', 'targeted_results/crosscheck.json')):
        run(script, [str(out/name)], name, archive)
    run('profitable_fixtures.py', [str(out/'profitable')], 'profitable/result.json', 'profitable_result.json')
    for case in ('demand13', 'chain16', 'L1', 'L2', 'L3'):
        for mode in ('count', 'run'):
            name = mode+'_'+case+'.json'
            run('targeted.py', [mode, case, str(out/name), '--seconds', '180' if mode == 'run' else '120'],
                name, 'targeted_results/'+name)
    for mode in ('count', 'run'):
        name = 'permuted_'+mode+'.json'
        run('permuted_fixture.py', [mode, str(out/name)], name, 'permuted_results/'+mode+'.json')
    (out/'verification.json').write_text(json.dumps({'status': 'PASS', 'checks': checks,
        'comparison': 'All JSON fields except elapsed_seconds; no large-scale experiment rerun.'}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
