"""Global MILP formulation for charged whole-subtree sharing."""

from collections import Counter
from fractions import Fraction
import json
import math
import time
import warnings

import numpy as np
import scipy
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix


def _intern(case):
    """Build a child-before-parent DAG from explicit trees."""
    if not isinstance(case, dict):
        raise ValueError("case must be an object")
    roots = case.get("roots")
    ranks = case.get("ranks")
    if not isinstance(roots, (list, tuple)) or not isinstance(ranks, dict):
        raise ValueError("roots must be a sequence and ranks must be a mapping")
    if any(not isinstance(s, str) or type(a) is not int or a < 0
           for s, a in ranks.items()):
        raise ValueError("ranks must map string symbols to nonnegative integers")
    nodes, table, object_ids, active = [], {}, {}, set()
    root_ids = []
    for root in roots:
        stack = [(root, False)]
        while stack:
            tree, done = stack.pop()
            oid = id(tree)
            if oid in object_ids:
                continue
            if not isinstance(tree, (list, tuple)) or len(tree) != 2:
                raise ValueError("each tree must be [symbol, [children]]")
            symbol, children = tree
            if not isinstance(symbol, str) or not isinstance(children, (list, tuple)):
                raise ValueError("tree symbol must be a string and children a sequence")
            if symbol not in ranks or ranks[symbol] != len(children):
                raise ValueError("missing or inconsistent symbol rank: " + symbol)
            if done:
                active.remove(oid)
                key = (symbol, tuple(object_ids[id(child)] for child in children))
                if key not in table:
                    table[key] = len(nodes)
                    nodes.append(key)
                object_ids[oid] = table[key]
            else:
                if oid in active:
                    raise ValueError("cyclic input is not a finite tree")
                active.add(oid)
                stack.append((tree, True))
                stack.extend((child, False) for child in reversed(children))
        root_ids.append(object_ids[id(root)])
    root_ids = list(dict.fromkeys(root_ids))
    root_counts = Counter(root_ids)
    parents = [Counter() for _ in nodes]
    for p, (_, children) in enumerate(nodes):
        for v, multiplicity in Counter(children).items():
            parents[v][p] = multiplicity
    raw_counts = [root_counts[v] for v in range(len(nodes))]
    for p in reversed(range(len(nodes))):
        for v, multiplicity in Counter(nodes[p][1]).items():
            raw_counts[v] += multiplicity * raw_counts[p]
    return nodes, root_ids, root_counts, parents, raw_counts


def _counts(nodes, roots, selected):
    demand = [0] * len(nodes)
    for v in roots:
        demand[v] += 1
    constructors = [0] * len(nodes)
    for p in reversed(range(len(nodes))):
        constructors[p] = 1 if p in selected else demand[p]
        for v in nodes[p][1]:
            demand[v] += constructors[p]
    return constructors


def _render(nodes, roots, selected, charge, constructor_symbols):
    """Emit explicit constructor/reference syntax and count its actual nodes."""
    occupied = set(constructor_symbols)
    names = {}
    next_name = 0
    for v in sorted(selected):
        name = "__macro" + str(next_name)
        while name in occupied:
            next_name += 1
            name = "__macro" + str(next_name)
        occupied.add(name)
        names[v] = name

    def tree(v, body=False):
        holder = []
        todo = [(v, body, holder)]
        while todo:
            u, force_constructor, destination = todo.pop()
            if u in selected and not force_constructor:
                destination.append([names[u], []])
                continue
            symbol, children = nodes[u]
            result = [symbol, []]
            destination.append(result)
            todo.extend((child, False, result[1])
                        for child in reversed(children))
        return holder[0]

    definitions = {names[v]: tree(v, True) for v in sorted(selected)}
    output = [tree(v) for v in roots]
    count = 0
    todo = output[:] + list(definitions.values())
    while todo:
        item = todo.pop()
        count += 1
        todo.extend(item[1])
    cost = Fraction(count) + charge * len(definitions)
    return {"definitions": definitions, "roots": output,
            "node_count": count, "definition_count": len(definitions),
            "charged_cost_exact": str(cost), "cost": str(cost)}, cost


def _finite(value):
    return float(value) if value is not None and math.isfinite(float(value)) else None


def solve(case, h, time_limit=20):
    """Solve MILP with an unshared fallback for valid inputs.
Charges accept integers, decimals or p/q strings; floats use their decimal string."""
    started = time.perf_counter()
    result = {"case_id": case.get("id") if isinstance(case, dict) else None,
              "status": "invalid_input", "h_exact": None,
              "lower_bound": None, "upper_bound": None, "gap": None,
              "objective": None, "encoding": None, "stats": {},
              "solver": {}, "timing": {}}
    try:
        charge = h if isinstance(h, Fraction) else Fraction(str(h))
        if charge < 0:
            raise ValueError("definition charge must be nonnegative")
        limit = float(time_limit)
        if not math.isfinite(limit) or limit <= 0:
            raise ValueError("time_limit must be finite and positive")
        nodes, roots, root_counts, parents, raw = _intern(case)
    except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
        result["message"] = str(exc)
        result["timing"]["total_seconds"] = time.perf_counter() - started
        return result

    result["h_exact"] = str(charge)
    N = len(nodes)
    candidates = [v for v, (_, children) in enumerate(nodes) if children]
    K = len(candidates)
    x_index = {v: N + j for j, v in enumerate(candidates)}
    denominator, numerator = charge.denominator, charge.numerator
    offset = len(roots) * denominator
    arities = [len(children) for _, children in nodes]
    coefficients = [a * denominator for a in arities] + [numerator + denominator] * K
    # Lower bound: c_v >= 1, x_v >= 0.
    analytic_lower = len(roots) + sum(arities)
    encoding, upper = _render(nodes, roots, set(), charge, case["ranks"])
    scaled_upper = int(upper * denominator)
    result["stats"] = {"input_root_count": len(case["roots"]),
                       "distinct_root_count": len(roots), "subterm_count": N,
                       "candidate_count": K, "constructor_variables": N,
                       "binary_variables": K, "raw_node_count": sum(raw)}
    solver_info = {"backend": "scipy.optimize.milp/HiGHS", "scipy_version": scipy.__version__,
                   "time_limit": limit, "mip_rel_gap_requested": 0.0,
                   "threads_requested": 1, "threads_enforcement_verified": False,
                   "warnings": [], "incumbent_validated": False,
                   "numerical_certificate_only": True, "formal_rational_proof": False}
    result["solver"] = solver_info
    model_done = time.perf_counter()
    solver_seconds, witness_seconds = 0.0, 0.0
    lower, raw_lower = float(analytic_lower), None
    lower_kind = "exact_analytic"
    status = "solver_error_feasible"
    raw_dual = None
    constraint_count = 0

    if not K:
        status = "optimal_trivial_exact"
        solver_info.update(message="No nonconstant candidates; no MILP required.",
                           formal_rational_proof=True, numerical_certificate_only=False)
    elif max([offset + sum(a * n for a, n in zip(coefficients[:N], raw))
              + (numerator + denominator) * K, denominator, sum(raw)]
             + coefficients) > 2 ** 50:
        status = "numeric_range_unsupported_feasible"
        solver_info["message"] = "Integer-scaled magnitude exceeds conservative 2**50 limit."
    else:
        rows, cols, data, lower_rows, upper_rows = [], [], [], [], []

        def row(entries, lb, ub):
            i = len(lower_rows)
            for col, value in entries.items():
                if value:
                    rows.append(i)
                    cols.append(col)
                    data.append(value)
            lower_rows.append(lb)
            upper_rows.append(ub)

        for v in range(N):
            # d = c_v - sum_p m_pv*c_p, so c_v - q_v = d-r_v.
            d = {v: 1}
            d.update({p: -m for p, m in parents[v].items()})
            r = root_counts[v]
            if v not in x_index:
                row(d, r, r)
            else:
                M, xi = raw[v] - 1, x_index[v]
                row(d, -np.inf, r)                  # c_v <= q_v
                row({**d, xi: M}, r, np.inf)        # c_v >= q_v - M*x_v
                row({v: 1, xi: M}, -np.inf, raw[v]) # c_v <= 1+M*(1-x_v)
        constraint_count = len(lower_rows)
        A = coo_matrix((data, (rows, cols)), shape=(constraint_count, N + K)).tocsc()
        variable_lower = np.array([1] * N + [0] * K, dtype=float)
        variable_upper = np.array(raw + [1] * K, dtype=float)
        constraints = LinearConstraint(A, lower_rows, upper_rows)
        model_done = time.perf_counter()
        solve_started = time.perf_counter()
        opt = None
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                try:
                    opt = milp(np.array(coefficients, dtype=float),
                               integrality=np.ones(N + K),
                               bounds=Bounds(variable_lower, variable_upper),
                               constraints=constraints,
                               options={"time_limit": limit, "mip_rel_gap": 0.0,
                                        "threads": 1, "random_seed": 0})
                finally:
                    solver_info["warnings"] = [str(w.message) for w in caught]
        except Exception as exc:
            solver_info["message"] = type(exc).__name__ + ": " + str(exc)
        solver_seconds = time.perf_counter() - solve_started
        if opt is not None:
            solver_info.update(status_code=int(opt.status), message=str(opt.message),
                               reported_objective_scaled=_finite(getattr(opt, "fun", None)),
                               reported_mip_gap=_finite(getattr(opt, "mip_gap", None)),
                               mip_node_count=(int(opt.mip_node_count)
                                               if getattr(opt, "mip_node_count", None) is not None else None))
            status = "limit_feasible" if opt.status == 1 else "solver_error_feasible"
            raw_dual = _finite(getattr(opt, "mip_dual_bound", None))
            witness_started = time.perf_counter()
            try:
                if getattr(opt, "x", None) is not None:
                    vector = np.asarray(opt.x)
                    if len(vector) != N + K or not np.all(np.isfinite(vector)):
                        raise ValueError("malformed solver incumbent")
                    rounded = [int(round(float(a))) for a in vector]
                    if max(abs(float(a) - b) for a, b in zip(vector, rounded)) > 1e-5:
                        raise ValueError("solver incumbent fails integrality check")
                    if any(b not in (0, 1) for b in rounded[N:]):
                        raise ValueError("binary incumbent out of range")
                    selected = {v for v in candidates if rounded[x_index[v]]}
                    canonical_counts = _counts(nodes, roots, selected)
                    if rounded[:N] != canonical_counts:
                        raise ValueError("integer constructor counts fail exact recurrence")
                    if any(not 1 <= c <= n for c, n in zip(canonical_counts, raw)):
                        raise ValueError("integer constructor counts out of range")
                    candidate_encoding, candidate_upper = _render(nodes, roots, selected, charge, case["ranks"])
                    exact_scaled = candidate_upper * denominator
                    model_scaled = offset + sum(a * b for a, b in zip(coefficients, rounded))
                    if exact_scaled.denominator != 1 or exact_scaled != model_scaled:
                        raise ValueError("rendered witness cost does not match integer MILP objective")
                    reported = _finite(getattr(opt, "fun", None))
                    if reported is None or abs(reported - (model_scaled - offset)) > 0.25:
                        raise ValueError("rendered cost does not match floating incumbent within 0.25 scaled unit")
                    solver_info["incumbent_validated"] = True
                    solver_info["validated_incumbent_scaled"] = int(exact_scaled)
                    if candidate_upper <= upper:
                        encoding, upper, scaled_upper = candidate_encoding, candidate_upper, int(exact_scaled)
                    if opt.status == 0:
                        status = "optimal_numerical"
            except (ValueError, OverflowError) as exc:
                solver_info["incumbent_rejection"] = str(exc)
                status = "incumbent_rejected_feasible"
            witness_seconds = time.perf_counter() - witness_started

    if raw_dual is not None:
        raw_lower = (raw_dual + offset) / denominator
        # Keep the numerical bound unrounded.
        margin = max(1e-7, 1e-7 * abs(raw_dual))
        padded_scaled = math.nextafter(raw_dual - margin + offset, -math.inf)
        padded_lower = math.nextafter(padded_scaled / denominator, -math.inf)
        solver_info["dual_padding_scaled"] = margin
        if padded_lower > float(upper):
            solver_info["dual_bound_rejection"] = "Padded dual bound exceeds exact feasible witness."
            if status == "optimal_numerical":
                status = "numerical_inconsistency_feasible"
        elif padded_lower > lower:
            lower = padded_lower
            lower_kind = "padded_numerical_not_formal"
    absolute_gap = max(0.0, float(upper) - lower)
    relative_gap = absolute_gap / max(1.0, abs(float(upper)))
    result.update(status=status, encoding=encoding, lower_bound=lower,
                  upper_bound=float(upper), gap=relative_gap)
    result["objective"] = {"lower_bound": lower, "lower_bound_kind": lower_kind,
                           "lower_bound_raw_solver": raw_lower,
                           "lower_bound_analytic_exact": str(analytic_lower),
                           "upper_bound": float(upper), "upper_bound_exact": str(upper),
                           "upper_bound_scaled": scaled_upper, "integer_scale": denominator,
                           "absolute_gap": absolute_gap, "relative_gap": relative_gap}
    result["stats"]["constraint_count"] = constraint_count
    result["timing"] = {"model_seconds": model_done - started,
                        "solver_seconds": solver_seconds, "witness_seconds": witness_seconds,
                        "total_seconds": time.perf_counter() - started}
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_json", help="JSON object containing id, roots, ranks")
    parser.add_argument("--h", default="1")
    parser.add_argument("--time-limit", type=float, default=20)
    args = parser.parse_args()
    with open(args.case_json, encoding="utf-8") as source:
        answer = solve(json.load(source), args.h, args.time_limit)
    print(json.dumps(answer, ensure_ascii=False, allow_nan=False))
