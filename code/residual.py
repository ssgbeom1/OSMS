"""Residual greedy selection with a heap of component-best moves."""
from fractions import Fraction
import heapq
import time


def local_state(g,state,vertices,selected,h):
    vs=set(vertices);counts={}
    for v in reversed(vertices):
        q=int(v in g['roots'])+sum(m*(counts[p] if p in vs else state['fixed'][p]) for p,m in g['parents'][v].items())
        counts[v]=1 if v in selected else q
    body={};demand={}
    for v in vertices:
        children=g['nodes'][v][1]
        assert all(c in vs or c in state['F'] or not g['nodes'][c][1] for c in children),'unexpected nonselected boundary child'
        body[v]=len(children)+sum(body[c] for c in children if c in vs and c not in selected)
        demand[v]=int(v in g['roots'])+sum(m*(counts[p] if p in vs else state['fixed'][p]) for p,m in g['parents'][v].items())
    cost=sum(len(g['nodes'][v][1])*counts[v] for v in vertices)+(h+1)*len(selected&vs)
    gains={v:(demand[v]-1)*body[v] for v in state['active']&vs}
    return cost,gains


def choose(g,state,h,prune=False,deadline=float('inf'),check_moves=False):
    h=Fraction(h);selected=set(state['active']) if prune else set();heap=[];trace=[];local_cost={}
    def update(i):
        cost,gains=local_state(g,state,state['components'][i],selected,h);local_cost[i]=cost
        choices=[v for v in gains if (v in selected)==prune]
        savings={v:h+1-gains[v] if prune else gains[v]-h-1 for v in choices}
        if not choices:return
        v=min(choices,key=lambda c:(-savings[c],c))
        if check_moves:
            for c in choices:
                other,_=local_state(g,state,state['components'][i],selected^{c},h)
                assert cost-other==savings[c],('residual marginal',c,cost,other,savings[c])
        if savings[v]>0:heapq.heappush(heap,(-savings[v],v,i))
    for i in range(len(state['components'])):update(i)
    while heap and time.perf_counter()<deadline:
        gain,v,i=heapq.heappop(heap);selected.symmetric_difference_update({v})
        trace.append({'candidate':v,'saving':str(-gain)})
        update(i)
    return selected,trace,bool(heap),state['offset']+sum(local_cost.values())
