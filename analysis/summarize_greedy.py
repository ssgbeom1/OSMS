"""Summarize residual-selection costs and times from diagnostic records."""

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'results/diagnostics/runs.csv'
METHODS = {'RG-add': 'Residual greedy addition', 'RG-prune': 'Residual greedy pruning'}


def write_csv(dest, name, rows):
    with (dest / name).open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summarize(source, dest):
    source, dest = Path(source), Path(dest)
    groups = defaultdict(list)
    with source.open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            if row['method'] in {'A1', *METHODS}:
                groups[row['input_id'], row['h'], row['method']].append(row)
    if not groups:
        raise ValueError('No residual-selection records found')
    for input_id, h in {(i, h) for i, h, _ in groups}:
        if h not in {'11/10', '5/4', '3/2', '2', '32'}:
            raise ValueError('Unexpected charge: ' + h)
        for method in ['A1', *METHODS]:
            runs = groups.get((input_id, h, method), [])
            if len(runs) != 3 or {r['repeat'] for r in runs} != {'0', '1', '2'}:
                raise ValueError('Expected three distinct repetitions: ' + input_id + ' ' + h + ' ' + method)
    conditions = []
    for (input_id, h, method), greedy in groups.items():
        if method not in METHODS:
            continue
        exact = groups[input_id, h, 'A1']
        assert len(greedy) == len(exact) == 3
        assert {r['repeat'] for r in greedy} == {r['repeat'] for r in exact} == {'0', '1', '2'}
        valid = all(r['valid_return'] == 'True' for r in greedy + exact)
        row = dict(input_id=input_id, h=h, method=METHODS[method], completed=valid,
                   exact_statuses=';'.join(r['status'] for r in exact),
                   greedy_statuses=';'.join(r['status'] for r in greedy),
                   reference_cost='', fixed_cost='', residual_reference_cost='',
                   absolute_excess='', full_gap_percent='', residual_gap_percent='',
                   exact_seconds='', greedy_seconds='', exact_over_greedy='', equal_cost='')
        if valid:
            for field in ['known_integer_optimum', 'profile_fixed_cost', 'profile_residual_signature']:
                assert len({r[field] for r in greedy + exact}) == 1
            optimum = Fraction(exact[0]['known_integer_optimum'])
            offset = Fraction(exact[0]['profile_fixed_cost'])
            assert all(r['status'] == 'optimal_numerical' and Fraction(r['cost']) == optimum for r in exact)
            assert all(r['status'] == 'FEASIBLE' for r in greedy)
            excess = max(Fraction(r['cost']) - optimum for r in greedy)
            assert excess >= 0 and optimum - offset > 0
            exact_time = median(float(r['seconds_primary']) for r in exact)
            greedy_time = median(float(r['seconds_primary']) for r in greedy)
            row.update(reference_cost=str(optimum), fixed_cost=str(offset),
                       residual_reference_cost=str(optimum - offset), absolute_excess=str(excess),
                       full_gap_percent=float(100 * excess / optimum),
                       residual_gap_percent=float(100 * excess / max(Fraction(1), abs(optimum - offset))),
                       exact_seconds=exact_time, greedy_seconds=greedy_time,
                       exact_over_greedy=exact_time / greedy_time, equal_cost=excess == 0)
        conditions.append(row)
    summaries = []
    for method in METHODS.values():
        for h in ['all', '11/10', '5/4', '3/2', '2', '32']:
            planned = [r for r in conditions if r['method'] == method and (h == 'all' or r['h'] == h)]
            rows = [r for r in planned if r['completed']]
            summaries.append(dict(method=method, h=h, planned=len(planned), completed=len(rows),
                equal_cost=sum(r['equal_cost'] for r in rows),
                full_gap_median=optional_median(r['full_gap_percent'] for r in rows),
                full_gap_max=optional_max(r['full_gap_percent'] for r in rows),
                residual_gap_median=optional_median(r['residual_gap_percent'] for r in rows),
                residual_gap_max=optional_max(r['residual_gap_percent'] for r in rows),
                absolute_excess_median=float(median(Fraction(r['absolute_excess']) for r in rows)) if rows else None,
                absolute_excess_max=float(max(Fraction(r['absolute_excess']) for r in rows)) if rows else None,
                time_ratio_median=optional_median(r['exact_over_greedy'] for r in rows),
                time_ratio_min=optional_min(r['exact_over_greedy'] for r in rows),
                time_ratio_max=optional_max(r['exact_over_greedy'] for r in rows)))
    dest.mkdir(parents=True, exist_ok=False)
    write_csv(dest, 'S13_residual_quality_time_conditions.csv', conditions)
    write_csv(dest, 'S14_residual_quality_time_by_charge.csv', summaries)
    evidence = dict(source=source.name, sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    scope='Summary of the supplied diagnostic CSV; no optimizer runs.',
                    quality='Maximum exact rational cost excess across three repetitions per condition.',
                    timing='Ratio of three-run primary-time medians within the same diagnostic batch.',
                    conditions=len(conditions), completed=sum(r['completed'] for r in conditions))
    (dest / 'reanalysis.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    return summaries


def optional_median(values):
    values = list(values)
    return median(values) if values else None


def optional_max(values):
    values = list(values)
    return max(values) if values else None


def optional_min(values):
    values = list(values)
    return min(values) if values else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--out', type=Path, default=ROOT / 'generated/residual_tables')
    args = parser.parse_args()
    summaries = summarize(args.source, args.out)
    print(json.dumps([s for s in summaries if s['h'] == 'all'], indent=2))


if __name__ == '__main__':
    main()
