from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Any, List


@dataclass(frozen=True)
class ExitCode:
    OK = 0
    BAD_ARGS = 2
    ERROR = 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="autodev-cli",
        description="Generated CLI with explicit contract and safer defaults.",
        exit_on_error=False,
    )
    p.add_argument("--hello", default="world", help="Greeting name to print")
    p.add_argument("--repeat", type=int, default=1, help="How many times to print the greeting (1-3)")
    p.add_argument("--json", action="store_true", help="Emit JSON response instead of plain text")
    return p


def _error(message: str) -> None:
    print(message, file=sys.stderr)


def _validate_repeat(repeat: int) -> None:
    if repeat < 1 or repeat > 3:
        raise ValueError("--repeat must be between 1 and 3")


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()

    try:
        args = parser.parse_args(argv)
    except argparse.ArgumentError as exc:
        _error(str(exc))
        return ExitCode.BAD_ARGS
    except SystemExit:
        return ExitCode.BAD_ARGS

    try:
        _validate_repeat(args.repeat)
    except ValueError as exc:
        _error(str(exc))
        return ExitCode.BAD_ARGS

    if args.json:
        payload = {
            "hello": args.hello,
            "repeat": args.repeat,
            "outputs": [f"hello {args.hello}" for _ in range(args.repeat)],
        }
        print(payload)
        return ExitCode.OK

    for _ in range(args.repeat):
        print(f"hello {args.hello}")
    return ExitCode.OK


if __name__ == "__main__":
    raise SystemExit(main())
