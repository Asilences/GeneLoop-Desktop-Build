"""Render a generated, self-contained SVG page in the existing isolated job."""
from pathlib import Path
import json
import re
import sys
import runpy
import xml.etree.ElementTree as ET


def render_component_page(directory, *, require_design=True):
    import cairosvg
    directory = Path(directory)
    source = directory / 'page.svg'
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 1_000_000:
        raise ValueError('component_page_svg_required')
    raw = source.read_bytes()
    root = ET.fromstring(raw)
    if root.tag != '{http://www.w3.org/2000/svg}svg':
        raise ValueError('component_svg_root_required')
    viewbox = [float(v) for v in re.split(r'[ ,]+', root.get('viewBox', '').strip())]
    if len(viewbox) != 4 or not all(0 < n <= 7680 for n in viewbox[2:]):
        raise ValueError('component_viewbox_invalid')
    for node in root.iter():
        if node.tag.rsplit('}', 1)[-1] in ('script', 'foreignObject', 'image', 'use', 'style'):
            raise ValueError('component_self_contained_vector_required')
        for name, value in node.attrib.items():
            if name.rsplit('}', 1)[-1] in ('href', 'src') or re.search(r'url\s*\(', value, re.I):
                raise ValueError('component_external_reference_refused')
    inspect_svg = runpy.run_path(str(Path(__file__).with_name('ppt_design_preflight.py')))['inspect_svg']
    report = inspect_svg(raw)
    if require_design and report['mechanical_status'] == 'failed':
        raise ValueError('component_design_preflight_failed: ' + json.dumps(report['findings'], ensure_ascii=False))
    target = directory / 'page.png'
    if target.exists() or target.is_symlink():
        raise ValueError('component_fresh_render_required')
    png = cairosvg.svg2png(bytestring=raw, output_width=round(viewbox[2]), output_height=round(viewbox[3]),
                          background_color='#FFFFFF', unsafe=False)
    target.write_bytes(png)
    # Keep validation separate from a scientific or visual acceptance verdict.
    (directory / 'design-check.json').write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
    return {'svg': 'page.svg', 'png': 'page.png', 'width': round(viewbox[2]), 'height': round(viewbox[3])}


if __name__ == '__main__':
    print(json.dumps(render_component_page(sys.argv[1], require_design='--reference-design-findings' not in sys.argv[2:])))
