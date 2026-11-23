"""File-only Kouri transport; admission, streaming settlement and budgets stay upstream.

Opt in with SSS_FILE_PROVIDER_CONFIG. No credentials enter the public binding,
task snapshots or child process environment. Other scenes retain their provider.
"""
import json
import os
import shlex
import stat
import hashlib
import time
from uuid import uuid4
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from src.motif_core.reuse.experience_registry import digest

ORIGIN = 'https://api.kourichat.com'
HEADER = 'X-SSS-File-Provider'


def binding():
    value = dict(version='file-provider-binding-v2', provider='kouri', upstream_origin=ORIGIN,
        base_url=ORIGIN+'/v1', model_map={'deepseek-flash':'deepseek-v4.1-flash', 'deepseek-v4-pro':'deepseek-v4-pro'},
        pricing_status='unverified', cost_basis='reference_tariff_only_not_kouri_charge',
        reasoning_policy='host_explicit_off', thinking={'type':'disabled'}, flash_reasoning_effort='none',
        streaming_usage='explicit_include_usage_when_streaming')
    return {**value, 'binding_sha256':digest(value)}


def load(path):
    if os.name != 'posix':
        raise ValueError('File provider override requires POSIX private file permissions')
    path = Path(path).absolute()
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or path.is_symlink() or path.resolve()!=path or
            info.st_nlink!=1 or info.st_mode & 0o077):
        raise ValueError('File provider config must be a private regular file (mode 600)')
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'): continue
        name, sep, value = line.partition('=')
        parts = shlex.split(value, comments=True)
        if not sep or len(parts)>1 or name.strip() in values:
            raise ValueError('invalid File provider configuration')
        values[name.strip()] = parts[0] if parts else ''
    url = urlsplit(values.get('KOURI_BASE_URL', ''))
    if (url.scheme!='https' or url.hostname!='api.kourichat.com' or url.port is not None or
            url.username or url.password or url.query or url.fragment or url.path not in ('','/','/v1','/v1/')):
        raise ValueError('File Kouri provider requires the verified HTTPS origin')
    credential = values.get('KOURI_API_KEY', '')
    if not credential or any(ord(c)<33 or ord(c)==127 for c in credential):
        raise ValueError('File provider credential unavailable')
    if values.get('KOURI_MODEL','deepseek-v4.1-flash')!='deepseek-v4.1-flash':
        raise ValueError('unsupported File provider task model')
    return {'credential':credential, 'provider_binding':binding()}


def configured():
    path = os.environ.get('SSS_FILE_PROVIDER_CONFIG')
    return load(path) if path else None


def payload(body):
    value = json.loads(body)
    logical = value.get('model')
    # The existing outer meter may have normalized the official Flash alias.
    if logical in ('deepseek-v4-flash', 'deepseek-v4.1-flash'):
        logical = 'deepseek-flash'
    if logical not in binding()['model_map']:
        raise ValueError('unbound File provider model')
    value['model'] = binding()['model_map'][logical]
    value['thinking'] = {'type':'disabled'}
    if value.get('stream') is True:
        options=value.get('stream_options',{})
        if not isinstance(options,dict):raise ValueError('invalid streaming usage options')
        value['stream_options']={**options,'include_usage':True}
    if logical=='deepseek-flash': value['reasoning_effort']='none'
    else: value.pop('reasoning_effort', None)
    return json.dumps(value, ensure_ascii=False).encode('utf-8')


def billing_usage(raw):
    """Copy explicit standard cache counters; never infer missing output tokens."""
    if not isinstance(raw,dict):return raw
    value=dict(raw);cached=value.get('prompt_tokens_details',{}).get('cached_tokens') if isinstance(value.get('prompt_tokens_details'),dict) else None
    prompt=value.get('prompt_tokens')
    if ('prompt_cache_hit_tokens' not in value and 'prompt_cache_miss_tokens' not in value
        and type(cached) is int and type(prompt) is int and 0<=cached<=prompt):
        value.update(prompt_cache_hit_tokens=cached,prompt_cache_miss_tokens=prompt-cached)
    return value


def attach(server, provider, *, selective=False):
    """Subclass one gate only. Selective mode is the shared Web outer meter.

    The SDK's inner gate forwards a public binding marker through the existing
    authenticated platform route. Only the outer host replaces Authorization;
    account admission and both existing cost ledgers remain in force.
    """
    if provider['provider_binding']!=binding(): raise ValueError('File provider binding changed')
    from .deepseek_cost_gate import HOP_HEADERS
    base = server.RequestHandlerClass
    from .model_usage import UpstreamEvidence

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(NoRedirect())

    class FileProviderHandler(base):
        def _call_upstream(self, body, method, *, stream=False):
            marker = self.headers.get(HEADER)
            if selective and marker is None:
                return super()._call_upstream(body, method, stream=stream)
            self.provider_retry_after = None
            self.upstream_evidence = UpstreamEvidence(None, ORIGIN + '/v1/chat/completions')
            if selective and marker!=binding()['binding_sha256']:
                return 400, 'application/json', b'{"error":"File provider binding mismatch"}'
            if self.path!='/v1/chat/completions':
                return 403, 'application/json', b'{"error":"unsupported File provider endpoint"}'
            try: request_body = payload(body)
            except (ValueError, TypeError):
                return 400, 'application/json', b'{"error":"invalid File provider model"}'
            headers = {k:v for k,v in self.headers.items() if k.lower() not in
                HOP_HEADERS | {'authorization','x-sss-model-gate-token',HEADER.lower()}}
            headers['Authorization'] = 'Bearer '+provider['credential']
            if stream: headers['Accept-Encoding']='identity'
            request = urllib.request.Request(ORIGIN+'/v1/chat/completions', data=request_body, headers=headers, method=method)
            self.upstream_evidence = UpstreamEvidence(request_body, request.full_url)
            metadata={'format':'file-provider-raw-usage-v1','trace_id':uuid4().hex,'epoch':time.time(),
                'session_id':self.headers.get('X-DeepSeek-Harness-Session-Id'),
                'request_sha256':hashlib.sha256(request_body).hexdigest(),
                'requested_model':json.loads(request_body)['model'],'binding_sha256':binding()['binding_sha256']}
            def save_metadata(values):
                # Separate diagnostic sidecar. The original budget ledger is
                # authoritative; raw counters are never silently "corrected".
                home=Path(os.environ.get('HARLESS_MANAGEMENT_PRIVATE_ROOT',Path(__file__).resolve().parents[2]/'.local'))/'provider-transports'
                try:
                    home.mkdir(parents=True,exist_ok=True,mode=0o700);path=home/'kouri-raw-usage.jsonl'
                    if path.is_symlink():return
                    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
                    with os.fdopen(fd,'a',encoding='utf-8') as f:f.write(json.dumps({**metadata,**values},ensure_ascii=False)+'\n')
                except OSError:pass  # Do not duplicate an already paid call on sidecar I/O failure.
            try:
                with opener.open(request, timeout=900) as response:
                    self.upstream_evidence.headers(response.status, response.headers)
                    content_type = response.headers.get('Content-Type', 'application/json')
                    if stream and content_type.split(';',1)[0].strip().lower()=='text/event-stream':
                        from .deepseek_cost_gate import StreamUsage
                        class RawUsage(StreamUsage):
                            def __init__(self):super().__init__();self.raw_usage={};self.models=set()
                            def line(self,line):
                                if not line.rstrip(b'\r\n') and self.data:
                                    try:
                                        item=json.loads(b'\n'.join(self.data))
                                        if isinstance(item,dict):
                                            if isinstance(item.get('usage'),dict):self.raw_usage=item['usage']
                                            if isinstance(item.get('model'),str) and len(item['model'])<=200:self.models.add(item['model'])
                                    except (ValueError,TypeError):pass
                                super().line(line)
                        monitor=RawUsage()
                        class Tee:
                            def read1(self,size):
                                chunk=response.read1(size);monitor.feed(chunk);return chunk
                            def __getattr__(self,name):return getattr(response,name)
                        try:
                            answer=self._stream_upstream(Tee(), content_type)
                            monitor.finish()
                            self.upstream_evidence.packet({'usage': monitor.raw_usage})
                            self.upstream_evidence.value['response_complete'] = True
                            # This return is the gate's pricing envelope. The
                            # original SSE body is relayed unchanged by the base.
                            envelope=json.dumps({'usage':billing_usage(monitor.raw_usage)}).encode() if monitor.raw_usage else answer
                            return response.status,'application/json',envelope
                        finally:
                            monitor.finish();save_metadata({'status':response.status,'raw_usage':monitor.raw_usage,
                                'reported_models':sorted(monitor.models),'stream_complete':getattr(self,'stream_complete',False)})
                    data=response.read()
                    self.upstream_evidence.body(content_type, data)
                    self.upstream_evidence.value['response_complete'] = True
                    try:
                        value=json.loads(data);save_metadata({'status':response.status,'raw_usage':value.get('usage'),
                            'reported_models':[value['model']] if isinstance(value.get('model'),str) else []})
                        if isinstance(value.get('usage'),dict):
                            value['usage']=billing_usage(value['usage']);data=json.dumps(value,ensure_ascii=False).encode()
                    except (ValueError,TypeError,AttributeError):pass
                    return response.status, content_type, data
            except urllib.error.HTTPError as error:
                self.provider_retry_after = error.headers.get('Retry-After')
                content_type = error.headers.get('Content-Type', 'application/json')
                self.upstream_evidence.headers(error.code, error.headers)
                try:
                    data = error.read()
                except Exception as read_error:
                    self.upstream_evidence.transport_error(read_error, content_type)
                    return 502, 'application/json', b'{"error":"File provider unavailable"}'
                self.upstream_evidence.body(content_type, data)
                self.upstream_evidence.value['response_complete'] = True
                return error.code, content_type, data
            except Exception as error:
                self.upstream_evidence.transport_error(error, 'application/json')
                return 502, 'application/json', b'{"error":"File provider unavailable"}'

    server.RequestHandlerClass = FileProviderHandler


def platform_headers(original, provider):
    def forward(headers):
        result = original(headers)
        result[HEADER] = provider['provider_binding']['binding_sha256']
        return result
    return forward
