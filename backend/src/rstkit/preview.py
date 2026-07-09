"""Server-side HTML preview of an rst document via docutils html5 writer.

parse.py stubs every directive/role name it encounters (globally) so that
parse-health and enrichment stay quiet and uniform. For preview we want the
opposite where possible: csv-table, figure, math, include etc. should render
for real. `_native_registries()` temporarily removes our stubs for names
docutils implements natively, then restores the stubbed state.

Sphinx-only constructs remain stubbed and render as nothing (toctree, todo)
or literal text (:doc:, :ref:) — acceptable for a live editing preview; the
"Full Sphinx build" toolbar action is the ground truth (later phase).
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote


@contextmanager
def _native_registries():
    from docutils.parsers.rst import directives, roles
    from docutils.parsers.rst import languages

    from .parse import _stubbed, _stubbed_roles

    lang = languages.get_language("en")
    saved_directives = dict(directives._directives)
    saved_roles = dict(roles._roles)
    try:
        for name in list(directives._directives):
            if name in _stubbed and _is_native_directive(name, lang):
                del directives._directives[name]
        for name in list(roles._roles):
            if name in _stubbed_roles and _is_native_role(name, lang):
                del roles._roles[name]
        yield
    finally:
        directives._directives.clear()
        directives._directives.update(saved_directives)
        roles._roles.clear()
        roles._roles.update(saved_roles)


def _is_native_directive(name: str, lang) -> bool:
    from docutils.parsers.rst import directives

    canonical = lang.directives.get(name, name)
    return canonical in directives._directive_registry


def _is_native_role(name: str, lang) -> bool:
    from docutils.parsers.rst import roles

    canonical = lang.roles.get(name, name)
    return canonical in roles._role_registry


_IMG_SRC = re.compile(r'(<img[^>]+src=")([^"]+)(")')


def _rewrite_asset_urls(html: str, doc_path: str) -> str:
    def repl(m: re.Match) -> str:
        uri = m.group(2)
        if uri.startswith(("http://", "https://", "data:", "/api/")):
            return m.group(0)
        return f'{m.group(1)}/api/asset?doc={quote(doc_path)}&uri={quote(uri)}{m.group(3)}'

    return _IMG_SRC.sub(repl, html)


_preview_srcdir: Path | None = None
_preview_docdir: Path | None = None


def _register_preview_toctree() -> None:
    """A toctree that RENDERS in the preview: a nav box listing each entry's
    resolved title (explicit "Title <doc>" or the target's first heading),
    instead of the default invisible stub."""
    import html as html_mod
    import re as re_mod

    from docutils import nodes
    from docutils.parsers import rst
    from docutils.parsers.rst import directives

    from .parse import _DummyOptionSpec

    entry_title_re = re_mod.compile(r"^(.*?)\s*<([^<>]+)>\s*$")

    class PreviewToctree(rst.Directive):
        required_arguments = 0
        optional_arguments = 100
        final_argument_whitespace = True
        has_content = True
        option_spec = _DummyOptionSpec()

        def run(self):  # noqa: D102
            from .toc import _first_heading_title

            items: list[str] = []
            for line in self.content:
                entry = line.strip()
                if not entry or entry.startswith(":"):
                    continue
                m = entry_title_re.match(entry)
                title, target = (m.group(1), m.group(2)) if m else (None, entry)
                if not title and _preview_srcdir and _preview_docdir:
                    if target.startswith("/"):
                        docname = target.lstrip("/")
                    else:
                        rel = (_preview_docdir / target).resolve()
                        try:
                            docname = rel.relative_to(_preview_srcdir).as_posix()
                        except ValueError:
                            docname = target
                    title = _first_heading_title(_preview_srcdir, docname)
                items.append(
                    f"<li>{html_mod.escape(title or target)} "
                    f'<span class="toctree-box__target">{html_mod.escape(target)}</span></li>'
                )
            caption = next(
                (v for k, v in (self.options or {}).items() if k == "caption"), None
            )
            head = f"<div class='toctree-box__caption'>{html_mod.escape(str(caption))}</div>" if caption else ""
            body = (
                f'<div class="toctree-box">{head}<div class="toctree-box__label">Contents (toctree)</div>'
                f"<ul>{''.join(items)}</ul></div>"
            )
            return [nodes.raw("", body, format="html")]

    directives.register_directive("toctree", PreviewToctree)


def render_preview(text: str, doc_path: str, source_abspath: str | None = None) -> str:
    """rst text -> HTML body fragment. Never raises: rendering failure
    returns an error box instead."""
    from docutils.core import publish_parts

    from .parse import _register_stub_directives, _register_stub_roles

    # make sure anything used by this text has at least a stub registered
    _register_stub_directives(text)
    _register_stub_roles(text)

    global _preview_srcdir, _preview_docdir
    if source_abspath:
        _preview_docdir = Path(source_abspath).parent
        depth = len([seg for seg in doc_path.replace("\\", "/").split("/") if seg]) - 1
        _preview_srcdir = Path(source_abspath).parents[depth] if depth >= 0 else _preview_docdir
    else:
        _preview_srcdir = _preview_docdir = None

    settings = {
        "report_level": 5,
        "halt_level": 5,
        "file_insertion_enabled": True,  # includes render inline, like Sphinx
        "raw_enabled": False,
        "math_output": "MathML",
        "embed_stylesheet": False,
        "stylesheet_path": "",
        "input_encoding": "utf-8",
        "output_encoding": "unicode",
        "warning_stream": False,
    }
    try:
        with _native_registries():
            _register_preview_toctree()
            try:
                parts = publish_parts(
                    source=text,
                    source_path=source_abspath,
                    writer_name="html5",
                    settings_overrides=settings,
                )
            finally:
                # _native_registries restores the stubbed registry state on
                # exit, which also removes this preview-only toctree
                pass
        body = parts["body"]
    except Exception as exc:  # noqa: BLE001 — preview must never 500
        return (
            '<div class="preview-error">Preview failed: '
            f"{type(exc).__name__}: {exc}</div>"
        )
    return _rewrite_asset_urls(body, doc_path)
