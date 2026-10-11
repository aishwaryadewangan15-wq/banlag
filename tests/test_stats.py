"""Study metrics (banlag.stats): interval maths against known values, kappa, and the pinned study numbers."""
import contextlib
import io
import unittest

from banlag import stats


class Wilson(unittest.TestCase):
    def test_known_values(self):
        lo, hi = stats.wilson(7, 10)
        self.assertAlmostEqual(lo, 0.3968, places=3)
        self.assertAlmostEqual(hi, 0.8922, places=3)
        lo, hi = stats.wilson(0, 10)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.2775, places=3)
        lo, hi = stats.wilson(10, 10)
        self.assertAlmostEqual(lo, 0.7225, places=3)
        self.assertAlmostEqual(hi, 1.0, places=12)

    def test_interval_always_contains_the_point_estimate_and_narrows_with_n(self):
        for n in (1, 5, 20, 100):
            for k in range(n + 1):
                lo, hi = stats.wilson(k, n)
                self.assertLessEqual(lo, k / n + 1e-12)
                self.assertGreaterEqual(hi, k / n - 1e-12)
        self.assertLess(stats.wilson(70, 100)[1] - stats.wilson(70, 100)[0], stats.wilson(7, 10)[1] - stats.wilson(7, 10)[0])

    def test_edges(self):
        self.assertEqual(stats.wilson(0, 0), (0.0, 1.0))
        with self.assertRaises(ValueError):
            stats.wilson(3, 2)


class Kappa(unittest.TestCase):
    def test_values(self):
        self.assertEqual(stats.cohen_kappa([('E', 'E'), ('D', 'D')]), 1.0)
        self.assertIsNone(stats.cohen_kappa([('E', 'E'), ('E', 'E')]))
        self.assertIsNone(stats.cohen_kappa([]))
        self.assertAlmostEqual(stats.cohen_kappa([('a', 'a'), ('a', 'b'), ('b', 'b'), ('b', 'a')]), 0.0)


class StudyNumbers(unittest.TestCase):
    """Pinned to the locked corpus: a change here means the corpus or the engine changed."""

    def test_pinned(self):
        m = {r['metric']: (r['k'], r['n']) for r in stats.study_metrics()['metrics']}
        self.assertEqual(m['combinations_E_in_both_passes'], (7, 10))
        self.assertEqual(m['uses_answers_present_use_unwarned'], (14, 20))
        self.assertEqual(m['prompt_dependent_disclosure'], (7, 7))
        self.assertEqual(m['engine_coder_agreement_primary'], (20, 20))
        self.assertEqual(m['engine_coder_agreement_all'], (40, 41))

    def test_table_carries_the_scope_statement(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            stats.main([])
        self.assertIn('not how often Google behaves this way in general', out.getvalue())
        self.assertIn('40% to 89%', out.getvalue())


if __name__ == '__main__':
    unittest.main()
