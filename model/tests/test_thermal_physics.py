import math
import numpy as np
import pytest
from grid_model.physics_ieee import TransformerParameters, run_profile, ultimate_rises, effective_oil_tau, aging_acceleration
from grid_model.transformer_predictor import TransformerPredictor
from grid_model.contracts import PredictRequest


def test_ieee_annex_c_rated_and_prior_load_reference():
    # C57.91-2011 Annex C parameters and corrected C.1 prior equilibrium.
    p = TransformerParameters(rated_power_kva=187000.,rated_top_oil_rise_c=36.,rated_hotspot_gradient_c=28.6,
                              load_loss_w=4870.,no_load_loss_w=1000.,oil_time_constant_s=3.5*3600,oil_exponent_n=1.,winding_exponent_m=1.)
    oil, winding = ultimate_rises(.634,p)
    assert oil == pytest.approx(18.14,abs=.01)
    assert ultimate_rises(1,p) == pytest.approx([36.,28.6])
    result = run_profile([0,3600],[.634,1.],[30,30],p)
    expected_oil = 36+(oil-36)*math.exp(-1/3.5)
    expected_gradient = 28.6+(winding-28.6)*math.exp(-3600/p.winding_time_constant_s)
    assert result["top_oil_c"][-1] == pytest.approx(30+expected_oil)
    assert result["hotspot_c"][-1] == pytest.approx(30+expected_oil+expected_gradient)


def test_ieee_aging_reference_and_no_arbitrary_life():
    assert aging_acceleration(110.) == pytest.approx(1.)
    assert aging_acceleration(117.) > 1.9
    p = TransformerParameters(oil_exponent_n=1.,winding_exponent_m=1.,normal_insulation_life_h=180000.)
    result = run_profile([0,3600],[1,1],[30,30],p)
    assert result["hotspot_c"] == pytest.approx([110,110])
    assert result["equivalent_aging_h"] == pytest.approx(1.)
    assert result["loss_of_life_percent"] == pytest.approx(100/180000)
    assert run_profile([0,60],[1,1],[30,30])["loss_of_life_percent"] is None


def test_oil_tau_correction_equal_rise_and_transient_units():
    p = TransformerParameters()
    assert effective_oil_tau(55,55,p) == pytest.approx(.8*10800)
    assert effective_oil_tau(0,55,p) == pytest.approx(10800)
    hot = run_profile([0,60,300],[.7,1.4,1.4],[30]*3)["hotspot_c"]
    assert hot[0] < hot[1] < hot[2]
    cooling = run_profile([0,60,300],[1,0,0],[30]*3)["hotspot_c"]
    assert cooling[0] > cooling[1] > cooling[2] > 30


@pytest.mark.parametrize("kwargs", [{"oil_time_constant_s":0},{"oil_exponent_n":float("nan")},{"rated_current_a":-1},{"normal_insulation_life_h":0}])
def test_bad_parameters(kwargs):
    with pytest.raises(ValueError): TransformerParameters(**kwargs)


def test_actual_alliander_reference_api_and_seconds_conversion():
    pytest.importorskip("transformer_thermal_model")
    from grid_model.physics_alliander import run_profile as iec
    p = TransformerParameters(oil_exponent_n=1,winding_exponent_m=1)
    result = iec([0,60,300],[.7,1.4,1.4],[30]*3,p)
    # Independent exact two-lag analytical case, k11=k21=k22=1.
    expected = [73.875,80.90991256505426,98.95120389123554]
    assert result["hotspot_c"] == pytest.approx(expected,abs=1e-9)
    np.testing.assert_allclose(result["top_oil_c"],run_profile([0,60,300],[.7,1.4,1.4],[30]*3,p)["top_oil_c"])
    equilibrium = iec([0,60,300],[1]*3,[30]*3,p)
    assert equilibrium["hotspot_c"] == pytest.approx([110]*3)


@pytest.mark.parametrize("kind", ["ieee_c57_91","alliander_iec"])
def test_forecast_domain_and_both_horizons(kind):
    if kind == "alliander_iec": pytest.importorskip("transformer_thermal_model")
    predictor = TransformerPredictor(kind)
    history = [dict(t_s=0,load_factor=.7,ambient_temp_c=30,sensor_valid=True),dict(t_s=1,load_factor=1.5,ambient_temp_c=30,sensor_valid=True)]
    assert predictor.predict(PredictRequest("rail_2",history)).data_quality == "invalid"
    response = predictor.predict(PredictRequest("transformer_1",history,hardware_domain="oil_transformer"))
    assert response.data_quality == "good" and not response.actuation_eligible
    assert response.predicted_hotspot_plus_300s_c > response.predicted_hotspot_plus_60s_c
    assert response.predicted_top_oil_plus_300s_c is not None
    assert response.observed_hotspot_c is None and response.estimated_hotspot_c is not None
    assert response.eta_to_80c_s is None and response.threshold_c == 110
