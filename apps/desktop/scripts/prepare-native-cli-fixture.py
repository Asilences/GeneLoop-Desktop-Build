"""Fetch only locked scripts for a small cross-platform CLI regression."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

app = Path(__file__).resolve().parents[1]
repo = app.parents[1]
bundle = app / '.local/cli-tools'
bundle.mkdir(parents=True, exist_ok=True)
archive = bundle / 'skill.tar.gz'
commit = '440557b8dc7c7257b69c04a0b014d5c50a78e6cb'
subprocess.run(['curl', '--fail', '--location', '--retry', '2', '--output', str(archive),
                'https://codeload.github.com/hugohe3/ppt-master/tar.gz/' + commit], check=True)
assert hashlib.sha256(archive.read_bytes()).hexdigest() == '080565fa68ab0cf4c8f75dbb3e0095a8ddd636298766bea394a9daf21c94de4d'
lock = json.loads((repo / 'scenarios/ppt_master/skill-lock.json').read_text())
prefix = 'ppt-master-' + commit + '/skills/ppt-master/'
with tarfile.open(archive) as tar:
    for member in tar:
        if not member.isfile() or not member.name.startswith(prefix + 'scripts/'):
            continue
        relative = member.name[len(prefix):]
        if relative not in lock['files'] or '..' in Path(relative).parts:
            continue
        data = tar.extractfile(member).read()
        assert hashlib.sha256(data).hexdigest() == lock['files'][relative]
        target = bundle / 'ppt-master' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
for name in ['desktop_python_entry.py', 'desktop_skill_runtime.py']:
    target = bundle / 'source/src/adapters' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(repo / 'src/adapters' / name, target)
target = bundle / 'source/scenarios/ppt_master/skill-lock.json'
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(repo / 'scenarios/ppt_master/skill-lock.json', target)
subprocess.run([sys.executable, '-B', str(app / 'scripts/check-native-cli.py'), str(bundle)], check=True)
