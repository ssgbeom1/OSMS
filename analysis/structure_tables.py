"""Derive forest and candidate-reduction tables from execution records."""
import argparse, csv, hashlib, json
from collections import defaultdict, Counter
from fractions import Fraction
from pathlib import Path
from statistics import median

from common import read, WORK, RECORDS

def csvout(p, rows):
    with p.open('w', encoding='utf-8-sig', newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader(); w.writerows(rows)

def main(root, out):
    out.mkdir(parents=True,exist_ok=True)
    audit=WORK/'audit/complete_rows.json'
    rows=[r for r in read(audit) if r['input_status']=='READY']
    monitors={r['slot']:r for r in map(json.loads,(RECORDS/'primary/rows.jsonl').read_text().splitlines())}
    by=defaultdict(list)
    for r in rows: by[r['condition']].append(r)
    inputs={}; h1=[]
    for cid,rr in by.items():
        if Fraction(rr[0]['h'])!=1: continue
        ff=[r for r in rr if r['method']=='Forest']; aa=[r for r in rr if r['method']=='A0']
        assert len(ff)==len(aa)==6 and all(r['valid_return'] and r['theorem_exact'] for r in ff)
        raw=read(Path(ff[0]['raw_file'])); fs=raw['forest_stats']
        assert Fraction(raw['cost'])+fs['independent_size']==Fraction(fs['all_U_cost'])
        key=tuple(rr[0][k] for k in ['distribution','representation','target_nodes'])
        inputs[key]=fs
        same=len({monitors[r['slot']]['execution_batch'] for r in ff+aa})==1
        eligible=same and all(r['valid_return'] and r['numeric_optimal'] for r in aa)
        if eligible: assert len({Fraction(r['cost']) for r in ff+aa})==1
        fmed=median(r['seconds_primary'] for r in ff)
        amed=median(r['seconds_primary'] for r in aa) if eligible else None
        h1.append(dict(condition=cid,**{k:rr[0][k] for k in ['distribution','representation','target_nodes','actual_nodes']},
          W=fs['nonconstant_classes'],U=fs['U'],J=fs['J'],forest_edges=fs['forest_edges'],alpha=fs['independent_size'],
          cost=raw['cost'],All_U_cost=fs['all_U_cost'],Forest_valid=6,A0_valid=sum(r['valid_return'] for r in aa),
          A0_optimal=sum(r['numeric_optimal'] for r in aa),A0_statuses=json.dumps(dict(Counter(r['status'] for r in aa))),
          same_batch=same,paired=eligible,Forest_primary_median_s=fmed,A0_primary_median_s=amed,
          A0_over_Forest=amed/fmed if eligible else None,raw_forest=ff[0]['raw_file']))
    assert len(h1)==17
    diag=list(map(json.loads,(RECORDS/'diagnostics/rows.jsonl').read_text().splitlines()))
    lp={ (r['input']['distribution'],r['input']['representation'],r['input']['target_nodes'],Fraction(r['h'])):r for r in diag if r['method']=='LP-on'}
    stages=[]
    for cid,rr in by.items():
        if Fraction(rr[0]['h'])<=1: continue
        key=tuple(rr[0][k] for k in ['distribution','representation','target_nodes'])
        fs=inputs[key]; aa=[r for r in rr if r['method']=='A1']; valid=[r for r in aa if r['valid_return']]
        rec=valid[0] if valid else lp[key+(Fraction(rr[0]['h']),)]
        raw=read(Path(rec['raw_file'])); p=raw['profile']
        if valid:
            assert p['initial_candidates']==fs['nonconstant_classes'] and p['joins']==fs['U']
            residual=fs['U']-p['forced']-p['excluded']
        else:
            residual=p['residual_candidates']
        assert 0<=residual<=fs['U']<=fs['nonconstant_classes']
        stages.append(dict(condition=cid,**{k:rr[0][k] for k in ['distribution','representation','target_nodes','actual_nodes','h']},
            W=fs['nonconstant_classes'],U=fs['U'],forced=p.get('forced'),excluded=p.get('excluded'),R=residual,
            R_over_U=residual/fs['U'],U_over_W=fs['U']/fs['nonconstant_classes'],
            A0_variables=2*fs['nonconstant_classes'],A0_constraints=3*fs['nonconstant_classes'],
            A1_variables=p['variables'] if valid else raw['nvars'],A1_constraints=p['constraints'] if valid else raw['nrows'],components=p['components'],max_component_candidates=p['max_component_candidates'],
            profile_origin='primary' if valid else 'retrospective_LP',A1_valid=len(valid),raw_profile=rec['raw_file']))
    assert len(stages)==85
    csvout(out/'h1_times.csv',h1); csvout(out/'candidate_reduction.csv',stages)
    hs=[]; red=[]
    for source in ['matplotlib','pydantic','aiohttp','jsonschema']:
        f=[r for r in h1 if r['distribution']==source]; pair=[r for r in f if r['paired']]
        hs.append(dict(source=source,inputs=len(f),Forest_completed=len(f),A0_completed=sum(r['A0_optimal']==6 for r in f),paired=len(pair),
           Forest_median=median(r['Forest_primary_median_s'] for r in f),Forest_max=max(r['Forest_primary_median_s'] for r in f),
           A0_over_Forest_median=median(r['A0_over_Forest'] for r in pair)))
        for rep in ['compact','fielded']:
            x=[r for r in stages if r['distribution']==source and r['representation']==rep]
            red.append(dict(source=source,representation=rep,n=len(x),W=median(r['W'] for r in x),U=median(r['U'] for r in x),
                R=median(r['R'] for r in x),R_max=max(r['R'] for r in x),U_over_W_pct=100*median(r['U_over_W'] for r in x),
                R_over_U_pct=100*median(r['R_over_U'] for r in x)))
    result=dict(audit_sha256=hashlib.sha256(audit.read_bytes()).hexdigest(),new_solver_runs=0,h1_by_source=hs,reduction_by_source_rep=red,
        naming_removed_by_join_pct=100*median(1-r['U_over_W'] for r in stages),naming_removed_after_join_pct=100*median(1-r['R_over_U'] for r in stages),
        Forest_range=[min(r['Forest_primary_median_s'] for r in h1),max(r['Forest_primary_median_s'] for r in h1)],
        Forest_failed_A0=[r for r in h1 if r['A0_optimal']<6],h1_nonempty_forest=sum(r['forest_edges']>0 for r in h1))
    (out/'review_summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('out',type=Path);a=p.parse_args();main(a.root,a.out)
