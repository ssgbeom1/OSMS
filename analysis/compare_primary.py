"""Build primary timing, quality and diagnostic comparisons."""
import argparse
from collections import Counter,defaultdict,OrderedDict
import csv
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
from statistics import median
import sys

from common import ROOT, WORK, RECORDS
sys.path.insert(0,str(ROOT/'runtime/primary'))
import checker


from common import read
def dump(p,x):Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False),encoding='utf-8')
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def writecsv(path,rows):
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
def timing(a,b,n):
    ratio=median(a)/median(b)
    return {'ratio':ratio,'reference_median':median(a),'new_median':median(b),
            'reference_min':min(a),'reference_max':max(a),'new_min':min(b),'new_max':max(b),
            'classification':'improved' if ratio>1.05 and max(b)<min(a) else 'regressed' if ratio<1/1.05 and max(a)<min(b) else 'unresolved','repeats':n}


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);args=p.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=False)
    mainaudit=WORK/'audit';assert read(mainaudit/'summary.json')['status']=='PASS'
    rows=read(mainaudit/'complete_rows.json')
    monitor={r['slot']:r for r in map(json.loads,(RECORDS/'primary/rows.jsonl').read_text().splitlines())}
    grouped=defaultdict(list)
    for r in rows:r['batch']=monitor[r['slot']]['execution_batch'];grouped[r['condition']].append(r)
    condition_table=[];paired=[];quality=[];roots=[];optima={};sourcecases={}
    for c,rr in grouped.items():
        info={k:rr[0][k] for k in ['condition','distribution','representation','target_nodes','actual_nodes','h','input_status']}
        by={m:[r for r in rr if r['method']==m] for m in {r['method'] for r in rr}}
        oo={Fraction(r['cost']) for r in rr if r['numeric_optimal'] or r['theorem_exact']};assert len(oo)<=1
        opt=next(iter(oo)) if oo else None
        if rr[0]['input_status']=='READY':
            key=(info['distribution'],info['representation'],info['target_nodes'],info['h']);optima[key]=opt;sourcecases[key]=rr
        line=dict(info,batches=','.join(sorted({r['batch'] for r in rr if r['attempted']})))
        for method,mm in by.items():
            valid=[r for r in mm if r['valid_return']]
            line[method+'_statuses']=json.dumps(dict(Counter(r['status'] for r in mm)))
            line[method+'_valid']=len(valid);line[method+'_optimal']=sum(r['numeric_optimal'] or r['theorem_exact'] for r in mm)
            line[method+'_primary_median']=median(r['seconds_primary'] for r in valid) if valid else None
            line[method+'_max_sampled_rss_MiB']=max((r['peak_sampled_rss_bytes']/2**20 for r in mm if r['attempted']),default=None)
            for stage in ['preprocess','model','solver','interpret','reconstruct']:
                vv=[r.get('seconds_'+stage) for r in valid if r.get('seconds_'+stage) is not None]
                line[method+'_'+stage+'_median']=median(vv) if vv else None
            if valid:
                q=dict(info,method=method,valid=len(valid),numeric_or_theorem_optimum=str(opt) if opt is not None else None,
                    costs=json.dumps(dict(Counter(r['cost'] for r in valid))),primary_median=median(r['seconds_primary'] for r in valid),
                    converged_greedy=sum(r['status']=='FEASIBLE' for r in valid) if 'Greedy' in method else None,
                    gap_percent_median=median(float((Fraction(r['cost'])-opt)/opt)*100 for r in valid) if opt else None,
                    gap_percent_max=max(float((Fraction(r['cost'])-opt)/opt)*100 for r in valid) if opt else None)
                quality.append(q)
        for ref,new in [('A0','A1'),('A1','A2'),('All-U','A1')]:
            if ref not in by or new not in by:continue
            a,b=by[ref],by[new];valid=all(r['valid_return'] for r in a+b);samebatch=len({r['batch'] for r in a+b})==1
            equal=valid and len({Fraction(r['cost']) for r in a+b})==1
            optimal=all(r['numeric_optimal'] for r in a+b)
            eligible=len(a)==len(b)==6 and valid and samebatch and (optimal and equal if ref!='All-U' else all(r['numeric_optimal'] for r in b))
            entry=dict(info,comparison=ref+'/'+new,eligible=eligible,same_batch=samebatch,equal_cost=equal)
            if eligible:
                entry.update(timing([r['seconds_primary'] for r in a],[r['seconds_primary'] for r in b],6))
                entry.update(additional_new_seconds=median(r['seconds_primary'] for r in b)-median(r['seconds_primary'] for r in a),
                    reference_peak_rss=max(r['peak_sampled_rss_bytes'] for r in a),new_peak_rss=max(r['peak_sampled_rss_bytes'] for r in b))
            paired.append(entry)
        if 'A1' in by:
            valid=[r for r in by['A1'] if r['valid_return']]
            if valid:
                first=min(valid,key=lambda r:r['repeat']);raw=read(first['raw_file']);log=Path(first['raw_file']).with_suffix('.stdout.txt').read_text()
                model=re.search(r'Solving MIP model with:\s+(\d+) rows\s+(\d+) cols',log)
                separation=re.search(r'\n\s+(\d+) \(separation\)',log)
                roots.append(dict(info,raw=first['raw_file'],repeat=first['repeat'],status=first['status'],
                    solver_invoked=bool(raw.get('parts')),
                    nrows_before=raw['profile']['constraints'],nvars_before=raw['profile']['variables'],
                    nrows_after=int(model[1]) if model else None,nvars_after=int(model[2]) if model else None,
                    separation_lp_iterations=int(separation[1]) if separation else None,
                    nodes=first['mip_node_count_sum'],residual_candidates=first['residual_candidates'],
                    max_component_candidates=first['profile_max_component_candidates']))
        condition_table.append(line)
    writecsv(out/'all_conditions.csv',condition_table);writecsv(out/'paired_times.csv',paired);writecsv(out/'quality.csv',quality);writecsv(out/'root_logs.csv',roots)
    diagroot=RECORDS/'diagnostics';receipt=read(diagroot/'receipt.json')
    planpath=ROOT/'protocol/diagnostics.json';seal=read(planpath)
    assert sha(planpath)==receipt['plan_sha256'] and sha(diagroot/'rows.jsonl')==receipt['rows_sha256']
    diags=[];errors=[];cache=OrderedDict();cachebytes=0;casepath=None;case=None;checks=0;reuses=0;casekeys={}
    monitors=list(map(json.loads,(diagroot/'rows.jsonl').read_text().splitlines()));assert len(monitors)==len(seal['slots'])==935
    for i,(mon,slot) in enumerate(zip(monitors,seal['slots'])):
        assert mon['slot']==i and all(mon[k]==slot[k] for k in ['input','h','method','repeat','kind'])
        inp=mon['input'];key=(inp['distribution'],inp['representation'],inp['target_nodes'],mon['h']);opt=optima[key]
        row={k:mon[k] for k in ['slot','h','method','repeat','kind','status','valid_return','raw_file']}
        row.update(input_id=inp['id'],distribution=inp['distribution'],representation=inp['representation'],target_nodes=inp['target_nodes'],actual_nodes=inp['nodes'],
                   known_integer_optimum=str(opt) if opt is not None else None,process_seconds=mon['wall_seconds'],peak_sampled_rss_bytes=mon['peak_sampled_rss_bytes'])
        path=Path(mon['raw_file'])
        if path.exists():
            raw=read(path);row['raw_sha256']=sha(path)
            for k in ['cost','lp_status','lp_full_objective_numeric','lp_residual_objective_numeric','lp_max_fractionality','lp_feasibility_violation','solver_invoked','error']:
                row[k]=raw.get(k)
            for k,v in raw.get('timing',{}).items():row['seconds_'+k]=v
            for k,v in raw.get('profile',{}).items():row['profile_'+k]=v
            if raw.get('profile'):
                reference=next((r for r in sourcecases[key] if r['method']=='A1' and r.get('profile_residual_signature')),None)
                if reference:assert raw['profile']['residual_signature']==reference['profile_residual_signature']
            if 'encoding' in raw:
                if casepath!=inp['case_file']:
                    assert sha(inp['case_file'])==inp['sha256'];case=read(inp['case_file']);casepath=inp['case_file'];cache.clear();cachebytes=0
                encoded=json.dumps(raw['encoding'],sort_keys=True,separators=(',',':'));ck=(mon['h'],hashlib.sha256(encoded.encode()).hexdigest());saved=cache.get(ck)
                if saved and saved[0]==encoded:verdict=saved[1];reuses+=1
                else:
                    verdict=checker.check(case,mon['h'],raw['encoding']);checks+=1
                    if len(encoded)<=64*1024*1024:
                        while cache and cachebytes+len(encoded)>64*1024*1024:
                            _,vv=cache.popitem(last=False);cachebytes-=len(vv[0])
                        cache[ck]=(encoded,verdict);cachebytes+=len(encoded)
                assert verdict['ok'] and Fraction(verdict['cost'])==Fraction(raw['cost'])
                row['witness_checked']=True
                if opt is not None:
                    gap=Fraction(raw['cost'])-opt;assert gap>=0
                    row['quality_gap_percent']=float(gap/opt)*100
                    if mon['method']=='A1' and mon['status']=='optimal_numerical':assert gap==0
            if mon['kind']=='LP' and mon['valid_return'] and opt is not None:
                value=raw['lp_full_objective_numeric'];difference=float(opt)-value
                if difference<-1e-5:errors.append({'slot':i,'issue':'LP_ABOVE_INTEGER_OPTIMUM','difference':difference})
                row.update(full_objective_gap=difference,full_gap_percent=difference/float(opt)*100,
                    residual_integer_optimum=float(opt-Fraction(raw['profile']['fixed_cost'])),zero_gap_numeric=abs(difference)<=1e-5)
            if mon['valid_return']:assert raw['valid_return'] and raw['timing']['primary']<=30
        elif mon['valid_return']:raise AssertionError('missing valid diagnostic raw')
        diags.append(row)
        if i%100==0:print('diagnostic audited',i,flush=True)
    dd=defaultdict(list)
    for r in diags:dd[(r['input_id'],r['h'])].append(r)
    lp=[];ablation=[]
    for (ident,h),rr in dd.items():
        certified={Fraction(r['known_integer_optimum']) for r in rr if r.get('known_integer_optimum') is not None}
        certified|={Fraction(r['cost']) for r in rr if r['method']=='A1' and r['valid_return'] and r['status']=='optimal_numerical'}
        assert len(certified)<=1
        optimum=next(iter(certified)) if certified else None
        feasible=[Fraction(r['cost']) for r in rr if r.get('cost') is not None and r['valid_return'] and r['kind']=='ablation']
        if optimum is not None:assert all(v>=optimum for v in feasible)
        for r in rr:
            if optimum is not None and r['valid_return'] and r.get('cost') is not None:
                r['quality_gap_percent']=float((Fraction(r['cost'])-optimum)/optimum)*100
            if r['kind']=='LP' and r['valid_return']:
                reference=optimum if optimum is not None else min(feasible) if feasible else None
                r['gap_reference_kind']='numeric_integer_optimum' if optimum is not None else 'best_feasible_diagnostic' if reference is not None else 'unavailable'
                if reference is not None:
                    difference=float(reference)-r['lp_full_objective_numeric']
                    if difference<-1e-5:errors.append({'input':ident,'h':h,'issue':'LP_ABOVE_CHECKED_FEASIBLE','difference':difference})
                    r['reference_minus_lp_numeric']=difference
                    if optimum is not None:
                        residual_opt=float(optimum-Fraction(r['profile_fixed_cost']))
                        r.update(full_objective_gap=difference,full_gap_percent=difference/float(optimum)*100,zero_gap_numeric=abs(difference)<=1e-5,
                                 residual_integer_optimum=residual_opt,residual_gap_percent=difference/max(1.0,abs(residual_opt))*100)
        pp={r['method']:r for r in rr if r['kind']=='LP'}
        if all(pp[m]['valid_return'] for m in ['LP-on','LP-off']):
            delta=pp['LP-on']['lp_full_objective_numeric']-pp['LP-off']['lp_full_objective_numeric']
            if abs(delta)>1e-5:errors.append({'input':ident,'h':h,'issue':'LP_PRESOLVE_DISAGREEMENT','difference':delta})
        lp.append({'input_id':ident,'h':h,**{m+'_'+k:r.get(k) for m,r in pp.items() for k in ['status','valid_return','lp_full_objective_numeric','lp_residual_objective_numeric','profile_fixed_cost','residual_integer_optimum','residual_gap_percent','full_objective_gap','full_gap_percent','lp_max_fractionality','zero_gap_numeric','gap_reference_kind','reference_minus_lp_numeric']}})
        for new in ['RG-add','RG-prune']:
            a=[r for r in rr if r['method']=='A1'];b=[r for r in rr if r['method']==new]
            valid=len(a)==len(b)==3 and all(r['valid_return'] for r in a+b)
            equal=valid and len({Fraction(r['cost']) for r in a+b})==1
            converged=valid and all(r['status']=='optimal_numerical' for r in a) and all(r['status']=='FEASIBLE' for r in b)
            line={'input_id':ident,'h':h,'comparison':'A1/'+new,'valid_all':valid,'equal_cost':equal,'eligible':bool(valid and equal and converged)}
            if valid:line.update(greedy_gap_percent=max(r['quality_gap_percent'] for r in b) if all(r.get('quality_gap_percent') is not None for r in b) else None,reference_median_all_valid=median(r['seconds_primary'] for r in a),new_median_all_valid=median(r['seconds_primary'] for r in b))
            if line['eligible']:line.update(timing([r['seconds_primary'] for r in a],[r['seconds_primary'] for r in b],3))
            ablation.append(line)
    writecsv(out/'diagnostic_runs.csv',diags);writecsv(out/'lp_comparison.csv',lp);writecsv(out/'residual_ablation.csv',ablation)
    summary={'status':'PASS' if not errors else 'FAIL','primary_audit':read(mainaudit/'summary.json')['status'],
        'primary_requested':len(rows),'primary_valid':sum(r['valid_return'] for r in rows),'primary_statuses':dict(Counter(r['status'] for r in rows)),
        'diagnostics':len(diags),'diagnostic_statuses':dict(Counter(r['status'] for r in diags)),
        'direct_witness_checks':checks,'byte_identical_reuses':reuses,'errors':errors,
        'timing_scope':'same-batch pairs only in primary summary; exposed-input post-hoc diagnostic ablation',
        'paired_summary':[],'ablation_summary':[]}
    for cmp in ['A0/A1','A1/A2','All-U/A1']:
        cc=[r for r in paired if r['comparison']==cmp and r['eligible']]
        summary['paired_summary'].append({'comparison':cmp,'conditions':len(cc),'median_ratio':median(r['ratio'] for r in cc) if cc else None,'classifications':dict(Counter(r['classification'] for r in cc))})
    for cmp in ['A1/RG-add','A1/RG-prune']:
        cc=[r for r in ablation if r['comparison']==cmp and r['eligible']]
        summary['ablation_summary'].append({'comparison':cmp,'conditions':len(cc),'median_ratio':median(r['ratio'] for r in cc) if cc else None,'classifications':dict(Counter(r['classification'] for r in cc))})
    dump(out/'summary.json',summary);print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
