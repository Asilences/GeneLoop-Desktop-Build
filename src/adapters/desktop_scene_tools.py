"""桌面固定工具：只处理宿主已复制的快照，不执行用户代码或公式。"""
from pathlib import Path
import argparse
import csv
import hashlib
import io
import json
import re
import zipfile

from src.adapters.harless_attachment_text import extract_attachment, _archive, _xml, _relationships, S, R
from src.adapters.paper_static_checks import source_diagnostics
from scenarios.data_analysis.table_inputs import extract_tables
from scenarios.data_analysis.evidence import DatasetEvidence


def workbook_tables(path):
    """复用 OOXML 路径/XML 守卫，保留空单元格；不计算公式。"""
    tables = []
    with _archive(path.read_bytes()) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            root = _xml(archive.read('xl/sharedStrings.xml'))
            strings = [''.join(n.text or '' for n in item.iter('{'+S+'}t')) for item in root]
        relations = _relationships(archive, 'xl/workbook.xml')
        workbook = _xml(archive.read('xl/workbook.xml'))
        for sheet in workbook.find('{'+S+'}sheets'):
            part = relations.get(sheet.get('{'+R+'}id'))
            if not part or not part.startswith('xl/worksheets/'):
                raise ValueError('workbook_sheets_unavailable')
            rows, formulas = [], 0
            for row in _xml(archive.read(part)).iterfind('.//{'+S+'}sheetData/{'+S+'}row'):
                values = {}
                for cell in row.findall('{'+S+'}c'):
                    match = re.fullmatch(r'([A-Z]{1,3})[1-9][0-9]*', cell.get('r', ''))
                    if not match:
                        raise ValueError('invalid_cell_address')
                    index = 0
                    for letter in match[1]:
                        index = index*26 + ord(letter)-64
                    if index > 128 or index in values:
                        raise ValueError('table_column_limit_or_duplicate_cell')
                    value = cell.find('{'+S+'}v')
                    text = value.text or '' if value is not None else ''
                    inline = cell.find('{'+S+'}is')
                    if cell.find('{'+S+'}f') is not None:
                        formulas += 1
                        # 缓存可能过期，统计工具拒绝把它当成观察值。
                        raise ValueError('table_contains_formulas_use_explicit_values')
                    if cell.get('t') == 's':
                        text = strings[int(text)]
                    elif inline is not None:
                        text = ''.join(n.text or '' for n in inline.iter('{'+S+'}t'))
                    if cell.get('t') in ('e', 'b'):
                        raise ValueError('table_error_or_boolean_cell')
                    values[index] = text
                if values:
                    rows.append(values)
                if len(rows) > 100001:
                    raise ValueError('dataset_row_limit')
            if rows:
                width = max(max(row) for row in rows)
                normalized = [[row.get(i, '') for i in range(1, width+1)] for row in rows]
                stream = io.StringIO(newline='')
                csv.writer(stream, lineterminator='\n').writerows(normalized)
                tables.append({'name': sheet.get('name', ''), 'csv': stream.getvalue()})
    return tables


def tables_for(path):
    if path.suffix.lower() == '.xlsx':
        return workbook_tables(path)
    document = extract_attachment(path, original_name=path.name)
    if document.get('status') != 'extracted':
        raise ValueError('no_extractable_table')
    return [{'name': str(index+1), 'csv': table}
            for index, table in enumerate(extract_tables(path, document))]


def dataset(path, plan):
    tables = tables_for(path)
    index = plan.get('table', 1)
    if not isinstance(index, int) or isinstance(index, bool) or not 1 <= index <= len(tables):
        raise ValueError('choose_existing_explicit_table')
    value = tables[index-1]
    normalized = path.parent/'normalized.csv'
    normalized.write_text(value['csv'], encoding='utf-8', newline='')
    files = DatasetEvidence(path.parent)
    version = hashlib.sha256(normalized.read_bytes()).hexdigest()
    source = files.pin(normalized.name, version)['source_id']
    summary = files.summary(source)
    result = {'table': index, 'table_name': value['name'], 'tables': len(tables), 'summary': summary}
    x, y = plan.get('x', ''), plan.get('y', '')
    if x or y:
        result['correlation'] = files.correlation(source, x, y)
    if plan.get('export'):
        result['csv'] = value['csv']
    return result


def run(action, source, plan):
    if action == 'tables':
        result = []
        for index, table in enumerate(tables_for(source)):
            rows = list(csv.reader(io.StringIO(table['csv'])))
            result.append({'table': index+1, 'name': table['name'], 'rows': len(rows)-1,
                           'columns': rows[0], 'preview': rows[1:4]})
        return {'tables': result, 'scope': 'literal_cells_only_no_formula_execution_or_inferred_data'}
    if action == 'data':
        return dataset(source, plan)
    if action == 'paper':
        bbl = (source/plan['bbl']).read_text(encoding='utf-8') if plan.get('bbl') else None
        return source_diagnostics(source, plan['main'], bbl)
    if action == 'archive':
        output = source.parent/'collection.zip'
        with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            for row in plan['files']:
                archive.write(source.parent/row['source'], row['target'])
        return {'path': output.name, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}
    raise ValueError('unsupported_desktop_action')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['tables', 'data', 'paper', 'archive'])
    parser.add_argument('source', type=Path)
    parser.add_argument('plan', type=Path)
    args = parser.parse_args()
    try:
        result = run(args.action, args.source, json.loads(args.plan.read_text(encoding='utf-8')))
    except (OSError, ValueError, KeyError, IndexError, TypeError, zipfile.BadZipFile) as error:
        code = str(error)
        result = {'error': code if re.fullmatch(r'[a-z_]{1,80}', code) else 'invalid_or_incomplete_source'}
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))


if __name__ == '__main__':
    main()
