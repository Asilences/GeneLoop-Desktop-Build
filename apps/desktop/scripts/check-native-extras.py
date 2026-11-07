"""One compact offline tool check. No chat model calls or user files."""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

bundle = Path(sys.argv[1]).resolve(strict=True)
work = Path(tempfile.mkdtemp(prefix='geneloop-complete-tools-')).resolve()
(work / 'projects').mkdir()
scripts = bundle / 'ppt-master/scripts'
sys.path[:0] = [str(bundle / 'source'), str(scripts), str(scripts / 'source_to_md')]
os.environ.update(GENELOOP_NATIVE_SKILL_RUNTIME='1', GENELOOP_PPT_MASTER_ROOT=str(scripts.parent),
                  GENELOOP_NATIVE_WORKSPACE=str(work), RL_renderPMBackend='_renderPM',
                  TIKTOKEN_CACHE_DIR=str(bundle / 'python-data/tiktoken'),
                  PLAYWRIGHT_BROWSERS_PATH=str(bundle / 'chromium'),
                  GENELOOP_NATIVE_SOFFICE=str(bundle / ('libreoffice/program/soffice.com' if sys.platform == 'win32' else 'libreoffice/Contents/MacOS/soffice')))
from src.adapters.desktop_skill_runtime import install
install()
checks = []
modules = ['pathops','uharfbuzz','edge_tts','mammoth','markdownify','ebooklib','nbconvert','nbformat',
           'openpyxl','requests','bs4','curl_cffi','google.genai','flask','playwright','tiktoken','svglib','_rl_renderPM']
for name in modules:
    importlib.import_module(name)
checks.append('optional_python_imports_' + str(len(modules)))
import config
import project_management.paths as project_paths
assert config.PROJECTS_DIR == work / 'projects' and project_paths.PROJECTS_ROOT == work / 'projects'
checks.append('skill_output_roots_private')
import doc_to_md
source = work / 'source.rtf'
source.write_text(r'{\rtf1\ansi GeneLoop native source conversion.}', encoding='ascii')
text = doc_to_md._convert_with_pandoc(source, work / 'source.md', '.rtf')
assert 'GeneLoop' in text
checks.append('office_legacy_document_conversion')
pandoc = bundle / ('extras/pandoc/pandoc.exe' if sys.platform == 'win32' else 'extras/pandoc/pandoc')
result = subprocess.run([str(pandoc), '-f', 'rst', '-t', 'html'], input=b'GeneLoop\n========\n\nNative source.', stdout=subprocess.PIPE, check=True)
assert b'Native source' in result.stdout
checks.append('pandoc_rst_conversion')
from io import BytesIO
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPM
drawing = svg2rlg(BytesIO(b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="30"><rect width="40" height="30" fill="blue"/></svg>'))
assert renderPM.drawToString(drawing, fmt='PNG').startswith(b'\x89PNG')
checks.append('svg_native_raster_fallback')
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    page = browser.new_page()
    page.set_content('<h1>GeneLoop</h1>')
    assert page.screenshot().startswith(b'\x89PNG')
    browser.close()
checks.append('shared_chromium_actual_screenshot')
import tiktoken
assert tiktoken.get_encoding('o200k_base').encode('GeneLoop')
checks.append('offline_tokenizer_cache')
ffmpeg = bundle / ('ffmpeg/ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg/ffmpeg')
result = subprocess.run([str(ffmpeg), '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.2',
                         '-af', 'loudnorm,afade=t=out:st=0.1:d=0.1', '-y', str(work / 'audio.wav')], check=True)
assert (work / 'audio.wav').stat().st_size > 1000
checks.append('ffmpeg_audio_filters')
# The isolated profile deliberately pins NumPy 1.26 for Intel Torch. Never
# import it into the main data-analysis interpreter (NumPy 2.2).
speech = bundle / 'speech'
assert (speech / 'provenance.json').is_file()
subprocess.run([sys.executable, '-B', '-c',
    'import sys;sys.path.insert(0,sys.argv[1]);import stable_whisper;'
    'model=stable_whisper.load_model("base",device="cpu",download_root=sys.argv[2]);'
    'assert model.is_multilingual;print("offline_cpu_alignment_model_loaded")',
    str(speech / 'site'), str(speech / 'cache/whisper')], check=True, timeout=120)
checks.append('offline_whisper_base_cpu')
from src.adapters.desktop_native_providers import NativeGateway
private = work / '.local/turn/work'
private.mkdir(parents=True)
(private / 'public.json').write_text('{"format":"sss-general-tools-v1","providers":[]}', encoding='utf-8')
import base64
os.environ['GENELOOP_NATIVE_PROVIDER_CONFIG'] = base64.b64encode(json.dumps({
    'format':'sss-general-tools-v1', 'providers':[{'id':'native-diagnostic','transport':'stdio',
    'command':'${PYTHON}', 'args':[], 'policy':'read_only','cost':'local_no_model'}],
    'credentials':{'DIAGNOSTIC_SECRET':'synthetic-not-a-real-credential'}}).encode()).decode()
gateway = NativeGateway(private, {}, private_root=private.parent, public_registry=private / 'public.json', config=private / 'absent.json')
assert gateway.providers()['native-diagnostic']['command'] == '${PYTHON}'
assert gateway.bound({'from_env':'DIAGNOSTIC_SECRET'}) == 'synthetic-not-a-real-credential'
assert 'GENELOOP_NATIVE_PROVIDER_CONFIG' not in os.environ
assert not any('synthetic-not-a-real-credential' in p.read_text(errors='ignore') for p in private.rglob('*.json'))
checks.append('private_provider_registry_and_credential_separation')
print(json.dumps({'kind':'native_optional_tools_offline_diagnostic','platform':sys.platform,
                  'model_api_requests':0,'checks':checks,'quality_acceptance':False}, ensure_ascii=False))
