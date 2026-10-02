"""Check result-table integrity and solver costs on small explicit trees."""
from pathlib import Path
from fractions import Fraction
from collections import Counter
import csv
import hashlib
import json
import sys
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'code'))


def rows(name):
    with (ROOT/name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def main():
    import engine, baseline, checker, forest, residual
    warnings.filterwarnings('ignore', message='Unrecognized options detected.*')
    manifest=ROOT/'MANIFEST.json'
    if manifest.exists():
        for name, expected in json.loads(manifest.read_text()).items():
            assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected, name
    table=rows('results/tables/S9_normalization_runs.csv')
    assert len(table)==1530
    complete={}
    for method in ['Global MILP baseline','Join-restricted MILP','Preprocessed global MILP']:
        group=[r for r in table if r['method']==method]
        assert len(group)==510,method
        counts=Counter(r['condition'] for r in group if r['numeric_optimal']=='True' and r['valid_return']=='True')
        complete[method]=sum(n==6 for n in counts.values())
    assert list(complete.values())==[65,80,84],complete
    primary=rows('results/primary/all_slots.csv')
    assert len(primary)==5184,len(primary)
    assert len(rows('results/tables/S1_h1_times.csv'))==17
    assert len(rows('results/tables/S2_candidate_reduction.csv'))==85
    cases=json.loads((ROOT/'examples/verification_cases.json').read_text())
    checked=0
    for case in cases:
        expected=Fraction(checker.solve(case,'1')['cost'])
        meta={s:{'arity':'rank','rank':n,'order':'ordered','prefix':0} for s,n in case['ranks'].items()}
        enc=forest.solve(case['roots'],meta,'1')
        assert Fraction(enc['cost'])==expected
        assert checker.check(case,'1',enc)['ok']
        checked+=1
    # Unnamed connectors must transmit demand.
    t=lambda s,*children:[s,list(children)]
    child=t('f',t('a')); parent=t('p',child,child); excluded=t('q',child)
    connector={'id':'excluded-connector','ranks':{'a':0,'f':1,'p':2,'q':1,**{f'r{i}':1 for i in range(5)}},
               'roots':[t(f'r{i}',parent if i<3 else excluded) for i in range(5)]}
    child=t('f',t('a'),t('b'),t('c')); parent=t('p',t('u',child),child)
    noncandidate={'id':'noncandidate-connector','ranks':{'a':0,'b':0,'c':0,'f':3,'p':2,'u':1,'r0':1,'r1':1},
                  'roots':[t('r0',parent),t('r1',parent)]}
    comparisons=0
    for case in cases[:8]+[connector,noncandidate]:
        g=engine.prepare(case)
        for hs in ['3/2','4']:
            h=Fraction(hs); expected=Fraction(checker.solve(case,hs)['cost'])
            for method in ['A0','A0-U','A1','A2']:
                result=engine.solve(case,g,method,hs,30)
                assert result['status']=='optimal_numerical',(method,result['status'])
                assert Fraction(result['cost'])==expected,(method,result['cost'],expected)
                assert checker.check(case,hs,result['encoding'])['ok']
                comparisons+=1
            state=engine.problem(g,h,'A1')
            for prune in [False,True]:
                chosen,trace,expired,predicted=residual.choose(g,state,h,prune,check_moves=True)
                enc,cost=baseline._render(g['nodes'],g['roots'],state['F']|chosen,h,case['ranks'])
                assert not expired and cost==predicted==engine.residual_cost(g,state,chosen,h)
                assert cost>=expected and checker.check(case,hs,enc)['ok']
    print(json.dumps({'status':'PASS','forest_oracle_cases':checked,'MILP_oracle_comparisons':comparisons,
                      'residual_greedy_paths':40,'normalization_completion':complete,'primary_slots':len(primary)}))


if __name__ == '__main__':
    main()
