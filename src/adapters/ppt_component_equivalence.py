"""Independent visible-text and rendered-page checks for parameterized SVGs."""
from pathlib import Path
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.adapters.ppt_design_preflight import font_independent_signature

from PIL import Image, ImageChops, ImageStat

# Reuse the video source-certification threshold, fixed before this PPT gate.
MAX_SOURCE_PIXEL_MAE = 1.0


def compare_component_pages(reference, actual, mode='preserve'):
    if mode not in ('preserve', 'font_repair_v1', 'readability_repair_v1'):
        raise ValueError('component_equivalence_mode_invalid')
    roots, texts, versions = [], [], []
    images = []
    for directory in map(Path, (reference, actual)):
        svg = directory / 'page.svg'
        png = directory / 'page.png'
        for path in (svg, png):
            if path.is_symlink() or not path.is_file():
                raise ValueError('component_equivalence_fixed_files_required')
        raw = svg.read_bytes()
        roots.append(ET.fromstring(raw))
        texts.append([''.join(node.itertext()) for node in roots[-1].iter()
                      if node.tag.rsplit('}', 1)[-1] == 'text'])
        picture = Image.open(png).convert('RGBA')
        images.append(Image.alpha_composite(Image.new('RGBA', picture.size, '#FFFFFF'), picture).convert('RGB'))
        versions.append({'svg_sha256': hashlib.sha256(raw).hexdigest(), 'png_sha256': hashlib.sha256(png.read_bytes()).hexdigest()})
    # ppt-master defines the page canvas by viewBox. Explicit SVG width/height
    # may be omitted without changing the exported page or its rendered size.
    viewboxes = [tuple(map(float, root.get('viewBox', '').replace(',', ' ').split())) for root in roots]
    same_contract = len(viewboxes[0]) == 4 and viewboxes[0] == viewboxes[1] and roots[0].get('data-pptx-page-role') == roots[1].get('data-pptx-page-role')
    same_size = images[0].size == images[1].size
    mae = sum(ImageStat.Stat(ImageChops.difference(*images)).mean) / 3 if same_size else None
    same_text = bool(texts[0]) and texts[0] == texts[1]
    signatures = [font_independent_signature((Path(directory) / 'page.svg').read_bytes(),
                                            allow_text_color=mode == 'readability_repair_v1')
                  for directory in (reference, actual)]
    font_only = signatures[0] == signatures[1]
    rendering_matches = font_only if mode != 'preserve' else mae <= MAX_SOURCE_PIXEL_MAE
    return {'passed': same_contract and same_size and same_text and rendering_matches,
            'mode': mode, 'font_independent_structure_equal': font_only,
            'visible_text_exact': same_text, 'page_contract_equal': same_contract,
            'pixel_mae': mae, 'pixel_mae_maximum': MAX_SOURCE_PIXEL_MAE,
            'source_byte_equivalent': versions[0]['svg_sha256'] == versions[1]['svg_sha256'], 'page_background': '#FFFFFF',
            'versions': versions, 'scope': 'exact_text_and_geometry_with_declared_style_repair' if mode != 'preserve' else 'exact_visible_text_and_source_render_equivalence'}


if __name__ == '__main__':
    print(json.dumps(compare_component_pages(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else 'preserve')))
