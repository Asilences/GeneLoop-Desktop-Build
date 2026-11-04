"""CLI material inheritance diagnostics with original stores and injected backends."""
from contextlib import contextmanager
import json
from types import SimpleNamespace

import pytest

from src.adapters.benchmark_script_materials import BenchmarkScriptMaterials
from src.adapters.capability_feedback import verify
from tests.test_benchmark_script_materials import data
from tests.test_evolution_benchmark import script_module


OWNER = 'overnight-research'


def continuation(directory, *, snapshot=None):
    return {'format': 'gene_benchmark_continuation_v1', 'owner': OWNER,
            'snapshot': snapshot or {'roots': []},
            'material_configuration': {'owner': OWNER, 'directory': str(directory),
                                       'publication_store': str(directory / 'publication-store')}}


@pytest.mark.parametrize('sibling_code_roots', [False, True])
def test_cli_reopens_original_material_store_and_passes_actual_library_to_native_backend(tmp_path, monkeypatch, data, sibling_code_roots):
    import src.adapters.benchmark_script_materials as native
    import src.adapters.evolution_benchmark_gene as gene
    module = script_module()
    code_root = tmp_path / '.local/code-r5' if sibling_code_roots else tmp_path
    code_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(module, 'ROOT', code_root)
    original, program, examples, source, calls = data
    directory = tmp_path / '.local/code-r4/.local/materials' if sibling_code_roots else tmp_path / '.local/original-materials'
    pool = BenchmarkScriptMaterials(OWNER, directory, learn=original._learn,
                                   catalog=original._catalog, execute=original._execute)
    acquired = pool.acquire(program, examples, source, 'diagnostic-real-store')
    config = continuation(directory, snapshot=acquired['snapshot'])
    prior = tmp_path / '.local/continuation.json'
    prior.write_text(json.dumps(config))
    opened = []
    @contextmanager
    def gate(_root):
        yield SimpleNamespace(state=SimpleNamespace(reserved_usd=0, request_count=0))
    def materials(owner, root, **kwargs):
        value = BenchmarkScriptMaterials(owner, root, catalog=original._catalog,
                                        execute=original._execute, **kwargs)
        opened.append(value)
        return value
    def run(host, **kwargs):
        assert host.materials.directory == directory.resolve()
        assert host.materials.materials.records()[0]['library'] == acquired['library']
        assert host.materials.catalog()['snapshot'] == acquired['snapshot']
        host.materials.execute(acquired['value_refs'][0], {'data': {'items': [1, 2]}},
                               tmp_path / '.local/actual-native-call', 'next-task')
        assert calls['execute'][-1]['libraries'] == [acquired['library']]
        assert kwargs['snapshot'] == acquired['snapshot']
        return {'status': 'completed', 'diagnostic': True}
    monkeypatch.setattr(native, 'BenchmarkScriptMaterials', materials)
    monkeypatch.setattr(module, 'CumulativeProposalGate', gate)
    monkeypatch.setattr(module, 'BenchmarkHost', lambda *args, **kwargs: SimpleNamespace(materials=kwargs['materials']))
    monkeypatch.setattr(gene, 'run_gene_benchmark', run)
    output = code_root / '.local/next-generation'
    monkeypatch.setattr(module.sys, 'argv', ['run', '--training-root', str(tmp_path / 'train'),
        '--test-root', str(tmp_path / 'test'), '--source-version', 'fixed', '--ledger-root', str(tmp_path / '.local/ledger'),
        '--output', str(output), '--task', 'fresh-task', '--mode', 'geneloop', '--continuation', str(prior), '--call-model'])
    before = prior.read_bytes()
    module.main()
    assert len(opened) == 1 and opened[0].directory == pool.directory
    assert not (output / 'materials').exists()
    assert prior.read_bytes() == before
    effective = json.loads((output / 'effective.json').read_text())
    assert effective['material_configuration'] == config['material_configuration']


def test_explicit_conflicting_root_cannot_silently_drop_inherited_pool(tmp_path, monkeypatch):
    module = script_module()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    directory = tmp_path / '.local/pool'
    directory.mkdir(parents=True)
    with pytest.raises(ValueError, match='root_conflict'):
        module.material_configuration(continuation(directory), tmp_path / '.local/empty-pool', tmp_path / '.local/run')


def test_legacy_nonempty_snapshot_requires_explicit_material_root(tmp_path, monkeypatch):
    module = script_module()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    legacy = {'format': 'gene_benchmark_continuation_v1', 'owner': OWNER, 'snapshot': {'roots': [{'id': 'C'}]}}
    with pytest.raises(ValueError, match='legacy_material_root_required'):
        module.material_configuration(legacy, None, tmp_path / '.local/run')
    directory = tmp_path / '.local/original-pool'
    assert module.material_configuration(legacy, directory, tmp_path / '.local/run')['directory'] == str(directory)


@pytest.mark.parametrize('field', ['owner', 'directory'])
def test_inherited_owner_and_private_root_checks_remain_effective(tmp_path, monkeypatch, field):
    module = script_module()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    directory = tmp_path / '.local/pool'
    directory.mkdir(parents=True)
    config = continuation(directory)
    if field == 'owner':
        config['material_configuration']['owner'] = 'another-owner'
    else:
        outside = tmp_path / 'public-pool'
        outside.mkdir()
        config['material_configuration']['directory'] = str(outside)
        config['material_configuration']['publication_store'] = str(outside / 'publication-store')
    with pytest.raises(ValueError, match='configuration_invalid' if field == 'owner' else 'private_material_root_required'):
        module.material_configuration(config, None, tmp_path / '.local/run')


def test_missing_inherited_directory_is_not_recreated_as_empty_pool(tmp_path, monkeypatch):
    module = script_module()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    directory = tmp_path / '.local/missing-pool'
    with pytest.raises(ValueError, match='inherited_material_directory_missing'):
        module.material_configuration(continuation(directory), None, tmp_path / '.local/run')
    assert not directory.exists()


def test_generation_records_original_backend_and_custom_publication_configuration(tmp_path):
    from tests.test_evolution_benchmark_gene import NativeHost, run
    host = NativeHost(tmp_path / 'trials')
    host.materials.directory = tmp_path / '.local/pool'
    host.materials.directory.mkdir(parents=True)
    host.materials.publication_store = tmp_path / '.local/custom-publication/store'
    result = run(tmp_path, host)
    configured = json.loads(verify(result['continuation']))['material_configuration']
    assert configured == {'owner': OWNER, 'directory': str(host.materials.directory),
                          'publication_store': str(host.materials.publication_store)}
    assert json.loads((tmp_path / 'generation/effective.json').read_text())['material_configuration'] == configured


def test_legacy_explicit_empty_pool_cannot_satisfy_inherited_snapshot(tmp_path, monkeypatch, data):
    import src.adapters.benchmark_script_materials as native
    module = script_module()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    original, program, examples, source, _ = data
    pool = BenchmarkScriptMaterials(OWNER, tmp_path / '.local/original-pool', learn=original._learn,
                                   catalog=original._catalog, execute=original._execute)
    acquired = pool.acquire(program, examples, source, 'diagnostic-real-store')
    legacy = {'format': 'gene_benchmark_continuation_v1', 'owner': OWNER, 'snapshot': acquired['snapshot']}
    prior = tmp_path / '.local/legacy.json'
    prior.write_text(json.dumps(legacy))
    @contextmanager
    def gate(_root):
        yield SimpleNamespace(state=SimpleNamespace(reserved_usd=0, request_count=0))
    def materials(owner, directory, **kwargs):
        return BenchmarkScriptMaterials(owner, directory, catalog=original._catalog, **kwargs)
    monkeypatch.setattr(native, 'BenchmarkScriptMaterials', materials)
    monkeypatch.setattr(module, 'CumulativeProposalGate', gate)
    hosts = []
    monkeypatch.setattr(module, 'BenchmarkHost', lambda *args, **kwargs: hosts.append(kwargs))
    output = tmp_path / '.local/next-generation'
    monkeypatch.setattr(module.sys, 'argv', ['run', '--training-root', str(tmp_path / 'train'),
        '--test-root', str(tmp_path / 'test'), '--source-version', 'fixed', '--ledger-root', str(tmp_path / '.local/ledger'),
        '--output', str(output), '--task', 'fresh-task', '--mode', 'geneloop', '--continuation', str(prior),
        '--materials-root', str(tmp_path / '.local/empty-pool'), '--call-model'])
    with pytest.raises(ValueError, match='inherited_material_backend_missing'):
        module.main()
    assert hosts == []
    assert json.loads((output / 'result.json').read_text())['status'] == 'failed'
