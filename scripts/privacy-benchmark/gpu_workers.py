"""Explicit benchmark worker placement; never used by task-selected policy."""
import multiprocessing
import os
import re


def select_worker_gpu(devices):
    if not devices:
        return None
    values = devices.split(',')
    if len(values) != len(set(values)) or any(not re.fullmatch(r'[0-9]+', value) for value in values):
        raise ValueError('invalid_benchmark_gpu_devices')
    identity = multiprocessing.current_process()._identity
    if not identity:
        raise ValueError('benchmark_gpu_selection_requires_pool_worker')
    selected = values[(identity[-1] - 1) % len(values)]
    os.environ['CUDA_VISIBLE_DEVICES'] = selected
    return selected
