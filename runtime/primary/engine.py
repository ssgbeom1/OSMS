"""MILP selection with exact demand accounting."""
from collections import Counter
from fractions import Fraction
import hashlib, json, math, time, warnings
import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import coo_matrix
import baseline
from telemetry import Recorder

OPTIONS={'presolve':True,'mip_rel_gap':0.0,'threads':1,'random_seed':0,
         'primal_feasibility_tolerance':1e-7,'dual_feasibility_tolerance':1e-7,
         'mip_feasibility_tolerance':1e-6}


def prepare(case):
    nodes,roots,r,parents,raw=baseline._intern(case)
    W={v for v,(s,ch) in enumerate(nodes) if ch}
    inc=[int(v in roots)+sum(parents[v].values()) for v in range(len(nodes))]
    U={v for v in W if inc[v]>=2}
    return {'nodes':nodes,'roots':roots,'r':r,'parents':parents,'raw':raw,'W':W,'U':U,'inc':inc}


def counts(g,S):
    q=[int(v in g['roots']) for v in range(len(g['nodes']))];c=q.copy()
    for p in reversed(range(len(q))):
        c[p]=1 if p in S else q[p]
        for v in g['nodes'][p][1]:q[v]+=c[p]
    return c,q


def reduce(g,h,rec=None):
    rec=rec or Recorder()
    nodes,U,W,inc=g['nodes'],g['U'],g['W'],g['inc'];lam=h+1
    with rec.span('preprocess_initial'):
        E=[]
        for _,ch in nodes:E.append(len(ch)+sum(E[v] for v in ch if v not in U))
        F={v for v in U if (inc[v]-1)*E[v]>=lam};D=set();rounds=0
    def gains(S):
        _,q=counts(g,S);b=[]
        for _,ch in nodes:b.append(len(ch)+sum(b[v] for v in ch if v not in S))
        return [(q[v]-1)*b[v] for v in range(len(nodes))]
    with rec.span('preprocess_interval'):
        while True:
            rounds+=1
            low=gains(U-D);added={v for v in U-F-D if low[v]>=lam};F|=added
            high=gains(F);removed={v for v in U-F-D if high[v]<=lam};D|=removed
            if not added and not removed:break
        rec.work['interval_rounds']+=rounds
        rec.work['gain_calls']+=2*rounds
        rec.work['gain_node_visits']+=4*rounds*len(nodes)
        rec.work['gain_child_position_visits']+=4*rounds*sum(len(ch) for _,ch in nodes)
    with rec.span('preprocess_count_closure'):
        Z=set(F);nonjoins=W-U
        rec.work['nonjoin_set_constructions']+=1
        rec.work['closure_node_visits']+=len(nodes)
        for v in reversed(range(len(nodes))):
            if v in nonjoins and (v in g['roots'] or all(p in Z for p in g['parents'][v])):
                assert inc[v]==1;Z.add(v)
    with rec.span('preprocess_partition'):
        R=W-Z;adj={v:set() for v in R}
        for v in R:
            for c in nodes[v][1]:
                if c in R:adj[v].add(c);adj[c].add(v)
        unseen=set(R);components=[]
        while unseen:
            seed=min(unseen);unseen.remove(seed);todo=[seed];part=[]
            while todo:
                p=todo.pop();part.append(p)
                for c in sorted(adj[p]&unseen):unseen.remove(c);todo.append(c)
            components.append(sorted(part))
    with rec.span('preprocess_fixed_counts'):
        active=U-F-D;fixed={v:1 for v in Z};variable=[];deterministic=0
        for comp in components:
            if active&set(comp):variable.append(comp);continue
            deterministic+=1
            for v in reversed(comp):
                fixed[v]=int(v in g['roots'])+sum(m*fixed[p] for p,m in g['parents'][v].items())
    return {'F':F,'D':D,'fixed':fixed,'components':variable,'active':active,
            'rounds':rounds,'deterministic_components':deterministic,'count_one':len(Z),
            'raw_components':len(components)}


def problem(g,h,method,rec=None):
    if method=='A0':
        state={'F':set(),'D':set(),'fixed':{},'components':[sorted(g['W'])] if g['W'] else [],
               'active':set(g['W']),'rounds':0,'deterministic_components':0,'count_one':0,'raw_components':1 if g['W'] else 0}
    else:state=reduce(g,h,rec)
    state['offset']=Fraction(len(g['roots']))+sum(len(g['nodes'][v][1])*c for v,c in state['fixed'].items())+(h+1)*len(state['F'])
    payload={'F':sorted(state['F']),'D':sorted(state['D']),'fixed':sorted(state['fixed'].items()),
             'components':state['components'],'active':sorted(state['active']),'offset':str(state['offset'])}
    state['signature']=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    return state


def build(g,state,vertices,h):
    vs=sorted(vertices);idx={v:i for i,v in enumerate(vs)}
    xs=sorted(state['active']&set(vs));xi={v:len(vs)+i for i,v in enumerate(xs)}
    den=h.denominator;lam=h.numerator+den
    objective=[den*len(g['nodes'][v][1]) for v in vs]+[lam]*len(xs)
    rr=[];cc=[];dd=[];lo=[];hi=[]
    def row(entries,a,b):
        k=len(lo)
        for c,value in entries.items():
            if value:rr.append(k);cc.append(c);dd.append(value)
        lo.append(a);hi.append(b)
    for v in vs:
        demand=int(v in g['roots']);d={idx[v]:1}
        for p,m in g['parents'][v].items():
            if p in idx:d[idx[p]]=-m
            else:
                assert p in state['fixed'],('missing boundary',v,p)
                demand+=m*state['fixed'][p]
        if v not in xi:row(d,demand,demand)
        else:
            M=g['raw'][v]-1;x=xi[v]
            row(d,-np.inf,demand)
            row({**d,x:M},demand,np.inf)
            row({idx[v]:1,x:M},-np.inf,g['raw'][v])
    matrix=coo_matrix((dd,(rr,cc)),shape=(len(lo),len(objective))).tocsc()
    lower=np.array([1]*len(vs)+[0]*len(xs),dtype=float)
    upper=np.array([g['raw'][v] for v in vs]+[1]*len(xs),dtype=float)
    assert max(objective+[int(sum(g['raw']))],default=0)<2**50
    return {'vs':vs,'xs':xs,'obj':np.array(objective,dtype=float),'lower':lower,'upper':upper,
            'matrix':matrix,'lo':np.array(lo),'hi':np.array(hi),'nvars':len(objective),'nrows':len(lo)}


def residual_cost(g,state,S,h):
    c,_=counts(g,state['F']|S)
    return state['offset']+sum(len(g['nodes'][v][1])*c[v] for comp in state['components'] for v in comp)+(h+1)*len(S)


def interpret_incumbent(m,g,state,h,opt):
    rounded=np.rint(opt.x)
    assert len(rounded)==m['nvars'] and np.all(np.isfinite(rounded))
    assert np.max(np.abs(rounded-opt.x),initial=0)<=1e-5,'fractional incumbent'
    ax=m['matrix']@rounded
    assert np.all(ax>=m['lo']-1e-5) and np.all(ax<=m['hi']+1e-5),'constraint violation'
    assert np.all(rounded>=m['lower']) and np.all(rounded<=m['upper'])
    chosen={v for j,v in enumerate(m['xs']) if rounded[len(m['vs'])+j]==1}
    actual={}
    for v in reversed(m['vs']):
        q=int(v in g['roots'])+sum(mult*(actual[p] if p in actual else state['fixed'][p]) for p,mult in g['parents'][v].items())
        actual[v]=1 if v in chosen else q
    assert all(actual[v]==int(rounded[j]) for j,v in enumerate(m['vs'])),'integer recurrence mismatch'
    exact_scaled=sum(h.denominator*len(g['nodes'][v][1])*actual[v] for v in m['vs'])+(h.numerator+h.denominator)*len(chosen)
    assert abs(float(opt.fun)-exact_scaled)<=1e-4,'incumbent objective mismatch'
    return chosen,exact_scaled


def solve(case,g,method,h='2',budget=30.0,rec=None):
    h=Fraction(h);rec=rec or Recorder();start=time.perf_counter();deadline=start+budget
    if h<0 or method not in ('A0','A1','A2'):raise ValueError('invalid h/method')
    search_deadline=deadline-min(5.0,budget*.1)
    scaled_ceiling=h.denominator*(len(g['roots'])+sum(len(ch)*g['raw'][v] for v,(_,ch) in enumerate(g['nodes'])))+(h.numerator+h.denominator)*len(g['W'])
    if scaled_ceiling>2**50:raise ValueError('numeric_range_unsupported')
    tick=time.perf_counter()
    with rec.span('preprocess'):state=problem(g,h,method,rec)
    pre=time.perf_counter()-tick
    groups=state['components'] if method=='A2' else [sorted(v for comp in state['components'] for v in comp)]
    groups=[g0 for g0 in groups if g0]
    selected=set(state['F']);parts=[];model_t=solver_t=interpret_t=0.0;optimal=True;expired=False
    total_vars=sum(len(c)+len(set(c)&state['active']) for c in state['components'])
    total_rows=sum(len(c)+2*len(set(c)&state['active']) for c in state['components'])
    for number,vertices in enumerate(groups):
        analytic=sum(len(g['nodes'][v][1]) for v in vertices)
        part={'id':number,'vertices':len(vertices),'candidates':len(set(vertices)&state['active']),
              'analytic_lower':analytic,'status':'NOT_RUN','numeric_bound':None,'reported_gap':None}
        if expired or time.perf_counter()>=search_deadline:
            expired=True;optimal=False;part['status']='INPUT_TIME_BUDGET';parts.append(part);continue
        tick=time.perf_counter()
        with rec.span('model'):m=build(g,state,vertices,h)
        model_t+=time.perf_counter()-tick
        remaining=search_deadline-time.perf_counter();part.update(nvars=m['nvars'],nrows=m['nrows'],nonzeros=m['matrix'].nnz,remaining_solver_budget=remaining)
        if remaining<=0:
            expired=True;optimal=False;part['status']='INPUT_TIME_BUDGET';parts.append(part);continue
        tick=time.perf_counter()
        try:
            with rec.span('solver'), warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                opt=milp(m['obj'],integrality=np.ones(m['nvars']),bounds=Bounds(m['lower'],m['upper']),
                         constraints=LinearConstraint(m['matrix'],m['lo'],m['hi']),
                         options=dict(OPTIONS,time_limit=remaining,disp=True))
        except Exception as exc:
            solver_t+=time.perf_counter()-tick;optimal=False
            part.update(status='solver_failure_feasible',error=type(exc).__name__+': '+str(exc))
            parts.append(part);continue
        solver_t+=time.perf_counter()-tick
        part['warnings']=[str(w.message) for w in caught]
        part['solver_status']=int(opt.status);part['message']=str(opt.message)
        val=getattr(opt,'mip_node_count',None)
        part['mip_node_count']=int(val) if val is not None and math.isfinite(float(val)) else None
        part['presolve_rows']=None;part['presolve_columns']=None
        part['presolve_statistics_note']='Not exposed as structured fields by this backend; retain raw solver log.'
        for source,target in [('mip_dual_bound','numeric_bound'),('mip_gap','reported_gap'),('fun','reported_objective')]:
            val=getattr(opt,source,None)
            if val is not None and math.isfinite(float(val)):part[target]=float(val)/(h.denominator if target!='reported_gap' else 1)
        if opt.status not in (0,1):
            part['rejected_failure_status_bound']=part['numeric_bound'];part['numeric_bound']=None
        with rec.span('interpret'):
            tick=time.perf_counter()
            if opt.x is not None:
                try:chosen,exact_scaled=interpret_incumbent(m,g,state,h,opt)
                except Exception as exc:
                    part.update(status='incumbent_rejected_feasible',numeric_bound=None,error=type(exc).__name__+': '+str(exc))
                    optimal=False;interpret_t+=time.perf_counter()-tick;parts.append(part);continue
                selected|=chosen
                part['chosen']=sorted(chosen)
                part['incumbent_scaled']=exact_scaled
            part['status']='optimal_numerical' if opt.status==0 and opt.x is not None else 'limit_feasible' if opt.status==1 else 'solver_failure_feasible'
            optimal &= part['status']=='optimal_numerical'
            interpret_t+=time.perf_counter()-tick;parts.append(part)
        known=float(state['offset'])+sum(p['numeric_bound'] if p['numeric_bound'] is not None else p['analytic_lower'] for p in parts)
        known+=sum(len(g['nodes'][v][1]) for rest in groups[number+1:] for v in rest)
        rec.publish(last_bound_numeric=known,bound_type='numerical_unverified_until_witness',completed_parts=len(parts))
    tick=time.perf_counter()
    with rec.span('reconstruct'):
        encoding,cost=baseline._render(g['nodes'],g['roots'],selected,h,case['ranks'])
    assert cost==residual_cost(g,state,selected-state['F'],h)
    reconstruction=time.perf_counter()-tick
    lower=float(state['offset'])+sum(p['numeric_bound'] if p['numeric_bound'] is not None else p['analytic_lower'] for p in parts)
    bound_rejected=lower>float(cost)+1e-4
    rejected_bound=lower if bound_rejected else None
    if bound_rejected:
        lower=float(state['offset'])+sum(p['analytic_lower'] for p in parts)
        optimal=False
    gap=max(0.0,float(cost)-lower)/max(1.0,abs(float(cost)))
    primary=time.perf_counter()-start
    status='optimal_numerical' if optimal else 'limit_feasible'
    if any(p['status'] in ('solver_failure_feasible','incumbent_rejected_feasible') for p in parts):status='solver_failure_feasible'
    if bound_rejected:status='solver_failure_feasible'
    if primary>budget:status='input_budget_exceeded_feasible'
    return {'status':status,'cost':str(cost),'encoding':encoding,'selected':sorted(selected),
            'bound_numeric':lower,'gap_numeric':gap,'numeric_certificate_only':True,
            'rejected_aggregate_bound':rejected_bound,
            'timing':{'primary':primary,'preprocess':pre,'model':model_t,'solver':solver_t,
                      'interpret':interpret_t,'reconstruct':reconstruction},'parts':parts,
            'profile':{'N':sum(g['raw']),'subterms':len(g['nodes']),'initial_candidates':len(g['W']),
                       'joins':len(g['U']),'forced':len(state['F']),'excluded':len(state['D']),
                       'count_one':state['count_one'],'fixed_count_vertices':len(state['fixed']),
                       'deterministic_components':state['deterministic_components'],
                       'components':len(state['components']),'raw_components':state['raw_components'],
                       'max_component_vertices':max(map(len,state['components']),default=0),
                       'max_component_candidates':max((len(set(c)&state['active']) for c in state['components']),default=0),
                       'variables':total_vars,'constraints':total_rows,'fixed_cost':str(state['offset']),
                       'residual_signature':state['signature']}}
