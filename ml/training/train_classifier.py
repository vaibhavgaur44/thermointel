"""Training entry point. Requires a validated, human-labeled CSV; never reports fabricated metrics."""
import argparse, json, pathlib

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--dataset",required=True); parser.add_argument("--output",default="models/classifier.json"); args=parser.parse_args()
    path=pathlib.Path(args.dataset)
    if not path.exists(): raise SystemExit(f"Dataset not found: {path}")
    raise SystemExit("Training scaffold ready: provide validated labels and implement a time-based split before fitting a production model.")

if __name__ == "__main__": main()