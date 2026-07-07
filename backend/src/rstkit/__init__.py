"""rstkit — rst round-trip engine for the semi-WYSIWYG Sphinx editor.

Core guarantee: a file that is parsed and serialized with no edits is
byte-identical to the original. See parse.py (span partition) and
serialize.py (span concatenation).
"""

__version__ = "0.1.0"
