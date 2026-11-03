"""Same file capacity as the Web adapter; image validation belongs to DSH."""
import json
from pathlib import Path
_limits = json.loads(Path(__file__).with_suffix('.json').read_text())
assert _limits['schema_version'] == 1
FILE_MAX_BYTES = _limits['file_max_bytes']
assert isinstance(FILE_MAX_BYTES, int) and FILE_MAX_BYTES > 0
