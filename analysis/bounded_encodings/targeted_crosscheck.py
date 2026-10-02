"""Compare the pruned enumerator with literal enumeration and count translation cases."""
from collections import Counter
from pathlib import Path
import json, time
import check as c
import targeted as t


def main(out):
    if out.exists():raise FileExistsError(out)
    stats=Counter(); details=Counter()
    deadline=time.monotonic()+120
    for roots in c.universe(5):
        n=sum(map(c.size,roots)); qualified=False
        for ordered,lang in ((False,roots),(True,tuple(c.translate(v) for v in roots))):
            c.variants.cache_clear()
            literal=set()
            for enc in c.encodings(lang,ordered):
                if c.syntax_cost(enc)<=n:literal.add(enc)
                if ordered:continue
                hit=False
                for part in enc:
                    for tree in part:
                        for v in c.subterms(tree):
                            if v[0] not in ('q','m'):continue
                            children=v[1][int(v[0]=='m'):]
                            if len(children)<2 or not any(x[0].startswith('@') for x in children):continue
                            expanded=[c.expand(x,enc[0]) for x in children]
                            if not any(not c.equal(x,y) for x in expanded for y in expanded):continue
                            details[v[0]]+=1;hit=True
                if hit:
                    stats['qualified_encodings']+=1;qualified=True
            generated=set()
            count=0
            for d,options,suffix,k,full in t.configurations(lang,ordered,deadline):
                count+=k
                generated.update(t.enumerate_configuration(d,options,suffix,full,n,deadline))
            assert generated==literal,(roots,ordered,len(generated),len(literal))
            assert count==len(generated)
            stats['generator_cases']+=1;stats['admitted_encodings']+=count
        stats['languages']+=1
        if qualified:stats['qualified_languages']+=1
    out.parent.mkdir(parents=True,exist_ok=True)
    result={'status':'PASS','scope':'All bound-five languages, source and target; syntax nodes <= N',
            'stats':dict(stats),'qualified_nodes_by_symbol':dict(details),
            'qualification':'Exchangeable group with distinct child expansions and a direct macro-reference child; duplicate-inclusive generated encodings.'}
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':
    import sys
    main(Path(sys.argv[1]))
