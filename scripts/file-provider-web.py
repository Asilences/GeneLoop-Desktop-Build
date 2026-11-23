"""File provider opt-in through the standard local Web lifecycle, same process.

The canonical Web entry and other scenes' certified code stay byte-for-byte.
Only this entry's create_server factory wraps its normal outer meter for File.
"""
import importlib.util
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def configure(module):
    from src.adapters.file_provider import configured, attach
    from src.adapters.model_api import model_api_root

    provider = configured()
    if not provider:
        raise ValueError('explicit local File provider configuration required')
    original = module.create_server

    def create(host, port, upstream, state, **kwargs):
        server = original(host, port, upstream, state, **kwargs)
        if upstream == model_api_root():
            attach(server, provider, selective=True)
        return server

    module.create_server = create


def main():
    spec=importlib.util.spec_from_file_location('file_provider_local_web',ROOT/'scripts/harness-web.py')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    configure(module)
    return module.main()


if __name__=='__main__':main()
