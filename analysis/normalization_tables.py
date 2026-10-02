"""Full roster, eligibility, exact cost agreement, and descriptive paired tables."""
import csv,json
from collections import Counter,defaultdict
from fractions import Fraction
from pathlib import Path
from statistics import median
from common import read,sha,atomic_json,WORK
from common import ROOT
import sys
sys.path.insert(0,str(ROOT/'code'))
import checker
def csvout(path,rows):
    if not rows:rows=[{'none':True}]
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)));w.writeheader();w.writerows(rows)
def analyze(planpath,data):
    out=WORK/'normalization';out.mkdir(parents=True,exist_ok=False)
    plan=read(planpath);rows=[json.loads(x) for x in (data/'rows.jsonl').read_text().splitlines()]
    assert len(rows)==len(plan['slots']) and [r['slot'] for r in rows]==list(range(len(rows)))
    receipt=read(data/'execution_receipt.json');assert sha(data/'rows.jsonl')==receipt['rows_sha256'] and sha(planpath)==receipt['plan_sha256']
    runs=[];by=defaultdict(list);fail=Counter();hashes={}
    checked={};case=None;case_id=None;witnesses=0
    for r,s in zip(rows,plan['slots']):
        assert all(r[k]==s[k] for k in ('condition','input','method','h','repeat'))
        rawpath=Path(r['raw_file']);raw=read(rawpath) if rawpath.exists() else {}
        if raw:hashes[str(rawpath)]=sha(rawpath)
        optimal=r['valid_return'] and r['status']=='optimal_numerical'
        if r['valid_return']:
            assert raw['check']['ok'] and raw['cost']==r['cost'] and raw['timing']['primary']<=plan['limits']['method']
            assert raw['bound_numeric']<=float(Fraction(raw['cost']))+1e-4
            entry=r['input']
            if case_id!=entry['id']:
                assert sha(entry['case_file'])==entry['sha256']
                case=read(entry['case_file']);case_id=entry['id'];checked={}
            encoded=json.dumps(raw['encoding'],sort_keys=True,separators=(',',':'))
            signature=(r['h'],encoded)
            if signature not in checked:
                verdict=checker.check(case,r['h'],raw['encoding'])
                assert verdict['ok'] and Fraction(verdict['cost'])==Fraction(raw['cost'])
                checked[signature]=verdict['cost'];witnesses+=1
            else:assert Fraction(checked[signature])==Fraction(raw['cost'])
        if not optimal:fail[r['method'],r['last_observed'].get('phase','unknown'),r['status']]+=1
        profile=raw.get('profile',{});e=r['input']
        rr={k:r[k] for k in ('slot','condition','method','h','repeat','status','valid_return')}
        rr.update(source=e['distribution'],representation=e['representation'],target_nodes=e['target_nodes'],N=e['nodes'],numeric_optimal=optimal,cost=r.get('cost'),
                  bound=raw.get('bound_numeric'),gap=raw.get('gap_numeric'),process_wall_s=r['wall_seconds'],peak_rss_mib=r['peak_sampled_rss_bytes']/1024**2,
                  last_observed_phase=r['last_observed'].get('phase'),raw_file=r['raw_file'])
        rr.update({f'time_{k}':v for k,v in raw.get('timing',{}).items()});rr.update({f'profile_{k}':v for k,v in profile.items()})
        runs.append(rr);by[r['condition'],r['method']].append(rr)
    methods=['A0','A0-U','A1'];conditions=[];pairs=[];summary={}
    for cid in range(85):
        group=[x for m in methods for x in by[cid,m]];assert len(group)==18
        costs={Fraction(x['cost']) for x in group if x['numeric_optimal']};assert len(costs)<=1,('optimal cost disagreement',cid,costs)
        if costs:
            opt=next(iter(costs));assert all(Fraction(x['cost'])>=opt for x in group if x['valid_return'])
        for m in methods:
            rr=by[cid,m];assert len(rr)==6
            first=rr[0];valid=[r for r in rr if r['valid_return']];ok=all(r['numeric_optimal'] for r in rr)
            cr={k:first[k] for k in ('condition','source','representation','target_nodes','N','h','method')}
            cr.update(attempted=6,valid=len(valid),optimal=sum(r['numeric_optimal'] for r in rr),complete=ok,statuses=json.dumps(dict(Counter(r['status'] for r in rr))),
                      cost=str(next(iter(costs))) if costs else None,peak_rss_mib_median=median(r['peak_rss_mib'] for r in rr),process_wall_median=median(r['process_wall_s'] for r in rr))
            for k in ('primary','preprocess','model','solver','interpret','reconstruct'):
                cr['valid_time_'+k+'_median']=median(r['time_'+k] for r in valid) if valid else None
            for k in ('initial_candidates','joins','forced','excluded','variables','constraints','components','max_component_candidates','fixed_count_vertices'):
                vals={r.get('profile_'+k) for r in rr if r.get('profile_'+k) is not None};assert len(vals)<=1
                cr[k]=next(iter(vals)) if vals else None
            conditions.append(cr)
        for ref,comp in [('A0','A0-U'),('A0-U','A1'),('A0','A1')]:
            aa,bb=by[cid,ref],by[cid,comp];eligible=all(r['numeric_optimal'] for r in aa+bb)
            pr={k:group[0][k] for k in ('condition','source','representation','target_nodes','N','h')};pr.update(reference=ref,comparison=comp,eligible=eligible,ratio=None,verdict='INELIGIBLE')
            if eligible:
                ta=[r['time_primary'] for r in aa];tb=[r['time_primary'] for r in bb];ratio=median(ta)/median(tb)
                verdict='IMPROVED' if ratio>1.05 and max(tb)<min(ta) else 'REGRESSED' if ratio<1/1.05 and max(ta)<min(tb) else 'UNRESOLVED'
                pr.update(ratio=ratio,verdict=verdict,rss_ratio=median(r['peak_rss_mib'] for r in aa)/median(r['peak_rss_mib'] for r in bb))
            pairs.append(pr)
    for m in methods:
        rr=[x for x in runs if x['method']==m]
        summary[m]=dict(attempted=len(rr),valid=sum(x['valid_return'] for x in rr),optimal_runs=sum(x['numeric_optimal'] for x in rr),complete_conditions=sum(x['complete'] for x in conditions if x['method']==m))
    paired=[]
    for ref,comp in [('A0','A0-U'),('A0-U','A1'),('A0','A1')]:
        for source in ['ALL','matplotlib','pydantic','aiohttp','jsonschema']:
            pp=[x for x in pairs if x['reference']==ref and x['comparison']==comp and (source=='ALL' or x['source']==source)]
            eligible=[x for x in pp if x['eligible']]
            paired.append(dict(reference=ref,comparison=comp,source=source,total=len(pp),eligible=len(eligible),ratio_median=median(x['ratio'] for x in eligible) if eligible else None,**dict(Counter(x['verdict'] for x in pp))))
    csvout(out/'runs.csv',runs);csvout(out/'conditions.csv',conditions);csvout(out/'pairs.csv',pairs);csvout(out/'paired_summary.csv',paired)
    csvout(out/'failures.csv',[dict(method=m,last_observed_phase=p,reason=s,count=n) for (m,p,s),n in sorted(fail.items())])
    atomic_json(out/'raw_hashes.json',hashes)
    joint=sum(all(r['numeric_optimal'] for m in methods for r in by[cid,m]) for cid in range(85))
    atomic_json(out/'audit.json',dict(status='PASS',rows=len(rows),conditions=85,joint_three_method_complete=joint,summary=summary,paired=paired,optimal_cost_agreement=True,all_valid_costs_not_below_best_optimum=True,raw_hashes_sha256=sha(out/'raw_hashes.json'),external_proof_review=False))
    atomic_json(out/'witness_checks.json',dict(status='PASS',direct_checks=witnesses))
if __name__=='__main__':
    import sys
    analyze(Path(sys.argv[1]),Path(sys.argv[2]))
