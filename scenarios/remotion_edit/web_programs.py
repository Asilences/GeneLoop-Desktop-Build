"""Web transport for an immutable published program; original TS owns validation."""
from __future__ import annotations
import hashlib,json,os,subprocess
from pathlib import Path
from mcp.server.mcpserver.exceptions import ToolError

ROOT=Path(__file__).resolve().parents[2]

def runtime_request(value):
    result=subprocess.run(['node','--experimental-strip-types',str(ROOT/'scripts/materialize-source-program.mjs')],
        input=json.dumps(value,ensure_ascii=False),capture_output=True,text=True,timeout=20,cwd=ROOT)
    if result.returncode:
        raise ToolError('published video program rejected: '+result.stderr[-1500:])
    return json.loads(result.stdout)

class PublishedPrograms:
    """Pin one already-published form; never consume a moving candidate or pointer."""
    def __init__(self,store,owner,request=runtime_request):
        path=Path(store)
        if not owner or path.is_symlink() or not path.is_absolute() or path.resolve()!=path or not path.is_dir():
            raise ToolError('invalid fixed video program store')
        self.store=str(path);self.owner=owner;self.request=request
        self.snapshot=self.resolve()
        self.policy=self.snapshot['policy'];self.library_path=self.snapshot['library_path']
        form=self.policy['form']
        # This web adapter supports exactly the published typed/all interface.
        # Other forms need their own reviewed transport before deployment.
        if form.get('representation')!='typed_tools' or form.get('library_scope','all')!='all':
            raise ToolError('published video interface is not supported by this web adapter')
        self.binding=form['parameter_binding'];self.naming=form['tool_naming']
        self.catalog=self.request({'operation':'catalog','library':self.library_path,
            'library_scope':'all','include_source':form['program_evidence']=='source'})
        if self.catalog['digest']!=self.policy['library_digest']:
            raise ToolError('published video catalog changed')
        self.check()
    def resolve(self):
        return self.request({'operation':'resolve_form','store':self.store,'owner':self.owner})
    def check(self):
        current=self.resolve()
        if current!=self.snapshot:
            raise ToolError('published video form changed during this Session')
    def materialize(self,program_id,parameters):
        self.check()
        value=self.request({'operation':'materialize','library':self.library_path,
            'program_id':program_id,'parameters':parameters,'parameter_binding':self.binding,'library_scope':'all'})
        if value.get('library_digest')!=self.policy['library_digest'] or value.get('program_id')!=program_id:
            raise ToolError('published video materialization changed')
        if hashlib.sha256(value['source'].encode()).hexdigest()!=value.get('source_sha256'):
            raise ToolError('published video source changed')
        self.check()
        return value

def from_environment():
    store=os.environ.get('GENELOOP_VIDEO_MOTIF_STORE')
    owner=os.environ.get('GENELOOP_VIDEO_MOTIF_OWNER')
    if not store and not owner:return None
    if not store or not owner:raise ToolError('incomplete published video configuration')
    return PublishedPrograms(store,owner)
