"""Execute and validate one timed selection method."""
import os
os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
import argparse
import json
import time
import traceback
from pathlib import Path
from telemetry import Recorder, atomic_json


def main():
    p = argparse.ArgumentParser()
    p.add_argument('case'); p.add_argument('method'); p.add_argument('h'); p.add_argument('output')
    p.add_argument('--method-seconds', type=float, default=30)
    p.add_argument('--prepare-seconds', type=float, default=60)
    p.add_argument('--check-seconds', type=float, default=30)
    args = p.parse_args()
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(output)
    rec = Recorder(output.with_suffix('.phase.json'))
    result = {'status': 'ERROR', 'method': args.method, 'h': args.h, 'input': args.case}
    try:
        with rec.span('imports'):
            import psutil
            import scipy
            import numpy
            import engine
            import heuristics
            import checker
            import forest
        process = psutil.Process()
        process.cpu_affinity([min(process.cpu_affinity())])
        result.update(cpu_affinity=process.cpu_affinity(), scipy=scipy.__version__, numpy=numpy.__version__,
                      solver_options=dict(engine.OPTIONS, disp=True))
        rec.group('prepare', args.prepare_seconds)
        with rec.span('input_load'):
            case = json.loads(Path(args.case).read_text(encoding='utf-8'))
        with rec.span('common_intern'):
            g = engine.prepare(case)
        if time.perf_counter() > rec.stage_deadline:
            raise TimeoutError('prepare budget')
        rec.group('method', args.method_seconds)
        with rec.span('method_total'):
            if args.method in ('A0','A1','A2'):
                result.update(engine.solve(case, g, args.method, args.h, args.method_seconds, rec))
            elif args.method == 'Forest':
                tick = time.perf_counter()
                with rec.span('forest_selection_and_reconstruction'):
                    metadata = {s:{'arity':'rank','rank':n,'order':'ordered','prefix':0} for s,n in case['ranks'].items()}
                    encoding = forest.solve(case['roots'],metadata,args.h)
                result.update(status='THEOREM_EXACT', cost=encoding['cost'], encoding=encoding,
                              forest_stats=encoding['stats'], timing={'primary':time.perf_counter()-tick},
                              bound_exact_theorem=encoding['cost'], bound_numeric=None)
            else:
                result.update(heuristics.solve(case, g, args.method, args.h, args.method_seconds, rec))
        result['N'] = sum(g['raw'])
        result['unique_subterms'] = len(g['nodes'])
        result['joins'] = len(g['U'])
        if result['timing']['primary'] > args.method_seconds:
            result['completed_algorithm_status'] = result['status']
            result['status'] = 'input_budget_exceeded_feasible'
        rec.group('check', args.check_seconds)
        with rec.span('external_check'):
            result['check'] = checker.check(case, args.h, result['encoding'])
        if time.perf_counter() > rec.stage_deadline:
            result['status'] = 'CHECK_BUDGET'
        elif not result['check']['ok']:
            result['status'] = 'INVALID_WITNESS'
        result['valid_return'] = (result['check']['ok'] and result['timing']['primary']<=args.method_seconds
                                  and result['status'] not in ('CHECK_BUDGET','INVALID_WITNESS'))
    except Exception:
        result.update(status='ERROR', valid_return=False, error=traceback.format_exc())
    result['telemetry'] = rec.result()
    rec.stage_group = 'output'; rec.stage_deadline = None
    with rec.span('output_write'):
        atomic_json(output, result)
    rec.publish(worker_complete=True)
    print(json.dumps({k: result.get(k) for k in ('status','method','h','cost','valid_return')}), flush=True)


if __name__ == '__main__':
    main()
