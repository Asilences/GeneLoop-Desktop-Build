"""Offline research candidates, separate from the production privacy contract.

Inputs contain only id/dataset/phase/text. Gold annotations are scored by a
different process. No downloads, remote code, pickle weights or prefix scoring.
"""
import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_sources(root, spec):
    selected = ('gliner', 'backend') if spec in ('gliner', 'gliner_person') else ('openmed',)
    receipts = {}
    for name in selected:
        folder = root / name
        metadata = json.loads((folder / 'source-metadata.json').read_text())
        files = {}
        for path in folder.iterdir():
            if path.name == 'source-metadata.json':
                continue
            assert path.is_file() and path.suffix not in ('.py', '.bin', '.part')
            source = next(row for row in metadata['siblings'] if row['rfilename'] == path.name)
            assert path.stat().st_size == source['size'], path.name
            if 'lfs' in source:
                assert digest(path) == source['lfs']['sha256'], path.name
            else:
                data = path.read_bytes()
                assert hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == source['blobId'], path.name
            files[path.name] = digest(path)
        receipts[name] = {'repository': metadata['id'], 'revision': metadata['sha'], 'files_sha256': files}
    return receipts


def load_gliner(root, output, spec):
    from gliner import GLiNER
    from gliner.data_processing.tokenizer import SpaCyTokenSplitter
    from spacy.lang.zh import ChineseTokenizer
    runtime = output / 'runtime'
    runtime.mkdir()
    config = json.loads((root / 'gliner/gliner_config.json').read_text())
    config['model_name'] = str((root / 'backend').resolve())
    (runtime / 'gliner_config.json').write_text(json.dumps(config))
    (runtime / 'model.safetensors').symlink_to((root / 'gliner/model.safetensors').resolve())
    model = GLiNER.from_pretrained(str(runtime), strict=True, local_files_only=True, map_location='cpu')
    model.eval()
    english = model.data_processor.words_splitter
    chinese = SpaCyTokenSplitter(lang='zh')
    chinese.nlp.tokenizer = ChineseTokenizer(chinese.nlp.vocab, segmenter='jieba')
    labels = list(spec['labels'])

    def predict(text, dataset):
        model.data_processor.words_splitter = chinese if dataset.startswith('zh_') else english
        tokens, _, _ = model.prepare_texts([text])
        words = tokens[0]['tokenized_text']
        if len(words) > spec['max_words']:
            return [], 'evaluation_length_limit', {'words': len(words)}
        # Use precisely the same prompt and tokenizer as the official processor,
        # disabling truncation for this capacity check before official inference.
        entity_ids = {label: index + 1 for index, label in enumerate(labels)}
        prepared, _ = model.data_processor.prepare_inputs([words], entity_ids)
        assert not model.data_processor.preprocess_text
        encoded = model.data_processor.transformer_tokenizer(prepared, is_split_into_words=True, truncation=False)
        length = len(encoded['input_ids'][0])
        if length > spec['encoder_max_tokens']:
            return [], 'evaluation_length_limit', {'words': len(words), 'tokens': length}
        inputs, _ = model.prepare_model_inputs([text], labels)
        assert int(inputs['words_mask'].max()) == len(words), 'silent_token_truncation'
        found = model.predict_entities(text, labels, flat_ner=spec['flat_ner'], threshold=spec['threshold'])
        return [{'start': item['start'], 'end': item['end'], 'label': spec['labels'][item['label']]} for item in found], None, {'words': len(words), 'tokens': length}
    return predict, {'strict_state_dict': True, 'runtime_config_sha256': digest(runtime / 'gliner_config.json')}


def load_openmed(root, output, spec):
    from transformers import AutoConfig, AutoTokenizer, AutoModelForTokenClassification, pipeline
    folder = root / 'openmed'
    tokenizer = AutoTokenizer.from_pretrained(folder, local_files_only=True, trust_remote_code=False)
    config = AutoConfig.from_pretrained(folder, local_files_only=True, trust_remote_code=False)
    # Official CPU SDPA implementation avoids the optional CUDA/compile path.
    config.reference_compile = False
    model, info = AutoModelForTokenClassification.from_pretrained(
        folder, config=config, local_files_only=True, trust_remote_code=False,
        use_safetensors=True, output_loading_info=True, attn_implementation='sdpa')
    assert not any(info.get(key) for key in ('missing_keys', 'unexpected_keys', 'mismatched_keys', 'error_msgs')), info
    model.eval()
    assert spec['aggregation'] in ('simple', 'official Transformers token-classification pipeline simple')
    detector = pipeline('token-classification', model=model, tokenizer=tokenizer,
                        aggregation_strategy='simple', device=-1)

    def predict(text, dataset):
        length = len(tokenizer(text, truncation=False)['input_ids'])
        if length > spec['max_tokens']:
            return [], 'evaluation_length_limit', {'tokens': length}
        found = detector(text)
        spans = []
        unmapped = Counter()
        for item in found:
            if float(item['score']) < spec['threshold']:
                continue
            name = item['entity_group']
            if name in spec['labels']:
                spans.append({'start': int(item['start']), 'end': int(item['end']), 'label': spec['labels'][name]})
            else:
                unmapped[name] += 1
        return spans, None, {'tokens': length, 'unmapped_labels': dict(unmapped)}
    # Transformers 5 returns sets for empty key collections. Preserve their
    # contents in the JSON receipt rather than failing after valid inference.
    serializable_info = {name: sorted(value) if isinstance(value, set) else value for name, value in info.items()}
    return predict, {'loading_info': serializable_info, 'reference_compile': False, 'attention': 'sdpa'}


def load_gliner_person(root, output, spec):
    """Official Presidio adapter; capacity checks never perform recognition."""
    from presidio_analyzer.predefined_recognizers import GLiNERRecognizer
    from presidio_analyzer.chunkers import TokenizerBasedTextChunker
    from gliner.data_processing.tokenizer import SpaCyTokenSplitter
    from spacy.lang.zh import ChineseTokenizer

    assert spec['labels'] == {'person': 'PERSON'}
    runtime = output / 'runtime'
    runtime.mkdir()
    config = json.loads((root / 'gliner/gliner_config.json').read_text())
    config['model_name'] = str((root / 'backend').resolve())
    (runtime / 'gliner_config.json').write_text(json.dumps(config))
    (runtime / 'model.safetensors').symlink_to((root / 'gliner/model.safetensors').resolve())
    chunker = TokenizerBasedTextChunker(
        max_tokens=spec['chunk_tokens'], overlap_tokens=spec['overlap_tokens'])
    detector = GLiNERRecognizer(
        model_name=str(runtime), entity_mapping=spec['labels'],
        flat_ner=spec['flat_ner'], multi_label=False, threshold=spec['threshold'],
        map_location='cpu', text_chunker=chunker, strict=True, local_files_only=True)
    if detector.gliner is None:
        detector.load()
    model = detector.gliner
    model.eval()
    english = model.data_processor.words_splitter
    chinese = SpaCyTokenSplitter(lang='zh')
    chinese.nlp.tokenizer = ChineseTokenizer(chinese.nlp.vocab, segmenter='jieba')

    def predict(text, dataset):
        model.data_processor.words_splitter = chinese if dataset.startswith('zh_') else english
        chunks = chunker.chunk(text)
        covered = {i for chunk in chunks for i in range(chunk.start, chunk.end)}
        if any(not char.isspace() and index not in covered for index, char in enumerate(text)):
            return [], 'evaluation_chunk_coverage_gap', {'chunks': len(chunks)}
        capacities = []
        for chunk in chunks:
            prepared, _, _ = model.prepare_texts([chunk.text])
            words = prepared[0]['tokenized_text']
            if len(words) > spec['max_words']:
                return [], 'evaluation_length_limit', {'chunks': len(chunks), 'words': len(words)}
            prompt, _ = model.data_processor.prepare_inputs([words], {'person': 1})
            assert not model.data_processor.preprocess_text
            encoded = model.data_processor.transformer_tokenizer(
                prompt, is_split_into_words=True, truncation=False)
            length = len(encoded['input_ids'][0])
            if length > spec['encoder_max_tokens']:
                return [], 'evaluation_length_limit', {'chunks': len(chunks), 'tokens': length}
            inputs, _ = model.prepare_model_inputs([chunk.text], ['person'])
            assert int(inputs['words_mask'].max()) == len(words), 'silent_token_truncation'
            capacities.append(length)
        found = detector.analyze(text=text, entities=['PERSON'])
        return ([{'start': p.start, 'end': p.end, 'label': p.entity_type} for p in found],
                None, {'chunks': len(chunks), 'max_encoder_tokens': max(capacities, default=0)})

    return predict, {'strict_state_dict': True, 'official_adapter': 'presidio.GLiNERRecognizer',
                     'runtime_config_sha256': digest(runtime / 'gliner_config.json'),
                     'chunker': 'presidio.TokenizerBasedTextChunker',
                     'chunk_tokens': spec['chunk_tokens'], 'overlap_tokens': spec['overlap_tokens'],
                     'no_silent_truncation': True, 'labels': ['person']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--candidate', choices=('gliner', 'gliner_person', 'openmed'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('HF_HUB_OFFLINE') == '1' and os.environ.get('TRANSFORMERS_OFFLINE') == '1'
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    config = json.loads(args.config.read_text())
    spec = dict(config[args.candidate], threshold=config['threshold'])
    sources = verify_sources(args.models, args.candidate)
    source_name = 'gliner' if args.candidate == 'gliner_person' else args.candidate
    assert sources[source_name]['revision'] == spec['revision']
    if args.candidate in ('gliner', 'gliner_person'):
        assert sources['backend']['revision'] == spec['backend_revision']
    rows = [json.loads(line) for line in args.inputs.read_text().splitlines()]
    assert all(set(row) == {'id', 'dataset', 'phase', 'text'} for row in rows)
    manifest = {'candidate': args.candidate, 'sources': sources, 'rows': len(rows),
                'config_sha256': digest(args.config), 'inputs_sha256': digest(args.inputs),
                'runner_sha256': digest(Path(__file__)), 'gold_passed_to_detector': False,
                'truncation': False, 'versions': {name: importlib.metadata.version(name) for name in
                    ('torch', 'transformers', 'gliner', 'spacy', 'jieba', 'numpy', 'safetensors')}}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    import torch
    torch.set_num_threads(config['torch_threads'])
    torch.set_num_interop_threads(1)
    torch.manual_seed(0)
    started = time.perf_counter()
    try:
        loader = {'gliner': load_gliner, 'gliner_person': load_gliner_person, 'openmed': load_openmed}[args.candidate]
        predictor, loading = loader(args.models, args.output, spec)
    except Exception as exc:
        manifest.update(load_seconds=time.perf_counter() - started, load_error=type(exc).__name__, load_error_message=str(exc), available_rows=0)
        (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        raise
    manifest.update(load_seconds=time.perf_counter() - started, loading=loading)
    counts = Counter()
    with (args.output / 'predictions-private.jsonl').open('w') as stream:
        for index, row in enumerate(rows, 1):
            started = time.perf_counter()
            try:
                with torch.inference_mode():
                    spans, error, capacity = predictor(row['text'], row['dataset'])
                assert all(0 <= span['start'] < span['end'] <= len(row['text']) for span in spans)
            except Exception as exc:
                spans, error, capacity = [], type(exc).__name__, {}
            result = {key: row[key] for key in ('id', 'dataset', 'phase')}
            result.update(pred=spans, error=error, capacity=capacity, seconds=time.perf_counter() - started)
            stream.write(json.dumps(result) + '\n')
            counts[error or 'available'] += 1
            if index % 25 == 0:
                stream.flush()
                print(json.dumps({'candidate': args.candidate, 'completed': index, 'counts': dict(counts)}), flush=True)
    manifest.update(status_counts=dict(counts), available_rows=counts['available'])
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
