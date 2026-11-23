"""Discover read-only script templates from successful native Bash observations.

Static admission is deliberately conservative; it is NOT a sandbox. Certification
and execution must also use the existing Linux namespace sandbox, with no network
and no persistent writable mounts. No source is executed in this compiler.
"""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
import re
import shlex
import posixpath

VERSION = 1
IMPORTS = {'json', 're', 'collections', 'pathlib', 'zipfile', 'hashlib', 'math',
           'statistics', 'itertools', 'csv', 'io', 'unicodedata', 'sys', 'posixpath',
           'urllib.request', 'urllib.parse', 'xml.etree.ElementTree', 'time'}
FORBIDDEN = {'eval', 'exec', 'compile', '__import__', 'getattr', 'setattr', 'delattr',
             'globals', 'locals', 'vars', 'input', 'breakpoint', 'exit', 'quit',
             'write', 'writelines', 'write_text', 'write_bytes', 'unlink', 'rename',
             'mkdir', 'rmdir', 'touch', 'extract', 'extractall', 'chdir'}

def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()

def digest(value):
    return sha(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')))


def script_reject(reason,node,source,space='executable_source'):
    error=ValueError(reason);line=getattr(node,'lineno',None);rows=source.splitlines()
    error.script_diagnostics={'kind':'script_admission','error':reason,'source_space':space,
        'line':line,'column':getattr(node,'col_offset',None),
        'source_line':rows[line-1] if line and line<=len(rows) else None}
    raise error

def virtual_host(workspace, virtual):
    if not virtual.startswith('/work/'):
        raise ValueError('script_outside_workspace')
    relative = virtual.removeprefix('/work/')
    if relative.startswith('inputs/'):
        return Path(workspace) / relative
    if relative.startswith('outputs/'):
        return Path(workspace) / 'outputs/code' / relative.removeprefix('outputs/')
    return Path(workspace) / 'code' / relative


def extract(command, workspace=None):
    """Extract one interpreter, retaining admission for a fixed input checksum."""
    cwd = '/work'
    prefix = re.match(r'^\s*cd\s+(\S+|\x27[^\x27]+\x27|"[^"]+")\s*&&\s*', command)
    if prefix:
        cwd = shlex.split(prefix.group(1))[0]; command = command[prefix.end():]
    # Native agents commonly checksum an input immediately before a heredoc.
    # Only this read of one fixed input is separable; arbitrary shell prefixes,
    # pipelines, expansion, options and output redirection remain rejected.
    checksum_path = None
    checksum = re.match(r'^sha256sum[ \t]+([^\n]*?)[ \t]*&&[ \t]*', command)
    if checksum:
        tokens = shlex.split(checksum.group(1))
        if (workspace is None or len(tokens) != 1 or tokens[0].startswith('-') or
                any(c in tokens[0] for c in '$`\\;|&<>*?[]{}~\r\n')):
            raise ValueError('script_checksum_fixed_input_required')
        checksum_path = posixpath.normpath(posixpath.join(cwd, tokens[0]))
        path = virtual_host(workspace, checksum_path)
        if (not path.is_file() or path.is_symlink() or
                not path.resolve().is_relative_to(Path(workspace).resolve())):
            raise ValueError('script_checksum_fixed_input_required')
        command = command[checksum.end():]
    def check_checksum_binding(source):
        if checksum_path is not None and not any(
                isinstance(node, ast.Constant) and isinstance(node.value, str) and
                posixpath.normpath(posixpath.join(cwd, node.value)) == checksum_path
                for node in ast.walk(ast.parse(source))):
            raise ValueError('script_checksum_input_not_bound')
    # A real Agent often saves code and invokes it later. Admit only an exact
    # single-file heredoc followed by that interpreter call, never arbitrary shell.
    saved = re.fullmatch(r"cat\s*>\s*(?P<path>\S+)\s*<<(?P<quote>['\"]?)(?P<delimiter>\w+)(?P=quote)\n(?P<body>.*?)\n(?P=delimiter)\n(?P<invocation>python3?\s+[^\n]+)", command.strip(), re.S)
    declared = None
    if saved:
        declared = (saved.group('path'), saved.group('body'))
        if not saved.group('quote') and re.search(r"[$`\\]",declared[1]):
            raise ValueError('script_heredoc_expansion_requires_evidence')
        command = saved.group('invocation')
        invocation = shlex.split(command)
        if len(invocation)>=2 and invocation[0] in ('python','python3') and invocation[1]==declared[0] and not any(p in {'|',';','&&','||','>','2>&1'} for p in invocation):
            if workspace:
                virtual=posixpath.normpath(posixpath.join(cwd,invocation[1]))
                if re.fullmatch(r'/tmp/[A-Za-z0-9_.-]+\.py',invocation[1]):
                    # Exact current-command bytes only. Never read a host /tmp
                    # path or promote an arbitrary previously saved temp file.
                    pass
                else:
                    if not virtual.startswith('/work/'):raise ValueError('script_outside_workspace')
                    path=virtual_host(workspace,virtual)
                    if path.is_symlink() or not path.resolve().is_relative_to(Path(workspace).resolve()):raise ValueError('script_source_not_fixed')
                    # Existing saved bytes still have to agree. A newly declared
                    # source may be absent from the native pre-call snapshot.
                    if path.exists() and path.read_bytes().decode('utf-8').strip()!=declared[1].strip():raise ValueError('saved_source_changed')
            # This source is created by the current command; it cannot exist in
            # the pre-call snapshot. Its bytes are witnessed by native arguments.
            check_checksum_binding(declared[1])
            return cwd, declared[1], invocation[2:], sha(declared[1])
    match = re.fullmatch(r"\s*python(?:3)?\s+(?:-\s*)?<<\s*(?P<quote>['\"]?)(?P<delimiter>[A-Za-z_]\w*)(?P=quote)[ \t]*\n(?P<body>.*?)\n(?P=delimiter)[ \t]*\s*", command, re.S)
    if match:
        source=match.group('body')
        if not match.group('quote') and re.search(r"[$`\\]",source):
            raise ValueError('script_heredoc_expansion_requires_evidence')
        check_checksum_binding(source)
        return cwd, source
    if checksum_path is not None:
        raise ValueError('script_checksum_heredoc_required')
    parts = shlex.split(command)
    if len(parts) == 3 and parts[0] in ('python', 'python3') and parts[1] == '-c':
        return cwd, parts[2]
    if workspace and len(parts)>=2 and parts[0] in ('python','python3') and parts[1].endswith('.py'):
        if any(p in {'|',';','&&','||','>','2>&1'} for p in parts):
            raise ValueError('script_pipeline_requires_separate_evidence')
        virtual = posixpath.normpath(posixpath.join(cwd,parts[1]))
        if not virtual.startswith('/work/'): raise ValueError('script_outside_workspace')
        path = virtual_host(workspace, virtual)
        if path.is_symlink() or not path.resolve().is_relative_to(Path(workspace).resolve()):
            raise ValueError('script_source_not_fixed')
        # Boundary witnesses hash actual UTF-8 bytes, including CRLF. Text-mode
        # newline conversion would incorrectly reject an unchanged saved file.
        source = path.read_bytes().decode('utf-8')
        if declared and (declared[0]!=parts[1] or source.strip()!=declared[1].strip()):
            raise ValueError('saved_source_changed')
        return cwd, source, parts[2:], sha(source)
    raise ValueError('single_python_invocation_required')

def compile_script(source, registered_files, *, argv=None):
    """registered_files maps exact source literals to bounded input contracts.

    Only paths actually present at the observed tool boundary can become slots.
    Source content and output are never used as a cached answer.
    """
    if len(source.encode()) > 48000: raise ValueError('script_size_limit')
    tree = ast.parse(source)
    nodes = list(ast.walk(tree))
    regex_names = {a.asname or a.name for n in tree.body if isinstance(n,ast.Import)
                   for a in n.names if a.name=='re'}
    # Allow regular-expression compilation, never Python compile/eval. Reject
    # a shadowed module name rather than inferring the callable dynamically.
    shadowed = {n.id for n in nodes if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Store)}
    shadowed |= {n.arg for n in nodes if isinstance(n,ast.arg)}
    shadowed |= {n.name for n in nodes if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    shadowed |= {a.asname or a.name.split('.')[0] for n in nodes if isinstance(n,ast.Import)
                 for a in n.names if n not in tree.body or a.name!='re'}
    shadowed |= {a.asname or a.name for n in nodes if isinstance(n,ast.ImportFrom) for a in n.names}
    regex_names -= shadowed
    sys_names = {a.asname or a.name for n in nodes if isinstance(n,ast.Import) for a in n.names if a.name=='sys'}
    if len(nodes) > 4000: raise ValueError('script_ast_limit')
    for node in nodes:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [node.module] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
            if any(m not in IMPORTS for m in modules) or getattr(node, 'level', 0):
                script_reject('import_not_admitted',node,source)
        regex_compile = (isinstance(node,ast.Attribute) and node.attr=='compile' and
                         isinstance(node.value,ast.Name) and node.value.id in regex_names)
        if isinstance(node, ast.Attribute) and (node.attr.startswith('_') or node.attr in FORBIDDEN) and not regex_compile:
            script_reject('attribute_not_admitted:' + node.attr,node,source)
        if isinstance(node, ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id in sys_names and node.attr!='argv':
            raise ValueError('only_sys_argv_is_admitted')
        if isinstance(node,(ast.Assign,ast.AugAssign,ast.AnnAssign)):
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]
            if any(isinstance(t,ast.Attribute) for t in targets):raise ValueError('attribute_mutation_not_admitted')
        if isinstance(node, ast.Name) and (node.id.startswith(('__', '_sm_')) or node.id in FORBIDDEN):
            raise ValueError('name_not_admitted:' + node.id)
        if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef, ast.Await, ast.Yield, ast.Global, ast.Nonlocal)):
            raise ValueError('statement_not_admitted')
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
            if name in ('open', 'ZipFile'):
                mode = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == 'mode'), ast.Constant('r'))
                if not isinstance(mode, ast.Constant) or mode.value not in ('r', 'rb', 'rt'):
                    raise ValueError('read_mode_required')
    slots = []; paths = []
    class Bind(ast.NodeTransformer):
        def visit_Constant(self, node):
            if isinstance(node.value, str) and node.value in registered_files:
                if node.value not in paths:
                    paths.append(node.value); slots.append(registered_files[node.value])
                return ast.copy_location(ast.Constant('__MOTIF_INPUT_' + str(paths.index(node.value)) + '__'), node)
            return node
    template = ast.unparse(Bind().visit(tree))
    uses_argv = any(isinstance(n,ast.Attribute) and n.attr=='argv' and isinstance(n.value,ast.Name) and n.value.id in sys_names for n in nodes)
    if (not slots and not (argv and uses_argv)) or len(slots) > 6: raise ValueError('bounded_registered_inputs_required')
    if any('__MOTIF_INPUT_' in n.value for n in nodes if isinstance(n, ast.Constant) and isinstance(n.value, str)):
        raise ValueError('reserved_placeholder')
    # Paths left in a template indicate a missed dependency, not a reusable input.
    template_tree = ast.parse(template)
    parents = {child: parent for parent in ast.walk(template_tree) for child in ast.iter_child_nodes(parent)}
    for node in ast.walk(template_tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if re.match(r'^(?:/|\.\.?/|[A-Za-z]:\\)', node.value):
                # A ZIP directory suffix or string separator is data, not an
                # unbound filesystem read. Keep this exception local to string
                # operations; open('/') and unregistered paths still fail.
                parent = parents.get(node)
                if (node.value in {'/', './', '../'} and isinstance(parent, ast.Call)
                        and node in parent.args and isinstance(parent.func, ast.Attribute)
                        and parent.func.attr in {'startswith', 'endswith', 'strip', 'lstrip', 'rstrip', 'split', 'rsplit', 'replace', 'count'}):
                    continue
                if node.value in {'/', './', '../'}:
                    # Archive member normalization also uses separator joins,
                    # concatenation and character membership tests. These are
                    # string data operations, not literal filesystem reads.
                    grandparent=parents.get(parent)
                    if (isinstance(parent,ast.Attribute) and parent.value is node and parent.attr=='join'
                            and isinstance(grandparent,ast.Call) and grandparent.func is parent):continue
                    if isinstance(parent,ast.BinOp) and isinstance(parent.op,ast.Add):
                        if isinstance(parent.left,ast.Constant) and isinstance(parent.right,ast.Constant):
                            if isinstance(parent.left.value,str) and isinstance(parent.right.value,str):
                                combined=parent.left.value+parent.right.value
                                if re.match(r'^(?:/|\.\.?/|[A-Za-z]:\\)',combined):script_reject('unbound_path_literal',node,template,'parameterized_template')
                        continue
                    if isinstance(parent,ast.Compare) and any(isinstance(op,(ast.In,ast.NotIn,ast.Eq,ast.NotEq)) for op in parent.ops):continue
                script_reject('unbound_path_literal',node,template,'parameterized_template')
    body = {'version': VERSION, 'language': 'python', 'template': template, 'inputs': slots}
    if argv and uses_argv:
        if len(argv)>32 or any(not a or len(a)>256 or a.startswith(('/', '..')) or any(c in a for c in '\n\r\x00') for a in argv):
            raise ValueError('bounded_scalar_arguments_required')
        body['argv_contract']={'max_items':32,'max_chars':256,'kind':'explicit_model_selected_scalars'}
    network = any(isinstance(n,ast.Import) and any(a.name=='urllib.request' for a in n.names) for n in nodes)
    if network:
        # Network stays disabled in the child. The replay driver only serves
        # bounded GETs to the existing metadata services, never arbitrary URLs.
        body['network_policy']='fixed_metadata_get_v1'
    return {**body, 'id': 'script_' + digest(body)[:24], 'source_sha256': sha(source), 'original_paths': paths}

def file_contract(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16_000_000:
        raise ValueError('bounded_regular_input_required')
    data = path.read_bytes(); suffix = path.suffix.lower()
    result = {'suffix': suffix, 'format': 'bytes'}
    if suffix == '.json':
        value = json.loads(data)
        def shape(v, depth=0):
            if isinstance(v, dict): return {'object': {k: shape(x, depth+1) for k,x in sorted(v.items())}} if depth < 3 else 'object'
            if isinstance(v, list): return {'array': shape(v[0], depth+1)} if v and depth < 3 else 'array'
            return 'null' if v is None else 'boolean' if isinstance(v,bool) else 'number' if isinstance(v,(int,float)) else 'string'
        result.update(format='json', shape=shape(value))
    elif suffix == '.zip':
        if not data.startswith(b'PK\x03\x04'): raise ValueError('zip_magic_mismatch')
        result['format'] = 'zip'
    else:
        data.decode('utf-8-sig'); result['format'] = 'text'
    return result

def observe(command, description, workspace, stdout, task_id, call_id):
    extracted = extract(command,workspace)
    cwd,source = extracted[:2]; argv=extracted[2] if len(extracted)>2 else None
    workspace = Path(workspace).resolve()
    cwd = posixpath.normpath(posixpath.join('/work', cwd))
    if cwd != '/work' and not cwd.startswith('/work/'): raise ValueError('workspace_invocation_required')
    files = {}; witnesses = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str): continue
        name = node.value
        if not name or len(name)>1024 or any(c in name for c in ('\x00','\n','\r')) or any(len(p.encode())>255 for p in name.split('/')):continue
        virtual = posixpath.normpath(posixpath.join(cwd,name))
        if not virtual.startswith('/work/'): continue
        relative = virtual.removeprefix('/work/')
        path = virtual_host(workspace, virtual)
        try:
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(workspace): continue
        except OSError:continue
        files[name] = file_contract(path)
        witnesses[name] = {'relative': path.relative_to(workspace).as_posix(), 'sha256': sha(path.read_bytes())}
    compiled = compile_script(source, files,argv=argv)
    literals = sorted({n.value for n in ast.walk(ast.parse(source)) if isinstance(n,ast.Constant)
                       and isinstance(n.value,str) and 3<=len(n.value)<=200 and any(c.isalnum() for c in n.value)
                       and n.value not in files})
    outputs=[]
    for n in ast.walk(ast.parse(source)):
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='print':
            outputs.extend(a.value for a in n.args if isinstance(a,ast.Constant) and isinstance(a.value,str) and len(a.value)<100)
    tree=ast.parse(source)
    modules=sorted({a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names}|{n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)})
    variables=sorted({target.id for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(x,ast.Attribute) and x.attr=='argv' for x in ast.walk(n.value)) for target in n.targets if isinstance(target,ast.Name)})
    interface={'language':'python','imports':modules,'stdout_labels':outputs,
               'argv_variables':variables,'url_literals':sorted({n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value.startswith(('https://','http://'))})}
    semantic='Input format: '+', '.join(c['suffix'] for c in compiled['inputs'])+'. Intent: '+description+'. Observed output labels: '+'; '.join(outputs)
    return {**compiled, 'interface':interface, 'description': semantic[:1800], 'literal_selectors':literals, 'source': source, 'observed_argv':argv,
            'witness': {'task_id': task_id, 'call_id': call_id, 'workspace': str(workspace), 'cwd': cwd,
                        'files': witnesses, 'stdout': stdout, 'stdout_sha256': sha(stdout)}}
