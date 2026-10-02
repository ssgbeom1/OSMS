"""Named boundary checks outside the frozen input universe."""
from collections import Counter
from fractions import Fraction
from pathlib import Path
import json
import check as c


def t(s, *ch):
    return s, tuple(ch)


def main(out):
    if out.exists():
        raise FileExistsError(out)
    a, b = t('a'), t('b')
    permuted = (t('q', a, b), t('q', b, a))
    assert c.equal(*permuted)
    assert len({c.translate(x) for x in permuted}) == 1
    assert not c.equal(t('q', a, a), t('q', a, b))
    assert c.equal(t('m', a, a, b), t('m', a, b, a))
    assert not c.equal(t('m', a, b), t('m', b, a))
    body = t('u', a)
    bodies = (body, body)
    outputs = (t('q', t('@0'), body, t('@1')),)
    mapped = tuple(tuple(c.lift(x, bodies) for x in part) for part in (bodies, outputs))
    assert c.expand(mapped[1][0], mapped[0]) == c.translate(c.expand(outputs[0], bodies))
    assert c.syntax_cost(mapped) == c.syntax_cost((bodies, outputs))
    adversarial_bodies = (t('u', b), t('u', a))
    adversarial_output = t('q', t('@0'), t('u', a), t('@1'))
    forward_bodies = tuple(c.lift(x, adversarial_bodies) for x in adversarial_bodies)
    forward_output = c.lift(adversarial_output, adversarial_bodies)
    assert c.expand(forward_output, forward_bodies) == c.translate(c.expand(adversarial_output, adversarial_bodies))
    wrong_output = ('q#3', tuple(c.lift(x, adversarial_bodies) for x in sorted(adversarial_output[1])))
    assert c.expand(wrong_output, forward_bodies) != c.translate(c.expand(adversarial_output, adversarial_bodies))
    root_reference = ((body,), (t('@0'),))
    assert c.expand(root_reference[1][0], root_reference[0]) == body
    assert any(
        any(x[0].startswith('@') for x in outputs)
        for bodies, outputs in c.encodings((body, t('u', body))))
    duplicate_case = (t('v', body, body),)
    assert any(len(bodies) == 2 and c.equal(c.expand(bodies[0], bodies), c.expand(bodies[1], bodies))
               for bodies, outputs in c.encodings(duplicate_case))
    d = t('d'); cd = t('c', d); ac = t('a', cd); bc = t('b', cd)
    abc = t('a', t('b', t('c')))
    examples = [t('x', ac, ac, bc, bc),
                t('x', t('y', ac), t('y', ac), t('y', bc), t('y', bc)),
                t('s', t('x', abc), t('x', abc), t('y', abc), t('y', abc))]
    records = []
    for root, expected in zip(examples, (12, 15, 13)):
        # All nonconstant canonical subsets; not arbitrary-encoding enumeration here.
        w, u, forest = c.selected_values((root,))
        assert w[2] == u[2] == forest[2] == expected
        records.append({'h': 1, 'optimum_in_canonical_family': expected, 'input': root})
    witness_output = t('s', t('x', t('@0')), t('x', t('@0')), t('y', t('@0')), t('y', t('@0')))
    witness = ((abc,), (witness_output,))
    assert c.expand(witness[1][0], witness[0]) == examples[2]
    assert c.syntax_cost(witness)+len(witness[0]) == 13
    # Metamorphic negative controls must be rejected by the independent equality path.
    assert not c.equal(t('v', a, b), t('v', b, a))
    assert c.erase(c.translate(t('m', a, a, b)))[0] == 'm'
    result = {'status': 'PASS', 'boundary_groups': 6, 'published_examples': records,
              'spelling_sorted_translation_negative_control_rejected': True,
              'note': 'Fixtures separate from exhaustive universe; published examples enumerate canonical choices only.'}
    out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    import sys
    main(Path(sys.argv[1]))
