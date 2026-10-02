"""Supervise a worker with stage deadlines and sampled process-tree memory."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
import psutil
from telemetry import atomic_json


def terminate(process):
    try:
        parent = psutil.Process(process.pid)
        for child in reversed(parent.children(recursive=True)):
            try: child.kill()
            except psutil.NoSuchProcess: pass
        process.kill()
    except (psutil.NoSuchProcess, ProcessLookupError):
        pass


def execute(command, output, process_seconds=130, rss_bytes=1073741824, sample_seconds=.05):
    output = Path(output)
    if output.exists() or output.with_suffix('.supervision.json').exists():
        raise FileExistsError('prior attempt output exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    phase_path = output.with_suffix('.phase.json')
    peak = 0; peaks = {}; samples = 0; phase = {}; censor = None; monitor_error = None
    phase_read_retries = 0; read_denied_since = None
    started = time.perf_counter()
    with output.with_suffix('.stdout.txt').open('w', encoding='utf-8') as stdout, output.with_suffix('.stderr.txt').open('w', encoding='utf-8') as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        try:
            while process.poll() is None:
                try:
                    if phase_path.exists():
                        try:
                            phase = json.loads(phase_path.read_text(encoding='utf-8'))
                            read_denied_since = None
                        except PermissionError:
                            phase_read_retries += 1
                            read_denied_since = read_denied_since or time.perf_counter()
                            if time.perf_counter()-read_denied_since > .25:
                                raise
                            # Keep monitoring while the phase record is unavailable.
                    parent = psutil.Process(process.pid)
                    tree = [parent, *parent.children(recursive=True)]
                    rss = sum(p.memory_info().rss for p in tree if p.is_running())
                    peak = max(peak,rss); samples += 1
                    label = phase.get('phase', 'startup')
                    peaks[label] = max(peaks.get(label,0),rss)
                    deadline = phase.get('group_deadline_perf')
                    if rss > rss_bytes: censor = 'MEMORY_CAP'
                    elif time.perf_counter()-started > process_seconds: censor = 'PROCESS_TIME_CAP'
                    elif deadline is not None and time.perf_counter()>deadline: censor = str(phase.get('group')).upper()+'_TIME_CAP'
                    if censor:
                        terminate(process); break
                except psutil.NoSuchProcess:
                    if process.poll() is None:
                        continue
                    break
                except Exception as error:
                    monitor_error = type(error).__name__+': '+str(error)
                    censor = 'MONITOR_ERROR'; terminate(process); break
                try:
                    process.wait(timeout=sample_seconds)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            process.wait()
    elapsed = time.perf_counter()-started
    record = {'status': censor or 'PROCESS_ERROR', 'wall_seconds': elapsed, 'returncode': process.returncode,
              'peak_sampled_rss_bytes': peak, 'phase_peak_sampled_rss_bytes': peaks,
              'rss_samples': samples, 'sample_seconds': sample_seconds, 'last_observed': phase,
              'limits': {'process_seconds': process_seconds, 'rss_bytes': rss_bytes},
              'monitor_error': monitor_error, 'raw_file': str(output)}
    record['phase_read_permission_retries'] = phase_read_retries
    if output.exists():
        try:
            raw = json.loads(output.read_text(encoding='utf-8'))
            record['worker_status'] = raw.get('status')
            record['cost'] = raw.get('cost')
            if censor is None and process.returncode == 0:
                record['status'] = raw.get('status', 'PROCESS_ERROR')
                record['valid_return'] = bool(raw.get('valid_return', False))
        except Exception as error:
            record['read_error'] = str(error)
    record.setdefault('valid_return', False)
    atomic_json(output.with_suffix('.supervision.json'), record)
    return record


def main():
    p = argparse.ArgumentParser()
    p.add_argument('case'); p.add_argument('method', choices=['A0','A1','A2','All-U','Greedy-add','Greedy-prune','Forest','No-sharing'])
    p.add_argument('h'); p.add_argument('output')
    p.add_argument('--method-seconds', type=float, default=30)
    p.add_argument('--prepare-seconds', type=float, default=60)
    p.add_argument('--check-seconds', type=float, default=30)
    p.add_argument('--process-seconds', type=float, default=130)
    p.add_argument('--rss-mib', type=int, default=1024)
    args = p.parse_args()
    worker = Path(__file__).with_name('worker.py')
    cmd = [sys.executable, '-B', str(worker), args.case, args.method, args.h, args.output,
           '--method-seconds', str(args.method_seconds), '--prepare-seconds', str(args.prepare_seconds),
           '--check-seconds', str(args.check_seconds)]
    print(json.dumps(execute(cmd,args.output,args.process_seconds,args.rss_mib*1024*1024)), flush=True)


if __name__ == '__main__':
    main()
