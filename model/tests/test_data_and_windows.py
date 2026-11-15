import numpy as np
import pytest
from grid_model.data import load, inspect, windows
from grid_model.features import features, sequence


@pytest.fixture(scope="module")
def dataset(): return load()


def test_fixture_integrity(dataset):
    assert len(dataset) == 194400
    assert dataset.scenario_id.nunique() == 36
    assert dataset.drop_duplicates("scenario_id").data_split.value_counts().to_dict() == {"train": 25, "test": 6, "val": 5}
    eta = dataset.target_time_to_80c_within_600s
    assert eta.isna().any() and (eta == -1).any() and (eta >= 0).any()
    assert inspect()["gaps"] == 0


def test_window_boundaries_and_online_parity(dataset):
    samples = windows(dataset, "train", stride=300, quick=True)
    for x, seq, y, row in samples:
        assert row["data_split"] == "train"
        history = dataset[(dataset.scenario_id == row["scenario_id"]) & (dataset.rail_id == row["rail_id"]) &
                          (dataset.elapsed_s <= row["t_s"]) & (dataset.elapsed_s > row["t_s"] - 300)]
        records = history.rename(columns={"elapsed_s": "t_s"}).to_dict("records")
        np.testing.assert_array_equal(features(records), x)
        np.testing.assert_array_equal(sequence(records)[0], seq)
        assert len(seq) == 60


def test_long_gap_rejected(dataset):
    records = dataset[(dataset.scenario_id == "S001") & (dataset.rail_id == "rail_1")].iloc[:300].rename(columns={"elapsed_s": "t_s"}).to_dict("records")
    for row in records[100:110]: row["sensor_valid"] = False
    with pytest.raises(ValueError, match="gap"): features(records)
