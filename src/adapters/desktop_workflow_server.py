"""Native entry to the existing scene MCP servers, never an Agent loop.

The Electron host supplies a private snapshot. This entry never receives the
original workspace path or model credentials. Public MCP schemas/validation,
semantic decision boundaries and receipt stores remain owned by each scene.
"""
from pathlib import Path
import importlib
import json
import os
import sys


def native_audit_pdf(report, target):
    """Render the already-finalized audit with the existing report engine.

    This is a fixed portable renderer, not the Linux learned-renderer package
    or its certification. It does not infer reference status or rewrite prose.
    """
    import hashlib
    import shutil
    from benchmarks.research_report_agent_v2.document_engine import build_document
    from src.adapters.paper_renderer import audit_pdf_content_coverage
    sections = []
    for key, value in report.items():
        rows = value if isinstance(value, list) else [value]
        paragraphs = [json.dumps(row, ensure_ascii=False, indent=2) if isinstance(row, (dict, list))
                      else str(row) for row in rows]
        if paragraphs:
            sections.append({'heading': key, 'paragraphs': paragraphs})
    result = build_document({'title': '参考文献与论文材料核验', 'subtitle': '本机审校报告',
                             'sections': sections, 'figures': [], 'metrics': [],
                             'requirements': {'style': 'brief', 'page_mode': 'auto', 'pages': None}},
                            target / 'layout')
    if not result['quality_passed']:
        raise ValueError('native_audit_pdf_layout_failed')
    output = target / 'reference-check-report.pdf'
    shutil.copyfile(result['path'], output)
    return {'renderer': 'existing_document_engine_native_v1',
            'renderer_motif_certified': False, 'semantic_quality_accepted': False,
            'pdf_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'content_coverage': audit_pdf_content_coverage(output, report)}


def create(kind, work):
    work = Path(work).resolve(strict=True)
    if work.name != 'work' or '.local' not in work.parts or work.is_symlink():
        raise ValueError('native_private_work_required')
    settings = json.loads((work / 'native-settings.json').read_text(encoding='utf-8'))
    inputs = work / 'inputs'
    if kind == 'paper':
        from scenarios.paper_proofreading.server import create_server
        return create_server(inputs, native_renderer=native_audit_pdf)
    if kind == 'report':
        os.environ.update(HARLESS_REPORT_WORKSPACE=str(work), HARLESS_PRIVATE_ROOT=str(work.parent))
        return importlib.import_module('scenarios.data_analysis.report_session').server
    if kind == 'general':
        from scenarios.general.runtime import create_server
        return create_server(work)
    if kind == 'ppt':
        from scenarios.research_ppt.web_scope import configure_web_scope
        configure_web_scope(work / 'job.json', work)
        from scenarios.research_ppt.delivery_server import create_server
        return create_server(work / 'job.json')
    if kind == 'skill':
        from scenarios.ppt_master.server import create_server
        sys.argv = [sys.argv[0], str(inputs)]
        return create_server()
    if kind == 'files':
        from mcp.server import MCPServer
        from mcp.types import ToolAnnotations
        # Existing module names are retained; this directory is app-owned.
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scenarios/file-management'))
        from common import digest
        from plan_tools import PlanScene
        os.environ['FM_WEB_WORKSPACE'] = str(work)
        spec = settings['file_task']
        spec['workspace'] = str(inputs)
        scene = PlanScene(spec, work / 'file-results' / (spec['task_id'] + '-' + digest(spec)[:16]))
        server = MCPServer('GeneLoop native file management')
        names = ('read_task', 'list_files', 'pin_file', 'read_file', 'hash_files', 'build_index',
                 'search_index', 'compare_snapshot', 'preview_actions', 'authorize_plan',
                 'execute_plan', 'restore_plan', 'submit_report')
        for name in names:
            server.add_tool(getattr(scene, name), name=name,
                            annotations=ToolAnnotations(readOnlyHint=name not in
                                ('build_index', 'execute_plan', 'restore_plan', 'submit_report')))
        return server
    raise ValueError('native_workflow_not_supported')


if __name__ == '__main__':
    create(sys.argv[1], Path(sys.argv[2])).run(transport='stdio')
