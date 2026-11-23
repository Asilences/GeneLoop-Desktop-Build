"""Prepare the bundled GeneLoop presentation Skill for a CLI-only regression."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

app = Path(__file__).resolve().parents[1]
repo = app.parents[1]
sys.path.insert(0, str(repo))
from scenarios.ppt_master.package import prepare_bundled_resources, runtime_lock

bundle = app / '.local/cli-tools'
bundle.mkdir(parents=True, exist_ok=True)
resources = prepare_bundled_resources()
lock = runtime_lock(resources)
for name in lock['files']:
    target = bundle / 'ppt-master' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(resources / name, target)
(bundle / 'ppt-master-desktop-lock.json').write_text(
    json.dumps(lock, ensure_ascii=True, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
for name in ['desktop_python_entry.py', 'desktop_skill_runtime.py']:
    target = bundle / 'source/src/adapters/desktop' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(repo / 'src/adapters/desktop' / name, target)
subprocess.run([sys.executable, '-B', str(app / 'scripts/check-native-cli.py'), str(bundle)], check=True)
