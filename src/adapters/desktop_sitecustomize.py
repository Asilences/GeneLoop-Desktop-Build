"""Installed as source/sitecustomize.py only in the native offline bundle."""
import os
if os.environ.get('GENELOOP_NATIVE_SKILL_RUNTIME') == '1':
    from src.adapters.desktop_skill_runtime import install
    install()
