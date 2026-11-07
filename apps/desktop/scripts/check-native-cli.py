"""Targeted regression for the unified Skill CLI, without rebuilding tools."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

bundle = Path(sys.argv[1]).resolve(strict=True)
work = Path(tempfile.mkdtemp(prefix='geneloop-cli-')).resolve()
(work / 'projects').mkdir()
source = work / '本机材料.docx'
with zipfile.ZipFile(source, 'w') as doc:
    doc.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    doc.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    doc.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>GeneLoop native CLI route.</w:t></w:r></w:p></w:body></w:document>')
python = bundle / ('python/python.exe' if sys.platform == 'win32' else 'python/bin/geneloop-python')
if not python.exists():
    python = Path(sys.executable)
env = {**os.environ, 'PYTHONPATH': str(bundle / 'source'), 'PYTHONDONTWRITEBYTECODE':'1',
       'GENELOOP_PPT_MASTER_ROOT':str(bundle / 'ppt-master'), 'GENELOOP_NATIVE_SKILL_RUNTIME':'1',
       'GENELOOP_NATIVE_WORKSPACE':str(work)}
subprocess.run([str(python), '-B', str(bundle / 'source/src/adapters/desktop_python_entry.py'),
                str(bundle / 'ppt-master/scripts/source_to_md.py'), str(source), '-o', str(work / 'out.md'), '--json'],
               env=env, check=True, timeout=60)
assert 'GeneLoop native CLI route' in (work / 'out.md').read_text(encoding='utf-8')
print(json.dumps({'kind':'native_unified_cli_actual_docx_conversion','platform':sys.platform,'passed':True,'model_requests':0}))
