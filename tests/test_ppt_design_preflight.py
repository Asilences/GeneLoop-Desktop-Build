import pytest

from src.adapters.ppt_design_preflight import contrast, inspect_svg


def svg(content):
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">' + content + '</svg>'


def test_old_pale_band_white_text_is_a_concrete_failure():
    report = inspect_svg(svg('<rect width="1280" height="720" fill="#F4F6F8"/>'
                             '<text x="40" y="50" fill="#FFFFFF">Conclusion</text>'), check_fonts=False)
    assert report['mechanical_status'] == 'failed'
    assert report['findings'][0]['rule'] == 'text_contrast'
    assert contrast('#ffffff', '#000000') == 21


def test_component_text_extent_is_rejected_before_installation(monkeypatch):
    monkeypatch.setattr('src.adapters.ppt_design_preflight.measured_text_bounds', lambda *args: (0, -20, 1300, 2))
    raw = svg('<text x="88" y="554" font-size="22">Overlong current content</text>')
    assert inspect_svg(raw, check_fonts=False)['mechanical_status'] == 'passed'
    report = inspect_svg(raw, check_fonts=False, check_bounds=True)
    assert report['mechanical_status'] == 'failed'
    assert report['findings'][0]['rule'] == 'text_canvas_overflow'


def test_complex_text_is_not_falsely_rejected_by_simple_bounds(monkeypatch):
    def unexpected(*args):
        raise AssertionError('Transforms need rendered review')
    monkeypatch.setattr('src.adapters.ppt_design_preflight.measured_text_bounds', unexpected)
    raw = svg('<g transform="translate(-1000,0)"><text x="1200" y="50">Transformed</text></g>')
    assert inspect_svg(raw, check_fonts=False, check_bounds=True)['mechanical_status'] == 'passed'


def test_actual_resolved_font_measures_text_anchor():
    import shutil
    if not shutil.which('fc-match') or not shutil.which('fc-query'):
        pytest.skip('Actual fontconfig environment required')
    from src.adapters.ppt_design_preflight import measured_text_bounds
    properties = {'font-size': '22', 'font-family': 'sans-serif'}
    left, _, right, _ = measured_text_bounds('Long measured text', properties)
    assert right > left
    centered = measured_text_bounds('Long measured text', {**properties, 'text-anchor': 'middle'})
    assert centered[0] < left and centered[2] < right


def test_opaque_dark_text_passes_and_complex_effects_remain_visual_review():
    report = inspect_svg(svg('<rect width="1280" height="720" fill="white"/>'
                             '<text x="40" y="50" fill="#172B4D">Conclusion</text>'), check_fonts=False)
    assert report['mechanical_status'] == 'passed'
    assert report['visual_review'] == 'pending'
    report = inspect_svg(svg('<g transform="translate(5,5)"><text x="40" y="50" fill="white">Title</text></g>'), check_fonts=False)
    assert not report['findings']


def test_missing_glyphs_are_reported_with_actual_codepoints(monkeypatch):
    monkeypatch.setattr('src.adapters.ppt_design_preflight.font_coverage',
                        lambda *args: {'file': '/font.ttf', 'index': 0, 'family': 'Diagnostic', 'characters': {ord('A')}})
    report = inspect_svg(svg('<text x="40" y="50">A中</text>'))
    assert report['findings'][0]['codepoints'] == ['U+4E2D']


def test_legal_overlapping_text_boxes_do_not_create_hard_failures():
    report = inspect_svg(svg('<text x="40" y="50">Title</text><text x="40" y="51">Subtitle</text>'), check_fonts=False)
    assert report['findings'] == []


def test_dark_path_background_is_not_misread_as_the_white_rectangle_below_it():
    report = inspect_svg(svg('<rect width="1280" height="720" fill="white"/>'
                             '<path d="M20 20 H400 V300 H20 Z" fill="#1A3A5C"/>'
                             '<text id="summary" x="40" y="70" fill="white">Conclusion</text>'), check_fonts=False)
    assert report['mechanical_status'] == 'passed'
    assert report['findings'] == []
    assert report['contrast_requires_visual_review'] == ['summary']


def test_css_font_quotes_and_old_fontconfig_index_banner_are_supported(monkeypatch):
    from types import SimpleNamespace
    from src.adapters.ppt_design_preflight import font_coverage
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(stdout=__file__ + '\n0\nNoto Sans CJK SC\n' if argv[0] == 'fc-match' else 'id 0\n20-7e 4e2d')
    monkeypatch.setattr('subprocess.run', run)
    font_coverage.cache_clear()
    result = font_coverage('"Noto Sans CJK SC", "DejaVu Sans"', 'regular')
    assert calls[0][-1] == 'Noto Sans CJK SC,DejaVu Sans:weight=regular'
    assert ord('中') in result['characters']
    font_coverage.cache_clear()


def test_runner_rejects_manifest_order_and_paths_before_export(tmp_path):
    from src.adapters.ppt_delivery_runner import fixed_file
    (tmp_path / 'inside.txt').write_text('source')
    with pytest.raises(ValueError, match='outside_workspace'):
        fixed_file(tmp_path.parent / 'outside.txt', tmp_path)
    (tmp_path / 'link.txt').symlink_to(tmp_path / 'inside.txt')
    with pytest.raises(ValueError):
        fixed_file(tmp_path / 'link.txt', tmp_path)
