"""Account-host child worker; reuses loaded models, never persists raw requests."""
import argparse
from contextlib import redirect_stdout
import json
import sys
from uuid import UUID

from .geneloop_privacy import MAX_BYTES, PrivacyRejected, admit_publication, decode_material_json, learning_view
from .geneloop_learning_trace import import_trace, prepare_trace, project

MAX_FRAME = MAX_BYTES + 4096


def _request_id(value):
    if value=='sdk':return value
    try:
        return value if str(UUID(value))==value else None
    except (TypeError,ValueError,AttributeError):
        return None


def execute_request(request):
    if not isinstance(request,dict) or set(request)!={'id','operation','value'} or _request_id(request['id']) is None:
        raise PrivacyRejected('invalid_input')
    value=request['value'];operation=request['operation']
    if operation=='learning':return learning_view(value)
    if operation=='publication':return admit_publication(value)
    if operation=='native_project':
        if not isinstance(value,dict) or set(value)!={'events','status'} or not isinstance(value['events'],list):
            raise PrivacyRejected('invalid_input')
        tools=list(dict.fromkeys(event['data']['name'] for event in value['events'] if event.get('type')=='tool/call'))
        return project(value['events'],'sdk',value['status'],tools)
    if operation=='project':
        if not isinstance(value,dict) or set(value)!={'input','scene','status','start','catalog','share'} or type(value['share']) is not bool:
            raise PrivacyRejected('invalid_input')
        return prepare_trace(value['input'],value['scene'],value['status'],value['start'],value['catalog'],value['share'])
    if operation=='import':
        if (not isinstance(value,dict) or set(value)!={'input','scene','status','start','allowed_tools'}
                or not isinstance(value['allowed_tools'],list) or not all(isinstance(tool,str) for tool in value['allowed_tools'])):
            raise PrivacyRejected('invalid_input')
        return import_trace(value['input'],value['scene'],value['status'],value['start'],value['allowed_tools'])
    raise PrivacyRejected('invalid_input')


def process(raw):
    identity=None
    try:
        if len(raw)>MAX_FRAME or not raw.endswith(b'\n'):
            raise PrivacyRejected('input_limit')
        request=decode_material_json(raw)
        if isinstance(request,dict):identity=_request_id(request.get('id'))
        # Third-party warnings must never corrupt framing or become tool replies.
        with redirect_stdout(sys.stderr):result=execute_request(request)
        encoded=json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(',',':'))
        if len(encoded.encode())>MAX_BYTES:raise PrivacyRejected('input_limit')
        return {'id':identity,'ok':True,'value':result}
    except Exception as error:
        reason=error.reason if isinstance(error,PrivacyRejected) else 'processing_failed'
        return {'id':identity,'ok':False,'reason':reason}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorized',action='store_true',required=True)
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    while raw:=sys.stdin.buffer.readline(MAX_FRAME+1):
        response=process(raw)
        sys.stdout.write(json.dumps(response,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n')
        sys.stdout.flush()
        finished=args.once or len(raw)>MAX_FRAME or not raw.endswith(b'\n')
        del raw,response
        if finished:break


if __name__=='__main__':main()
