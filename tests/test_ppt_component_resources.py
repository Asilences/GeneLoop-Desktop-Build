import xml.etree.ElementTree as ET
import pytest
from src.adapters.ppt.authoring.ppt_component_render import validate_local_svg_resources


def svg(body):
    return ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg">' + body + '</svg>')


def test_self_contained_template_shadow_and_gradient_are_not_external_requests():
    validate_local_svg_resources(svg('''<defs><filter id="shadow"><feGaussianBlur stdDeviation="3"/></filter>
      <linearGradient id="paint"><stop offset="0" stop-color="#fff"/></linearGradient></defs>
      <g id="card"><rect width="10" height="10" filter="url(#shadow)" fill="url(#paint)"/></g>'''))


@pytest.mark.parametrize('value', ['url(https://example.com/a.svg#paint)', 'url(file:///tmp/a)',
                                  'url(data:image/svg+xml,abc)', 'url(#missing)', 'url(#paint) red',
                                  'url(\\23paint)', 'url(#paint) url(#other)'])
def test_external_missing_or_ambiguous_paint_is_still_refused(value):
    root = svg('<defs><linearGradient id="paint"/></defs><rect/>')
    root[-1].set('fill', value)
    with pytest.raises(ValueError, match='component_external_reference_refused'):
        validate_local_svg_resources(root)


@pytest.mark.parametrize('body', ['<image href="https://example.com/a.png"/>',
                                 '<use href="#x"/>', '<style>text{fill:red}</style>',
                                 '<foreignObject/>', '<script/>'])
def test_active_and_external_dependency_tags_remain_refused(body):
    with pytest.raises(ValueError):
        validate_local_svg_resources(svg(body))


def test_duplicate_wrong_kind_and_recursive_resources_are_refused():
    for body in ['<defs><filter id="x"/><filter id="x"/></defs>',
                 '<rect id="x" fill="url(#x)"/>',
                 '<pattern id="x"><rect fill="url(#x)"/></pattern>']:
        with pytest.raises(ValueError):
            validate_local_svg_resources(svg(body))
