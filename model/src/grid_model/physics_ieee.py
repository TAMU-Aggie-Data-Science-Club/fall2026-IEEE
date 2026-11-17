"""IEEE C57.91-2011 conventional Clause 7 model, not Annex G.

Independent equation implementation; source/limits/reference cases in PHYSICS.md.
Inputs in SI seconds, W, A, degC and per-unit current at rated voltage/frequency.
No transformer parameter or insulation life is inferred from the 12 V rig.
"""
from dataclasses import dataclass, asdict
import math
import numpy as np


@dataclass(frozen=True)
class TransformerParameters:
    rated_current_a: float = 1500.
    rated_power_kva: float = 1000.
    load_loss_w: float = 5000.
    no_load_loss_w: float = 1000.
    rated_top_oil_rise_c: float = 55.
    rated_hotspot_gradient_c: float = 25.
    oil_time_constant_s: float = 10800.
    winding_time_constant_s: float = 300.
    oil_exponent_n: float = .8
    winding_exponent_m: float = .8
    cooling: str = "ONAN"
    iec_k11: float = 1.
    iec_k21: int = 1
    iec_k22: int = 1
    threshold_c: float = 110.
    normal_insulation_life_h: float | None = None
    provenance: str = "illustrative synthetic transformer; NOT a heat-run calibration"

    def __post_init__(self):
        positive = (self.rated_current_a, self.rated_power_kva, self.load_loss_w, self.no_load_loss_w,
                    self.rated_top_oil_rise_c, self.rated_hotspot_gradient_c,
                    self.oil_time_constant_s, self.winding_time_constant_s, self.iec_k11,
                    self.iec_k21, self.iec_k22)
        if any(not math.isfinite(v) or v <= 0 for v in positive): raise ValueError("positive finite transformer ratings/thermal parameters required")
        if not 0 < self.oil_exponent_n <= 1 or not 0 < self.winding_exponent_m <= 1:
            raise ValueError("IEEE exponents must be in (0,1]")
        if self.cooling not in {"ONAN", "ONAF"}: raise ValueError("supported IEC cooling: ONAN/ONAF")
        if type(self.iec_k21) is not int or type(self.iec_k22) is not int: raise ValueError("Alliander k21/k22 require integers")
        if not math.isfinite(self.threshold_c) or not -50 < self.threshold_c < 250: raise ValueError("invalid transformer threshold")
        if self.normal_insulation_life_h is not None and (not math.isfinite(self.normal_insulation_life_h) or self.normal_insulation_life_h <= 0):
            raise ValueError("normal insulation life must be explicitly positive")


def validate_profile(times_s, load_factor, ambient_c):
    times, load, ambient = [np.asarray(x, dtype=float) for x in (times_s, load_factor, ambient_c)]
    if any(x.ndim != 1 for x in (times, load, ambient)) or len(times) < 2 or len({len(times), len(load), len(ambient)}) != 1:
        raise ValueError("equal 1-D time/load/ambient arrays with at least two samples required")
    if not all(np.isfinite(x).all() for x in (times, load, ambient)): raise ValueError("nonfinite transformer input")
    if (np.diff(times) <= 0).any() or times[0] < 0: raise ValueError("strictly increasing seconds required")
    if ((load < 0) | (load > 3)).any(): raise ValueError("load factor outside supported 0..3 pu")
    if ((ambient < -50) | (ambient > 60)).any(): raise ValueError("ambient outside supported -50..60 degC")
    return times, load, ambient


def ultimate_rises(load_factor, parameters):
    p = parameters
    ratio = p.load_loss_w / p.no_load_loss_w
    oil = p.rated_top_oil_rise_c * ((load_factor**2 * ratio + 1) / (ratio + 1)) ** p.oil_exponent_n
    winding = p.rated_hotspot_gradient_c * load_factor ** (2 * p.winding_exponent_m)
    return oil, winding


def effective_oil_tau(initial_rise, ultimate_rise, p):
    """Clause 7 load-dependent tau; continuous limit avoids 0/0 at equilibrium."""
    a, b = ultimate_rise / p.rated_top_oil_rise_c, initial_rise / p.rated_top_oil_rise_c
    if a < 0 or b < 0: raise ValueError("oil rise must be nonnegative")
    if math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-12):
        factor = p.oil_exponent_n * max(a, 1e-12) ** (1 - 1 / p.oil_exponent_n)
    else:
        factor = (a - b) / (a ** (1 / p.oil_exponent_n) - b ** (1 / p.oil_exponent_n))
    return p.oil_time_constant_s * factor


def aging_acceleration(hotspot_c):
    """Thermally upgraded paper, 110 degC reference; IEEE uses +273 and 383."""
    hotspot = np.asarray(hotspot_c, dtype=float)
    if not np.isfinite(hotspot).all() or ((hotspot < -50) | (hotspot > 300)).any():
        raise ValueError("hotspot outside supported aging calculation range")
    return np.exp(15000 / 383 - 15000 / (hotspot + 273))


def run_profile(times_s, load_factor, ambient_c, parameters=None, initial_load_factor=None):
    p = parameters or TransformerParameters()
    times, load, ambient = validate_profile(times_s, load_factor, ambient_c)
    initial = load[0] if initial_load_factor is None else float(initial_load_factor)
    if not math.isfinite(initial) or not 0 <= initial <= 3: raise ValueError("invalid initial load factor")
    oil, winding = ultimate_rises(initial, p)
    top, hot = [ambient[0] + oil], [ambient[0] + oil + winding]
    for i, dt in enumerate(np.diff(times), 1):
        target_oil, target_winding = ultimate_rises(load[i], p)
        tau = effective_oil_tau(oil, target_oil, p)
        oil = target_oil + (oil - target_oil) * math.exp(-dt / tau)
        winding = target_winding + (winding - target_winding) * math.exp(-dt / p.winding_time_constant_s)
        # Ambient is held piecewise constant per step: the conventional rise model,
        # not the Annex G variable-ambient energy balance implementation.
        top.append(ambient[i] + oil); hot.append(ambient[i] + oil + winding)
    acceleration = aging_acceleration(hot)
    equivalent_h = float(np.trapezoid(acceleration, times) / 3600)
    return dict(model="ieee_c57_91", edition="IEEE C57.91-2011 Clause 7; thermally upgraded paper Clause 5",
                times_s=times.tolist(), top_oil_c=top, hotspot_c=hot,
                aging_acceleration=acceleration.tolist(), equivalent_aging_h=equivalent_h,
                equivalent_aging_factor=equivalent_h / ((times[-1] - times[0]) / 3600),
                loss_of_life_percent=None if p.normal_insulation_life_h is None else 100 * equivalent_h / p.normal_insulation_life_h,
                parameters=asdict(p), limitations="conventional lumped model; piecewise constant ambient/load; no Annex G or moisture/oxygen model")
