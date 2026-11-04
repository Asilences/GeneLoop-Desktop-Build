"""A small rendering drift cannot hide changed scientific text."""
from PIL import Image

from src.adapters.ppt_component_equivalence import compare_component_pages


def page(directory, text, color='white'):
    directory.mkdir()
    (directory / 'page.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 72" width="128" height="72"><text x="1" y="20">' + text + '</text></svg>')
    Image.new('RGB', (128, 72), color).save(directory / 'page.png')
    return directory


def test_identical_text_and_pixels_accept_svg_formatting_difference(tmp_path):
    reference = page(tmp_path / 'reference', 'Accuracy 93.2')
    actual = page(tmp_path / 'actual', 'Accuracy 93.2')
    (actual / 'page.svg').write_text((actual / 'page.svg').read_text().replace('><text', '>\n <text'))
    result = compare_component_pages(reference, actual)
    assert result['passed'] and result['visible_text_exact'] and not result['source_byte_equivalent']
    assert result['pixel_mae_maximum'] == 1.0


def test_changed_number_fails_even_if_supplied_pixels_are_identical(tmp_path):
    result = compare_component_pages(page(tmp_path / 'reference', 'Accuracy 93.2'), page(tmp_path / 'actual', 'Accuracy 99.2'))
    assert result['passed'] is False and result['visible_text_exact'] is False


def test_changed_page_render_fails_with_identical_text(tmp_path):
    result = compare_component_pages(page(tmp_path / 'reference', 'same'), page(tmp_path / 'actual', 'same', 'black'))
    assert result['passed'] is False and result['pixel_mae'] == 255.0


def test_implicit_dimensions_and_transparent_page_canvas_share_export_semantics(tmp_path):
    reference = page(tmp_path / 'reference', 'same')
    actual = page(tmp_path / 'actual', 'same')
    path = reference / 'page.svg'
    path.write_text(path.read_text().replace(' width="128" height="72"', ''))
    Image.new('RGBA', (128, 72), (0, 0, 0, 0)).save(reference / 'page.png')
    result = compare_component_pages(reference, actual)
    assert result['passed'] and result['page_contract_equal'] and result['pixel_mae'] == 0


def test_font_repair_certificate_allows_font_change_and_rejects_content_or_geometry_change(tmp_path):
    reference = page(tmp_path / 'reference', 'Accuracy 93.2')
    actual = page(tmp_path / 'actual', 'Accuracy 93.2', 'black')
    path = actual / 'page.svg'
    path.write_text(path.read_text().replace('<text ', '<text font-family="Noto Sans CJK SC" '))
    path.write_text(path.read_text().replace('><text', '>\n  <text'))
    result = compare_component_pages(reference, actual, 'font_repair_v1')
    assert result['passed'] and result['font_independent_structure_equal']
    assert compare_component_pages(reference, actual)['passed'] is False
    path.write_text(path.read_text().replace('x="1"', 'x="2"'))
    assert compare_component_pages(reference, actual, 'font_repair_v1')['passed'] is False


def test_readability_repair_cannot_change_shapes_or_numbers(tmp_path):
    reference = page(tmp_path / 'reference', 'Accuracy 93.2')
    actual = page(tmp_path / 'actual', 'Accuracy 93.2', 'black')
    path = actual / 'page.svg'
    path.write_text(path.read_text().replace('<text ', '<text fill="#ffffff" '))
    assert compare_component_pages(reference, actual, 'readability_repair_v1')['passed']
    assert not compare_component_pages(reference, actual, 'font_repair_v1')['passed']
    path.write_text(path.read_text().replace('93.2', '99.2'))
    assert not compare_component_pages(reference, actual, 'readability_repair_v1')['passed']
