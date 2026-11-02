"""Run offline Capability and efficiency-study regressions; makes no model calls."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
env = {**os.environ, 'SSS_PYTHON': sys.executable}

commands = [
    [sys.executable, '-m', 'pytest', '-q',
     'tests/test_capability_contract.py',
     'tests/test_capability_builder.py', 'tests/test_capability_authoring.py',
     'tests/test_source_program_bridge.py',
     'tests/test_capability_proposal_loop.py', 'tests/test_source_capability_worker.py',
     'tests/test_capability_output_verifier.py',
     'tests/test_capability_improvement.py',
     'tests/test_capability_container_compat.py',
     'tests/test_efficiency_rsi_measurement.py',
     'tests/test_rsi_protocol.py', 'tests/test_rsi_quality.py'],
    ['node', '--test', 'tests/test_capability_contract.mjs',
     'tests/test_capability_runtime.mjs', 'tests/test_rsi_protocol.mjs',
     'tests/test_capability_store.mjs', 'tests/test_source_capability_runtime.mjs',
     'tests/test_rsi_native_harness.mjs', 'tests/test_source_programs.mjs'],
]

for command in commands:
    subprocess.run(command, cwd=ROOT, env=env, check=True)

print('效率 RSI 离线检查完成；模型请求 0，不代表真实任务质量或效率收益。')
