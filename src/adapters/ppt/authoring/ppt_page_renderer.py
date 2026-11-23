"""Deterministic, editable page compositions using the owning project's theme."""
from pathlib import Path
import base64
import hashlib
import json
import math
import os
import re
import sys
from uuid import uuid4
from xml.sax.saxutils import escape

if __package__:
    from src.adapters.ppt.authoring.ppt_design_preflight import font_coverage,exporter_text_width


def validate_chart(chart):
    if not isinstance(chart, dict) or not isinstance(chart.get('labels'), list) or not isinstance(chart.get('values'), list):
        raise ValueError('page_chart_flat_labels_and_numeric_values_arrays_required')
    labels, values = chart['labels'], chart['values']
    if len(labels) != len(values):
        raise ValueError(f'page_chart_length_mismatch: labels={len(labels)}, values={len(values)}')
    if not 1 <= len(labels) <= 6:
        raise ValueError(f'page_chart_count_out_of_range: max_bars=6, received={len(labels)}; select supported comparisons or use a separate table page; do not change scientific values')
    if any(not isinstance(label, str) or not label.strip() for label in labels):
        raise ValueError('page_chart_nonempty_text_labels_required')
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in values):
        raise ValueError('page_chart_nonnegative_finite_numbers_required: strings and nested series are unsupported; preserve source values')
    return labels, values


def bullet_row_heights(required, height):
    """Keep the existing grid unless spare space can resolve a local overflow."""
    equal=height/len(required)
    if max(required)<=equal:return [equal]*len(required)
    if sum(required)>height:return None
    spare=(height-sum(required))/len(required)
    return [value+spare for value in required]


def render_page(request):
    from PIL import Image, ImageFont
    project = Path(request['project'])
    if not project.is_relative_to('/work/projects') or project.resolve() != project or project.is_symlink():
        raise ValueError('page_project_outside_workspace')
    page = request['page']
    if not re.fullmatch(r'[\w-]{1,128}\.svg', page):
        raise ValueError('page_filename_invalid')
    target = project / 'svg_output' / page
    notes = project / 'notes' / (Path(page).stem + '.md')
    for parent in (target.parent, notes.parent):
        if not parent.is_dir() or parent.resolve() != parent:
            raise ValueError('page_project_directory_changed')
    for path in (target, notes):
        if path.exists() and (path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1):
            raise ValueError('page_target_changed')
    expected = request.get('expected_page_sha256')
    if target.exists():
        if not expected or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError('page_revision_requires_current_sha256')
    elif expected is not None:
        raise ValueError('page_revision_source_missing')
    theme, content = request['theme'], request['content']
    geometry = request['layout_config']['geometry']
    margin, right_column = geometry['margin_x'], geometry['right_column_x']
    colors, sizes = theme['colors'], theme['font_sizes_pt']
    family = 'Noto Sans CJK SC'
    face = font_coverage(family, 'regular')['file']
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
             'width="1280" height="720" viewBox="0 0 1280 720" data-pptx-page-role="content">',
             f'<rect width="1280" height="720" fill="{colors["bg"]}"/>']
    serial = 0

    def wrapped(value, width, role='body'):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('page_nonempty_text_required')
        size = sizes[role]
        lines, line = [], ''
        for char in value:
            if char == '\n' or exporter_text_width(line + char,family,size) > width:
                if line:
                    lines.append(line)
                line = '' if char == '\n' else char
            else:
                line += char
        if line:
            lines.append(line)
        return lines

    def text(value, box, role='body', color=None):
        nonlocal serial
        x, y, width, height = box
        size = sizes[role]
        lines=wrapped(value,width,role)
        step = size * 1.5
        if len(lines) * step > height:
            raise ValueError(f'page_text_capacity_exceeded: role={role}, characters={len(value)}, required_lines={len(lines)}, max_lines={int(height // step)}; shorten this text or choose a wider layout; do not remeasure fonts')
        serial += 1
        for index, line in enumerate(lines):
            parts.append(f'<text id="text-{serial}-{index}" x="{x}" y="{y + size + index * step}" '
                         f'font-family="{family}" font-size="{size}" fill="{color or colors["text"]}">{escape(line)}</text>')

    def bullets(values, box):
        if not isinstance(values, list) or not 1 <= len(values) <= 8:
            raise ValueError('page_body_requires_one_to_eight_items')
        x, y, width, height = box
        required=[len(wrapped(value,width))*sizes['body']*1.5+12 for value in values]
        rows=bullet_row_heights(required,height)
        if rows is None:
            index=max(range(len(required)),key=lambda i:required[i])
            raise ValueError(f'page_body_capacity_exceeded: item_index={index}, required_total_height={sum(required)}, available_height={height}; shorten content.body[{index}] or choose a wider layout; keep project/page/layout at the tool argument top level')
        offset=0
        for index, value in enumerate(values):
            text(value, (x, y + offset, width, rows[index] - 12))
            offset+=rows[index]

    layout = request['layout']
    title = content['title']
    if layout in ('cover', 'section', 'closing'):
        text(title, (margin, 205, 1104, 150), 'title', colors['primary'])
        if content.get('body'):
            bullets(content['body'], (margin, 390, 1050, 210))
    else:
        text(title, (margin, 48, 1104, 110), 'title', colors['primary'])
        if layout == 'bullets':
            bullets(content['body'], (margin, 190, 1104, 420))
        elif layout == 'two_column':
            columns = content.get('columns', [])
            if len(columns) != 2:
                raise ValueError('page_two_columns_required')
            for x, column in zip((margin, right_column), columns):
                text(column['title'], (x, 180, 500, 65), 'heading', colors['primary'])
                bullets(column['body'], (x, 270, 500, 345))
        elif layout == 'image_text':
            image_path = Path(content['image'])
            if (not image_path.is_relative_to('/work') or image_path.resolve() != image_path or
                    image_path.is_symlink() or not image_path.is_file() or image_path.stat().st_nlink != 1 or
                    image_path.stat().st_size > 30_000_000):
                raise ValueError('page_image_outside_workspace')
            with Image.open(image_path) as picture:
                if picture.format not in ('PNG', 'JPEG'):
                    raise ValueError('page_png_or_jpeg_required')
                media = 'image/png' if picture.format == 'PNG' else 'image/jpeg'
                picture.verify()
            data = base64.b64encode(image_path.read_bytes()).decode()
            image_x, image_y, image_width, image_height = geometry['image_box']
            parts.append(f'<image x="{image_x}" y="{image_y}" width="{image_width}" height="{image_height}" '
                         f'preserveAspectRatio="xMidYMid meet" xlink:href="data:{media};base64,{data}"/>')
            bullets(content['body'], (right_column, 208, 500, 360))
        elif layout == 'bar_chart':
            chart = content['chart']
            labels, values = validate_chart(chart)
            maximum = max(values) or 1
            for index, (label, value) in enumerate(zip(labels, values)):
                y = 200 + index * 60
                text(label, (margin, y, 230, 50), 'secondary')
                parts.append(f'<rect x="340" y="{y + 5}" width="{700 * value / maximum}" height="30" fill="{colors["accent"]}"/>')
                text(str(value), (1060, y, 130, 50), 'secondary')
            if chart.get('unit'):
                text(chart['unit'], (340, 590, 820, 40), 'secondary')
        else:
            raise ValueError('page_layout_unknown')
    if content.get('source'):
        text(content['source'], (margin, 655, 1104, 45), 'source', colors['muted'])
    parts.append('</svg>')
    raw = '\n'.join(parts).encode()
    pending = target.with_name(target.name + '.' + uuid4().hex + '.pending')
    try:
        pending.write_bytes(raw)
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError('page_source_changed_during_composition')
        if not target.exists() and expected is not None:
            raise ValueError('page_source_changed_during_composition')
        os.replace(pending, target)
    finally:
        pending.unlink(missing_ok=True)
    if content.get('notes'):
        pending_notes = notes.with_name(notes.name + '.' + uuid4().hex + '.pending')
        try:
            pending_notes.write_text(content['notes'], encoding='utf-8')
            os.replace(pending_notes, notes)
        finally:
            pending_notes.unlink(missing_ok=True)
    return {'page': str(target), 'sha256': hashlib.sha256(raw).hexdigest(), 'layout': layout,
            'representation': 'editable_svg_shapes', 'next_action': 'compose_remaining_pages_then_finalize_ppt'}


if __name__ == '__main__':
    print(json.dumps(render_page(json.loads(base64.b64decode(sys.argv[1]))), ensure_ascii=False))
