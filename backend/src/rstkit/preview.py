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


def render_preview(text: str, doc_path: str, source_abspath: str | None = None) -> str:
    """rst text -> HTML body fragment. Never raises: rendering failure
    returns an error box instead."""
    from docutils.core import publish_parts

    from .parse import _register_stub_directives, _register_stub_roles

    # make sure anything used by this text has at least a stub registered
    _register_stub_directives(text)
    _register_stub_roles(text)

    settings = {
        "report_level": 5,
        "halt_level": 5,
        "file_insertion_enabled": True,  # includes render inline, like Sphinx
        "raw_enabled": False,
        "math_output": "MathML",
        "embed_stylesheet": False,
        "stylesheet_path": "",
        "input_encoding": "unicode",
        "output_encoding": "unicode",
        "warning_stream": False,
    }
    try:
        with _native_registries():
            parts = publish_parts(
                source=text,
                source_path=source_abspath,
                writer_name="html5",
                settings_overrides=settings,
            )
        body = parts["body"]
    except Exception as exc:  # noqa: BLE001 — preview must never 500
        return (
            '<div class="preview-error">Preview failed: '
            f"{type(exc).__name__}: {exc}</div>"
        )
    return _rewrite_asset_urls(body, doc_path)
