"""Descriptive final tables from already audited records, no benchmark reruns."""
import csv,json
from collections import defaultdict,Counter
from fractions import Fraction
from pathlib import Path
from statistics import median
import sys

from common import ROOT, WORK, RECORDS
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def csvread(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def mid(x):return median(x) if x else None
def grouped(rows,key):
    result=defaultdict(list)
    for r in rows:result[key(r)].append(r)
    return result
def table(p,rows):
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)));w.writeheader();w.writerows(rows)

def main():
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
    analysis=WORK/'comparison';assert read(analysis/'summary.json')['status']=='PASS'
    rr=read(WORK/'audit/complete_rows.json')
    high=[r for r in rr if r['input_status']=='READY' and Fraction(r['h'])>1]
    completion=[]
    for m,mm in grouped(high,lambda r:r['method']).items():
        cc=grouped(mm,lambda r:r['condition'])
        completion.append({'method':m,'attempted':len(mm),'valid':sum(r['valid_return'] for r in mm),
            'numeric_optimal':sum(r['numeric_optimal'] for r in mm),'all_six_valid_conditions':sum(all(r['valid_return'] for r in rows) for rows in cc.values()),
            'all_six_numeric_optimal_conditions':sum(all(r['numeric_optimal'] for r in rows) for rows in cc.values()),
            'statuses':json.dumps(dict(Counter(r['status'] for r in mm)))})
    table(out/'completion_high_h.csv',completion)
    pairs=csvread(analysis/'paired_times.csv');eligible=[r for r in pairs if r['eligible']=='True']
    pairtables=[]
    for (cmp,source),cc in grouped(eligible,lambda r:(r['comparison'],r['distribution'])).items():
        pairtables.append({'comparison':cmp,'source':source,'conditions':len(cc),'ratio_median':mid([float(r['ratio']) for r in cc]),
            'ratio_min':min(float(r['ratio']) for r in cc),'ratio_max':max(float(r['ratio']) for r in cc),
            'classifications':json.dumps(dict(Counter(r['classification'] for r in cc))),
            'RSS_ratio_median':mid([float(r['reference_peak_rss'])/float(r['new_peak_rss']) for r in cc]),
            'RSS_lower_new':sum(float(r['reference_peak_rss'])>float(r['new_peak_rss']) for r in cc)})
    table(out/'timing_by_source.csv',pairtables)
    quality=csvread(analysis/'quality.csv');hrows=[]
    for scope in ['all_ready','target_100k_matched']:
        for h in ['1','11/10','5/4','3/2','2','32']:
            cc=[r for r in quality if r['method']=='All-U' and r['h']==h and (scope=='all_ready' or int(r['target_nodes'])==100000)]
            gaps=[float(r['gap_percent_median']) for r in cc if r['gap_percent_median']]
            hrows.append({'scope':scope,'h':h,'conditions':len(cc),'known_optimum_conditions':len(gaps),
                          'AllU_gap_median_percent':mid(gaps),'AllU_gap_max_percent':max(gaps) if gaps else None})
    table(out/'all_u_gap_by_h.csv',hrows)
    details=[]
    for c,cc in grouped(high,lambda r:r['condition']).items():
        methods=grouped(cc,lambda r:r['method']);base={k:cc[0][k] for k in ['condition','distribution','representation','target_nodes','actual_nodes','h']}
        for m in ['A0','A1','A2']:
            mm=methods[m];valid=[r for r in mm if r['valid_return']]
            line=dict(base,method=m,valid=len(valid),optimal=sum(r['numeric_optimal'] for r in mm),
                      statuses=json.dumps(dict(Counter(r['status'] for r in mm))),rss_max_MiB=max(r['peak_sampled_rss_bytes'] for r in mm)/2**20)
            for stage in ['primary','preprocess','model','solver','interpret','reconstruct']:
                line[stage+'_median_seconds']=mid([r['seconds_'+stage] for r in valid if r.get('seconds_'+stage) is not None])
            for k in ['profile_variables','profile_constraints','profile_components','profile_max_component_candidates','residual_candidates']:
                vals=[r[k] for r in mm if r.get(k) is not None];line[k]=mid(vals)
            details.append(line)
    table(out/'all_high_h_phases.csv',details)
    failed=[r for r in details if r['optimal']<6];table(out/'incomplete_optimality_conditions.csv',failed)
    dr=csvread(analysis/'diagnostic_runs.csv');lp=[r for r in dr if r['method']=='LP-on']
    known=[r for r in lp if r['gap_reference_kind']=='numeric_integer_optimum']
    integral=[r for r in known if r['zero_gap_numeric']=='True']
    lpstats={'conditions':len(lp),'known_integer_optimum':len(known),'zero_objective_gap':len(integral),
        'positive_objective_gap':sum(float(r['full_objective_gap'])>1e-5 for r in known),
        'fractional_returned_vector':sum(float(r['lp_max_fractionality'])>1e-6 for r in lp),
        'full_gap_percent_median':mid([float(r['full_gap_percent']) for r in known]),
        'full_gap_percent_max':max(float(r['full_gap_percent']) for r in known),
        'residual_gap_percent_median':mid([float(r['residual_gap_percent']) for r in known]),
        'residual_gap_percent_max':max(float(r['residual_gap_percent']) for r in known),
        'unknown_integer_optimum':[r for r in lp if r['gap_reference_kind']!='numeric_integer_optimum']}
    rgreedy=[]
    for m in ['RG-add','RG-prune']:
        mm=[r for r in dr if r['method']==m];valid=[r for r in mm if r['valid_return']=='True'];cc=grouped(mm,lambda r:(r['input_id'],r['h']))
        full=[rows for rows in cc.values() if all(r['valid_return']=='True' and r['status']=='FEASIBLE' and r['quality_gap_percent']!='' for r in rows)]
        gaps=[max(float(r['quality_gap_percent']) for r in rows) for rows in full]
        rgreedy.append({'method':m,'attempted':len(mm),'valid_converged':len(valid),'complete_conditions_with_known_optimum':len(full),
                        'optimal_conditions':sum(g==0 for g in gaps),'gap_percent_median':mid(gaps),'gap_percent_max':max(gaps)})
    originalgreedy=[]
    for m in ['Greedy-add','Greedy-prune']:
        cc=grouped([r for r in high if r['method']==m],lambda r:r['condition'])
        full=[v for v in cc.values() if all(r['valid_return'] and r['status']=='FEASIBLE' for r in v)]
        qs={int(r['condition']):r for r in quality if r['method']==m}
        gaps=[float(qs[v[0]['condition']]['gap_percent_max']) for v in full if qs[v[0]['condition']]['gap_percent_max']]
        originalgreedy.append({'method':m,'all_six_converged_conditions':len(full),'known_optimum_conditions':len(gaps),'gap_percent_max':max(gaps) if gaps else None})
    allu=[r for r in eligible if r['comparison']=='All-U/A1'];a01=[r for r in eligible if r['comparison']=='A0/A1']
    summary={'completion':completion,'lp':lpstats,'residual_greedy':rgreedy,'original_greedy':originalgreedy,
        'A1_over_AllU_time_ratio_median':mid([1/float(r['ratio']) for r in allu]),
        'A1_minus_AllU_seconds_median':mid([float(r['additional_new_seconds']) for r in allu]),
        'A1_minus_AllU_seconds_max':max(float(r['additional_new_seconds']) for r in allu),
        'A0_over_A1_RSS_median':mid([float(r['reference_peak_rss'])/float(r['new_peak_rss']) for r in a01]),
        'A1_lower_RSS_conditions':sum(float(r['reference_peak_rss'])>float(r['new_peak_rss']) for r in a01),
        'max_sampled_RSS_MiB':max(r['peak_sampled_rss_bytes'] for r in rr if r['attempted'])/2**20}
    (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
