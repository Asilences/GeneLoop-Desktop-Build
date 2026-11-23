"""Audit the final delivered files without scoring or changing a solver run."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def host(workspace, virtual):
    path = PurePosixPath(virtual)
    if not path.is_absolute() or '..' in path.parts or path.parts[:2] != ('/', 'work'):
        raise ValueError('delivery_path_outside_workspace')
    relative = path.relative_to('/work')
    if relative.parts[:1] == ('outputs',):
        target = workspace / 'outputs/code' / Path(*relative.parts[1:])
    elif relative.parts[:1] == ('inputs',):
        target = workspace / Path(*relative.parts)
    else:
        target = workspace / 'code' / Path(*relative.parts)
    if target.resolve() != target.absolute() or not target.is_file():
        raise ValueError('delivery_file_missing_or_indirect')
    return target


def audit(trial):
    trial = Path(trial).resolve()
    workspace = trial / 'workspace'
    effective = json.loads((trial / 'effective.json').read_text())
    rows = [json.loads(line) for line in (trial / 'native-tools.jsonl').read_text().splitlines()]
    native = [row for row in rows if row['name'] == 'capability_call' and row['phase'] == 'finished'
              and row['result']['status'] == 'succeeded']

    def pair(png):
        try:
            pdf = str(PurePosixPath(png).with_suffix('.pdf'))
            return {'png': host(workspace, png), 'pdf': host(workspace, pdf)}
        except ValueError:
            return None

    # The selection rule is frozen before either arm runs. It never reads a
    # reference image, reference code, metric, or judge response.
    answer = (trial / 'answer.txt').read_text() if (trial / 'answer.txt').exists() else ''
    mentions = list(dict.fromkeys(re.findall(r'/work/outputs/[A-Za-z0-9_./-]+\.png', answer)))
    mentions = [path for path in mentions if pair(path)]
    candidates = []
    if len(mentions) == 1:
        candidates.append(('unique_final_answer_png', mentions[0]))
    candidates += [('last_output_image_read', row['arguments']['file_path']) for row in reversed(rows)
                   if row['name'] == 'read_image' and row['phase'] == 'finished'
                   and row['arguments']['file_path'].startswith('/work/outputs/')]
    candidates += [('last_successful_native_output', row['result']['result']['output_directory']+'/chart.png')
                   for row in reversed(native)]
    canonical = '/work/outputs/rendered/chart.png' if effective.get('program_layout', '').startswith('parameter-files-') else '/work/outputs/chart.png'
    candidates.append(('canonical_output', canonical))
    selected = next(((reason, virtual, pair(virtual)) for reason, virtual in candidates if pair(virtual)), None)
    if selected is None:
        return {'status': 'missing_delivery', 'task_id': effective['task_id'], 'native_successes': len(native)}
    reason, png, figures = selected
    output = {'format': 'chartmimic_delivery_audit_v1', 'status': 'figures_present',
              'task_id': effective['task_id'], 'selection': reason, 'virtual_png': png,
              'figures': {kind: {'path': str(path), 'sha256': sha(path)} for kind, path in figures.items()},
              'native_successes': len(native), 'native_unchanged_delivery': False,
              'quality': 'not_assessed_by_this_audit'}
    for row in reversed(native):
        receipt = row['result']['result']
        if receipt['output_directory'] != str(PurePosixPath(png).parent):
            continue
        files = {file['path']: file for file in receipt['files']}
        if not all(path.name in files and files[path.name]['sha256'] == sha(path) for path in figures.values()):
            continue
        exported = receipt.get('reusable_program')
        if not exported:
            continue
        source = host(workspace, exported['path'])
        if sha(source) != exported['source_sha256']:
            raise ValueError('delivered_native_source_changed')
        call = trial / 'capability-calls' / row['call_id']
        manifest = json.loads((call / 'manifest.json').read_text())
        arguments = json.loads((call / 'args.json').read_text())
        programs = []
        for ref in manifest['libraries'] + manifest.get('artifact_libraries', []):
            library = Path(ref['path'])
            if sha(library) != ref['sha256']:
                raise ValueError('delivery_native_library_changed')
            programs += json.loads(library.read_text())['programs']
        program = next(item for item in programs if item['id'] == receipt['program_id'])
        if 'inputs' in arguments:
            inputs = [{'virtual': path, 'path': str(host(workspace, path)), 'sha256': sha(host(workspace, path))}
                      for path in arguments['inputs']]
            granted = {item['path']: item['sha256'] for item in manifest['inputs']}
            if any(granted.get(item['virtual']) != item['sha256'] for item in inputs):
                raise ValueError('delivery_granted_input_changed')
        else:
            sidecars = [item for item in row['result']['receipts'] if item.get('backend_receipt', {}).get('value_materialization')]
            exported_inputs = sidecars[0]['backend_receipt']['value_materialization']['exported_inputs']
            inputs = [{'virtual': item['path'], 'path': str(host(workspace, item['path'])), 'sha256': item['sha256']}
                      for item in sorted(exported_inputs, key=lambda item: item['input_slot'])]
            if any(sha(Path(item['path'])) != item['sha256'] for item in inputs):
                raise ValueError('delivery_value_input_changed')
        output.update(status='reproducible_native_delivery', native_unchanged_delivery=True,
                      source={'path': str(source), 'sha256': sha(source)}, inputs=inputs,
                      input_argument_indices=program['input_argument_indices'],
                      output_argument_index=program['output_argument_index'], native_call_id=row['call_id'])
        return output
    source = workspace / 'code/plot.py'
    parameter = workspace / 'code/plot-spec.json'
    if source.is_file() and parameter.is_file():
        output.update(status='ordinary_source_and_parameters_present',
                      source={'path': str(source), 'sha256': sha(source)},
                      inputs=[{'virtual': '/work/plot-spec.json', 'path': str(parameter), 'sha256': sha(parameter)}],
                      input_argument_indices=[0], output_argument_index=1)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.output.open('x') as stream:
        json.dump(audit(args.trial), stream, indent=2)
        stream.write('\n')
