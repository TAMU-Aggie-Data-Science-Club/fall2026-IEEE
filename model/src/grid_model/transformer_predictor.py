import numpy as np
from .contracts import PredictResponse
from .physics_ieee import TransformerParameters, run_profile as ieee_profile
from .crossing import first_crossing


class TransformerPredictor:
    """Oil-transformer histories require explicit per-unit load and domain."""
    def __init__(self, model="ieee_c57_91", parameters=None):
        if model not in {"ieee_c57_91", "alliander_iec"}: raise ValueError("unknown transformer physics model")
        self.kind = model
        self.parameters = parameters or TransformerParameters()
        self.metadata = {"version": "2011-conventional" if model == "ieee_c57_91" else "0.5.0"}
        self.fallback_reason = None
        self.hardware_domain = "oil_transformer"

    def profile(self, times, load, ambient):
        if self.kind == "ieee_c57_91": return ieee_profile(times, load, ambient, self.parameters)
        from .physics_alliander import run_profile
        return run_profile(times, load, ambient, self.parameters)

    def predict(self, request):
        p, obs = self.parameters, request.observations
        response = PredictResponse(request.rail_id, obs[-1].get("rail_hotspot_temp_c") if obs else None,
                                   None, None, None, self.kind, self.metadata["version"], "invalid",
                                   hardware_domain="oil_transformer", actuation_eligible=False,
                                   limitation="requires explicit transformer load factor, ratings and initialized thermal history", threshold_c=p.threshold_c)
        if request.hardware_domain != "oil_transformer" or len(obs) < 2: return response
        try:
            if any(not row.get("sensor_valid", True) for row in obs): return response
            times = [row["t_s"] for row in obs]
            load, ambient = [row["load_factor"] for row in obs], [row["ambient_temp_c"] for row in obs]
            if request.current_t_s is not None and request.current_t_s-times[-1] > 5: return response
            end = times[-1]
            future_times = np.arange(end+1, end+301).tolist()
            result = self.profile(times+future_times, load+[load[-1]]*300, ambient+[ambient[-1]]*300)
            hot, top = np.asarray(result["hotspot_c"]), np.asarray(result["top_oil_c"])
            start = len(obs)-1
            trajectory = hot[start:]
            response.estimated_hotspot_c = float(hot[start])
            response.estimated_top_oil_c = float(top[start])
            response.predicted_hotspot_plus_60s_c = float(hot[start+60])
            response.predicted_hotspot_plus_300s_c = float(hot[-1])
            response.predicted_top_oil_plus_60s_c = float(top[start+60])
            response.predicted_top_oil_plus_300s_c = float(top[-1])
            response.eta_to_threshold_s = first_crossing(np.arange(301), trajectory, p.threshold_c)
            response.data_quality = "good"
            response.assumption = "constant future load factor/ambient; initial history begins at load equilibrium"
            response.limitation = result["limitations"]
            if "equivalent_aging_h" in result:
                from .physics_ieee import aging_acceleration
                response.equivalent_aging_h = float(np.trapezoid(aging_acceleration(trajectory), dx=1)/3600)
            return response
        except (ValueError, KeyError, TypeError, ImportError) as exc:
            response.limitation = str(exc)
            return response
