"""Frozen research exposure profiles; no candidate execution or model calls.

An interface description is information, not a selectable capability. The
callable vocabulary is solely the returned validated snapshot. All profiles
retain ordinary program authoring; this module never restricts algorithms.
"""
from __future__ import annotations

import copy
import re

from src.adapters.capability_contract import create_capability_snapshot, validate_capability_snapshot


CREATION_VALUE_ARMS = ('flat_without_C', 'description_only_C', 'hierarchical_with_C')


def balanced_order(arms, replicates=6):
    """Return a fixed Latin rotation, reversing every second complete block.

    For three arms and six replicates, every arm occupies each within-replicate
    position twice. A shorter partial block is deterministic and has position
    counts differing by at most one; it cannot claim complete balance.
    """
    if (not isinstance(arms, (list, tuple)) or len(arms) < 2
            or any(not isinstance(arm, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', arm) for arm in arms)
            or len(set(arms)) != len(arms)):
        raise ValueError('frontier_profile_arms_invalid')
    if type(replicates) is not int or not 1 <= replicates <= 1000:
        raise ValueError('frontier_profile_replicates_invalid')
    names = list(arms)
    order = []
    for replicate in range(replicates):
        shift = replicate % len(names)
        row = names[shift:] + names[:shift]
        if (replicate // len(names)) % 2:
            row.reverse()
        order.extend((arm, replicate) for arm in row)
    return order


def _subset(snapshot, roots):
    lookup = {capability['id']: capability for capability in snapshot['capabilities']}
    selected = {}
    todo = list(roots)
    while todo:
        ref = todo.pop()
        if ref['id'] in selected:
            continue
        capability = lookup[ref['id']]
        selected[ref['id']] = capability
        todo.extend(capability['dependencies'])
    return create_capability_snapshot(snapshot['owner'], roots, list(selected.values()))


def creation_value_profile(hierarchical_snapshot, c_ref, base_refs, j_ref, c_description, *, replicates=6):
    """Match lower-level materials and C's documentation, varying callability.

    ``c_description`` is a trusted host's public interface summary, never model
    source or final-test feedback. The helper copies only that summary, C's
    public contract and identity. It does not copy implementation, dependency
    definitions, certification reports, or execution results into the card.
    """
    snapshot = validate_capability_snapshot(hierarchical_snapshot)
    if not isinstance(base_refs, (list, tuple)) or not base_refs:
        raise ValueError('frontier_profile_base_references_invalid')
    references = [*base_refs, j_ref, c_ref]
    if any(not isinstance(ref, dict) or set(ref) != {'id', 'sha256'}
           or ref not in snapshot['roots'] for ref in references):
        raise ValueError('frontier_profile_reference_not_visible')
    if len({ref['id'] for ref in references}) != len(references):
        raise ValueError('frontier_profile_references_not_distinct')
    if (not isinstance(c_description, str) or not c_description.strip()
            or len(c_description.encode('utf-8')) > 16384):
        raise ValueError('frontier_profile_description_invalid')
    lookup = {capability['id']: capability for capability in snapshot['capabilities']}
    c = lookup[c_ref['id']]
    if c['certification'] != 'certified' or c['lifecycle'] != 'active':
        raise ValueError('frontier_profile_C_not_active_certified')
    flat = _subset(snapshot, [*base_refs, j_ref])
    with_c = _subset(snapshot, [*base_refs, j_ref, c_ref])
    if ({row['id'] for row in with_c['capabilities']}
            != {row['id'] for row in flat['capabilities']} | {c_ref['id']}):
        raise ValueError('frontier_profile_unmatched_C_dependencies')
    card = {'format': 'capability_reference_interface_v1',
        'reference': copy.deepcopy(c_ref), 'contract': copy.deepcopy(c['contract']),
        'description': c_description,
        'scope': 'Interface documentation only. Callable operations and aliases are solely '
            'those in the current capability table and validated snapshot. This card '
            'does not grant an alias or execution authority.'}
    return {'format': 'frontier_creation_value_profile_v1',
        'snapshots': {'flat_without_C': flat, 'description_only_C': copy.deepcopy(flat),
            'hierarchical_with_C': with_c},
        'reference_interfaces': {'flat_without_C': [], 'description_only_C': [copy.deepcopy(card)],
            'hierarchical_with_C': [copy.deepcopy(card)]},
        'order': balanced_order(CREATION_VALUE_ARMS, replicates)}
