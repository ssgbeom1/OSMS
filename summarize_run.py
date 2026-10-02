"""Check and summarize newly generated runs, including partial schedules."""
from pathlib import Path
from fractions import Fraction
from collections import Counter
import argparse
import csv
import json
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'code'))
sys.path.insert(0, str(ROOT/'analysis'))
import checker
from common import read, sha, atomic_json


def reference_costs():
    with (ROOT/'results/primary/all_slots.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    result = {}
    for row in rows:
        if row['numeric_optimal']=='True' or row['theorem_exact']=='True':
            key = (row['distribution'], row['representation'], int(row['target_nodes']), Fraction(row['h']))
            cost = Fraction(row['cost'])
            if key in result and result[key]!=cost:
                raise ValueError('Conflicting reference costs')
            result[key] = cost
    return result


def summarize(records, out):
    records = records.resolve()
    out = out.resolve()
    records.relative_to(ROOT)
    out.relative_to(ROOT)
    if not records.is_dir():
        raise ValueError('Records directory does not exist')
    suites = [s for s in ['primary','diagnostics','normalization'] if (records/s/'rows.jsonl').is_file()]
    if not suites:
        raise ValueError('No run rosters found')
    out.mkdir(parents=True, exist_ok=False)
    inputs = {(x['distribution'],x['representation'],x['target_nodes']):x for x in read(ROOT/'data/inputs.json')['inputs']}
    references = reference_costs()
    rows, errors, coverage = [], [], []
    checked, matches = 0, 0
    case_path, case = None, None
    for suite in suites:
        source = [json.loads(s) for s in (records/suite/'rows.jsonl').read_text().splitlines() if s.strip()]
        plan = read(ROOT/'protocol'/f'{suite}.json')['slots']
        if len(source)>len(plan) or [r['slot'] for r in source]!=list(range(len(source))):
            raise ValueError('Invalid roster prefix: '+suite)
        coverage.append(dict(suite=suite,recorded=len(source),planned=len(plan),complete=len(source)==len(plan)))
        for row in source:
            expected = plan[row['slot']]
            if any(row.get(k)!=v for k,v in expected.items() if k!='status'):
                raise ValueError('Roster differs from protocol: '+suite+' '+str(row['slot']))
            item = row.get('input') or inputs[row['distribution'],row['representation'],row['target_nodes']]
            key = (item['distribution'],item['representation'],item['target_nodes'],Fraction(row['h']))
            ref = references.get(key)
            entry = dict(suite=suite,slot=row['slot'],input=item['id'],h=row['h'],method=row['method'],
                         status=row['status'],valid_return=row.get('valid_return',False),
                         cost=row.get('cost'),reference_optimum=str(ref) if ref is not None else None,
                         gap_percent=None,primary_seconds=None,process_seconds=row.get('wall_seconds'),
                         peak_sampled_rss_bytes=row.get('peak_sampled_rss_bytes'),representation_checked=False,
                         optimum_cost_match=None)
            try:
                raw_path = ROOT/row['raw_file'] if row.get('raw_file') else None
                if raw_path and raw_path.is_file():
                    raw_path.resolve().relative_to(ROOT)
                    raw = read(raw_path)
                    if raw['method']!=row['method'] or Fraction(raw['h'])!=Fraction(row['h']):
                        raise ValueError('Worker result differs from roster')
                    entry['primary_seconds'] = raw.get('timing',{}).get('primary')
                    if row.get('valid_return'):
                        if 'encoding' in raw:
                            if case_path!=item['case_file']:
                                if sha(ROOT/item['case_file'])!=item['sha256']:
                                    raise ValueError('Input hash mismatch')
                                case = read(ROOT/item['case_file']); case_path = item['case_file']
                            verdict = checker.check(case,row['h'],raw['encoding'])
                            cost = Fraction(raw['cost'])
                            if not verdict['ok'] or Fraction(verdict['cost'])!=cost or Fraction(row['cost'])!=cost:
                                raise ValueError('Representation or cost check failed')
                            entry['representation_checked'] = True; checked += 1
                            if ref is not None:
                                if cost<ref:raise ValueError('Cost below reported optimum')
                                entry['gap_percent'] = float((cost-ref)/ref)*100 if ref else 0.0
                                if row['status'] in ['optimal_numerical','THEOREM_EXACT']:
                                    if cost!=ref:raise ValueError('Optimum differs from reported cost')
                                    entry['optimum_cost_match'] = True; matches += 1
                        elif row['method'] not in ['LP-on','LP-off']:
                            raise ValueError('Valid return has no representation')
                elif row.get('valid_return'):
                    raise ValueError('Valid return has no worker result')
            except (ValueError,KeyError,TypeError,AssertionError) as e:
                errors.append(dict(suite=suite,slot=row['slot'],error=str(e)))
            rows.append(entry)
    if rows:
        with (out/'runs.csv').open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    summary = dict(status='PASS' if not errors else 'FAIL',coverage=coverage,rows=len(rows),
                   statuses=dict(Counter(r['status'] for r in rows)),representation_checks=checked,
                   optimum_cost_matches=matches,errors=errors,
                   scope='Run integrity and available cost comparisons; timings are fresh measurements.')
    atomic_json(out/'summary.json',summary)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    result=summarize(args.records,args.out)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['status']=='PASS' else 1)
