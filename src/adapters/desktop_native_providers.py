"""Reuse the public gateway validator with host-only, in-memory credentials."""
import base64
import json
import os
from mcp.server.mcpserver.exceptions import ToolError
from src.adapters.general_tools import Gateway


class NativeGateway(Gateway):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        raw = os.environ.pop('GENELOOP_NATIVE_PROVIDER_CONFIG', None)
        self.native_config = json.loads(base64.b64decode(raw, validate=True)) if raw else {'format':'sss-general-tools-v1','providers':[]}
        self.native_credentials = self.native_config.pop('credentials', {})

    def private_providers(self):
        return self.native_config

    def bound(self, value):
        if isinstance(value, dict) and set(value) == {'from_env'}:
            name = value['from_env']
            if name not in self.native_credentials:
                raise ToolError('provider credential is not configured')
            return self.native_credentials[name]
        return super().bound(value)
