from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class PredictRequest:
    rail_id: str
    observations: list[dict]
    forecast_horizon_s: int = 300
    current_t_s: float | None = None


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

    def __post_init__(self):
        self.prediction_time_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self):
        return asdict(self)
