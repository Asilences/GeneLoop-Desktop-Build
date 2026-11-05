"""Typed syntax exemptions preserve scientific-content leak counterexamples."""
from src.adapters.ppt_component_literals import technical_literals

SVG = '<svg xmlns="http://www.w3.org/2000/svg"><rect fill="#2E5C8A"/><text>Scientific result</text></svg>'


def test_read_keys_and_actual_presentation_palette_are_structural_literals():
    result = technical_literals('data.get("fill"); data["bold"]; BLUE="#2E5C8A"', SVG)
    assert result == {'interface_keys': ['bold', 'fill'], 'presentation_palette': ['#2E5C8A']}


def test_literal_also_emitted_as_data_is_not_exempted_as_an_interface_key():
    result = technical_literals('data.get("fill"); print("fill"); print("Adam")', SVG)
    assert 'fill' not in result['interface_keys']
    assert 'Adam' not in result['interface_keys'] + result['presentation_palette']
    assert 'Adam' not in technical_literals('data.setdefault("Adam", 1)', SVG)['interface_keys']


def test_palette_code_used_as_scientific_text_remains_under_the_content_guard():
    result = technical_literals('BLUE="#2E5C8A"', SVG.replace('Scientific result', 'Measured code #2E5C8A'))
    assert result['presentation_palette'] == []
