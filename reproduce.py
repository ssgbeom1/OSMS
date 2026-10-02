"""Verify files, execute study schedules, and analyze new runs."""
from pathlib import Path
import argparse, collections, csv, hashlib, importlib.metadata, json, os
import platform, shutil, subprocess, sys, time

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'analysis'))
from common import read,sha,atomic_json

def relative(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()

def fresh(path):
    path=Path(path).resolve()
    path.relative_to(ROOT)
    path.mkdir(parents=True,exist_ok=False)
    return path

def verify():
    manifest=read(ROOT/'MANIFEST.json')
    files=manifest.get('files',manifest)
    for name,digest in files.items():
        if isinstance(digest,dict):digest=digest['sha256']
        if sha(ROOT/name)!=digest:raise ValueError('File hash mismatch: '+name)
    print(json.dumps({'status':'PASS','files':len(files)}),flush=True)

def environment():
    versions={n:importlib.metadata.version(n) for n in ['numpy','scipy','psutil']}
    expected=read(ROOT/'metadata/environment.json')
    required={'numpy':'1.26.4','scipy':'1.12.0','psutil':'7.2.2'}
    if versions!=required:raise ValueError('Install requirements.txt: '+str(versions))
    if sys.version_info[:2]!=(3,12):raise ValueError('Python 3.12 is required for this replication')
    import psutil
    affinity=psutil.Process().cpu_affinity()
    return dict(python=sys.version,platform=platform.platform(),packages=versions,cpu_affinity=affinity,
                physical_cpus=psutil.cpu_count(logical=False),logical_cpus=psutil.cpu_count(),
                note='Fresh host measurements; timing and time-limited completion can differ from the archived run.')

def rebuild_inputs(out):
    out=fresh(out);environment()
    sys.path.insert(0,str(ROOT/'runtime/primary'))
    from run_one import execute
    report=[]
    for item in read(ROOT/'data/inputs.json')['inputs']:
        dest=out/(item['id']+'.json');status=out/'reports'/(item['id']+'.json')
        cmd=[sys.executable,'-B',str(ROOT/'runtime/primary/prepare_one.py'),
             'data/sources/'+item['distribution'],item['representation'],str(item['target_nodes']),
             relative(dest),relative(status),'--prepare-seconds','120']
        record=execute(cmd,relative(status),220,4096*2**20,.05)
        if not record['valid_return']:raise RuntimeError('Input conversion failed: '+item['id'])
        expected=next(e for e in read(ROOT/'data/inputs.json')['inputs'] if e['id']==item.get('alias_of',item['id']))
        if item['status']=='READY':
            if sha(dest)!=item['sha256']:raise ValueError('Prepared input hash differs: '+item['id'])
        else:
            a=read(dest);b=read(ROOT/expected['case_file'])
            if a['roots']!=b['roots'] or a['ranks']!=b['ranks']:raise ValueError('Alias roots differ')
            alias=next(x for x in read(ROOT/'data/alias_files.json') if Path(x['file']).stem==item['id'])
            if sha(dest)!=alias['sha256']:raise ValueError('Alias serialized input differs')
        report.append(dict(input=item['id'],status='PASS',sha256=sha(dest),historical_status=item['status']))
        atomic_json(out/'input_checks.json',report)
        print(item['id'],'PASS',flush=True)

def selected_input(slot,inputs):
    if 'input' in slot:return slot['input']
    return inputs[slot['distribution'],slot['representation'],slot['target_nodes']]

def schedule_run(out,suite,max_slots,resume):
    if max_slots is not None and max_slots<=0:raise ValueError('--max-slots must be positive')
    environment_record=environment()
    out=Path(out).resolve();out.relative_to(ROOT)
    if not resume:
        out=fresh(out)
        atomic_json(out/'environment.json',environment_record)
        atomic_json(out/'plan_hashes.json',{n:sha(ROOT/'protocol'/f'{n}.json') for n in ['primary','diagnostics','normalization']})
    elif not out.is_dir():raise ValueError('Resume directory does not exist')
    elif read(out/'plan_hashes.json')!={n:sha(ROOT/'protocol'/f'{n}.json') for n in ['primary','diagnostics','normalization']}:
        raise ValueError('Resume protocol has changed')
    sys.path.insert(0,str(ROOT/'runtime/primary'))
    from run_one import execute
    inputs={(e['distribution'],e['representation'],e['target_nodes']):e for e in read(ROOT/'data/inputs.json')['inputs']}
    session='fresh-'+str(time.time_ns())
    remaining=max_slots
    for name in (['primary','diagnostics','normalization'] if suite=='all' else [suite]):
        directory=out/'records'/name;directory.mkdir(parents=True,exist_ok=True)
        rowsfile=directory/'rows.jsonl';planpath=ROOT/'protocol'/f'{name}.json';plan=read(planpath)
        rows=list(map(json.loads,rowsfile.read_text().splitlines())) if rowsfile.exists() else []
        if [r['slot'] for r in rows]!=list(range(len(rows))):raise ValueError('Noncontiguous resume prefix')
        for i,slot in enumerate(plan['slots']):
            if i<len(rows):continue
            if remaining is not None and remaining<=0:
                atomic_json(out/'state.json',dict(status='PARTIAL',suite=name,completed=i,total=len(plan['slots'])))
                return
            item=selected_input(slot,inputs);base=dict(slot,slot=i)
            if name=='primary':base['execution_batch']=session
            elif name=='normalization':base['execution_batch']=session
            if item['status']!='READY':
                result=dict(base,status='ALIAS_NOT_EXECUTED',alias_of=item.get('alias_of'))
            else:
                if sha(ROOT/item['case_file'])!=item['sha256']:raise ValueError('Input hash mismatch')
                target=directory/'runs'/f'{i:06d}.json'
                # Recover a committed worker result after scheduler interruption.
                sidecar=target.with_suffix('.supervision.json')
                if sidecar.exists():
                    supervision=read(sidecar)
                elif any(target.parent.glob(target.stem+'.*')):
                    raise RuntimeError('Uncommitted interrupted attempt preserved at '+relative(target)+'. Use a new run directory; no evidence was overwritten.')
                else:
                    worker=ROOT/('code/worker.py' if name=='normalization' else 'runtime/diagnostics/diagnostic_worker.py' if name=='diagnostics' else 'runtime/primary/worker.py')
                    command=[sys.executable,'-B',str(worker),item['case_file'],slot['method'],slot['h'],relative(target)]
                    if name!='diagnostics':command+=['--prepare-seconds','120','--method-seconds','30','--check-seconds','60']
                    supervision=execute(command,relative(target),220,4096*2**20,.05)
                result=dict(base,**supervision,process_limit_reason='INPUT_PROCESS_LIMIT')
            with rowsfile.open('a',encoding='utf-8') as f:f.write(json.dumps(result)+'\n')
            rows.append(result)
            atomic_json(out/'state.json',dict(status='RUNNING',suite=name,completed=i+1,total=len(plan['slots'])))
            print(name,i+1,len(plan['slots']),slot['method'],result['status'],flush=True)
            if remaining is not None:remaining-=1
        receipt=dict(status='EXECUTED',retained_rows=len(rows),rows_sha256=sha(rowsfile),plan_sha256=sha(planpath),wall_seconds=sum(r.get('wall_seconds',0) for r in rows))
        atomic_json(directory/('receipt.json' if name=='diagnostics' else 'execution_receipt.json'),receipt)
    atomic_json(out/'state.json',dict(status='EXECUTED',suite=suite))

def analyze(out,records):
    for suite in ['primary','diagnostics','normalization']:
        rowsfile=records/suite/'rows.jsonl'
        expected=len(read(ROOT/'protocol'/f'{suite}.json')['slots'])
        if not rowsfile.is_file() or sum(bool(s.strip()) for s in rowsfile.read_text().splitlines())!=expected:
            raise ValueError('Complete all three schedules before analysis; use summarize_run.py for partial runs.')
    out=fresh(out)
    env=dict(os.environ,REPRO_WORK=str(out),REPRO_RECORDS=str(records.resolve()),PYTHONDONTWRITEBYTECODE='1')
    commands=[['audit_primary.py',str(ROOT/'protocol'),str(records/'primary'),str(out/'audit')],
              ['compare_primary.py',str(out/'comparison')],['final_tables.py',str(out/'final')],
              ['structure_tables.py',str(ROOT),str(out/'structure')],
              ['normalization_tables.py',str(ROOT/'protocol/normalization.json'),str(records/'normalization')]]
    for args in commands:
        with (out/(args[0]+'.log')).open('w',encoding='utf-8') as log:
            done=subprocess.run([sys.executable,'-B',str(ROOT/'analysis'/args[0]),*args[1:]],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        if done.returncode:raise RuntimeError('Analysis failed; inspect '+relative(out/(args[0]+'.log')))
        print(args[0],'PASS',flush=True)
    for p in [out/'audit/summary.json',out/'comparison/summary.json',out/'normalization/audit.json']:
        if read(p)['status']!='PASS':raise ValueError('Audit did not pass: '+str(p))
    export_tables(out)
    compare_fresh_costs(out)
    atomic_json(out/'receipt.json',dict(status='PASS',records=relative(records),historical=False))

def compare_fresh_costs(out):
    from fractions import Fraction
    with (ROOT/'results/primary/all_slots.csv').open(encoding='utf-8-sig',newline='') as f:old=list(csv.DictReader(f))
    known={}
    for r in old:
        if r['numeric_optimal']=='True' or r['theorem_exact']=='True':known[int(r['condition'])]=Fraction(r['cost'])
    checked=0
    for r in read(out/'audit/complete_rows.json'):
        if (r['numeric_optimal'] or r['theorem_exact']) and r['condition'] in known:
            if Fraction(r['cost'])!=known[r['condition']]:raise ValueError('Fresh optimum disagrees with historical cost: '+str(r['condition']))
            checked+=1
    atomic_json(out/'fresh_comparison.json',dict(status='PASS',optimal_cost_matches=checked,
        timing_policy='Report fresh times and completion separately; no equality criterion for elapsed time or capped completion.'))

def export_tables(out):
    from publication_labels import header,value
    specs={'S1_h1_times.csv':'structure/h1_times.csv','S2_candidate_reduction.csv':'structure/candidate_reduction.csv',
           'S3_paired_times.csv':'comparison/paired_times.csv','S4_high_h_phases.csv':'final/all_high_h_phases.csv',
           'S5_lp_comparison.csv':'comparison/lp_comparison.csv','S6_residual_ablation.csv':'comparison/residual_ablation.csv',
           'S7_all_conditions.csv':'comparison/all_conditions.csv','S8_normalization_conditions.csv':'normalization/conditions.csv',
           'S9_normalization_runs.csv':'normalization/runs.csv','S10_normalization_pairs.csv':'normalization/pairs.csv',
           'S11_normalization_failures.csv':'normalization/failures.csv','S12_normalization_source_summary.csv':'normalization/paired_summary.csv'}
    target=out/'tables';target.mkdir()
    for name,source in specs.items():
        with (out/source).open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
        if name.startswith('S8_'):
            for row in rows:row['reference_optimum_cost']=row.pop('cost')
        rows=[{header(k):value(v) if k in {'method','reference','comparison'} else
               v.replace('\\','/') if v.startswith(('records\\','data\\','protocol\\')) else v
               for k,v in row.items()} for row in rows]
        with (target/name).open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    from summarize_greedy import summarize
    residual_out=out/'residual_summary'
    summarize(out/'comparison/diagnostic_runs.csv',residual_out)
    for name in ['S13_residual_quality_time_conditions.csv','S14_residual_quality_time_by_charge.csv']:
        shutil.copyfile(residual_out/name,target/name)
    atomic_json(out/'table_comparison.json',dict(scope='fresh measurements',reference='results/tables',timings_may_differ=True))

def main():
    p=argparse.ArgumentParser(description=__doc__);commands=p.add_subparsers(dest='command',required=True)
    commands.add_parser('verify')
    a=commands.add_parser('analyze');a.add_argument('--out',type=Path,default=ROOT/'generated/reanalysis');a.add_argument('--records',type=Path,required=True)
    a=commands.add_parser('run');a.add_argument('--out',type=Path,required=True);a.add_argument('--suite',choices=['all','primary','diagnostics','normalization'],default='all');a.add_argument('--max-slots',type=int);a.add_argument('--resume',action='store_true')
    a=commands.add_parser('rebuild-inputs');a.add_argument('--out',type=Path,default=ROOT/'generated/rebuilt_inputs')
    args=p.parse_args();os.chdir(ROOT)
    if args.command!='verify':verify()
    if args.command=='verify':verify()
    elif args.command=='analyze':analyze(args.out,args.records)
    elif args.command=='run':schedule_run(args.out,args.suite,args.max_slots,args.resume)
    else:rebuild_inputs(args.out)
if __name__=='__main__':main()
