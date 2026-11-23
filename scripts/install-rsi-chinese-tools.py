"""Download only the frozen official Chinese assets into a new private directory.

Install stanza==1.11.0 in a separate environment first. No product dependency,
runtime, service or user source is modified; downloads are verified before use.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads((Path(__file__).resolve().parents[1]/'config/rsi-privacy-chinese-tools.json').read_text())
    if importlib.metadata.version('stanza') != spec['version']:
        raise ValueError('chinese_candidate_dependency_mismatch')
    destination = args.model_dir.absolute()
    if destination.exists():
        raise ValueError('new_model_directory_required')
    destination.mkdir(parents=True, mode=0o700)
    import stanza
    stanza.download('zh-hans', model_dir=str(destination), package=None,
        processors={'tokenize':'gsdsimp','ner':spec['ner_package']}, resources_version=spec['resource_version'])
    for name, digest in spec['files'].items():
        if hashlib.sha256((destination/name).read_bytes()).hexdigest() != digest:
            raise ValueError('chinese_candidate_asset_mismatch')
    print('Frozen Chinese model assets verified; backend remains opt-in.')


if __name__=='__main__':main()
