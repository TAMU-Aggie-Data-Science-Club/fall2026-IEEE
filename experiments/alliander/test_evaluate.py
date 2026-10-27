"""Checks for leakage boundaries and correctness of the actual library adapter."""

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import evaluate as experiment


class ExperimentTests(unittest.TestCase):
    def test_calibration_refuses_test_scenarios(self):
        with self.assertRaisesRegex(ValueError, "train and val"):
            experiment.calibrate(pd.DataFrame({"data_split": ["test"]}),
                                 pd.DataFrame({"data_split": ["val"]}))

    def test_constant_profile_sparse_steps_match_one_second_simulation(self):
        sparse = experiment.forecast(1.2, 25., 48., experiment.make_transformer(5., 20.))
        dense = experiment.forecast(1.2, 25., 48., experiment.make_transformer(5., 20.), tuple(range(301)))
        np.testing.assert_allclose(sparse, dense[[59, 299]], atol=1e-9)

    def test_hot_start_is_not_silently_reset_to_ambient(self):
        cold = experiment.forecast(.7, 25., 25., experiment.make_transformer(5., 20.))
        hot = experiment.forecast(.7, 25., 65., experiment.make_transformer(5., 20.))
        self.assertTrue(np.all(hot > cold))

    def test_missing_targets_are_excluded_per_horizon_and_baselines_share_rows(self):
        origins = pd.DataFrame({"scenario_id": ["S1", "S1"], "rail_id": ["rail_1"] * 2,
                                "elapsed_s": [0, 30], "data_split": ["test"] * 2,
                                "scenario_type": ["normal"] * 2, "rail_hotspot_temp_c": [40., 41.],
                                experiment.TARGETS[0]: [42., 43.], experiment.TARGETS[1]: [45., np.nan]})
        table = experiment.prediction_table(origins, np.array([[41., 44.], [42., 45.]]))
        self.assertEqual(table.groupby("horizon_s").size().to_dict(), {60: 2, 300: 1})
        scores = experiment.score(table, ["data_split", "horizon_s"])
        self.assertEqual([s["n"] for s in scores], [2, 2, 1, 1])

    def test_invalid_sensor_and_off_cadence_rows_are_not_forecast(self):
        data = pd.DataFrame({"sensor_valid": [1, 0, 1, 1], "elapsed_s": [0, 30, 31, 60],
                             experiment.TARGETS[0]: [40., 40., 40., np.nan],
                             experiment.TARGETS[1]: [41., 41., 41., np.nan]})
        self.assertEqual(experiment.sample_origins(data, 30).index.tolist(), [0])

    def test_cross_split_scenario_is_rejected_before_fitting(self):
        data = pd.DataFrame({"scenario_id": ["S1", "S1"], "rail_id": ["rail_1"] * 2,
                             "elapsed_s": [0, 1], "sensor_valid": [1, 1], "data_split": ["train", "test"],
                             **{c: [25., 25.] for c in experiment.INPUTS + experiment.TARGETS}})
        scenarios = pd.DataFrame({"scenario_id": ["S1"], "data_split": ["train"]})
        # Include all split names so rejection specifically exercises scenario overlap.
        extra = data.iloc[[0]].assign(scenario_id="S2", data_split="val")
        data = pd.concat([data, extra])
        with patch.object(pd, "read_csv", side_effect=[data, scenarios]):
            with self.assertRaisesRegex(ValueError, "multiple splits"):
                experiment.load_data(experiment.Path("unused"))


if __name__ == "__main__":
    unittest.main()
