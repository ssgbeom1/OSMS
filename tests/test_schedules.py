"""Check full roster membership, balance, input identity and runtime selection."""
from pathlib import Path
from collections import Counter
import importlib.util,json
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text(encoding='utf-8-sig'))
def main():
    inputs=read('data/inputs.json')['inputs'];ready={e['id'] for e in inputs if e['status']=='READY'}
    assert len(inputs)==24 and len(ready)==17
    p=read('protocol/primary.json')['slots'];d=read('protocol/diagnostics.json')['slots'];n=read('protocol/normalization.json')['slots']
    assert len(p)==5184 and len(d)==935 and len(n)==1530
    assert [s['slot'] for s in p]==list(range(5184))
    assert [s['slot'] for s in n]==list(range(1530))
    assert set(Counter((s['condition'],s['method']) for s in p).values())=={6}
    assert Counter(s['method'] for s in n)=={'A0':510,'A0-U':510,'A1':510}
    assert Counter(s['method'] for s in d)=={'A1':255,'RG-add':255,'RG-prune':255,'LP-on':85,'LP-off':85}
    for slots in [d,n]:assert {s['input']['id'] for s in slots}==ready
    for cid in range(85):
        rows=[s for s in n if s['condition']==cid]
        orders=[tuple(s['method'] for s in rows if s['repeat']==rep) for rep in range(6)]
        assert len(set(orders))==6
    for path in ['runtime/primary/worker.py','runtime/diagnostics/diagnostic_worker.py','code/worker.py']:
        assert (ROOT/path).is_file()
    print(json.dumps({'status':'PASS','primary_slots':len(p),'diagnostic_slots':len(d),'normalization_slots':len(n),'unique_inputs':len(ready)}))
if __name__=='__main__':main()
