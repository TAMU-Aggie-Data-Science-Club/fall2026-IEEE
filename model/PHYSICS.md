# Transformer physics, domains and verification

The oil-transformer analysis models are **IEEE C57.91-2011 conventional Clause 7**
and the actual **Alliander IEC 60076-7** library. Ridge remains a reproducible
benchmark. A separate RC family describes the low-voltage rig. None is physically
commissioned, IEEE endorsed, or a utility protection relay.

## IEEE implementation and sources

`physics_ieee.py` independently implements the conventional model, rather than
renaming Ridge or distributing proprietary standard text. Equations/terminology
were checked against these primary technical sources:

- [IEEE Transformers Committee comparison, C57.91-2011 versus IEC 60076-7:2018](https://grouper.ieee.org/groups/transformers/subcommittees/insulation_life/c57.91/LoadingGuideComparison-IEEE-IEC-R1.pdf): Clause 5 aging, Clause 7 oil/winding calculation, scope and cooling exponents.
- [IEEE published C57.91-1995 correction sheet](https://standards.ieee.org/wp-content/uploads/import/documents/erratas/C57.91-1995_errata.pdf): corrected 15000 aging coefficient and corrected Annex C prior-load reference. This is a historical equation check, not a claim to implement the 1995 edition.
- [Authors' open IET paper, DOI 10.1049/iet-gtd.2020.0155](https://ietresearch.onlinelibrary.wiley.com/doi/10.1049/iet-gtd.2020.0155): IEEE oil time-constant correction, Eq. 12, and limitations under varying ambient.

This implements the conventional equations used by C57.91-2011, **not Annex G**
or every requirement of the standard. Manufacturer heat-run parameters and an
authorized engineering review of the applicable standard remain necessary for
deployment. The inaccessible NREL report was not used as verification evidence.

Using load factor `K=I/I_rated`, loss ratio `R=P_load,rated/P_no-load`, rated oil
rise `O_r`, rated winding gradient `G_r`, exponents `n,m`:

```text
O_u = O_r * ((1 + R*K²)/(1+R))^n
G_u = G_r * K^(2m)
tau_o = tau_o,r * (a-b)/(a^(1/n)-b^(1/n)), a=O_u/O_r, b=O_initial/O_r
O_next = O_u + (O_initial-O_u)*exp(-dt/tau_o)
G_next = G_u + (G_initial-G_u)*exp(-dt/tau_w)
top_oil = ambient + O_next
hot_spot = top_oil + G_next
FAA = exp(15000/383 - 15000/(hot_spot+273))
equivalent_aging_h = integral(FAA dt_seconds)/3600
```

The equal-rise tau ratio uses its analytic limit to avoid 0/0. FAA is for
thermally upgraded paper at the 110°C reference, using the standard's 273/383
convention. Equivalent aging is numerical trapezoidal integration; choose
sufficient temporal resolution. Percent life consumption is returned only if an
explicit normal insulation life is supplied, never an assumed remaining lifetime.
Moisture, oxygen, maintenance, dielectric/mechanical failure and other life
factors are not modeled.

All public inputs use **seconds, W, A, kVA, °C, and dimensionless per-unit load**.
Temperature rises have K/°C-difference units. Parameters include ratings, losses,
oil/winding rises/time constants, cooling and exponents. Rated voltage/frequency
and fixed cooling are assumed. Inputs are bounded to supported finite values.
Ambient/load are held piecewise constant per integration interval; varying ambient
uses the conventional rise treatment, not an Annex G energy balance.

## Actual Alliander integration

The optional dependency is pinned to `transformer-thermal-model==0.5.0`
([project](https://github.com/alliander-opensource/transformer-thermal-model),
[published release](https://pypi.org/project/transformer-thermal-model/0.5.0/)).
It is MPL-2.0; source is neither copied nor modified. Release 0.5.0 requires
NumPy >=2.2.5,<3, pandas >=2,<3 and Pydantic >=2.11.1,<3. It preserves the
existing pandas 2 dashboard environment instead of requiring a pandas 3 upgrade.

The adapter calls the installed public APIs: `UserTransformerSpecifications`,
`PowerTransformer`, `CoolerType`, `InputProfile.create`,
`schemas.thermal_model.initial_state.InitialLoad`, and `Model(...).run()`.
It reads `top_oil_temp_profile` and `hot_spot_temp_profile` from the returned
`OutputProfile`. See [upstream API documentation](https://alliander-opensource.github.io/transformer-thermal-model/api_reference/model/).
The inspected installed release, not assumptions about current `main`, defines
the supported adapter contract.

Per-unit load is explicitly converted to **secondary-side amperes**. Seconds are
converted to **minutes** for the library time constants. Oil exponent is `x=n`,
winding exponent is `y=2m`; hot-spot factor is explicitly 1 because the supplied
gradient already represents hot spot over top oil. Enclosure surcharge and end
temperature reduction are explicitly zero. IEC `k11/k21/k22` are configurable;
they are not silently mapped onto the IEEE model. Initial-load equilibrium is
explicit, and the complete causal loading history is replayed before forecasting.
Library-specific aging is not relabeled as IEEE aging.

## Reference tests and comparisons

Tests cover Annex C's 187 MVA example parameters (`O_r=36`, `G_r=28.6`,
`R=4.87`, `tau=3.5h`, `n=m=1`), its approximately 18.14°C oil rise at 0.634 pu,
an independently evaluated exponential load step, and FAA(110°C)=1. The matched
two-lag IEC reference uses `n=m=k11=k21=k22=1`, starting at 0.7 pu and stepping
to 1.4 pu at 30°C ambient. Independently calculated hot spots are
73.875°C at 0s, 80.909912565°C at 60s, and 98.951203891°C at 300s.
These are equation/reference cases, not measured transformer validation or a
claim that all IEC cooling modes equal IEEE.

```sh
python -m pip install -e './model[physics,ml,dev]' -e './algorithm[ui,dev]'
python -m grid_model compare-physics --parameters model/configs/transformer.json
python -m grid_model compare-detection --artifact model/artifacts/ridge-demo
python -m grid_model calibrate-rc
python -m grid_model predict --model ieee_c57_91 --input model/configs/transformer-request.json
python -m grid_model predict --model alliander_iec --input model/configs/transformer-request.json
python -m pytest model/tests algorithm/tests -q
```

The physics comparison generates 18 distinct transformer loading scenarios with
10/4/4 train/validation/test splits. IEEE-generated and IEC-generated references
are reported separately. Forecasts hold only current loading, while truth can
include future unknown load changes. Self-model errors are consistency/forcing
errors, never measured accuracy. The original RC-trained Ridge cannot accept
real transformer currents as an in-domain model, so it remains unchanged and a
**separate transformer-domain Ridge surrogate** is trained on only the generated
training scenarios. Its validation split selects regularization; test never fits.

The example request is a declared synthetic loading history, not a sensor capture.
Transformer requests require `hardware_domain:oil_transformer`, explicit
`load_factor`, ambient and monotonic seconds. Calculated current oil/hot-spot state
is returned as `estimated_*`, separately from optional `observed_hotspot_c`;
missing measurements are not invented. Pass `--parameters PATH` to use a reviewed
transformer parameter JSON. Forecasts assume initial-load equilibrium at the
first history sample and hold the latest forcing for the next 300 seconds.

## Threshold metrics and physical suitability

Temperature MAE/RMSE are separate from classification. Detection reports precision,
recall, TP/FP/FN/TN and excludes already-hot observations in a separate future-onset
table. Each candidate supplies its own temperatures/trajectory; prediction hashes
guard against accidentally comparing a shared array. Physics crossing times use
the model trajectory; regression times are explicitly sparse interpolations.
Timing MAE includes only matched crossings and reports missed/unavailable counts.
The dedicated warning cutoff/classifier is chosen on validation only and does
not change Ridge temperatures or physical safety limits. Classifier scores are
not calibrated confidence percentages.

The dashboard selects IEEE, Alliander, calibrated RC or original Ridge and shows
the producing model, limitations, thresholds and temperatures. Oil models are
analysis-only. The coordinator and policy independently gate model/hardware
domain and eligibility; they cannot actuate the demo rails. Actual USB mode is
still monitor-only. RC calibration currently fits **synthetic training data**;
`physical_calibration_verified=false` is preserved. Physical RC calibration,
transformer factory data, hardware pins/polarity/ratings and independent cutoffs
are all outstanding. No physical serial, sensor or relay verification is claimed.
