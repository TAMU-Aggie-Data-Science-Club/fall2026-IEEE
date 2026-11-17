"""Adapter to unmodified MPL-2.0 Alliander transformer-thermal-model 0.5.0."""
from importlib.metadata import version
import numpy as np
import pandas as pd
from .physics_ieee import TransformerParameters, validate_profile


def run_profile(times_s, load_factor, ambient_c, parameters=None, initial_load_factor=None):
    # Imports are optional: the RC demo never requires the physics extra.
    from transformer_thermal_model.model import Model
    from transformer_thermal_model.cooler import CoolerType
    from transformer_thermal_model.schemas import UserTransformerSpecifications, InputProfile
    from transformer_thermal_model.schemas.thermal_model.initial_state import InitialLoad
    from transformer_thermal_model.transformer import PowerTransformer
    if version("transformer-thermal-model") != "0.5.0": raise ValueError("install the inspected physics extra (Alliander 0.5.0)")
    p = parameters or TransformerParameters()
    times, load, ambient = validate_profile(times_s, load_factor, ambient_c)
    initial = load[0] if initial_load_factor is None else float(initial_load_factor)
    if not np.isfinite(initial) or not 0 <= initial <= 3: raise ValueError("invalid initial load factor")
    specs = UserTransformerSpecifications(
        no_load_loss=p.no_load_loss_w, load_loss=p.load_loss_w, nom_load_sec_side=p.rated_current_a,
        time_const_oil=p.oil_time_constant_s / 60, time_const_windings=p.winding_time_constant_s / 60,
        top_oil_temp_rise=p.rated_top_oil_rise_c, winding_oil_gradient=p.rated_hotspot_gradient_c,
        hot_spot_fac=1., oil_exp_x=p.oil_exponent_n, winding_exp_y=2*p.winding_exponent_m,
        oil_const_k11=p.iec_k11, winding_const_k21=p.iec_k21, winding_const_k22=p.iec_k22,
        amb_temp_surcharge=0., end_temp_reduction=0.)
    transformer = PowerTransformer(user_specs=specs, cooling_type=CoolerType[p.cooling])
    index = pd.Timestamp("2026-01-01") + pd.to_timedelta(times, unit="s")
    profile = InputProfile.create(datetime_index=index, load_profile=load*p.rated_current_a,
                                  ambient_temperature_profile=ambient)
    result = Model(temperature_profile=profile, transformer=transformer,
                   initial_condition=InitialLoad(initial_load=initial*p.rated_current_a)).run()
    return dict(model="alliander_iec", edition="IEC 60076-7 via Alliander 0.5.0", times_s=times.tolist(),
                top_oil_c=result.top_oil_temp_profile.to_numpy().tolist(),
                hotspot_c=result.hot_spot_temp_profile.to_numpy().tolist(),
                limitations="specified parameters and initial-load equilibrium; no physical validation; IEC is not IEEE")
