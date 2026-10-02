"""Recompute headline completion and paired timing from the released tables."""
from collections import Counter
from fractions import Fraction
from pathlib import Path
from statistics import median
import csv
import json

ROOT=Path(__file__).resolve().parent


def read(name):
    with (ROOT/name).open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def completed(rows, method):
    selected=[r for r in rows if r['method']==method]
    counts=Counter(r['condition'] for r in selected
                   if r['valid_return']=='True' and r['numeric_optimal']=='True')
    return sum(n==6 for n in counts.values())


def summary():
    slots=read('results/primary/all_slots.csv')
    high=[r for r in slots if r['input_status']=='READY' and Fraction(r['h'])>1]
    normalization=read('results/tables/S9_normalization_runs.csv')
    paired=read('results/tables/S3_paired_times.csv')
    primary_ratios=[float(r['ratio']) for r in paired if r['eligible']=='True'
                    and r['comparison']=='Global MILP baseline / Preprocessed global MILP']
    pairs=read('results/tables/S10_normalization_pairs.csv')
    ablation=[]
    for reference,comparison in [('Global MILP baseline','Join-restricted MILP'),
                                 ('Join-restricted MILP','Preprocessed global MILP')]:
        selected=[r for r in pairs if r['reference']==reference and r['comparison']==comparison and r['eligible']=='True']
        ablation.append({'reference':reference,'comparison':comparison,'eligible':len(selected),
                         'median_ratio':median(float(r['ratio']) for r in selected),
                         'verdicts':dict(Counter(r['verdict'] for r in selected))})
    return {'primary':{'planned_slots':len(slots),'attempted':sum(r['attempted']=='True' for r in slots),
                       'complete_conditions':{m:completed(high,m) for m in ['A0','A1','A2']},
                       'eligible_timing_conditions':len(primary_ratios),'median_speedup':median(primary_ratios)},
            'normalization':{'runs':len(normalization),'complete_conditions':{m:completed(normalization,m) for m in
                ['Global MILP baseline','Join-restricted MILP','Preprocessed global MILP']},'pairs':ablation}}


if __name__=='__main__':
    print(json.dumps(summary(),indent=2))
