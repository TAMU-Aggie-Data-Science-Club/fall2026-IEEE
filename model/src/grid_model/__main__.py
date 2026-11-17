import argparse
import json
from datetime import datetime, timezone
from .data import DEFAULT_DATA, inspect
from .training import train, evaluate
from .contracts import PredictRequest
from .inference import Predictor


def main():
    parser = argparse.ArgumentParser(description="Synthetic-only thermal model tools")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("inspect"); p.add_argument("--data", default=DEFAULT_DATA); p.add_argument("--scenarios")
    p = sub.add_parser("train")
    p.add_argument("--model", choices=["persistence", "ridge", "rc", "lstm", "transformer"], default="ridge")
    p.add_argument("--data", default=DEFAULT_DATA); p.add_argument("--output")
    p.add_argument("--seed", type=int, default=42); p.add_argument("--quick", action="store_true"); p.add_argument("--epochs", type=int)
    p.add_argument("--config", default="model/configs/default.yaml", help="JSON-compatible YAML window settings")
    p = sub.add_parser("evaluate"); p.add_argument("--artifact", required=True); p.add_argument("--data"); p.add_argument("--split", choices=["train", "val", "test"], default="test")
    p = sub.add_parser("predict"); p.add_argument("--artifact"); p.add_argument("--input", required=True, help="JSON PredictRequest file")
    p.add_argument("--model", choices=["ieee_c57_91", "alliander_iec", "calibrated_rc", "ridge", "rc"], default="rc")
    p.add_argument("--parameters", default="model/configs/transformer.json"); p.add_argument("--calibration")
    p = sub.add_parser("compare-physics"); p.add_argument("--parameters", default="model/configs/transformer.json"); p.add_argument("--output", default="model/reports/physics-comparison")
    p = sub.add_parser("compare-detection"); p.add_argument("--data", default=DEFAULT_DATA); p.add_argument("--artifact", default="model/artifacts/ridge-demo"); p.add_argument("--output", default="model/reports/detection-comparison")
    p = sub.add_parser("calibrate-rc"); p.add_argument("--data", default=DEFAULT_DATA); p.add_argument("--output", default="model/artifacts/rc-calibration/calibration.json")
    args = parser.parse_args()
    try:
        if args.command == "inspect": result = inspect(args.data, args.scenarios)
        elif args.command == "train":
            output = args.output or f"model/artifacts/{args.model}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
            with open(args.config, encoding="utf-8") as stream: config = json.load(stream)
            result = train(args.model, args.data, output, args.seed, args.quick, args.epochs, config)
        elif args.command == "evaluate": result = evaluate(args.artifact, args.split, args.data)
        elif args.command == "compare-physics":
            from .physics_comparison import comparison
            from .physics_ieee import TransformerParameters
            with open(args.parameters) as stream: parameters = TransformerParameters(**json.load(stream))
            result = comparison(args.output, parameters)
        elif args.command == "compare-detection":
            from .detection import compare
            result = compare(args.data, args.artifact, args.output)
        elif args.command == "calibrate-rc":
            from .calibration import calibrate
            result = calibrate(args.data, args.output)
        else:
            with open(args.input) as stream: request = PredictRequest(**json.load(stream))
            from .selection import select_model
            predictor = Predictor(args.artifact) if args.artifact and args.model == "rc" else select_model(args.model,args.artifact,args.parameters,args.calibration)
            result = predictor.predict(request).to_dict()
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, ImportError) as exc: parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__": main()
