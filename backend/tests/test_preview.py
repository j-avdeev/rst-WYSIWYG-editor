from rstkit.preview import render_preview


def test_preview_include_reads_utf8_file(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    source = root / "index.rst"
    source.write_text("Before.\n\n.. include:: included.rst\n", encoding="utf-8")
    (root / "included.rst").write_text("Included **текст**.\n", encoding="utf-8")

    html = render_preview(source.read_text(encoding="utf-8"), "index.rst", str(source))

    assert "Preview failed" not in html
    assert "Included" in html
    assert "текст" in html


def test_preview_rewrites_image_urls():
    html = render_preview(".. image:: image.png\n", "index.rst")

    assert '/api/asset?doc=index.rst&uri=image.png' in html
