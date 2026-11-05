"""Inspect approved source snapshots and fill native PPTX template text."""
from pathlib import Path
from collections import Counter
import argparse
import json
import re
import shutil
import subprocess
import sys
import zipfile

from defusedxml import ElementTree
from lxml import etree

from scenarios.ppt_master.windows_delivery import attach_render_job, validate_windows_deck
from scenarios.research_ppt.documents import pptx_slide_paths, safe_zip
from scenarios.research_ppt.validation import NS, _read_package
from src.adapters.harless_attachment_text import extract_attachment

FIELD = re.compile(r'\{\{([A-Z][A-Z0-9_]{0,39})\}\}')
TEXT = '{' + NS['a'] + '}t'


def read_source(path, page):
    if path.suffix != '.pptx':
        document = extract_attachment(path, original_name=path.name)
        if document.get('status') != 'extracted':
            raise ValueError('资料中没有可用文字。')
        text = document['text']
        pages = max(1, (len(text) + 11999) // 12000)
        if not 1 <= page <= pages:
            raise ValueError('段号超出资料范围。')
        return {'text': text[(page-1)*12000:page*12000], 'pages': pages, 'locator': 'section'}
    with safe_zip(path) as archive:
        slides = pptx_slide_paths(archive)
        if not 1 <= page <= len(slides):
            raise ValueError('页码超出模板范围。')
        root = ElementTree.fromstring(archive.read(slides[page-1]))
        parts = [element.text or '' for element in root.iter(TEXT)]
        return {'text': '\n'.join(parts)[:12000], 'pages': len(slides), 'locator': 'slide',
                'fields': sorted({field for text in parts for field in FIELD.findall(text)})}


def fill_template(template, values, stage, renderer):
    if not isinstance(values, dict) or not values or len(values) > 60 or any(
            not re.fullmatch(r'[A-Z][A-Z0-9_]{0,39}', key) or not isinstance(value, str)
            or not value.strip() or len(value) > 2000 or any(ord(c) < 32 for c in value)
            or FIELD.search(value) for key, value in values.items()):
        raise ValueError('需要由字段名和单行非空文字构成的模板替换表。')
    check = {'warnings': [], 'errors': []}
    _read_package(template, check)
    if check['errors']:
        return {'mechanical_status': 'failed', 'findings': check['errors']}
    deck = stage / 'presentation.pptx'
    used = Counter()
    page_texts = []
    with safe_zip(template) as original:
        changed = {}
        for name in pptx_slide_paths(original):
            xml = original.read(name)
            root = etree.fromstring(xml, parser=etree.XMLParser(resolve_entities=False, no_network=True))
            found = False
            for element in root.iter(TEXT):
                def substitute(match):
                    key = match[1]
                    if key not in values:
                        raise ValueError('模板字段缺少内容：' + key)
                    used[key] += 1
                    return values[key]
                text = element.text or ''
                replacement = FIELD.sub(substitute, text)
                if replacement != text:
                    element.text = replacement
                    found = True
            if FIELD.search(''.join(root.itertext())):
                raise ValueError('模板字段跨多个文字段，需把完整字段置于同一文字样式段。')
            page_texts.append([item.text for item in root.iter(TEXT) if item.text and item.text.strip()])
            if found:
                changed[name] = etree.tostring(root, encoding='UTF-8', xml_declaration=True, standalone=True)
        if set(used) != set(values):
            raise ValueError('提交了模板中不存在的字段。')
        with zipfile.ZipFile(deck, 'x', compression=zipfile.ZIP_DEFLATED) as output:
            for name in original.namelist():
                output.writestr(name, changed[name] if name in changed else original.read(name))
    result = validate_windows_deck(stage, deck, page_texts, renderer, require_notes=False)
    if not result['passed']:
        return {'mechanical_status': 'failed', 'findings': result['errors']}
    pdf = next(row for row in result['artifacts'] if row['kind'] == 'pdf')
    shutil.copyfile(pdf['path'], stage / 'presentation.pdf')
    return {'mechanical_status': 'passed', 'review_status': 'pending', 'fields': dict(used),
            'changed_slide_parts': sorted(changed), 'pages': len(page_texts),
            'libreoffice_version': result['dependencies']['libreoffice_version'],
            'warnings': result['warnings'],
            'artifacts': [{'kind': 'pptx', 'path': deck.name, 'sha256': result['pptx_sha256']},
                          {**pdf, 'path': 'presentation.pdf'}]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['inspect', 'fill'])
    parser.add_argument('source', type=Path)
    parser.add_argument('--page', type=int, default=1)
    parser.add_argument('--values', type=Path)
    parser.add_argument('--renderer', type=Path)
    args = parser.parse_args()
    try:
        attach_render_job()
        if args.action == 'inspect':
            result = read_source(args.source, args.page)
        else:
            result = fill_template(args.source, json.loads(args.values.read_text(encoding='utf-8')),
                                   args.source.parent, args.renderer)
        print(json.dumps(result, ensure_ascii=True))
        return int(result.get('mechanical_status') == 'failed')
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        print(json.dumps({'mechanical_status': 'failed', 'error': str(error)}, ensure_ascii=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
