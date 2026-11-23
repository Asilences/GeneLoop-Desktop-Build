"""Native substrate for the existing general MCP; Web source stays byte-stable."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from src.adapters.session_files import SessionFiles


def verify_native_ocr():
    root = Path(os.environ['GENELOOP_PDF_OCR_ROOT'])
    expected = {'eng': '7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2',
                'chi_sim': 'a5fcb6f0db1e1d6d8522f39db4e848f05984669172e584e8d76b6b3141e1f730'}
    for name, digest in expected.items():
        item = root / 'tessdata' / (name + '.traineddata')
        if item.is_symlink() or not item.is_file() or hashlib.sha256(item.read_bytes()).hexdigest() != digest:
            raise ValueError('native_ocr_data_version_changed')
    return True


def create_server(work):
    from scenarios.general.runtime import create_server as original
    work = Path(work).resolve()
    server = original(work)
    files = SessionFiles(work / 'inputs')
    runner = [os.environ['SSS_PPT_NODE_EXECUTABLE'], os.environ['GENELOOP_NATIVE_CODE_RUNNER']]
    child_env = {name: os.environ[name] for name in ('PATH', 'SystemRoot', 'SYSTEMROOT', 'WINDIR') if name in os.environ}
    child_env.update(ELECTRON_RUN_AS_NODE='1', HOME=str(work), USERPROFILE=str(work),
                     TEMP=str(work), TMP=str(work), TMPDIR=str(work))

    def runtime_capabilities() -> dict:
        """Probe actual native code and pinned OCR dependencies; never infer model image support."""
        try:
            probe = subprocess.run([*runner, '--capabilities'], env=child_env, capture_output=True, timeout=15)
            code = probe.returncode == 0 and json.loads(probe.stdout).get('available') is True
        except (OSError, subprocess.SubprocessError, ValueError): code = False
        try:
            import pymupdf
            ocr = verify_native_ocr()
        except (ImportError, OSError, ValueError, KeyError): ocr = False
        return {'code': {'available': code, 'language': 'typescript/javascript', 'network': False,
                         'isolation': 'QuickJS WASM', 'cpu_ms': 10000, 'wall_ms': 75000, 'memory_mib': 64},
                'content_editing': {'available': True, 'scope': 'new output versions; source files remain unchanged'},
                'ocr': {'available': ocr, 'provider': 'PyMuPDF + pinned tessdata'},
                'vision': {'available': None, 'provider': 'DSH native attachments',
                           'requirement': 'Active model image capability is checked by the DSH host.'},
                'inputs': files.list_files()}

    def execute_code(program: str) -> dict:
        """Run isolated TypeScript/JavaScript in QuickJS WASM, without host APIs or network.
        Use inputs.list/read_text/read_base64, outputs.write_text, and console.log.
        Inputs are approved snapshots; outputs are new text files only.
        """
        if len(program.encode()) > 256*1024: raise ToolError('code program exceeds 256KiB')
        grant = work / 'general-task.json'
        allowed = grant.is_file() and json.loads(grant.read_text()).get('allow_output') is True
        try:
            result = subprocess.run(runner, input=json.dumps({'workspace': str(work), 'program': program, 'allow_output': allowed}),
                                    text=True, capture_output=True, timeout=75, env=child_env)
        except (OSError, subprocess.SubprocessError) as error:
            raise ToolError('native code runtime unavailable: ' + type(error).__name__) from error
        if result.returncode: raise ToolError('isolated code execution failed: ' + result.stderr[-1200:])
        output = json.loads(result.stdout)
        output['status'] = 'execution_failed' if output['result'].get('error') else 'completed'
        return output

    for function in (runtime_capabilities, execute_code):
        server.remove_tool(function.__name__)
        server.add_tool(function, annotations=ToolAnnotations(readOnlyHint=function==runtime_capabilities,
                                                             destructiveHint=False, openWorldHint=False))
    return server
