"""Exact syntax, expansion and cost checks, with a small exhaustive oracle."""

from __future__ import annotations

import argparse
from copy import deepcopy
from fractions import Fraction
import json
import re
import sys


MAX_CANDIDATES = 17


def _charge(value):
    if not isinstance(value, str) or not re.fullmatch(r"[+-]?\d+(?:/[1-9]\d*)?", value):
        raise ValueError("h must be an exact integer or rational string")
    result = Fraction(value)
    if result < 0:
        raise ValueError("h must be nonnegative")
    return result


def _case_header(case):
    if not isinstance(case, dict) or not isinstance(case.get("id"), str):
        raise ValueError("case must contain a string id")
    ranks = case.get("ranks")
    if not isinstance(ranks, dict) or any(
        not isinstance(k, str) or not k or type(v) is not int or v < 0
        for k, v in ranks.items()
    ):
        raise ValueError("ranks must map nonempty symbols to nonnegative integers")
    if not isinstance(case.get("roots"), list):
        raise ValueError("case roots must be a list")
    return ranks


def solve(case, h):
    """Enumerate nonconstant-subtree subsets for a bounded exact oracle.
Roots form a set; children stay ordered. Definitions retain their root and
replace selected proper subtrees with names. Bottom-up subset order breaks ties."""
    charge = _charge(h)
    ranks = _case_header(case)
    nodes, index = [], {}
    candidate_nodes = []

    def collect(term):
        if not isinstance(term, list) or len(term) != 2:
            raise ValueError("each input term must be [symbol, [children]]")
        symbol, children = term
        if not isinstance(symbol, str) or symbol not in ranks:
            raise ValueError("input symbol is absent from ranks")
        if not isinstance(children, list) or len(children) != ranks[symbol]:
            raise ValueError("input constructor rank mismatch")
        child_ids = tuple(collect(child) for child in children)
        key = (symbol, child_ids)
        if key not in index:
            index[key] = len(nodes)
            nodes.append(key)
            if children:
                candidate_nodes.append(index[key])
        return index[key]

    root_nodes = list(dict.fromkeys(collect(root) for root in case["roots"]))
    n = len(candidate_nodes)
    if n > MAX_CANDIDATES:
        raise ValueError(f"{n} nonconstant candidates exceeds bound {MAX_CANDIDATES}")
    bits = [0] * len(nodes)
    for pos, node in enumerate(candidate_nodes):
        bits[node] = 1 << pos
    # Count stored occurrences, retaining each definition root.
    denominator, numerator = charge.denominator, charge.numerator
    best_value, best_mask = None, None
    sizes = [1] * len(nodes)
    for mask in range(1 << n):
        stored_bodies = 0
        selected_count = 0
        for node, (_, children) in enumerate(nodes):
            body_size = 1
            for child in children:
                body_size += sizes[child]
            if mask & bits[node]:
                stored_bodies += body_size
                selected_count += 1
                sizes[node] = 1
            else:
                sizes[node] = body_size
        stored_nodes = stored_bodies + sum(sizes[node] for node in root_nodes)
        value = stored_nodes * denominator + selected_count * numerator
        if best_value is None or value < best_value:
            best_value, best_mask = value, mask

    selected = [node for node in candidate_nodes if best_mask & bits[node]]
    names = {}
    serial = 0
    for node in selected:
        while f"__c055_d{serial}" in ranks:
            serial += 1
        names[node] = f"__c055_d{serial}"
        serial += 1

    def render(node, own_root=False):
        if node in names and not own_root:
            return [names[node], []]
        symbol, children = nodes[node]
        return [symbol, [render(child) for child in children]]

    return {
        "cost": str(Fraction(best_value, denominator)),
        "roots": [render(node) for node in root_nodes],
        "definitions": {names[node]: render(node, own_root=True) for node in selected},
        "subsets": 1 << n,
        "candidates": n,
    }


def check(case, h, encoding):
    """Check all definitions, expansion and exact cost using a local constructor table."""
    errors = []
    try:
        charge = _charge(h)
        ranks = _case_header(case)
        if not isinstance(encoding, dict):
            raise ValueError("encoding must be an object")
        definitions = encoding.get("definitions")
        if not isinstance(definitions, dict):
            raise ValueError("definitions must be a name-to-body object")
        if any(not isinstance(name, str) or not name for name in definitions):
            raise ValueError("definition names must be nonempty strings")
        if set(definitions) & set(ranks):
            raise ValueError("definition names must be fresh outside the ranked alphabet")
        if not isinstance(encoding.get("roots"), list):
            raise ValueError("encoding roots must be a list")

        # Compare ordered trees using checker-local constructor IDs.
        structures = {}

        def intern(symbol, children):
            key = (symbol, tuple(children))
            if key not in structures:
                structures[key] = len(structures)
            return structures[key]

        def unpack(term):
            if not isinstance(term, list) or len(term) != 2:
                raise ValueError("each stored term must be [symbol, [children]]")
            symbol, children = term
            if not isinstance(symbol, str) or not isinstance(children, list):
                raise ValueError("malformed stored term")
            return symbol, children

        def input_tree(term):
            symbol, children = unpack(term)
            if symbol not in ranks:
                raise ValueError("input symbol is absent from ranks")
            if len(children) != ranks[symbol]:
                raise ValueError("input constructor rank mismatch")
            return intern(symbol, [input_tree(child) for child in children])

        expected = {input_tree(root) for root in case["roots"]}
        for name, body in definitions.items():
            symbol, children = unpack(body)
            if symbol not in ranks or ranks[symbol] == 0 or not children:
                raise ValueError(f"definition {name} must keep a nonconstant constructor root")

        state, expanded = {}, {}

        def expand_name(name):
            if state.get(name) == "visiting":
                raise ValueError(f"cyclic definition reference at {name}")
            if state.get(name) == "done":
                return expanded[name]
            state[name] = "visiting"
            value = expand_term(definitions[name])
            expanded[name] = value
            state[name] = "done"
            return value

        def expand_term(term):
            symbol, children = unpack(term)
            if symbol in ranks:
                if len(children) != ranks[symbol]:
                    raise ValueError(f"constructor rank mismatch at {symbol}")
                return intern(symbol, [expand_term(child) for child in children])
            if symbol not in definitions:
                raise ValueError(f"missing definition name {symbol}")
            if children:
                raise ValueError(f"definition reference {symbol} must be nullary")
            return expand_name(symbol)

        for name in definitions:
            expand_name(name)
        actual = {expand_term(root) for root in encoding["roots"]}
        if actual != expected:
            errors.append("expanded output set differs from the input root set")

        # Count every stored node, including references and definition bodies.
        def count(term):
            _, children = unpack(term)
            return 1 + sum(count(child) for child in children)

        stored = sum(count(root) for root in encoding["roots"])
        stored += sum(count(body) for body in definitions.values())
        computed = Fraction(stored) + charge * len(definitions)
        declared = _charge(encoding.get("cost"))
        if declared != computed:
            errors.append(f"wrong cost: declared {declared}, direct syntax gives {computed}")
        return {"ok": not errors, "errors": errors, "cost": str(computed)}
    except (ValueError, TypeError, RecursionError) as error:
        return {"ok": False, "errors": [str(error)]}


def preflight():
    """Check one valid encoding and five invalid mutations."""
    a = ["a", []]
    f = ["f", [a]]
    case = {"id": "unit-three-repetitions", "ranks": {"a": 0, "f": 1, "g": 2},
            "roots": [["g", [["g", [f, f]], f]]]}
    ref = ["D", []]
    positive = {"cost": "15/2", "roots": [["g", [["g", [ref, ref]], ref]]],
                "definitions": {"D": ["f", [["a", []]]]}}
    accepted = check(case, "1/2", positive)
    if not accepted["ok"]:
        raise AssertionError(accepted)
    result = solve(case, "1/2")
    if result["cost"] != "15/2" or result["subsets"] != 8 or not check(case, "1/2", result)["ok"]:
        raise AssertionError(result)
    controls = {}
    for label in ("selfcycle", "wrongcost", "constantbody", "missingname", "rankmismatch"):
        broken = deepcopy(positive)
        if label == "selfcycle":
            broken["definitions"]["D"] = ["f", [["D", []]]]
        elif label == "wrongcost":
            broken["cost"] = "0"
        elif label == "constantbody":
            broken["definitions"]["D"] = ["a", []]
        elif label == "missingname":
            broken["definitions"] = {}
        else:
            broken["roots"][0][1].pop()
        verdict = check(case, "1/2", broken)
        if verdict["ok"]:
            raise AssertionError(f"checker accepted {label}")
        controls[label] = verdict
    return {"status": "preflight_pass", "positive": result, "controls": controls,
            "scope": "one unit fixture only; no scientific cases executed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("solve", "check"), nargs="?")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    if args.preflight:
        if args.mode:
            parser.error("--preflight does not accept a mode")
        result = preflight()
    else:
        if args.mode is None:
            parser.error("provide solve, check, or --preflight")
        request = json.load(sys.stdin)
        result = (solve(request["case"], request["h"]) if args.mode == "solve"
                  else check(request["case"], request["h"], request["encoding"]))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
