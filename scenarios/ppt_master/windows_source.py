"""Inspect approved source snapshots and fill native PPTX template text."""
from pathlib import Path
from collections import Counter
import argparse
import hashlib
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
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'


def text_shapes(root):
    for shape in root.iter('{'+P+'}sp'):
        identifier = shape.find('./{'+P+'}nvSpPr/{'+P+'}cNvPr')
        body = shape.find('{'+P+'}txBody')
        if identifier is not None and body is not None:
            text = '\n'.join(''.join(node.text or '' for node in paragraph.iter(TEXT))
                             for paragraph in body.findall('{'+NS['a']+'}p'))
            yield identifier.get('id'), body, text


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
                'shapes': [{'shape_id': identifier, 'text': text,
                            'text_sha256': hashlib.sha256(text.encode()).hexdigest()}
                           for identifier, _, text in text_shapes(root)],
                'fields': sorted({field for text in parts for field in FIELD.findall(text)})}


def edit_template(template, edits, stage, renderer):
    """按实际页序与形状 ID 修改副本，保留未编辑的 ZIP 部件。"""
    if not isinstance(edits, list) or not 1 <= len(edits) <= 60:
        raise ValueError('需要 1–60 项文本框修改。')
    planned = {}
    for edit in edits:
        if (not isinstance(edit, dict) or set(edit) != {'page', 'shape_id', 'before_sha256', 'text'}
                or type(edit['page']) is not int or edit['page'] < 1
                or not isinstance(edit['shape_id'], str) or not edit['shape_id'].isdigit()
                or not isinstance(edit['before_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', edit['before_sha256'])
                or not isinstance(edit['text'], str) or not edit['text'].strip() or len(edit['text']) > 2000
                or any(ord(c) < 32 and c != '\n' for c in edit['text'])):
            raise ValueError('修改需要页号、形状 ID、原文字摘要和非空新文字。')
        key = (edit['page'], edit['shape_id'])
        if key in planned:
            raise ValueError('同一文本框不能重复修改。')
        planned[key] = edit
    check = {'warnings': [], 'errors': []}
    _read_package(template, check)
    if check['errors']:
        return {'mechanical_status': 'failed', 'findings': check['errors']}
    deck, changed, page_texts, used = stage/'presentation.pptx', {}, [], set()
    with safe_zip(template) as original:
        for page, name in enumerate(pptx_slide_paths(original), 1):
            root = etree.fromstring(original.read(name), parser=etree.XMLParser(resolve_entities=False, no_network=True))
            for identifier, body, text in text_shapes(root):
                key = (page, identifier)
                if key not in planned:
                    continue
                if key in used or hashlib.sha256(text.encode()).hexdigest() != planned[key]['before_sha256']:
                    raise ValueError('原文字摘要变化或文本框不唯一，请重新读取模板。')
                used.add(key)
                # 复用原有文字段的字体/样式，保留形状、母版、位置及主题。
                paragraphs = body.findall('{'+NS['a']+'}p')
                template_run = next((run for paragraph in paragraphs for run in paragraph.findall('{'+NS['a']+'}r')), None)
                import copy
                for paragraph in paragraphs:
                    body.remove(paragraph)
                for line in planned[key]['text'].split('\n'):
                    paragraph = etree.SubElement(body, '{'+NS['a']+'}p')
                    if paragraphs:
                        props = paragraphs[0].find('{'+NS['a']+'}pPr')
                        if props is not None:
                            paragraph.append(copy.deepcopy(props))
                    run = copy.deepcopy(template_run) if template_run is not None else etree.Element('{'+NS['a']+'}r')
                    for node in list(run):
                        if node.tag != '{'+NS['a']+'}rPr':
                            run.remove(node)
                    etree.SubElement(run, TEXT).text = line
                    paragraph.append(run)
                changed[name] = etree.tostring(root, encoding='UTF-8', xml_declaration=True, standalone=True)
            page_texts.append([node.text for node in root.iter(TEXT) if node.text and node.text.strip()])
        if used != set(planned):
            raise ValueError('找不到指定页的文本框。')
        with zipfile.ZipFile(deck, 'x', compression=zipfile.ZIP_DEFLATED) as output:
            for name in original.namelist():
                output.writestr(name, changed.get(name, original.read(name)))
    result = validate_windows_deck(stage, deck, page_texts, renderer, require_notes=False)
    if not result['passed']:
        return {'mechanical_status': 'failed', 'findings': result['errors']}
    pdf = next(row for row in result['artifacts'] if row['kind'] == 'pdf')
    shutil.copyfile(pdf['path'], stage/'presentation.pdf')
    return {'mechanical_status': 'passed', 'review_status': 'pending', 'pages': len(page_texts),
            'changed_slide_parts': sorted(changed), 'text_shapes_edited': len(used),
            'artifacts': [{'kind': 'pptx', 'path': deck.name, 'sha256': result['pptx_sha256']},
                          {**pdf, 'path': 'presentation.pdf'}]}


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
    parser.add_argument('action', choices=['inspect', 'fill', 'edit'])
    parser.add_argument('source', type=Path)
    parser.add_argument('--page', type=int, default=1)
    parser.add_argument('--values', type=Path)
    parser.add_argument('--renderer', type=Path)
    args = parser.parse_args()
    try:
        attach_render_job()
        if args.action == 'inspect':
            result = read_source(args.source, args.page)
        elif args.action == 'fill':
            result = fill_template(args.source, json.loads(args.values.read_text(encoding='utf-8')),
                                   args.source.parent, args.renderer)
        else:
            result = edit_template(args.source, json.loads(args.values.read_text(encoding='utf-8')),
                                   args.source.parent, args.renderer)
        print(json.dumps(result, ensure_ascii=True))
        return int(result.get('mechanical_status') == 'failed')
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        print(json.dumps({'mechanical_status': 'failed', 'error': str(error)}, ensure_ascii=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
