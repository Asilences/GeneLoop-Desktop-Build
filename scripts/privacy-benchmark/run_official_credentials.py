"""Use the frozen deadline controller with a warmed opt-in public backend."""
import hashlib
import json
import os
from pathlib import Path
import sys

import run_pii as pii
import run_credentials_bounded as controller

_INITIALIZE=pii.initialize


def initialize(config_path):
    from gpu_workers import select_worker_gpu
    select_worker_gpu(os.environ.get('GENELOOP_PRIVACY_BENCHMARK_GPUS'))
    _INITIALIZE(config_path)
    from src.adapters.rsi_privacy_candidates import candidate_context
    with candidate_context(from_environment=True):
        pass


def main():
    # Same arguments and no reuse policy as the R4 controller. The host owns the
    # explicit candidate configuration and matching SHA; source data cannot set it.
    path=os.environ['SSS_RSI_PRIVACY_CANDIDATE_CONFIG']
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==os.environ['SSS_RSI_PRIVACY_CANDIDATE_SHA256']
    pii.initialize=initialize
    controller.pii.initialize=initialize
    controller.main()


if __name__=='__main__':main()
