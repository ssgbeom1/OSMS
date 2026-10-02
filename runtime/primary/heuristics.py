"""Dynamic add and prune heuristics for charged subtree sharing."""
from fractions import Fraction
import time
import baseline
from telemetry import Recorder


def state(g, selected, h):
    q = [int(v in g['roots']) for v in range(len(g['nodes']))]
    for p in reversed(range(len(q))):
        copies = 1 if p in selected else q[p]
        for child in g['nodes'][p][1]:
            q[child] += copies
    body = []
    for _, children in g['nodes']:
        body.append(len(children) + sum(body[c] for c in children if c not in selected))
    gains = [(q[v]-1)*body[v] for v in range(len(q))]
    cost = len(g['roots']) + sum(len(ch)*(1 if v in selected else q[v])
                                for v, (_, ch) in enumerate(g['nodes'])) + (h+1)*len(selected)
    return cost, gains


def choose(g, h, method, deadline=float('inf'), check_moves=False):
    h = Fraction(h)
    if h < 0 or method not in ('All-U', 'Greedy-add', 'Greedy-prune', 'No-sharing'):
        raise ValueError('invalid charge/method')
    selected = set() if method in ('Greedy-add','No-sharing') else set(g['U'])
    trace = []
    if method in ('All-U','No-sharing'):
        return selected, trace, False
    prune = method == 'Greedy-prune'
    while time.perf_counter() < deadline:
        cost, gains = state(g, selected, h)
        choices = sorted(v for v in g['U'] if (v in selected) == prune)
        if not choices:
            return selected, trace, False
        savings = {v: h+1-gains[v] if prune else gains[v]-h-1 for v in choices}
        v = min(choices, key=lambda c: (-savings[c], c))
        if check_moves:
            for candidate in choices:
                ranks = {symbol: len(children) for symbol, children in g['nodes']}
                _, direct = baseline._render(g['nodes'], g['roots'], selected ^ {candidate}, h, ranks)
                assert cost-direct == savings[candidate], (candidate, cost, direct, savings[candidate])
        if savings[v] <= 0:
            return selected, trace, False
        if time.perf_counter() >= deadline:
            break
        selected.symmetric_difference_update({v})
        trace.append({'candidate': v, 'saving': str(savings[v]), 'cost_after': str(cost-savings[v])})
    return selected, trace, True


def solve(case, g, method, h, budget, rec=None):
    h = Fraction(h); rec = rec or Recorder()
    start = time.perf_counter()
    with rec.span('heuristic_selection'):
        selected, trace, expired = choose(g, h, method, start+budget-min(5.0,budget*.1))
    selection_seconds = time.perf_counter()-start
    tick = time.perf_counter()
    with rec.span('reconstruct'):
        encoding, cost = baseline._render(g['nodes'], g['roots'], selected, h, case['ranks'])
    reconstruction = time.perf_counter()-tick
    assert cost == state(g, selected, h)[0]
    lower = len(g['roots']) + sum(len(ch) for _, ch in g['nodes'])
    primary = time.perf_counter()-start
    return {'status': 'heuristic_budget_exceeded_feasible' if primary>budget else 'limit_feasible' if expired else 'FEASIBLE',
            'cost': str(cost), 'encoding': encoding, 'selected': sorted(selected), 'trace': trace,
            'bound_numeric': None, 'bound_exact_analytic': str(lower),
            'gap_numeric': None, 'gap_exact_analytic': str((cost-lower)/max(Fraction(1),abs(cost))),
            'optimality': 'not_claimed', 'timing': {'primary': primary, 'selection': selection_seconds,
                                                  'reconstruct': reconstruction}}
