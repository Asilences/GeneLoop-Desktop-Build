"""Recompute non-rendered module annotations without changing visible content."""
import hashlib
import json
import sys
import math
import xml.etree.ElementTree as ET


def annotation_signature(raw):
    root = ET.fromstring(raw, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
    rows = [(node.tag if isinstance(node.tag, str) else '#comment',
             sorted((key, value) for key, value in node.attrib.items() if key != 'data-pptx-bounds'),
             node.text, node.tail) for node in root.iter()]
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()


def repair_module_annotations(raw, measure_text=None):
    root = ET.fromstring(raw, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
    if measure_text is None:
        sys.path.insert(0, '/opt/geneloop/ppt-master/scripts')
        from svg_quality.checker import SVGQualityChecker, _resolve_project_font_sizes, _resolve_project_letter_spacings
        parents = {id(child): parent for parent in root.iter() for child in parent}
        sizes = _resolve_project_font_sizes(root)
        spacings = _resolve_project_letter_spacings(root, sizes)
        measure_text = lambda node: SVGQualityChecker._estimated_text_bounds(node, parents, sizes, spacings)
    canvas = list(map(float, root.get('viewBox', '').replace(',', ' ').split()))
    if len(canvas) != 4:
        return None, []
    def tag(node):
        return node.tag.rsplit('}', 1)[-1] if isinstance(node.tag, str) else '#comment'
    def bounds(node):
        kind = tag(node)
        if kind == 'text':
            return measure_text(node)
        if kind in ('g', 'title', 'desc', 'metadata', '#comment'):
            return []
        if kind in ('rect', 'image'):
            x, y, width, height = (float(node.get(key, '0')) for key in ('x', 'y', 'width', 'height'))
            return x, y, x + width, y + height
        if kind in ('circle', 'ellipse'):
            cx, cy = float(node.get('cx', '0')), float(node.get('cy', '0'))
            rx, ry = (float(node.get('r', '0')), float(node.get('r', '0'))) if kind == 'circle' else (float(node.get('rx', '0')), float(node.get('ry', '0')))
            return cx - rx, cy - ry, cx + rx, cy + ry
        if kind == 'line':
            x1, y1, x2, y2 = (float(node.get(key, '0')) for key in ('x1', 'y1', 'x2', 'y2'))
            return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
        return None
    proposals = []
    for group in root:
        if tag(group) != 'g' or group.get('data-pptx-layer') is not None:
            continue
        if any(node.get(key) is not None for node in group.iter() for key in
               ('transform', 'filter', 'clip-path', 'mask', 'data-pptx-layer', 'data-pptx-placeholder')):
            return None, []
        boxes = []
        # Text measurements include its tspans. No double counting of runs.
        def visit(node):
            box = bounds(node)
            if box is None:
                raise ValueError('unsupported_annotation_geometry')
            if box:
                boxes.append(box)
            if tag(node) != 'text':
                for child in node:
                    visit(child)
        try:
            visit(group)
        except (ValueError, TypeError):
            return None, []
        if not boxes:
            return None, []
        box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
        if not all(math.isfinite(value) for value in box):
            return None, []
        if box[0] < canvas[0] or box[1] < canvas[1] or box[2] > canvas[0] + canvas[2] or box[3] > canvas[1] + canvas[3]:
            return None, []
        proposals.append((group, box))
    for i, (_, a) in enumerate(proposals):
        for _, b in proposals[i + 1:]:
            if min(a[2], b[2]) - max(a[0], b[0]) > 1 and min(a[3], b[3]) - max(a[1], b[1]) > 1:
                return None, []
    changes = []
    for group, (x1, y1, x2, y2) in proposals:
        if x2 <= x1 or y2 <= y1:
            return None, []
        value = ' '.join(format(value, '.9g') for value in (x1, y1, x2 - x1, y2 - y1))
        if group.get('data-pptx-bounds') != value:
            changes.append({'object': group.get('id'), 'before': group.get('data-pptx-bounds'), 'after': value})
            group.set('data-pptx-bounds', value)
    if not changes:
        return None, []
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    result = ET.tostring(root, encoding='utf-8')
    if annotation_signature(raw) != annotation_signature(result):
        raise ValueError('annotation_repair_changed_visible_content')
    return result, changes
