"""Package-relative paths and lossless representation loading."""
from pathlib import Path
import gzip, hashlib, json, os
ROOT=Path(__file__).resolve().parents[1]
WORK=Path(os.environ.get('REPRO_WORK',str(ROOT/'generated/reanalysis'))).resolve()
RECORDS=Path(os.environ.get('REPRO_RECORDS',str(ROOT/'generated/full_run/records'))).resolve()
def path(p):
    p=Path(p)
    return p if p.is_absolute() else ROOT/p
def sha(p):
    h=hashlib.sha256()
    with path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def read(p):
    result=json.loads(path(p).read_text(encoding='utf-8-sig'))
    if isinstance(result,dict) and 'encoding_file' in result:
        b=gzip.decompress(path(result['encoding_file']).read_bytes())
        if hashlib.sha256(b).hexdigest()!=result['encoding_sha256']:raise ValueError('Representation hash mismatch')
        result['encoding']=json.loads(b)
    return result
def atomic_json(p,obj):
    p=path(p);p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_suffix(p.suffix+'.tmp');temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(p)
