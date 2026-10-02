"""Recheck primary representations, costs, statuses and aggregate records."""
import argparse
from collections import Counter, defaultdict, OrderedDict
import csv
from fractions import Fraction
import hashlib
import importlib.metadata
import json
from pathlib import Path
from statistics import median
import sys

from common import ROOT, WORK, RECORDS
sys.path.insert(0,str(ROOT/'runtime/primary'))
import checker


from common import read
def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False),encoding='utf-8')
def csv_write(p,rows):
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with Path(p).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)


def compare(ref,new):
    ratio=median(ref)/median(new)
    label='improved' if ratio>1.05 and max(new)<min(ref) else 'regressed' if ratio<1/1.05 and max(ref)<min(new) else 'unresolved'
    return ratio,label


def audit(frozen,run,out):
    out.mkdir(parents=True,exist_ok=False)
    f2=read(ROOT/'protocol/settings.json');plan=read(ROOT/'protocol/primary.json')
    receipt=read(run/'execution_receipt.json');f3=read(ROOT/'data/inputs.json')
    assert receipt['rows_sha256']==digest(run/'rows.jsonl')
    evidence={str(run/'rows.jsonl'):digest(run/'rows.jsonl')}
    acquisition=read(ROOT/'data/sources.json')
    for source in acquisition['sources']:
        for item in source['files']:
            assert digest(ROOT/'data/sources'/source['package']/item['path'])==item['sha256']
    inputs={(x['distribution'],x['representation'],x['target_nodes']):x for x in f3['inputs']}
    for x in f3['inputs']:
        if x['status']=='READY':assert digest(x['case_file'])==x['sha256']
    monitors=[json.loads(s) for s in (run/'rows.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(monitors)==len(plan['slots'])==receipt['retained_rows']
    assert [r['slot'] for r in monitors]==list(range(len(monitors)))
    rows=[];profiles={};bounds=defaultdict(list);optima=defaultdict(set);costs=defaultdict(list)
    case=None;loaded_case=None;verified=0;raw_count=0;errors=[];check_cache=OrderedDict();cache_bytes=0;cache_hits=0
    for mon,slot in zip(monitors,plan['slots']):
        assert all(mon[k]==slot[k] for k in ('slot','condition','distribution','version','representation','target_nodes','h','repeat','method'))
        key=(mon['distribution'],mon['representation'],mon['target_nodes']);entry=inputs[key]
        row={k:mon[k] for k in ('slot','condition','distribution','version','representation','target_nodes','h','repeat','method','status')}
        row.update(input_status=entry['status'],actual_nodes=entry.get('nodes'),target_reached=entry.get('target_reached'),
                   alias_of=entry.get('alias_of'),valid_return=bool(mon.get('valid_return')),attempted=bool(mon.get('raw_file')),
                   process_seconds=mon.get('wall_seconds'),peak_sampled_rss_bytes=mon.get('peak_sampled_rss_bytes'),
                   last_phase=mon.get('last_observed',{}).get('phase'),process_limit_reason=mon.get('process_limit_reason'),
                   method_limit_seconds=f2['limits']['method_seconds'],rss_limit_mib=f2['limits']['rss_mib'],
                   prepare_limit_seconds=f2['limits']['prepare_seconds'],check_limit_seconds=f2['limits']['check_seconds'],
                   applied_process_limit_seconds=mon.get('limits',{}).get('process_seconds'),
                   preparation_status=entry.get('preparation_status'))
        row['last_observed_bound_numeric']=mon.get('last_observed',{}).get('last_bound_numeric')
        raw_path=Path(mon['raw_file']) if mon.get('raw_file') else None
        if raw_path and raw_path.exists():
            raw_count+=1;raw=read(raw_path);evidence[str(raw_path)]=digest(raw_path)
            assert raw['method']==mon['method'] and raw['h']==mon['h']
            row.update(raw_file=str(raw_path),raw_sha256=evidence[str(raw_path)],worker_status=raw['status'],
                cost=raw.get('cost'),bound_numeric=raw.get('bound_numeric'),gap_numeric=raw.get('gap_numeric'),
                bound_exact_analytic=raw.get('bound_exact_analytic'),bound_exact_theorem=raw.get('bound_exact_theorem'),
                error=raw.get('error'),raw_valid_return=raw.get('valid_return',False),
                unique_subterms=raw.get('unique_subterms'),joins=raw.get('joins'))
            for k,v in raw.get('timing',{}).items():row['seconds_'+k]=v
            for k,v in raw.get('profile',{}).items():row['profile_'+k]=v
            if raw.get('profile'):
                row['residual_candidates']=raw['profile']['constraints']-raw['profile']['variables']
            phase=raw.get('telemetry',{}).get('phase_seconds',{})
            for k in ('imports','input_load','common_intern','external_check','preprocess_count_closure','preprocess_interval'):
                row['phase_seconds_'+k]=phase.get(k)
            parts=raw.get('parts',[])
            nodecounts=[p.get('mip_node_count') for p in parts]
            row['mip_node_count_sum']=sum(nodecounts) if parts and all(x is not None for x in nodecounts) else None
            row['mip_node_count_missing_parts']=sum(x is None for x in nodecounts)
            row['model_nonzeros_sum']=sum(p['nonzeros'] for p in parts) if parts and all('nonzeros' in p for p in parts) else None
            row['part_statuses']=json.dumps(dict(Counter(p['status'] for p in parts)),sort_keys=True)
            if 'encoding' in raw:
                if loaded_case!=entry['case_file']:
                    case=read(entry['case_file']);loaded_case=entry['case_file'];check_cache=OrderedDict();cache_bytes=0
                encoded=json.dumps(raw['encoding'],sort_keys=True,separators=(',',':'))
                ch=hashlib.sha256(encoded.encode()).hexdigest();cachekey=(raw['h'],ch)
                # Cache by exact canonical JSON.
                saved=check_cache.get(cachekey)
                if saved is not None and saved[0]==encoded:
                    verdict=saved[1];cache_hits+=1;check_cache.move_to_end(cachekey)
                else:
                    verdict=checker.check(case,raw['h'],raw['encoding'])
                    if len(encoded)<=64*1024*1024:
                        if cachekey in check_cache:cache_bytes-=len(check_cache.pop(cachekey)[0])
                        while check_cache and cache_bytes+len(encoded)>64*1024*1024:
                            _,removed=check_cache.popitem(last=False);cache_bytes-=len(removed[0])
                        check_cache[cachekey]=(encoded,verdict);cache_bytes+=len(encoded)
                row['audit_witness_ok']=verdict['ok'];verified+=1
                if not verdict['ok'] or Fraction(verdict['cost'])!=Fraction(raw['cost']):
                    errors.append({'slot':row['slot'],'issue':'WITNESS_OR_COST','verdict':verdict})
                if row['valid_return']:
                    assert verdict['ok'] and raw['valid_return'] and mon['returncode']==0
                    assert raw['timing']['primary']<=f2['limits']['method_seconds']
                    c=Fraction(raw['cost']);costs[row['condition']].append(c)
                    if raw['status'] in ('optimal_numerical','THEOREM_EXACT'):optima[row['condition']].add(c)
                    if raw.get('bound_numeric') is not None:bounds[row['condition']].append(float(raw['bound_numeric']))
                    if raw.get('bound_exact_analytic') is not None:
                        assert Fraction(raw['bound_exact_analytic'])<=c
                    if raw['status']=='optimal_numerical' and parts:
                        assert all(p['status']=='optimal_numerical' for p in parts)
                        parts_cost=Fraction(raw['profile']['fixed_cost'])+sum(Fraction(p['incumbent_scaled'],Fraction(raw['h']).denominator) for p in parts)
                        assert parts_cost==c
            elif row['valid_return']:raise AssertionError('valid return missing encoding')
            if raw.get('profile') and row['method'] in ('A1','A2'):
                profile=raw['profile'];sig=tuple(profile[k] for k in ('residual_signature','variables','constraints','fixed_cost','components','max_component_candidates'))
                previous=profiles.setdefault(row['condition'],sig);assert previous==sig
            del raw
        elif row['valid_return']:raise AssertionError('valid return missing raw file')
        row['numeric_optimal']=row['valid_return'] and row['status']=='optimal_numerical'
        row['theorem_exact']=row['valid_return'] and row['status']=='THEOREM_EXACT'
        rows.append(row)
        if len(rows)%100==0:print('audited',len(rows),flush=True)
    for condition,values in optima.items():
        if len(values)!=1:errors.append({'condition':condition,'issue':'INCOMPATIBLE_OPTIMA','costs':list(map(str,values))})
        if values and min(costs[condition])<min(values):errors.append({'condition':condition,'issue':'FEASIBLE_BELOW_NUMERIC_OPTIMUM'})
    for condition,values in bounds.items():
        if values and costs[condition] and max(values)>float(min(costs[condition]))+1e-4:
            errors.append({'condition':condition,'issue':'LOWER_ABOVE_FEASIBLE_COST','lower':max(values)})
    grouped=defaultdict(list)
    for row in rows:grouped[(row['condition'],row['method'])].append(row)
    comparisons=[]
    for condition in sorted({r['condition'] for r in rows}):
        for ref,new in [('A0','A1'),('A1','A2')]:
            a=grouped.get((condition,ref),[]);b=grouped.get((condition,new),[])
            if not a or not b:continue
            c={k:a[0][k] for k in ('condition','distribution','representation','target_nodes','actual_nodes','h','input_status')}
            c.update(comparison=ref+'/'+new,eligible=False,reason='not_six_valid_numeric_optima',
                     residual_candidates=next((r.get('residual_candidates') for r in b if r.get('residual_candidates') is not None),None),
                     max_component_candidates=next((r.get('profile_max_component_candidates') for r in b if r.get('profile_max_component_candidates') is not None),None))
            if len(a)==len(b)==6 and all(r['numeric_optimal'] for r in a+b) and len({r['cost'] for r in a+b})==1:
                ratio,label=compare([r['seconds_primary'] for r in a],[r['seconds_primary'] for r in b])
                c.update(eligible=True,reason='',ratio=ratio,classification=label,
                    ref_median_seconds=median(r['seconds_primary'] for r in a),new_median_seconds=median(r['seconds_primary'] for r in b))
                for method,rr in [('ref',a),('new',b)]:
                    for stage in ('preprocess','model','solver','interpret','reconstruct'):
                        c[method+'_'+stage+'_median_seconds']=median(r['seconds_'+stage] for r in rr)
            comparisons.append(c)
    completion=[]
    for method in sorted({r['method'] for r in rows}):
        rr=[r for r in rows if r['method']==method]
        completion.append({'method':method,'requested':len(rr),'aliases':sum(r['status']=='ALIAS_NOT_EXECUTED' for r in rr),
            'unique_executable':sum(r['input_status']=='READY' for r in rr),'attempted':sum(r['attempted'] for r in rr),
            'not_run_global_budget':sum(r['status']=='NOT_RUN_GLOBAL_BUDGET' for r in rr),
            'input_unavailable':sum(r['input_status'] not in ('READY','ALIAS_IDENTICAL_PREFIX') for r in rr),
            'invalid_attempts':sum(r['attempted'] and not r['valid_return'] for r in rr),
            'valid_returns':sum(r['valid_return'] for r in rr),'numeric_optimal':sum(r['numeric_optimal'] for r in rr),
            'theorem_exact':sum(r['theorem_exact'] for r in rr),'statuses':dict(Counter(r['status'] for r in rr))})
    strata=[]
    for cmp in ('A0/A1','A1/A2'):
        for source in ['ALL']+[s['distribution'] for s in f2['sources']]:
            for subset in ('ALL','residual_candidates_ge_10','actual_nodes_ge_1000000'):
                cc=[c for c in comparisons if c['comparison']==cmp and c['eligible'] and (source=='ALL' or c['distribution']==source)
                    and (subset!='residual_candidates_ge_10' or c['residual_candidates']>=10)
                    and (subset!='actual_nodes_ge_1000000' or c['actual_nodes']>=1000000)]
                strata.append({'comparison':cmp,'source':source,'subset':subset,'eligible_conditions':len(cc),
                    'median_ratio':median(c['ratio'] for c in cc) if cc else None,'classifications':dict(Counter(c['classification'] for c in cc))})
    quality=[]
    for (condition,method),rr in grouped.items():
        valid=[r for r in rr if r['valid_return']]
        known=next(iter(optima[condition])) if len(optima[condition])==1 else None
        q={k:rr[0][k] for k in ('condition','distribution','representation','target_nodes','actual_nodes','h','method','input_status')}
        q.update(valid_runs=len(valid),known_optimum=str(known) if known is not None else None,
            known_optimum_status='theorem_supported' if any(r['theorem_exact'] for r in rows if r['condition']==condition) else 'numeric_only' if known is not None else 'unavailable',
            converged_greedy_runs=sum(r['status']=='FEASIBLE' for r in valid) if method.startswith('Greedy') else None,
            costs=json.dumps(dict(Counter(r['cost'] for r in valid))),
            max_relative_error_to_known_optimum=float(max(Fraction(r['cost'])-known for r in valid)/max(Fraction(1),abs(known))) if valid and known is not None else None,
            max_converged_greedy_relative_error=float(max(Fraction(r['cost'])-known for r in valid if r['status']=='FEASIBLE')/max(Fraction(1),abs(known))) if known is not None and method.startswith('Greedy') and any(r['status']=='FEASIBLE' for r in valid) else None)
        quality.append(q)
    failure_phases=Counter((r['method'],r['status'],r.get('last_phase')) for r in rows if r['attempted'] and not r['valid_return'])
    summary={'status':'PASS' if not errors else 'FAIL','requested_slots':len(rows),'attempted':sum(r['attempted'] for r in rows),
        'valid_returns':sum(r['valid_return'] for r in rows),'raw_outputs_read':raw_count,'witnesses_checked':verified,
        'byte_identical_check_reuses':cache_hits,'direct_checker_calls':verified-cache_hits,
        'input_statuses':dict(Counter(x['status'] for x in f3['inputs'])),'statuses':dict(Counter(r['status'] for r in rows)),
        'completion':completion,'strata':strata,'errors':errors,'runtime_wall_seconds':receipt['wall_seconds'],
        'failure_phases':[{'method':k[0],'status':k[1],'last_observed_phase':k[2],'count':n} for k,n in failure_phases.items()],
        'interpretation':'Numerical MILP status; exact feasibility and cost checks by a separate same-project checker. Paired ratios require six complete, equal-cost optimal returns per method. All slots are retained; comparisons are descriptive.'}
    csv_write(out/'all_slots.csv',rows);csv_write(out/'comparisons.csv',comparisons);csv_write(out/'quality.csv',quality)
    dump(out/'summary.json',summary);dump(out/'evidence_hashes.json',evidence)
    dump(out/'input_table.json',f3['inputs']);dump(out/'complete_rows.json',rows)
    print(json.dumps({k:summary[k] for k in ('status','requested_slots','attempted','valid_returns','witnesses_checked','statuses')}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('freeze_directory',type=Path);p.add_argument('run_directory',type=Path);p.add_argument('output_directory',type=Path)
    a=p.parse_args();audit(a.freeze_directory,a.run_directory,a.output_directory)
