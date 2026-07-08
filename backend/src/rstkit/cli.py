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
        text = data.decode(doc.encoding, "replace").removeprefix(chr(0xFEFF))
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


def cmd_strict(args: argparse.Namespace) -> int:
    """Serializer quality metric: for every block the editor would let the
    user edit richly (i.e. enrichable text blocks and headings), simulate a
    dirty save — view -> PM (pmbridge) -> serialize -> verify-reparse — and
    report the pass rate. This is the Phase 2 gate: editable blocks must
    survive a forced re-serialization at >=95% (target 100%)."""
    from .inline import enrich_nodes
    from .pmbridge import UnsupportedView, pm_from_heading, pm_from_view
    from .pmserialize import SerializeError
    from .verify import VerifyError, serialize_and_verify_block

    root = Path(args.root)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    t0 = time.monotonic()
    ok: Counter = Counter()
    failed: Counter = Counter()
    skipped: Counter = Counter()
    failures: list[tuple[str, str, str]] = []
    total_files = 0

    for path in _iter_rst_files(root):
        if args.limit and total_files >= args.limit:
            break
        total_files += 1
        rel = str(path.relative_to(root))
        try:
            doc = parse_rst(path.read_bytes(), rel, check_health=False)
            enrich_nodes(doc.nodes)
        except Exception as exc:
            failures.append((rel, "<file>", f"{type(exc).__name__}: {exc}"))
            continue
        for node in doc.nodes:
            if node.type == "heading":
                pm = pm_from_heading(node)
                kind = "heading"
            elif node.type == "text" and node.view is not None:
                try:
                    pm = pm_from_view(node.view)
                except UnsupportedView:
                    skipped["text/" + node.view.get("type", "?")] += 1
                    continue
                kind = node.view.get("type", "?")
            elif node.type == "directive" and node.view is not None:
                try:
                    pm = pm_from_view(node.view)
                except UnsupportedView:
                    skipped["directive/" + node.view.get("type", "?")] += 1
                    continue
                kind = node.view.get("type", "?")
            else:
                skipped[node.type] += 1
                continue
            try:
                serialize_and_verify_block(pm)
                ok[kind] += 1
            except (SerializeError, VerifyError) as exc:
                failed[kind] += 1
                if len(failures) < args.max_failures:
                    snippet = node.raw_source[:120].replace("\n", "\\n")
                    failures.append((rel, kind, f"{exc} | {snippet}"))

    elapsed = time.monotonic() - t0
    total_ok = sum(ok.values())
    total_failed = sum(failed.values())
    total = total_ok + total_failed
    rate = (100.0 * total_ok / total) if total else 100.0

    print(f"rstkit strict — {root}")
    print(f"  files:            {total_files}")
    print(f"  editable blocks:  {total}")
    print(f"  verified ok:      {total_ok} ({rate:.2f}%)")
    print(f"  failed:           {total_failed}")
    print(f"  skipped (opaque): {sum(skipped.values())}")
    print(f"  elapsed:          {elapsed:.1f}s")
    print("  per kind (ok/failed):")
    for kind in sorted(set(ok) | set(failed)):
        print(f"    {kind:24s} {ok[kind]}/{failed[kind]}")
    if skipped:
        print(f"  skipped detail: {dict(skipped.most_common())}")
    for rel, kind, msg in failures[: args.max_failures]:
        print(f"  FAIL [{kind}] {rel}: {msg}")

    threshold_ok = rate >= args.threshold
    print("PASS" if threshold_ok else "FAIL")
    return 0 if threshold_ok else 1


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252/cp866 which cannot print the
    # Cyrillic corpus content that appears in failure diagnostics.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="rstkit")
    sub = parser.add_subparsers(dest="command", required=True)

    rt = sub.add_parser("roundtrip", help="parse+serialize every .rst file and byte-compare")
    rt.add_argument("root", help="docs root directory")
    rt.add_argument("--json", help="write JSON report to this path")
    rt.add_argument("--fail-on-diff", action="store_true", help="exit 1 on any diff/error")
    rt.add_argument("--no-health", action="store_true", help="skip docutils parse-health check (faster)")
    rt.add_argument("--limit", type=int, default=0, help="process at most N files")
    rt.set_defaults(func=cmd_roundtrip)

    st = sub.add_parser("strict", help="force-reserialize every editable block and verify")
    st.add_argument("root", help="docs root directory")
    st.add_argument("--limit", type=int, default=0, help="process at most N files")
    st.add_argument("--threshold", type=float, default=95.0, help="min pass %% for exit 0")
    st.add_argument("--max-failures", type=int, default=25, help="failure examples to print")
    st.set_defaults(func=cmd_strict)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
