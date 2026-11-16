"""Leakage and physics checks for the model comparison."""

import unittest

import numpy as np
import pandas as pd

import compare


def episode(power):
    n = len(power)
    return pd.DataFrame({"scenario_id": "S1", "rail_id": "rail_1", "elapsed_s": range(n),
                         "ambient_temp_c": 25.0, "rail_power_w": power,
                         "rail_hotspot_temp_c": np.linspace(30, 60, n)})


class CompareTests(unittest.TestCase):
    def test_features_ignore_the_future(self):
        power = np.r_[np.full(300, 6.0), np.full(300, 19.0)]
        full = compare.add_features(episode(power))
        changed = episode(power)
        changed.loc[400:, ["rail_power_w", "rail_hotspot_temp_c"]] = 99.0
        past = compare.add_features(changed)
        pd.testing.assert_frame_equal(full.loc[:399, compare.FEATURES[:2] + compare.FEATURES[3:]],
                                      past.loc[:399, compare.FEATURES[:2] + compare.FEATURES[3:]])

    def test_step_clock_counts_each_step_once(self):
        clock = compare.step_clock(np.r_[np.full(300, 6.0), np.full(300, 19.0), np.full(300, 6.0)])
        self.assertEqual(clock[-1, 2:].tolist(), [1, 1])
        self.assertEqual(clock[299, 0], 1800)  # no step seen yet
        self.assertLess(clock[310, 0], 10)  # detected within seconds of the jump

    def test_rc_forecast_holds_equilibrium_and_relaxes_towards_it(self):
        params = {1: [400.0, 3.0]}
        frame = pd.DataFrame({"rail": [1, 1], "A": 25.0, "P_m5": 10.0, "T_m5": [55.0, 35.0]})
        at_rest, heating = compare.rc_forecast(frame, params, 300)
        self.assertAlmostEqual(at_rest, 55.0)
        self.assertTrue(35.0 < heating < 55.0)


if __name__ == "__main__":
    unittest.main()
