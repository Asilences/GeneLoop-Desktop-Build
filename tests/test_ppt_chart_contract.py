import pytest
from src.adapters.ppt.authoring.ppt_page_renderer import validate_chart,bullet_row_heights


def test_local_text_overflow_borrows_spare_space_without_changing_font_or_content():
    rows=bullet_row_heights([120,84,84,48],360)
    assert rows is not None and sum(rows)==360
    assert all(allocated>=needed for allocated,needed in zip(rows,[120,84,84,48]))
    assert bullet_row_heights([48,48,48,48],360)==[90]*4
    assert bullet_row_heights([120]*4,360) is None


def test_real_failure_shape_reports_seven_bars_instead_of_false_numeric_error():
    with pytest.raises(ValueError, match=r'count_out_of_range: max_bars=6, received=7'):
        validate_chart({'labels': list('ABCDEFG'), 'values': [1.25] * 7})
    labels, values = validate_chart({'labels': list('ABCDEF'), 'values': [0.0, 1, 2.4, 3, 4, 5]})
    assert len(labels) == len(values) == 6
    assert values == [0.0, 1, 2.4, 3, 4, 5]


@pytest.mark.parametrize('chart,reason', [
    ({'labels': ['A'], 'values': []}, 'length_mismatch'),
    ({'labels': [], 'values': []}, 'count_out_of_range'),
    ({'labels': ['A'], 'values': [[1.0]]}, 'finite_numbers'),
    ({'labels': ['A'], 'values': ['1.0']}, 'finite_numbers'),
    ({'labels': ['A'], 'values': [-1]}, 'finite_numbers'),
    ({'labels': ['A'], 'values': [float('nan')]}, 'finite_numbers'),
    ({'labels': [''], 'values': [1]}, 'text_labels'),
])
def test_invalid_input_has_distinct_actionable_reason_without_numeric_coercion(chart, reason):
    with pytest.raises(ValueError, match=reason):
        validate_chart(chart)
