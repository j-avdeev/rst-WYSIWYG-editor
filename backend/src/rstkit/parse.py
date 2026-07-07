"""Parse rst bytes into a span-partitioned EdDoc.

Fidelity strategy (see plan): the authoritative block partition comes from a
line scanner that assigns every source line to exactly one top-level block
(the partition invariant). Node raw_source is an exact slice of the original
text, so identity serialization is byte-exact by construction. docutils runs
alongside as a parse-health check (and, in later phases, to enrich whitelisted
blocks with real structure); its notoriously unreliable line numbers are never
used for span boundaries.

Phase 0 classification is deliberately coarse: headings, directives (all
opaque), comments, transitions, and generic "text" runs. Misclassification can
shift content between adjacent blocks but can never break byte fidelity.
"""

from __future__ import annotations

import re
from collections import Counter

from .model import EdDoc, EdNode

# reST section adornment characters (docutils spec)
_ADORNMENT_CHARS = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")

_DIRECTIVE_RE = re.compile(r"^(\s*)\.\.[ \t]+([\w.-]+)::")
_SUBST_DEF_RE = re.compile(r"^(\s*)\.\.[ \t]+\|[^|\n]+\|[ \t]+([\w.-]+)::")
_EXPLICIT_MARKUP_RE = re.compile(r"^\s*\.\.(\s|$)")


class SourceText:
    """Decoded file content plus the metadata needed to re-encode it exactly."""

    def __init__(self, data: bytes):
        self.bom = data.startswith(b"\xef\xbb\xbf")
        raw = data[3:] if self.bom else data
        self.encoding = "utf-8"
        self.warnings: list[str] = []
        try:
            self.text = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                self.text = raw.decode("cp1251")
                self.encoding = "cp1251"
                self.warnings.append("file is not UTF-8; decoded as cp1251")
            except UnicodeDecodeError:
                self.text = raw.decode("latin-1")
                self.encoding = "latin-1"
                self.warnings.append("file is not UTF-8/cp1251; decoded as latin-1")
        # keepends=True: joining lines reproduces the text byte-for-byte
        self.lines: list[str] = self.text.splitlines(keepends=True)
        crlf = self.text.count("\r\n")
        lf = self.text.count("\n") - crlf
        if crlf and lf:
            self.eol = "mixed"
        elif crlf:
            self.eol = "crlf"
        elif lf:
            self.eol = "lf"
        else:
            self.eol = "none"


def _strip_eol(line: str) -> str:
    return line.rstrip("\r\n")


def _is_blank(line: str) -> bool:
    return not _strip_eol(line).strip()


def _indent(line: str) -> int:
    s = _strip_eol(line).expandtabs(8)
    return len(s) - len(s.lstrip(" "))


def _is_adornment(line: str) -> bool:
    s = _strip_eol(line).rstrip()
    return len(s) >= 2 and s[0] in _ADORNMENT_CHARS and s == s[0] * len(s)


def scan_blocks(lines: list[str]) -> list[EdNode]:
    """Partition lines into top-level blocks. Every line belongs to exactly
    one block; blank runs attach to the preceding block (or the first block
    if the file starts with blanks)."""
    n = len(lines)
    nodes: list[EdNode] = []
    i = 0

    def emit(type_: str, start: int, end: int, **attrs) -> int:
        # absorb trailing blank lines into this block
        while end < n and _is_blank(lines[end]):
            end += 1
        nodes.append(
            EdNode(
                type=type_,
                span=(start, end),
                raw_source="".join(lines[start:end]),
                attrs=attrs,
            )
        )
        return end

    # leading blank lines attach to the first real block
    while i < n and _is_blank(lines[i]):
        i += 1
    leading_end = i
    if leading_end and leading_end >= n:
        # file is all blank
        return [EdNode(type="text", span=(0, n), raw_source="".join(lines))]

    while i < n:
        start = 0 if (not nodes and leading_end) else i
        line = lines[i]
        stripped = _strip_eol(line)

        # --- explicit markup: directive / substitution def / comment -------
        if _EXPLICIT_MARKUP_RE.match(stripped) and _indent(line) == 0:
            base_indent = 0
            j = i + 1
            while j < n and (_is_blank(lines[j]) or _indent(lines[j]) > base_indent):
                j += 1
            m = _SUBST_DEF_RE.match(stripped) or _DIRECTIVE_RE.match(stripped)
            if m:
                i = emit("directive", start, j, name=m.group(2))
            else:
                i = emit("comment", start, j)
            continue

        # --- overline heading ----------------------------------------------
        if (
            _is_adornment(line)
            and i + 2 < n
            and not _is_blank(lines[i + 1])
            and not _is_adornment(lines[i + 1])
            and _is_adornment(lines[i + 2])
            and _strip_eol(lines[i + 2]).strip()[0] == _strip_eol(line).strip()[0]
        ):
            i = emit(
                "heading", start, i + 3,
                underline=_strip_eol(line).strip()[0], overline=True,
            )
            continue

        # --- transition ------------------------------------------------------
        if _is_adornment(line) and len(_strip_eol(line).strip()) >= 4 and (
            i + 1 >= n or _is_blank(lines[i + 1])
        ):
            i = emit("transition", start, i + 1)
            continue

        # --- underline heading ----------------------------------------------
        if (
            not _is_adornment(line)
            and _indent(line) == 0
            and i + 1 < n
            and _is_adornment(lines[i + 1])
        ):
            i = emit(
                "heading", start, i + 2,
                underline=_strip_eol(lines[i + 1]).strip()[0], overline=False,
            )
            continue

        # --- generic text run -------------------------------------------------
        # Consume the non-blank run, then keep consuming any indented
        # continuation (literal blocks after ::, block quotes, nested content)
        # separated by blanks. Heading underlines directly below a single line
        # were already dispatched above, so no heading can start inside a run.
        j = i
        while True:
            while j < n and not _is_blank(lines[j]):
                j += 1
            if j >= n:
                break
            k = j
            while k < n and _is_blank(lines[k]):
                k += 1
            if k < n and _indent(lines[k]) > 0:
                j = k  # indented continuation belongs to this block
                continue
            break
        if j == i:  # safety: never loop without progress
            j = i + 1
        i = emit("text", start, j)

    return nodes


def verify_partition(nodes: list[EdNode], line_count: int) -> None:
    """Raise if spans do not exactly partition [0, line_count)."""
    pos = 0
    for node in nodes:
        if node.span[0] != pos:
            raise AssertionError(
                f"span gap/overlap at line {pos}: next span {node.span}"
            )
        if node.span[1] <= node.span[0]:
            raise AssertionError(f"empty span {node.span}")
        pos = node.span[1]
    if pos != line_count:
        raise AssertionError(f"spans end at {pos}, file has {line_count} lines")


def docutils_error_count(text: str, path: str = "<string>") -> int:
    """Parse with docutils (all directives stubbed, reporting silenced) and
    return the number of ERROR/SEVERE system messages. Parse-health only —
    never used for spans."""
    from docutils import frontend, utils
    from docutils.parsers import rst

    _register_stub_directives(text)
    _register_stub_roles(text)

    settings = frontend.get_default_settings(rst.Parser)
    settings.report_level = 5
    settings.halt_level = 5
    settings.file_insertion_enabled = False
    settings.raw_enabled = False
    document = utils.new_document(path, settings)
    errors = 0

    def observer(msg) -> None:
        nonlocal errors
        if msg["level"] >= 3:  # ERROR or SEVERE
            errors += 1

    document.reporter.attach_observer(observer)
    rst.Parser().parse(text, document)
    return errors


class _DummyOptionSpec(dict):
    """Accepts any directive option unvalidated (pattern from sphinx autodoc)."""

    def __bool__(self) -> bool:
        return True

    def __contains__(self, key) -> bool:
        return True

    def __getitem__(self, key):
        return lambda value: value


_stubbed: set[str] = set()


def _register_stub_directives(text: str) -> None:
    """Register a pass-through stub for every directive name in the source,
    shadowing built-ins too. Phase 0 treats all directives as opaque; real
    parsing is reintroduced per whitelist type in later phases."""
    from docutils import nodes
    from docutils.parsers import rst
    from docutils.parsers.rst import directives

    names = set(re.findall(r"^\s*\.\.[ \t]+([\w.-]+)::", text, re.M))
    names |= set(re.findall(r"^\s*\.\.[ \t]+\|[^|\n]+\|[ \t]+([\w.-]+)::", text, re.M))
    for name in names:
        key = name.lower()
        if key in _stubbed:
            continue

        class StubDirective(rst.Directive):
            required_arguments = 0
            optional_arguments = 100
            final_argument_whitespace = True
            has_content = True
            option_spec = _DummyOptionSpec()

            def run(self):  # noqa: D102
                node = nodes.comment(self.block_text, self.block_text)
                node["rstkit_directive"] = self.name
                return [node]

        directives.register_directive(key, StubDirective)
        _stubbed.add(key)


_stubbed_roles: set[str] = set()


def _register_stub_roles(text: str) -> None:
    """Register a pass-through stub for every interpreted-text role used in
    the source that docutils doesn't know (Sphinx roles like :doc:, :ref:)."""
    from docutils import nodes
    from docutils.parsers.rst import languages, roles

    names = set(re.findall(r"(?<![\w`.:]):([\w.+-]+):`", text))
    lang = languages.get_language("en")
    for name in names:
        key = name.lower()
        if key in _stubbed_roles:
            continue
        role_fn, _ = roles.role(key, lang, 1, _SilentReporter())
        if role_fn is not None:
            _stubbed_roles.add(key)
            continue

        def stub_role(role, rawtext, text_, lineno, inliner, options=None, content=None):
            return [nodes.literal(rawtext, text_)], []

        roles.register_local_role(key, stub_role)
        _stubbed_roles.add(key)


class _SilentReporter:
    """Minimal reporter duck-type for roles.role() lookup."""

    def error(self, *args, **kwargs):
        return None


def directive_inventory(text: str) -> Counter:
    """Corpus statistics: directive name -> count (regex-based, parser-free)."""
    inv = Counter(re.findall(r"^\s*\.\.[ \t]+([\w.-]+)::", text, re.M))
    for name in re.findall(r"^\s*\.\.[ \t]+\|[^|\n]+\|[ \t]+([\w.-]+)::", text, re.M):
        inv[f"|subst| {name}"] += 1
    return inv


def parse_rst(data: bytes, path: str = "<string>", check_health: bool = True) -> EdDoc:
    src = SourceText(data)
    nodes = scan_blocks(src.lines)
    verify_partition(nodes, len(src.lines))
    errors = 0
    if check_health and src.text.strip():
        try:
            errors = docutils_error_count(src.text, path)
        except Exception as exc:  # docutils crash must never block opening a file
            src.warnings.append(f"docutils parse failed: {exc!r}")
    return EdDoc(
        path=path,
        encoding=src.encoding,
        bom=src.bom,
        eol=src.eol,
        nodes=nodes,
        warnings=src.warnings,
        parse_errors=errors,
    )
