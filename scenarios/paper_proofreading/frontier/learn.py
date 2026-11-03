"""Compatibility alias; implementation lives in the shared Script adapter."""
import sys
from src.adapters import capability_script_learning as _implementation

# Preserve legacy module-level injections and function globals as one module.
sys.modules[__name__] = _implementation
