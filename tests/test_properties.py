"""Metamorphic and property tests: transformations that must never change (or must always change) a verdict.

Seeded stdlib randomness keeps them deterministic, and there are no extra dependencies. Each property is checked for every
notified entry in the registry, not on hand-picked examples.
"""
import itertools
import random
import unittest

from banlag.claims import restriction_statements
from banlag.legal import match_formula, registry

DB = registry()
ENTRIES = DB['entries']
OTHERS = sorted(DB['other_actives'])
SEED = 2026


def variants(names, rng):
    """Same set, different surface: order, letter case and surrounding whitespace."""
    p = list(names)
    rng.shuffle(p)
    style = [str.upper, str.title, str.lower, lambda s: '  ' + s + ' ']
    return [rng.choice(style)(x) for x in p]


def sentence(names, tail='is prohibited in India.'):
    return 'The fixed-dose combination of ' + ' + '.join(n.title() for n in names) + ' ' + tail


class MatcherProperties(unittest.TestCase):
    def test_order_case_and_whitespace_never_change_an_exact_match(self):
        rng = random.Random(SEED)
        for e in ENTRIES:
            for _ in range(25):
                v = variants(e['ingredients'], rng)
                with self.subTest(entry=e['id'], input=v):
                    r = match_formula(v)
                    self.assertEqual(r['status'], 'EXACT_NOTIFICATION_MATCH')
                    self.assertEqual(r['entry']['id'], e['id'])

    def test_no_strict_subset_inherits_a_prohibition(self):
        for e in ENTRIES:
            ing = e['ingredients']
            for k in range(1, len(ing)):
                for sub in itertools.combinations(ing, k):
                    r = match_formula(list(sub))
                    with self.subTest(entry=e['id'], subset=sub):
                        if r['status'] == 'EXACT_NOTIFICATION_MATCH':  # only allowed when the subset is itself a notified set
                            self.assertEqual(set(r['entry']['ingredients']), set(sub))

    def test_no_superset_inherits_a_prohibition(self):
        for e in ENTRIES:
            for extra in OTHERS + sorted({i for x in ENTRIES for i in x['ingredients']}):
                if extra in e['ingredients']:
                    continue
                r = match_formula(e['ingredients'] + [extra])
                with self.subTest(entry=e['id'], extra=extra):
                    if r['status'] == 'EXACT_NOTIFICATION_MATCH':
                        self.assertEqual(set(r['entry']['ingredients']), set(e['ingredients']) | {extra})

    def test_duplicates_and_unknown_names_abstain(self):
        for e in ENTRIES:
            ing = e['ingredients']
            with self.subTest(entry=e['id']):
                self.assertNotEqual(match_formula(ing + [ing[0]])['status'], 'EXACT_NOTIFICATION_MATCH')
                self.assertNotEqual(match_formula(ing + ['zz-not-a-drug'])['status'], 'EXACT_NOTIFICATION_MATCH')


class StatementProperties(unittest.TestCase):
    """restriction_statements(text, entry) must follow the exact set, the jurisdiction and the event's final status."""

    def setUp(self):
        self.rng = random.Random(SEED)

    def test_exact_set_in_any_order_is_a_restriction_statement(self):
        for e in ENTRIES:
            for _ in range(5):
                p = list(e['ingredients'])
                self.rng.shuffle(p)
                with self.subTest(entry=e['id'], order=p):
                    self.assertTrue(restriction_statements(sentence(p), e))

    def test_dropping_or_adding_an_ingredient_breaks_it(self):
        for e in ENTRIES:
            p = list(e['ingredients'])
            self.rng.shuffle(p)
            extra = self.rng.choice([o for o in OTHERS if o not in p])
            with self.subTest(entry=e['id'], extra=extra):
                self.assertFalse(restriction_statements(sentence(p + [extra]), e))
                if len(p) > 2:
                    self.assertFalse(restriction_statements(sentence(p[:-1]), e))

    def test_other_jurisdiction_and_revocation_break_it(self):
        for e in ENTRIES:
            p = e['ingredients']
            with self.subTest(entry=e['id']):
                self.assertFalse(restriction_statements(sentence(p, 'is prohibited in Canada.'), e))
                self.assertFalse(restriction_statements(sentence(p, 'was prohibited in India, but the ban was revoked.'), e))
                self.assertFalse(restriction_statements(sentence(p, 'may be prohibited in India next year.'), e))


if __name__ == '__main__':
    unittest.main()
