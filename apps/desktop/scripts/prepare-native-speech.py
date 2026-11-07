"""Build the optional upstream subtitle aligner into an isolated CPU profile."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import urllib.request

destination = Path(sys.argv[1]).resolve()
if destination.name != 'speech' or not (destination.parent / '.geneloop-tools').is_file():
    raise ValueError('expected generated desktop speech directory')
site = destination / 'site'
site.mkdir(parents=True, exist_ok=True)
wheelhouse = destination.parent.parent / '.local' / 'speech-wheels'
wheelhouse.mkdir(parents=True, exist_ok=True)
build_python = os.environ.get('GENELOOP_BUILD_PYTHON', sys.executable)
subprocess.run([build_python, '-m', 'pip', 'wheel', '--index-url', 'https://pypi.org/simple',
                '--no-deps', '--wheel-dir', str(wheelhouse), 'stable-ts==2.19.1',
                'openai-whisper==20250625'], check=True)
intel_mac = sys.platform == 'darwin' and platform.machine() == 'x86_64'
windows = sys.platform == 'win32'
torch = '2.2.2' if intel_mac else '2.8.0'
cpu = '+cpu' if windows else ''
args = [sys.executable, '-B', '-m', 'pip', 'install', '--index-url', 'https://pypi.org/simple',
        '--only-binary=:all:', '--find-links', str(wheelhouse), '--target', str(site),
        'torch==' + torch + cpu, 'torchaudio==' + torch + cpu, 'numpy==1.26.4',
        'stable-ts==2.19.1', 'openai-whisper==20250625']
if windows:
    args += ['--extra-index-url', 'https://download.pytorch.org/whl/cpu']
# The embedded Windows distribution has no pip; the build host may provide it.
pip_source = os.environ.get('GENELOOP_BUILD_PIP_PATH')
if pip_source:
    args = [sys.executable, '-B', '-c',
            'import sys;sys.path.append(sys.argv.pop(1));from pip._internal.cli.main import main;raise SystemExit(main())',
            pip_source, *args[4:]]
subprocess.run(args, check=True)
sys.path.insert(0, str(site))
import whisper
url = whisper._MODELS['base']
expected = url.split('/')[-2]
model_dir = destination / 'cache' / 'whisper'
model_dir.mkdir(parents=True, exist_ok=True)
model = model_dir / 'base.pt'
if not model.exists():
    urllib.request.urlretrieve(url, model)
actual = hashlib.file_digest(model.open('rb'), 'sha256').hexdigest()
if actual != expected:
    raise ValueError('upstream Whisper base model checksum mismatch')
packages = sorted(({'name': d.metadata['Name'], 'version': d.version}
                   for d in importlib.metadata.distributions(path=[str(site)])), key=lambda d: d['name'].lower())
(destination / 'provenance.json').write_text(json.dumps({
    'platform': sys.platform, 'arch': platform.machine(), 'device': 'cpu',
    'packages': packages, 'model': {'name': 'base', 'url': url, 'sha256': actual},
    'algorithm': 'upstream stable-ts forced alignment; no generated timestamps'
}, indent=2) + '\n', encoding='utf-8')
