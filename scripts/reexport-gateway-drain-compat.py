#!/usr/bin/env python3
"""Preserve certified Paper/PPT IR after the bounded HTTP 413 drain fix."""
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('gateway_drain_compat',ROOT/'scripts/reexport-native-capabilities-compat.py')
compat=importlib.util.module_from_spec(spec);spec.loader.exec_module(compat)
compat.RELEASES=[
    ('paper-web-v43','paper-web-v44','paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json',{'scripts/harless_gateway.mjs'}),
    ('ppt-master-v40','ppt-master-v41','ppt',
     'scenarios/ppt_master/contracts.json',{'scripts/harless_gateway.mjs'}),
]
compat.REGISTRY_SELECTED={old:old for old,*_ in compat.RELEASES}
compat.ADDITIONAL_LOCKS={'scripts/reexport-gateway-drain-compat.py'}
original_record=compat.compatibility_record

def compatibility_record(candidate,validation_record):
    value=original_record(candidate,validation_record)
    value.update(repairs=['typed_413_before_bounded_connection_close'],
        runtime_delta='An oversized HTTP body receives a complete Content-Length framed 413 before '
                      'the connection closes; queued request bytes drain without buffering for at most five seconds. '
                      'Transport capacity, authorization, normal forwarding and learned IR are unchanged.')
    return value

compat.compatibility_record=compatibility_record
if __name__=='__main__':compat.main()
