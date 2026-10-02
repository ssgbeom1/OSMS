"""Supervised package input conversion."""
import argparse
from pathlib import Path
import time
import traceback
from package_adapter import convert
from telemetry import Recorder, atomic_json


def main():
    p=argparse.ArgumentParser()
    p.add_argument('source_root');p.add_argument('representation',choices=['compact','fielded'])
    p.add_argument('target_nodes',type=int);p.add_argument('case_output');p.add_argument('report_output')
    p.add_argument('--prepare-seconds',type=float,default=120)
    a=p.parse_args();output=Path(a.report_output);case_path=Path(a.case_output)
    if output.exists() or case_path.exists():raise FileExistsError('preserve previous preparation')
    rec=Recorder(output.with_suffix('.phase.json'));rec.group('prepare',a.prepare_seconds)
    result={'status':'PREPARE_ERROR','valid_return':False}
    try:
        with rec.span('package_conversion'):
            case,manifest=convert(a.source_root,a.representation,a.target_nodes,case_path.stem,rec)
        result.update(manifest)
        if case:
            with rec.span('prepared_input_write'):atomic_json(case_path,case)
            result.update(valid_return=time.perf_counter()<=rec.stage_deadline,case_file=str(case_path))
            if not result['valid_return']:result['status']='PREPARE_TIME_CAP'
    except Exception:
        result.update(status='PREPARE_ERROR',valid_return=False,error=traceback.format_exc())
    result['telemetry']=rec.result()
    atomic_json(output,result)


if __name__=='__main__':main()
