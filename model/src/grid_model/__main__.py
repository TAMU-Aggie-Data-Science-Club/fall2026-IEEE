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
    args = parser.parse_args()
    try:
        if args.command == "inspect": result = inspect(args.data, args.scenarios)
        elif args.command == "train":
            output = args.output or f"model/artifacts/{args.model}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
            with open(args.config, encoding="utf-8") as stream: config = json.load(stream)
            result = train(args.model, args.data, output, args.seed, args.quick, args.epochs, config)
        elif args.command == "evaluate": result = evaluate(args.artifact, args.split, args.data)
        else:
            with open(args.input) as stream: request = PredictRequest(**json.load(stream))
            result = Predictor(args.artifact).predict(request).to_dict()
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, ImportError) as exc: parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__": main()
