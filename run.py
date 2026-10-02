"""Prepare an input or run one supervised selection method."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'code'))
METHODS = {
    'forest': 'Forest', 'global-milp': 'A0', 'join-restricted-milp': 'A0-U',
    'preprocessed-milp': 'A1', 'component-milp': 'A2',
    'maximal-sharing': 'All-U', 'greedy-add': 'Greedy-add',
    'greedy-prune': 'Greedy-prune', 'no-sharing': 'No-sharing',
    'residual-add': 'RG-add', 'residual-prune': 'RG-prune',
    'lp-presolve-on': 'LP-on', 'lp-presolve-off': 'LP-off',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare', help='Convert a Python package directory')
    prepare.add_argument('--source', type=Path, required=True)
    prepare.add_argument('--representation', choices=['compact','fielded'], required=True)
    prepare.add_argument('--target-nodes', type=int, required=True)
    prepare.add_argument('--out', type=Path, required=True)
    solve = commands.add_parser('solve', help='Execute one fresh supervised run')
    solve.add_argument('--case', type=Path, required=True)
    solve.add_argument('--method', choices=METHODS, required=True)
    solve.add_argument('--h', required=True, help='Nonnegative integer or rational, e.g. 11/10')
    solve.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists() or args.out.with_suffix('.manifest.json').exists():
        parser.error('Output already exists; choose a new path.')
    if args.command == 'prepare':
        from package_adapter import convert
        from telemetry import atomic_json
        case, manifest = convert(args.source, args.representation, args.target_nodes, args.out.stem)
        atomic_json(args.out.with_suffix('.manifest.json'), manifest)
        if case is None:
            raise SystemExit('Conversion failed; inspect the manifest.')
        atomic_json(args.out, case)
        print(json.dumps({'status':manifest['status'], 'nodes':manifest['nodes']}))
        return
    from fractions import Fraction
    h = Fraction(args.h)
    if h < 0 or (args.method == 'forest' and h > 1):
        parser.error('The forest method requires 0 <= h <= 1; other methods require h >= 0.')
    from run_one import execute
    diagnostic = args.method.startswith(('residual-', 'lp-'))
    worker = ROOT/'code'/('diagnostic_worker.py' if diagnostic else 'worker.py')
    command = [sys.executable, '-B', str(worker), str(args.case.resolve()),
               METHODS[args.method], str(h), str(args.out.resolve())]
    if not diagnostic:
        command += ['--method-seconds','30','--prepare-seconds','120','--check-seconds','60']
    result = execute(command, args.out.resolve(), process_seconds=220,
                     rss_bytes=4096*1024*1024, sample_seconds=.05)
    print(json.dumps({k:result.get(k) for k in ['status','cost','valid_return','wall_seconds','peak_sampled_rss_bytes']}))
    if not result.get('valid_return'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
