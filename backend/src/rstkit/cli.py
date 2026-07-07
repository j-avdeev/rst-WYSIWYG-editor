"""Corpus round-trip harness: the project's permanent quality gate.

    rstkit roundtrip <docs-root> [--json report.json] [--fail-on-diff]
                     [--no-health] [--limit N]

Identity mode: for every .rst file, parse -> serialize -> byte-compare.
Pass criterion: 100% byte-identical, zero normalizations.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from .parse import directive_inventory, parse_rst
from .serialize import serialize

_EXCLUDED_DIRS = {"build", "_build", ".git", "node_modules", "__pycache__"}


def _iter_rst_files(root: Path):
    for path in sorted(root.rglob("*.rst")):
        if any(part.lower() in _EXCLUDED_DIRS for part in path.parts):
            continue
        yield path


def cmd_roundtrip(args: argparse.Namespace) -> int:
    root = Path(args.root)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    t0 = time.monotonic()
    identical = 0
    diffs: list[str] = []
    errors: list[tuple[str, str]] = []
    warnings: list[tuple[str, str]] = []
    parse_error_files: list[tuple[str, int]] = []
    inventory: Counter = Counter()
    block_types: Counter = Counter()
    eols: Counter = Counter()
    encodings: Counter = Counter()
    total = 0

    for path in _iter_rst_files(root):
        if args.limit and total >= args.limit:
            break
        total += 1
        rel = str(path.relative_to(root))
        try:
            data = path.read_bytes()
            doc = parse_rst(data, rel, check_health=not args.no_health)
            out = serialize(doc)
        except Exception as exc:
            errors.append((rel, f"{type(exc).__name__}: {exc}"))
            continue
        if out == data:
            identical += 1
        else:
            diffs.append(rel)
        text = data.decode(doc.encoding, "replace").lstrip("\\ufeff")
        inventory.update(directive_inventory(text))
        for node in doc.nodes:
            block_types[node.type] += 1
        eols[doc.eol] += 1
        encodings[doc.encoding] += 1
        for w in doc.warnings:
            warnings.append((rel, w))
        if doc.parse_errors:
            parse_error_files.append((rel, doc.parse_errors))

    elapsed = time.monotonic() - t0
    ok = not diffs and not errors

    print(f"rstkit roundtrip — {root}")
    print(f"  files:          {total}")
    print(f"  byte-identical: {identical}")
    print(f"  diffs:          {len(diffs)}")
    print(f"  errors:         {len(errors)}")
    print(f"  encodings:      {dict(encodings)}")
    print(f"  eol styles:     {dict(eols)}")
    print(f"  block types:    {dict(block_types.most_common())}")
    print(f"  docutils files w/ errors: {len(parse_error_files)}")
    print(f"  elapsed:        {elapsed:.1f}s")
    print("  top directives:")
    for name, count in inventory.most_common(15):
        print(f"    {name:24s} {count}")
    for rel in diffs[:20]:
        print(f"  DIFF  {rel}")
    for rel, msg in errors[:20]:
        print(f"  ERROR {rel}: {msg}")
    if warnings:
        print(f"  warnings: {len(warnings)} (first 10)")
        for rel, w in warnings[:10]:
            print(f"    {rel}: {w}")

    if args.json:
        report = {
            "root": str(root),
            "files": total,
            "byte_identical": identical,
            "diffs": diffs,
            "errors": [{"file": f, "message": m} for f, m in errors],
            "warnings": [{"file": f, "message": m} for f, m in warnings],
            "docutils_error_files": [
                {"file": f, "errors": c} for f, c in parse_error_files
            ],
            "directive_inventory": dict(inventory.most_common()),
            "block_types": dict(block_types.most_common()),
            "eol": dict(eols),
            "encodings": dict(encodings),
            "elapsed_sec": round(elapsed, 1),
        }
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  report written to {args.json}")

    print("PASS" if ok else "FAIL")
    return 0 if (ok or not args.fail_on_diff) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rstkit")
    sub = parser.add_subparsers(dest="command", required=True)

    rt = sub.add_parser("roundtrip", help="parse+serialize every .rst file and byte-compare")
    rt.add_argument("root", help="docs root directory")
    rt.add_argument("--json", help="write JSON report to this path")
    rt.add_argument("--fail-on-diff", action="store_true", help="exit 1 on any diff/error")
    rt.add_argument("--no-health", action="store_true", help="skip docutils parse-health check (faster)")
    rt.add_argument("--limit", type=int, default=0, help="process at most N files")
    rt.set_defaults(func=cmd_roundtrip)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
