"""Metadata-only correction keeps rendered geometry and visible text intact."""
import pytest

from src.adapters.ppt_annotation_repair import annotation_signature, repair_module_annotations


SVG = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">
<!-- Retain the project author comment. -->
<g id="a" data-pptx-bounds="0 0 400 100"><text id="first" x="20" y="40">First</text></g>
<g id="b" data-pptx-bounds="0 50 400 100"><text id="second" x="20" y="140">Second</text></g>
</svg>'''


def measure(node):
    return (20, 20, 80, 40) if node.get('id') == 'first' else (20, 120, 100, 140)


def test_annotations_change_without_changing_paint_text_or_comments():
    result, changes = repair_module_annotations(SVG, measure)
    assert len(changes) == 2
    assert annotation_signature(result) == annotation_signature(SVG)
    assert b'Retain the project author comment.' in result
    assert repair_module_annotations(result, measure) == (None, [])


def test_actual_overlap_and_off_canvas_content_are_never_hidden():
    assert repair_module_annotations(SVG, lambda node: (20, 20, 80, 40)) == (None, [])
    assert repair_module_annotations(SVG, lambda node: (-20, 20, 80, 40)) == (None, [])
    assert repair_module_annotations(SVG, lambda node: (20, 20, float('nan'), 40)) == (None, [])


def test_unsupported_painted_geometry_preserves_the_original_annotation():
    raw = SVG.replace(b'<text id="first"', b'<path d="M0 0 H50 V50 Z"/><text id="first"')
    assert repair_module_annotations(raw, measure) == (None, [])


def test_source_preview_pixels_are_identical():
    cairo = pytest.importorskip('cairosvg')
    result, _ = repair_module_annotations(SVG, measure)
    assert cairo.svg2png(bytestring=SVG) == cairo.svg2png(bytestring=result)


def test_program_pages_can_receive_missing_non_rendered_annotations():
    raw = SVG.replace(b' data-pptx-bounds="0 0 400 100"', b'').replace(b' data-pptx-bounds="0 50 400 100"', b'')
    result, changes = repair_module_annotations(raw, measure)
    assert len(changes) == 2
    assert all(row['before'] is None for row in changes)
    assert annotation_signature(raw) == annotation_signature(result)
