import json
from pathlib import Path
import tempfile
import unittest

from scenarios.agentic_vbench.preflight import audit_native_trace, inspect_task


class AgenticVBenchPreflightTests(unittest.TestCase):
    def test_official_step_timeout_and_variable_storyboard_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory)/'agentic_vbench_assembly'/'example'
            (task/'steps/solve').mkdir(parents=True)
            (task/'environment').mkdir()
            (task/'task.toml').write_text('[[steps]]\nname="solve"\n[steps.agent]\ntimeout_sec=1800\n')
            (task/'steps/solve/instruction.md').write_text(
                '### Slot 1\n### Slot 2\n### Slot 3\n'
                '/workspace/output/solution.mp4 /workspace/output/solution.json')
            (task/'environment/Dockerfile').write_text('RUN apt-get install ffmpeg')
            result = inspect_task(task)
            self.assertEqual(result['storyboard_slots'], 3)
            self.assertEqual(result['agent']['timeout_sec'], 1800)
            self.assertEqual(result['deliverables'], ['/workspace/output/solution.json', '/workspace/output/solution.mp4'])
            # No tests/ or oracle was needed or read.

    def test_successful_process_program_remains_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'native-tools.jsonl'
            path.write_text(json.dumps({'phase': 'finished', 'name': 'execute', 'call_id': 'one',
                'arguments': {'command': "python3 - <<'PY'\nimport subprocess\nsubprocess.run(['ffmpeg','-version'])\nPY"},
                'result': {'returncode': 0}})+'\n')
            report = audit_native_trace(path)
            program = report['programs'][0]
            self.assertEqual(program['status'], 'extracted')
            self.assertEqual(program['script']['reason'], 'import_not_admitted')
            self.assertEqual(program['artifact']['reason'], 'program_import_not_admitted')
            self.assertIsNone(report['certified_capabilities'])

    def test_shell_and_failed_calls_are_not_invented_python_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'native-tools.jsonl'
            rows = [{'phase': 'finished', 'name': 'execute', 'call_id': str(i),
                     'arguments': {'command': command}, 'result': {'returncode': rc}}
                    for i, (command, rc) in enumerate([('ffmpeg -version', 0), ('python3 missing.py', 2)])]
            path.write_text('\n'.join(json.dumps(row) for row in rows))
            report = audit_native_trace(path)
            self.assertEqual([p['status'] for p in report['programs']],
                             ['not_extracted', 'original_execution_failed'])


if __name__ == '__main__':
    unittest.main()
