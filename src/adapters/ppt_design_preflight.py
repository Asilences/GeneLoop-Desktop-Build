"""Mechanical checks for self-contained SVG pages in the actual font environment."""
from functools import lru_cache
from pathlib import Path
import math
import re
import subprocess
import hashlib
import json
import xml.etree.ElementTree as ET


def rgb(value):
    value = value.strip().lower()
    names = {'white': '#ffffff', 'black': '#000000'}
    value = names.get(value, value)
    if re.fullmatch(r'#[0-9a-f]{3}', value):
        value = '#' + ''.join(c * 2 for c in value[1:])
    if not re.fullmatch(r'#[0-9a-f]{6}', value):
        return None
    return [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]


def contrast(foreground, background):
    colors = [rgb(value) for value in (foreground, background)]
    if any(value is None for value in colors):
        return None
    def luminance(color):
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in color]
        return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))
    light, dark = sorted(map(luminance, colors), reverse=True)
    return (light + .05) / (dark + .05)


@lru_cache(maxsize=128)
def font_coverage(family, weight):
    families = [name.strip().strip('"\'') for name in family.split(',')]
    pattern = ','.join(name.replace('\\', '\\\\').replace(':', '\\:') for name in families)
    matched = subprocess.run(['fc-match', '-f', '%{file}\n%{index}\n%{family}\n',
                              pattern + ':weight=' + weight], capture_output=True, text=True, check=True, timeout=15)
    lines = matched.stdout.splitlines()
    if len(lines) < 3 or not Path(lines[0]).is_file():
        raise ValueError('ppt_font_resolution_failed')
    index = int(lines[1] or 0) & 0xffff
    queried = subprocess.run(['fc-query', '--index', str(index), '--format', '%{charset}', lines[0]],
                             capture_output=True, text=True, check=True, timeout=15)
    characters = set()
    charset = '\n'.join(line for line in queried.stdout.splitlines() if not re.fullmatch(r'id \d+', line))
    for span in charset.split():
        limits = span.split('-')
        first, last = int(limits[0], 16), int(limits[-1], 16)
        if not 0 <= first <= last <= 0x10ffff:
            raise ValueError('ppt_font_charset_invalid')
        characters.update(range(first, last + 1))
    return {'file': lines[0], 'index': index, 'family': lines[2], 'characters': frozenset(characters)}


def number(value):
    if value is None or not re.fullmatch(r'-?(?:\d+(?:\.\d*)?|\.\d+)(?:px)?', value.strip()):
        return None
    result = float(value.removesuffix('px'))
    return result if math.isfinite(result) else None


def measured_text_bounds(text, properties):
    """Measure simple untransformed text with the same resolved font file."""
    from PIL import ImageFont
    size = number(properties.get('font-size', '16'))
    if size is None or size <= 0 or size > 400:
        return None
    weight = 'bold' if properties.get('font-weight') in ('bold', '600', '700', '800', '900') else 'regular'
    resolved = font_coverage(properties.get('font-family', 'sans-serif'), weight)
    font = ImageFont.truetype(resolved['file'], size=round(size), index=resolved['index'])
    left, top, right, bottom = font.getbbox(text, anchor='ls')
    anchor = properties.get('text-anchor', 'start')
    if anchor not in ('start', 'middle', 'end'):
        return None
    offset = font.getlength(text) * {'start': 0, 'middle': .5, 'end': 1}[anchor]
    return left - offset, top, right - offset, bottom


def inspect_svg(raw, *, check_fonts=True, check_bounds=False):
    """Only enforce unambiguous findings. Complex effects remain review items."""
    root = ET.fromstring(raw)
    findings, resolved_fonts, rectangles, unresolved_contrast = [], {}, [], []
    serial = 0
    try:
        canvas = [float(value) for value in re.split(r'[ ,]+', root.get('viewBox', '').strip())]
        if len(canvas) != 4 or not all(math.isfinite(value) for value in canvas):
            canvas = None
    except ValueError:
        canvas = None

    def visit(node, inherited, complex_effect=False):
        nonlocal serial
        serial += 1
        identity = node.get('id') or 'element-' + str(serial)
        properties = dict(inherited)
        properties.update(node.attrib)
        for declaration in node.get('style', '').split(';'):
            if ':' in declaration:
                key, value = declaration.split(':', 1)
                properties[key.strip()] = value.strip()
        complex_effect = complex_effect or any(key in node.attrib for key in ('transform', 'filter', 'mask', 'clip-path')) or properties.get('opacity', '1') != '1'
        tag = node.tag.rsplit('}', 1)[-1]
        fill = properties.get('fill', '#000000')
        opaque = properties.get('opacity', '1') == '1' and properties.get('fill-opacity', '1') == '1'
        if tag == 'rect':
            box = [number(node.get(k, '0' if k in ('x', 'y') else '')) for k in ('x', 'y', 'width', 'height')]
            if not complex_effect and opaque and all(v is not None for v in box) and rgb(fill) is not None:
                rectangles.append((*box, fill))
            elif fill != 'none':
                rectangles.append(None)
        elif tag in ('path', 'circle', 'ellipse', 'polygon', 'polyline', 'image', 'use') and (
                tag in ('image', 'use') or fill != 'none' or properties.get('stroke', 'none') != 'none'):
            # An intervening painted shape may cover the last known rectangle.
            # Its actual background requires rendered review. Never infer white
            # background through a dark rounded path or a transformed shape.
            rectangles.append(None)
        if tag in ('text', 'tspan'):
            text = (node.text or '') + ''.join(child.tail or '' for child in node)
            x, y = number(node.get('x')), number(node.get('y'))
            if check_bounds and canvas and text.strip() and not len(node) and x is not None and y is not None and not complex_effect:
                extent = measured_text_bounds(text, properties)
                if extent:
                    left, top, right, bottom = extent
                    cx, cy, width, height = canvas
                    if x + left < cx - 1 or y + top < cy - 1 or x + right > cx + width + 1 or y + bottom > cy + height + 1:
                        findings.append({'rule': 'text_canvas_overflow', 'object': identity, 'severity': 'error',
                                         'bounds': [round(x + left, 2), round(y + top, 2), round(x + right, 2), round(y + bottom, 2)],
                                         'canvas': canvas, 'next_action': 'shorten_or_reflow_this_text_before_installation'})
            if x is not None and y is not None and not complex_effect and opaque:
                for rectangle in reversed(rectangles):
                    if rectangle is None:
                        unresolved_contrast.append(identity)
                        break
                    rx, ry, width, height, background = rectangle
                    if rx <= x <= rx + width and ry <= y <= ry + height:
                        ratio = contrast(fill, background)
                        if ratio is not None and ratio < 4.5:
                            findings.append({'rule': 'text_contrast', 'object': identity, 'severity': 'error',
                                             'ratio': round(ratio, 3), 'foreground': fill, 'background': background})
                        break
            if check_fonts and text.strip():
                family = properties.get('font-family', 'sans-serif')
                weight = 'bold' if properties.get('font-weight') in ('bold', '600', '700', '800', '900') else 'regular'
                font = font_coverage(family, weight)
                missing = sorted({ord(c) for c in text if not c.isspace() and ord(c) not in font['characters']})
                resolved_fonts[family + ':' + weight] = {k: v for k, v in font.items() if k != 'characters'}
                if missing:
                    findings.append({'rule': 'missing_glyphs', 'object': identity, 'severity': 'error',
                                     'font_family': family,
                                     'codepoints': ['U+' + format(c, '04X') for c in missing]})
        for child in node:
            visit(child, properties, complex_effect)

    visit(root, {})
    return {'version': 1, 'findings': findings, 'fonts': resolved_fonts, 'contrast_requires_visual_review': unresolved_contrast,
            'mechanical_status': 'failed' if findings else 'passed', 'visual_review': 'pending',
            'limitations': ['Contrast covers solid rectangles behind text anchors. Optional bounds cover simple positioned text; nested text and complex effects require visual review.',
                            'Font cmap coverage requires actual rendered-page review for shaping and fallback.']}


def font_independent_signature(raw, *, allow_text_color=False):
    root = ET.fromstring(raw)
    rows = []
    for node in root.iter():
        attributes = {key: value for key, value in node.attrib.items() if key != 'font-family'}
        color_repair = allow_text_color and node.tag.rsplit('}', 1)[-1] in ('text', 'tspan')
        if color_repair:
            attributes.pop('fill', None)
        if 'style' in attributes:
            attributes['style'] = ';'.join(declaration for declaration in attributes['style'].split(';')
                                           if declaration.split(':', 1)[0].strip() not in
                                           (('font-family', 'fill') if color_repair else ('font-family',)))
        text = node.text if node.text and node.text.strip() else None
        tail = node.tail if node.tail and node.tail.strip() else None
        rows.append([node.tag, sorted(attributes.items()), text, tail])
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def apply_font_rule(raw, rule):
    root = ET.fromstring(raw)
    changed = False
    for node in root.iter():
        if node.get('font-family') == rule['from_family']:
            node.set('font-family', rule['to_family'])
            changed = True
        if 'style' in node.attrib:
            declarations = []
            for declaration in node.get('style').split(';'):
                if ':' in declaration:
                    key, value = declaration.split(':', 1)
                    if key.strip() == 'font-family' and value.strip() == rule['from_family']:
                        declaration = key + ':' + rule['to_family']
                        changed = True
                declarations.append(declaration)
            node.set('style', ';'.join(declarations))
    if not changed:
        return None
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    result = ET.tostring(root, encoding='utf-8')
    if font_independent_signature(result) != font_independent_signature(raw):
        raise ValueError('font_repair_changed_content_or_geometry')
    return result
