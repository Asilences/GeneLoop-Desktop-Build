"""Request-scoped, content-free local diagnostics; never a tool response."""
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter

_ACTIVE = ContextVar('privacy_diagnostics', default=None)


@contextmanager
def observe_privacy():
    rows = []
    token = _ACTIVE.set(rows)
    try:
        yield rows
    finally:
        _ACTIVE.reset(token)


@contextmanager
def privacy_stage(name):
    rows = _ACTIVE.get()
    if rows is None:
        yield
        return
    started = perf_counter()
    row = {'stage': name}
    try:
        yield
    except Exception as error:
        row['error_type'] = type(error).__name__
        raise
    finally:
        row['seconds'] = perf_counter() - started
        rows.append(row)
