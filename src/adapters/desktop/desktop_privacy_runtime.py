"""Native dependency loading; shared privacy policy and scanners stay unchanged."""
import os
import sys

from src.adapters.filesystem_paths import Path


def prepare(site):
    site = Path(site)
    if not site.is_dir():
        return
    # Imports traverse deeply nested country recognizers even before NLP starts.
    # Keep the Win32 extended namespace at the actual filesystem boundary.
    location = os.fspath(site)
    if location not in sys.path:
        sys.path.insert(0, location)
    if os.name != 'nt':
        return
    # Presidio constructs its default configuration using ../conf. Win32 does
    # not normalize '..' in extended paths. Reuse our normalizing Path only in
    # those resource loaders, without replacing pathlib/open process-wide or
    # changing vendor bytes, recognizers, configuration or model selection.
    from presidio_analyzer import analyzer_engine_provider
    from presidio_analyzer.nlp_engine import nlp_engine_provider
    from presidio_analyzer.recognizer_registry import recognizers_loader_utils
    for module in (analyzer_engine_provider, nlp_engine_provider, recognizers_loader_utils):
        module.Path = Path
