import argparse
import hashlib
import json
from pathlib import Path
import time

import run_pii as pii


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    frozen = {'case_sha256': hashlib.sha256(args.cases.read_bytes()).hexdigest(),
              'config_sha256': hashlib.sha256(args.config.read_bytes()).hexdigest()}
    cases = json.loads(args.cases.read_text())
    pii.initialize(str(args.config))
    from src.adapters.geneloop_privacy import learning_view, PrivacyRejected
    from src.adapters.privacy_diagnostics import observe_privacy
    rows = []
    for intent in cases['intents']:
        for variant in cases['variants']:
            source = {'text': intent['text']}
            sensitive = []
            if variant == 'structured_identity':
                source.update(cases['synthetic_identity'])
                sensitive = list(cases['synthetic_identity'].values())
            elif variant == 'inline_identity':
                source['text'] += cases['inline_identity']
                sensitive = cases['inline_sensitive_values']
            original = json.dumps(source, ensure_ascii=False, sort_keys=True)
            try:
                with observe_privacy() as stages:
                    output = learning_view(source)
                encoded = json.dumps(output, ensure_ascii=False)
                row = {'id': intent['id'], 'variant': variant, 'accepted': True,
                       'invariants': len(intent['keep']), 'retained_invariants': sum(value in output.get('text', '') for value in intent['keep']),
                       'sensitive_values': len(sensitive), 'literal_residual_values': sum(value in encoded for value in sensitive)}
            except PrivacyRejected as error:
                row = {'id': intent['id'], 'variant': variant, 'accepted': False, 'invariants': len(intent['keep']),
                       'reason': error.reason, 'detector': error.detector}
            row['stages'] = stages
            row['original_unchanged'] = original == json.dumps(source, ensure_ascii=False, sort_keys=True)
            rows.append(row)
    controls = []
    for source in cases['refusal_controls']:
        try:
            learning_view(source)
            controls.append(False)
        except PrivacyRejected:
            controls.append(True)
    result = {**frozen, 'cases': rows, 'secret_field_controls_rejected': controls,
              'accepted': sum(row['accepted'] for row in rows), 'total': len(rows),
              'retained_invariants': sum(row.get('retained_invariants', 0) for row in rows),
              'all_invariants': sum(row['invariants'] for row in rows),
              'accepted_invariants': sum(row['invariants'] for row in rows if row['accepted']),
              'literal_residual_values': sum(row.get('literal_residual_values', 0) for row in rows),
              'wall_seconds': time.perf_counter() - started, 'cloud_requests': 0, 'cloud_api_cost': 0}
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({key: result[key] for key in ('accepted', 'total', 'retained_invariants', 'all_invariants', 'literal_residual_values')}), flush=True)


if __name__ == '__main__':
    main()
