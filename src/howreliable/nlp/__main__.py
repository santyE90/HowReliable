"""Local CLI for deterministic offline report extraction."""

import argparse
from datetime import date, datetime
from pathlib import Path

from howreliable.nlp import ProcessingConfig, process_owner_reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract reported components, symptoms and local relations offline"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--mode", choices=("full_corpus", "as_of"), default="full_corpus")
    parser.add_argument("--cutoff", type=date.fromisoformat)
    parser.add_argument("--generation-utc", type=datetime.fromisoformat, required=True)
    args = parser.parse_args(argv)
    config = ProcessingConfig(mode=args.mode, cutoff=args.cutoff)
    result = process_owner_reports(
        args.input,
        args.output,
        provenance_path=args.provenance,
        config=config,
        clock=lambda: args.generation_utc,
    )
    print(
        f"completed {result.output_record_count} rows; deterministic report extraction; "
        f"SHA-256={result.output_sha256}; membership={result.membership_filename}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
