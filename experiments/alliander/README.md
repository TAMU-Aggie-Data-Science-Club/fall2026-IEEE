# Prince's first model test: Alliander

This experiment runs the real `transformer-thermal-model==0.6.0` Python package on the team's synthetic ESP32 CSVs. It predicts the hot-spot temperature **60 seconds and 300 seconds ahead** and compares it with persistence: predict that the temperature stays at its current measured value.

The purpose is to establish a repeatable first comparison. This is an empirical adaptation to a 12 V demo, not validation of an actual transformer or of IEC 60076-7 accuracy.

## Recorded result

Held-out scenarios S031-S036, with a forecast issued every 30 seconds:

| Forecast horizon | Scored predictions | Alliander MAE | Persistence MAE | Alliander RMSE | Persistence RMSE |
|---|---|---|---|---|---|
| 60 seconds | 1,037 | 0.919 C | 1.007 C | 1.400 C | 1.697 C |
| 300 seconds | 893 | 4.815 C | 4.395 C | 6.716 C | 7.344 C |

Alliander reduced average absolute error by **8.7% at 60 seconds**, but increased it by **9.6% at 300 seconds**. Its lower RMSE at both horizons indicates fewer/lower large squared errors, despite the worse five-minute average absolute error. It is not a clear overall winner for this demo. In the five-minute normal-load test, average absolute error was 3.11 C versus persistence's 1.95 C, so the mismatch affects ordinary operation as well as overload transitions.

The selected values were **10 minutes oil time constant and 20 C nominal oil rise for each rail**. Ten minutes is the upper boundary of the predefined search, so this is a limited parameter comparison rather than an optimized fit. The test set was not used to extend the search after seeing its results.

Median runtime was **0.129 ms per rail for both horizons**, with a 95th percentile of **0.147 ms**, across 6,234 timed forecast calls. This measures warm laptop Python execution, including profile construction but excluding CSV loading, plotting, transformer construction, and hardware I/O. Calibration plus CSV loading took 3.22 seconds. No ESP32 inference or memory benchmark was performed.

The input audit counted 194,400 rows and 814 invalid sensor rows. Training used 2,169 sampled forecast origins; validation used 864. All six automated checks passed, including agreement between sparse and one-second simulations, split leakage rejection, missing-label filtering, and identical baseline scoring rows.

The CSV's future targets represent noise-free simulated temperatures. These errors therefore measure agreement with the synthetic generator, not accuracy against future physical sensor measurements. Per-episode metrics and the complete run record are saved locally; subsequent runs may have different timings.

## Run it

From the repository root, use Python 3.12 or newer (this run used Python 3.14.7):

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r experiments/alliander/requirements.txt
mkdir -p data/raw/entropy_mock
```

Copy the user-supplied `model_training_timeseries.csv`, `model_training_scenarios.csv`, and `rail_config.csv` into `data/raw/entropy_mock/`. These files are local inputs; they are deliberately absent from Git. See [the source register](../../DATA.md) for provenance and redistribution status.

```sh
python -m unittest discover -s experiments/alliander -p 'test_*.py' -v
python experiments/alliander/evaluate.py
```

To use a different local input directory:

```sh
python experiments/alliander/evaluate.py --data-dir '/absolute/path/to/Mock Data'
```

The script overwrites its generated reports under ignored `data/processed/alliander/`; use `--output-dir` to keep a separate run. Raw inputs are never modified.

## What the script does

1. **Check the CSVs.** Validate unique `(scenario_id, rail_id, elapsed_s)` keys, split agreement between files, finite sensor values, and sensor validity flags. Group episodes by scenario and rail and sort by elapsed time. No interpolation, forward filling, or future sensor data enter this test.
2. **Preserve the supplied scenario split.** There are 25 training, 5 validation, and 6 test scenarios. All three rails in a scenario stay together. Random row splitting would put closely related observations into both training and testing.
3. **Map sensor inputs into Alliander.** `rail_current_a` becomes load current, `ambient_temp_c` becomes ambient temperature, and `rail_hotspot_temp_c` initializes the temperature state. Forecast load and ambient remain fixed at their current readings. Voltage and power are not extra model inputs: this library uses current and transformer loss specifications. The measured hot spot is used as a proxy for initial top-oil temperature because this demo has no oil sensor.
4. **Fit demo parameters on training data.** For each rail, try oil time constants of 2, 5, and 10 minutes. For each time constant, pick the nominal top-oil rise from 10, 20, and 30 C with the lowest training mean squared error across the two available horizons. Sample a training origin every 60 seconds. Use validation mean absolute error to select the time constant and its training-fitted rise. Do not refit using validation or test targets.
5. **Freeze the parameters and evaluate.** Forecast every 30 seconds on each valid scenario/rail sequence. Exclude blank labels independently for each horizon, so the last available 60-second targets are still usable after 300-second targets end. Score the Alliander and persistence forecasts on exactly the same rows.
6. **Save accuracy and computation cost.** MAE is the average absolute error in degrees C; smaller is better. RMSE penalizes large misses more. Bias shows systematic overprediction or underprediction. Record per-episode results as well as overall results so one easy rail cannot hide a difficult one. Time actual two-horizon Python calls, including input-profile construction.

For example, a 300-second forecast issued at elapsed second 600 uses the observed current, ambient, and hot spot at second 600. It is compared with `target_hotspot_temp_plus_300s_c` from that row. Observations from seconds 601 through 900 are not inputs.

The sparse model profile uses offsets 0, 60, and 300 seconds. With constant inputs and this fixed cooling configuration, the library's exponential updates give the same horizon values as a one-second simulation; a regression test verifies that equivalence.

## Assumptions that affect interpretation

The synthetic CSVs were generated using a simple first-order RC emulator, rather than IEEE or IEC transformer equations. An oil-immersed transformer model is therefore a structural mismatch, and this experiment must not be described as proving transformer accuracy.

Missing transformer specifications are filled with **illustrative assumptions**, not discovered physical ratings: 1 A nominal current, 12 W nominal load loss, 0.1 W no-load loss, zero ambient surcharge, 5 C winding/oil gradient, 1 minute winding time constant, and hot-spot factor 1. All other fixed coefficients come from Alliander's `DistributionTransformer` defaults. `results.json` records the complete effective specifications for each rail, including its selected oil time constant and rise. These quantities require real hardware measurements before physical interpretation.

Every forecast restarts with the current hot spot as the model's oil temperature and zero initial winding/oil excess. This is a proxy adapter, not an observed oil/winding state. Unknown future load transitions will also cause errors even if the current thermal state is known. The replay CSV has load-shedding interventions and is intentionally not mixed into this unmitigated forecast benchmark.

Forecast windows overlap, so prediction counts are not independent trials. The six held-out scenarios, rather than thousands of neighboring rows, are the relevant unit of generalization. No confidence interval or deployment acceptance limit is claimed.

## Outputs

All generated files stay under `data/processed/alliander/`:

| File | Contents |
|---|---|
| `results.json` | Parameters, calibration trials, source SHA-256 hashes, package versions, data audit, metrics, and runtime |
| `metrics.csv` | MAE, RMSE, signed bias, 95th percentile absolute error, and counts by split/horizon/model |
| `per_episode_metrics.csv` | The same metrics by scenario, rail, and horizon |
| `predictions.csv` | Truth and both predictions, keyed by issue time and horizon |
| `forecast_errors.png` | Held-out forecast errors versus true future temperature |

No PID tuning, threshold-crossing classifier, hardware command, real ESP32 runtime, or ESP32 memory measurement is part of this experiment. The Python package runs on the laptop in the proposed architecture. Laptop latency does not demonstrate that Python/pandas will run on an ESP32.

## Sources

- Team model shortlist: user-supplied **Entropy Meeting 2.pdf**, Prince Kumar's “Model Research” slide.
- Data format and synthetic-data caveats: user-supplied **Data Contract README.pdf** and its CSVs.
- [Alliander source and MPL-2.0 license](https://github.com/alliander-opensource/transformer-thermal-model).
- [Model description](https://alliander-opensource.github.io/transformer-thermal-model/theoretical_documentation/model_description/).
- [Initial-state behavior](https://alliander-opensource.github.io/transformer-thermal-model/examples/initial_temperature/).

The package is used as a dependency; its source is not copied into this repository.
