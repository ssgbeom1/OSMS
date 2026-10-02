"""Optimal macro selection for rational definition charges from zero to one."""
from fractions import Fraction
import argparse,json,time


def check_metadata(meta):
    for name,m in meta.items():
        if not isinstance(name,str):raise ValueError('symbol must be a string')
        if m['arity'] not in ('rank','mixed','unranked'):raise ValueError('arity policy')
        if m['order'] not in ('ordered','unordered','partial'):raise ValueError('order policy')
        for k in ('rank','prefix'):
            if not isinstance(m[k],int) or isinstance(m[k],bool) or m[k]<0:raise ValueError(k)


def solve(roots,meta,h='1'):
    charge=Fraction(str(h))
    if not 0<=charge<=1:raise ValueError('solver supports only 0<=h<=1')
    check_metadata(meta)
    started=time.perf_counter()
    labels=[];children=[];sizes=[];index={};object_ids={};raw_occurrences=0
    # Cache object visits; structural signatures determine equality.
    def intern(root):
        nonlocal raw_occurrences
        pending=[(root,False)];active=set()
        while pending:
            t,ready=pending.pop();oid=id(t)
            if oid in object_ids:continue
            if not isinstance(t,(list,tuple)) or len(t)!=2 or not isinstance(t[0],str) or not isinstance(t[1],(list,tuple)):
                raise ValueError('term must be [symbol,children]')
            symbol,cs=t
            if symbol not in meta:raise ValueError('unknown symbol '+symbol)
            m=meta[symbol];n=len(cs)
            legal=n==m['rank'] if m['arity']=='rank' else n>0 if m['arity']=='unranked' else (n==0 and m['rank']==0) or (n>0 and n>=m['rank'])
            if not legal:raise ValueError('illegal actual arity')
            if n and m['order']=='partial' and n<m['prefix']:raise ValueError('missing ordered prefix')
            if not ready:
                if oid in active:raise ValueError('cyclic input object')
                active.add(oid);pending.append((t,True))
                pending.extend((c,False) for c in reversed(cs));continue
            active.remove(oid)
            ids=[object_ids[id(c)] for c in cs]
            prefix=n if m['order']=='ordered' else 0 if m['order']=='unordered' else m['prefix']
            ids=tuple(ids[:prefix]+sorted(ids[prefix:]))
            sig=(symbol,n,ids)
            if sig not in index:
                index[sig]=len(labels);labels.append(symbol);children.append(ids);sizes.append(1+sum(sizes[v] for v in ids))
            object_ids[oid]=index[sig];raw_occurrences+=1
        return object_ids[id(root)]
    rootids=list(dict.fromkeys(intern(t) for t in roots))
    N=sum(sizes[v] for v in rootids)
    incoming=[0]*len(labels)
    for v in rootids:incoming[v]+=1
    for cs in children:
        for v in cs:incoming[v]+=1
    U={v for v,cs in enumerate(children) if cs and incoming[v]>=2}
    J={v for v in U if incoming[v]==2 and len(children[v])==1 and (children[v][0] in U or not children[children[v][0]])}
    graph={v:[] for v in J}
    for v in J:
        child=children[v][0]
        if child in J:graph[v].append(child);graph[child].append(v)
    parents={};order=[];components=[]
    for seed in sorted(J):
        if seed in parents:continue
        components.append(seed);parents[seed]=None;stack=[seed]
        while stack:
            v=stack.pop();order.append(v)
            for w in graph[v]:
                if w==parents[v]:continue
                if w in parents:raise AssertionError('residual graph is not a forest')
                parents[w]=v;stack.append(w)
    take={};skip={}
    for v in reversed(order):
        below=[w for w in graph[v] if parents.get(w)==v]
        take[v]=1+sum(skip[w] for w in below)
        skip[v]=sum(max(take[w],skip[w]) for w in below)
    independent=set();stack=[(v,False) for v in components]
    while stack:
        v,blocked=stack.pop();chosen=not blocked and take[v]>=skip[v]
        if chosen:independent.add(v)
        stack.extend((w,chosen) for w in graph[v] if parents.get(w)==v)
    selected=U-independent
    names={};counter=0
    for v in sorted(selected):
        while '@m'+str(counter) in meta:counter+=1
        names[v]='@m'+str(counter);counter+=1
    interning_selection_seconds=time.perf_counter()-started
    reconstruction_start=time.perf_counter()
    def render(v,keep=False):
        if v in names and not keep:return [names[v],[]]
        answer=[labels[v],[]];todo=[(v,answer[1])]
        while todo:
            current,dest=todo.pop()
            for w in children[current]:
                if w in names:dest.append([names[w],[]])
                else:
                    child=[labels[w],[]];dest.append(child);todo.append((w,child[1]))
        return answer
    encoded={'roots':[render(v) for v in rootids], 'definitions':{names[v]:render(v,True) for v in sorted(selected)}}
    def count(ts):
        total=0;stack=list(ts)
        while stack:
            t=stack.pop();total+=1;stack.extend(t[1])
        return total
    stored=count(encoded['roots'])+count(encoded['definitions'].values())
    actual=stored+charge*len(selected)
    baseline=Fraction(len(rootids)+sum(map(len,children)))+(charge+1)*len(U)
    expected=baseline-charge*len(independent)
    if actual!=expected or actual>N:raise AssertionError('reconstruction cost mismatch')
    reconstruction_seconds=time.perf_counter()-reconstruction_start
    encoded.update(cost=str(actual),stats={'input_roots_after_dedup':len(rootids),'input_nodes':N,'distinct_subterms':len(labels),
        'nonconstant_classes':sum(bool(c) for c in children),'unary_classes':sum(len(c)==1 for c in children),
        'unary_occurrences':None,'U':len(U),'J':len(J),'forest_edges':sum(map(len,graph.values()))//2,
        'forest_components':len(components),'independent_size':len(independent),'all_U_cost':str(baseline),
        'saving_against_all_U':str(baseline-actual),'stored_nodes':stored,'definitions':len(selected),
        'interning_selection_seconds':interning_selection_seconds,'reconstruction_seconds':reconstruction_seconds})
    demands=[0]*len(labels)
    for v in rootids:demands[v]+=1
    for v in reversed(range(len(labels))):
        for w in children[v]:demands[w]+=demands[v]
    encoded['stats']['unary_occurrences']=sum(demands[v] for v,c in enumerate(children) if len(c)==1)
    return encoded


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',help='JSON containing roots, metadata, optional h')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    with open(args.input,encoding='utf-8-sig') as f:data=json.load(f)
    result=solve(data['roots'],data['metadata'],data.get('h','1'))
    with open(args.output,'x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)


if __name__=='__main__':main()
