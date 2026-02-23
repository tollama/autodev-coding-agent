from __future__ import annotations
import argparse

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="autodev-cli")
    p.add_argument("--hello", default="world")
    return p

def main(argv: list[str] | None = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    print(f"hello {args.hello}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
