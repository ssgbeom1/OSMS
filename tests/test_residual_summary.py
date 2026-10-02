"""Check retrospective summaries, failure retention, and fresh-table export."""
import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'analysis'))
sys.path.insert(0, str(ROOT))
from summarize_greedy import summarize
import reproduce

NAMES = ['S13_residual_quality_time_conditions.csv', 'S14_residual_quality_time_by_charge.csv']


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.rows = read(ROOT / 'results/diagnostics/runs.csv')

    def test_reported_tables(self):
        out = self.work / 'summary'
        summarize(ROOT / 'results/diagnostics/runs.csv', out)
        for name in NAMES:
            self.assertEqual(read(out / name), read(ROOT / 'results/tables' / name))
        self.assertEqual(sum(r['completed'] == 'False' for r in read(out / NAMES[0])), 2)
        with self.assertRaises(FileExistsError):
            summarize(ROOT / 'results/diagnostics/runs.csv', out)

    def test_changed_completion_and_empty_subsets(self):
        for row in self.rows:
            if row['h'] == '11/10' and row['method'] in ['A1', 'RG-add', 'RG-prune']:
                row['valid_return'] = 'False'
                row['status'] = 'METHOD_TIME_CAP'
        source = self.work / 'fresh.csv'
        write(source, self.rows)
        out = self.work / 'summary'
        summarize(source, out)
        records = read(out / NAMES[0])
        self.assertEqual(len(records), 170)
        self.assertEqual(sum(r['completed'] == 'True' for r in records), 134)
        for row in read(out / NAMES[1]):
            if row['h'] == '11/10':
                self.assertEqual(row['completed'], '0')
                self.assertEqual(row['time_ratio_median'], '')

    def test_reject_missing_repeat_and_mixed_models(self):
        bad = [r for r in self.rows if not (r['method'] == 'RG-add' and r['repeat'] == '0')]
        source = self.work / 'missing.csv'
        write(source, bad)
        with self.assertRaises(ValueError):
            summarize(source, self.work / 'missing_out')
        self.assertFalse((self.work / 'missing_out').exists())
        next(r for r in self.rows if r['method'] == 'RG-add' and r['valid_return'] == 'True')['profile_residual_signature'] = 'different'
        write(source, self.rows)
        with self.assertRaises(AssertionError):
            summarize(source, self.work / 'mixed_out')

    def test_full_export_includes_added_tables(self):
        sources = {
            'S1': 'structure/h1_times.csv', 'S2': 'structure/candidate_reduction.csv',
            'S3': 'comparison/paired_times.csv', 'S4': 'final/all_high_h_phases.csv',
            'S5': 'comparison/lp_comparison.csv', 'S6': 'comparison/residual_ablation.csv',
            'S7': 'comparison/all_conditions.csv', 'S8': 'normalization/conditions.csv',
            'S9': 'normalization/runs.csv', 'S10': 'normalization/pairs.csv',
            'S11': 'normalization/failures.csv', 'S12': 'normalization/paired_summary.csv',
        }
        for prefix, relative in sources.items():
            rows = read(next((ROOT / 'results/tables').glob(prefix + '_*.csv')))
            if prefix == 'S8':
                for row in rows:
                    row['cost'] = row.pop('reference_optimum_cost')
            write(self.work / relative, rows)
        shutil.copyfile(ROOT / 'results/diagnostics/runs.csv', self.work / 'comparison/diagnostic_runs.csv')
        reproduce.export_tables(self.work)
        self.assertEqual(len(list((self.work / 'tables').glob('*.csv'))), 14)
        for name in NAMES:
            self.assertEqual(read(self.work / 'tables' / name), read(ROOT / 'results/tables' / name))


if __name__ == '__main__':
    unittest.main()
