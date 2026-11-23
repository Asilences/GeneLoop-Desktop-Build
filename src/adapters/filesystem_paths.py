"""Pathlib semantics with Windows extended paths only at the filesystem boundary.

Stored paths, hashes and account-containment comparisons keep their normal
spelling. No registry changes, directory aliases or global monkey-patches.
"""
from __future__ import annotations

import ntpath
import os
import sys
from pathlib import Path as NativePath, PurePath, WindowsPath


def windows_io_path(value: str) -> str:
    """Use the native long-path namespace, including network shares."""
    value = ntpath.abspath(value)
    if value.startswith('\\\\?\\'):
        return value
    if value.startswith('\\\\'):
        return '\\\\?\\UNC\\' + value[2:]
    return '\\\\?\\' + value


def windows_logical_path(value: str) -> str:
    if value.lower().startswith('\\\\?\\unc\\'):
        return '\\\\' + value[8:]
    if value.startswith('\\\\?\\') and len(value) > 6 and value[5:7] == ':\\':
        return value[4:]
    return value


if os.name == 'nt':
    def _logical_parts(parts):
        return tuple(windows_logical_path(str(part) if isinstance(part, PurePath) else os.fspath(part)) for part in parts)

    class Path(WindowsPath):
        """Keep logical paths unchanged while using Unicode Win32 file APIs."""
        def __new__(cls, *parts):
            return super().__new__(cls, *_logical_parts(parts))

        def __init__(self, *parts):
            # pathlib moved argument initialization into __init__ in 3.12.
            if sys.version_info >= (3, 12):
                super().__init__(*_logical_parts(parts))

        def __fspath__(self) -> str:
            return windows_io_path(str(self))

        def resolve(self, strict=False):
            return type(self)(windows_logical_path(str(super().resolve(strict=strict))))

        def rename(self, target):
            target = type(self)(target)
            os.rename(self, target)
            return target

        def replace(self, target):
            target = type(self)(target)
            os.replace(self, target)
            return target
else:
    Path = NativePath
