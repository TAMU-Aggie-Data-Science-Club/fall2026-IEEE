from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class PredictRequest:
    rail_id: str
    observations: list[dict]
    forecast_horizon_s: int = 300
    current_t_s: float | None = None
    hardware_domain: str = "demo_rc"


@dataclass
class PredictResponse:
    rail_id: str
    observed_hotspot_c: float | None
    predicted_hotspot_plus_60s_c: float | None
    predicted_hotspot_plus_300s_c: float | None
    eta_to_80c_s: float | None
    model_id: str
    model_version: str
    data_quality: str
    prediction_time_utc: str = ""
    assumption: str = "constant current loading, no intervention"
    hardware_domain: str = "demo_rc"
    actuation_eligible: bool = True
    limitation: str = "synthetic RC-domain model; no calibrated confidence interval or physical validation"
    threshold_c: float = 80.
    eta_to_threshold_s: float | None = None
    predicted_top_oil_plus_60s_c: float | None = None
    predicted_top_oil_plus_300s_c: float | None = None
    equivalent_aging_h: float | None = None
    estimated_hotspot_c: float | None = None
    estimated_top_oil_c: float | None = None

    def __post_init__(self):
        self.prediction_time_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self):
        return asdict(self)
