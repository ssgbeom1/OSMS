"""Residual greedy and continuous LP diagnostic worker."""
import os
os.environ.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys
import time
import traceback
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'primary'))
from telemetry import Recorder,atomic_json


def main():
    p=argparse.ArgumentParser();p.add_argument('case');p.add_argument('method',choices=['A1','RG-add','RG-prune','LP-on','LP-off']);p.add_argument('h');p.add_argument('output');a=p.parse_args()
    out=Path(a.output);assert not out.exists();rec=Recorder(out.with_suffix('.phase.json'))
    result={'method':a.method,'h':a.h,'input':a.case,'status':'ERROR','valid_return':False}
    try:
        with rec.span('imports'):
            import numpy as np
            import scipy
            from scipy.optimize import milp,Bounds,LinearConstraint
            import psutil
            import engine,baseline,checker,residual
        process=psutil.Process();process.cpu_affinity([min(process.cpu_affinity())])
        result.update(cpu_affinity=process.cpu_affinity(),numpy=np.__version__,scipy=scipy.__version__)
        rec.group('prepare',120)
        with rec.span('input_load'):case=json.loads(Path(a.case).read_text(encoding='utf-8'))
        with rec.span('common_intern'):g=engine.prepare(case)
        if time.perf_counter()>rec.stage_deadline:raise TimeoutError('common preparation')
        h=Fraction(a.h);rec.group('method',30);start=time.perf_counter()
        with rec.span('method_total'):
            if a.method=='A1':result.update(engine.solve(case,g,'A1',h,30,rec))
            else:
                tick=time.perf_counter()
                with rec.span('preprocess'):state=engine.problem(g,h,'A1',rec)
                pre=time.perf_counter()-tick;vertices=sorted(v for comp in state['components'] for v in comp)
                result['profile']={'residual_signature':state['signature'],'fixed_cost':str(state['offset']),
                    'residual_candidates':len(state['active']),'components':len(state['components']),
                    'max_component_candidates':max((len(set(c)&state['active']) for c in state['components']),default=0)}
                if a.method.startswith('LP'):
                    tick=time.perf_counter()
                    with rec.span('model'):m=engine.build(g,state,vertices,h)
                    model=time.perf_counter()-tick;remaining=start+27-time.perf_counter();assert remaining>0,'preprocessing exhausted diagnostic search budget'
                    tick=time.perf_counter()
                    if m['nvars']:
                        options=dict(engine.OPTIONS,presolve=a.method=='LP-on',time_limit=remaining,disp=True)
                        with rec.span('lp_solver'),warnings.catch_warnings(record=True) as ww:
                            warnings.simplefilter('always')
                            opt=milp(m['obj'],integrality=np.zeros(m['nvars']),bounds=Bounds(m['lower'],m['upper']),
                                     constraints=LinearConstraint(m['matrix'],m['lo'],m['hi']),options=options)
                        result.update(lp_status=int(opt.status),message=str(opt.message),warnings=[str(w.message) for w in ww])
                        if opt.x is not None:
                            ax=m['matrix']@opt.x
                            violation=max(float(np.max(m['lo']-ax,initial=0)),float(np.max(ax-m['hi'],initial=0)),
                                          float(np.max(m['lower']-opt.x,initial=0)),float(np.max(opt.x-m['upper'],initial=0)))
                            result.update(lp_residual_objective_numeric=float(opt.fun)/h.denominator,
                                lp_full_objective_numeric=float(state['offset'])+float(opt.fun)/h.denominator,
                                lp_max_fractionality=float(np.max(np.abs(opt.x-np.rint(opt.x)),initial=0)),lp_feasibility_violation=violation)
                        result['status']='LP_OPTIMAL_NUMERICAL' if opt.status==0 else 'LP_LIMIT_OR_FAILURE'
                    else:
                        result.update(status='LP_OPTIMAL_NUMERICAL',lp_status=0,lp_full_objective_numeric=float(state['offset']),
                                      lp_residual_objective_numeric=0.0,lp_max_fractionality=0.0,lp_feasibility_violation=0.0)
                    result['timing']={'primary':time.perf_counter()-start,'preprocess':pre,'model':model,'solver':time.perf_counter()-tick}
                    result['valid_return']=result['status']=='LP_OPTIMAL_NUMERICAL' and result['timing']['primary']<=30 and result['lp_feasibility_violation']<=1e-5
                    result.update(interpretation='Continuous LP numeric optimum, no integer witness or exact rational certificate; empty residual handled without solver.',solver_invoked=bool(m['nvars']),nvars=m['nvars'],nrows=m['nrows'])
                else:
                    tick=time.perf_counter()
                    with rec.span('residual_selection'):
                        chosen,trace,expired,predicted=residual.choose(g,state,h,a.method=='RG-prune',start+27)
                    selection=time.perf_counter()-tick;tick=time.perf_counter()
                    with rec.span('reconstruct'):
                        encoding,cost=baseline._render(g['nodes'],g['roots'],state['F']|chosen,h,case['ranks'])
                        assert cost==predicted==engine.residual_cost(g,state,chosen,h)
                    reconstruction=time.perf_counter()-tick
                    result.update(status='limit_feasible' if expired else 'FEASIBLE',encoding=encoding,cost=str(cost),selected=sorted(state['F']|chosen),trace=trace,
                        timing={'primary':time.perf_counter()-start,'preprocess':pre,'selection':selection,'reconstruct':reconstruction})
        if 'encoding' in result:
            rec.group('check',60)
            with rec.span('external_check'):verdict=checker.check(case,a.h,result['encoding'])
            result['check']=verdict
            result['valid_return']=verdict['ok'] and Fraction(verdict['cost'])==Fraction(result['cost']) and result['timing']['primary']<=30 and time.perf_counter()<=rec.stage_deadline
            if not result['valid_return']:result['status']='BUDGET_OR_WITNESS_FAILURE'
    except Exception:result.update(status='ERROR',valid_return=False,error=traceback.format_exc())
    result['telemetry']=rec.result();rec.stage_group='output';rec.stage_deadline=None
    with rec.span('output_write'):atomic_json(out,result)
    rec.publish(worker_complete=True)
    print(json.dumps({k:result.get(k) for k in ['method','status','cost','valid_return']}),flush=True)


if __name__=='__main__':main()
