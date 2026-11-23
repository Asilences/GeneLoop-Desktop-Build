"""Shared tool scope, persisted file reads, and verified operation receipts."""
import copy
import json
from typing import Annotated
from uuid import uuid4

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from common import ROOT
from plan_tools import atomic

FORMAT='sss-mcp-learning-v1'
OPERATION_TOOLS=['read_task','list_files','select_files','pin_file','read_file','collect_reads','hash_files','build_index',
       'search_index','compare_snapshot','preview_actions','execute_plan','inspect_plan_result','restore_plan','submit_report']

def operator_contract(name):
    # These declarations express tool authority, never a sequence of tools.
    rows={'list_files':('read',False,[],None),'pin_file':('read',True,['source_id'],None),
          'read_file':('read',True,[],['readable','metadata_only','unreadable','unsupported']),
          'preview_actions':('stage',False,['plan_id'],['validated_copy_plan']),
          'execute_plan':('authorized_write',True,['receipt_id'],['executed_verified']),
          'inspect_plan_result':('read',True,['primary_file_id'],['verified_plan_results'])}
    effect,auto,exports,statuses=rows.get(name,('semantic',False,[],None))
    return {'format':FORMAT,'effect':effect,'auto_continue':auto,'exports':exports,**({'statuses':statuses} if statuses else {}),
            **({'scope_requirements':{'result_read_allowed':True}} if name=='inspect_plan_result' else {}),
            **({'safe_interleaving':True} if name=='list_files' else {})}

BATCH_OPERATION_TOOLS = [*OPERATION_TOOLS, 'pin_files', 'read_files']
Handles = Annotated[list[str], Field(min_length=1, max_length=40)]

def batch_operator_contract(name):
    c=operator_contract(name)
    if name=='inspect_plan_result':c={**c,'exports':['primary_file_id','files[].file_id']}
    if name in ('pin_files','read_files'):
        c={'format':'sss-mcp-learning-v1','effect':'read','auto_continue':True,'exports':['source_ids'] if name=='pin_files' else [],
           'statuses':['pinned_batch'] if name=='pin_files' else ['read_batch_complete']}
    return c

def reviewed_execution_version(current):
    policy = ROOT / "config/file-management-runtime-compatibility.json"
    if not policy.is_file():
        return current
    versions = json.loads(policy.read_text(encoding="utf-8")).get("execution_versions", {})
    return versions.get(current, current)


class ScopedOperationEvidence:
    def stamp(self,out,authorized=False):
        return {**copy.deepcopy(out),'_sss_scope':self.learning_scope,'_sss_authorized':authorized}
    def pin_file(self,file_id:str):return self.stamp(super().pin_file(file_id))
    def read_file(self,source_id:str):return self.stamp(super().read_file(source_id))


class DurableOperationEvidence(ScopedOperationEvidence):
    fields=('plans','receipts','result_handles','handles','reads','index','collections','collection_results','search_receipts')

    def pin_file(self,file_id:str):
        v=super().pin_file(file_id);self.persist();return v
    def read_file(self,source_id:str):
        v=super().read_file(source_id);self.persist();return v
    def pin_files(self,file_ids:Handles):
        self.active()
        if len(file_ids)!=len(set(file_ids)):raise ToolError('unique current file handles required')
        for fid in file_ids:self.file(fid)
        rows=[self.pin_file(fid) for fid in file_ids]
        return self.stamp({'status':'pinned_batch','file_ids':file_ids,'source_ids':[r['source_id'] for r in rows],'count':len(rows)})
    def read_files(self,source_ids:Handles):
        self.active()
        if len(source_ids)!=len(set(source_ids)) or any(s not in self.handles for s in source_ids):raise ToolError('unique actual pinned handles required')
        rows=[self.read_file(s) for s in source_ids]
        return self.stamp({'status':'read_batch_complete','reads':rows,'count':len(rows)})
    def receipt(self,plan_id):
        rid=next((r for r,p in self.result_handles.items() if p==plan_id),None) or 'receipt-'+uuid4().hex
        self.result_handles[rid]=plan_id;self.persist();value={**self.receipts[plan_id],'receipt_id':rid}
        atomic(self.output/'operation-receipts'/f'{rid}.json',value);return self.stamp(value,True)
