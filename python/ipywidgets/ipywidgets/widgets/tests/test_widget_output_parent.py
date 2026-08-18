# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

"""Regression tests for the parent-request handling added in ipywidgets#4021.

https://github.com/jupyter-widgets/ipywidgets/pull/4021 made
``Output.__enter__`` resolve a parent request (shell parent, falling back to
the kernel parent) and pin it on the calling thread via ``ip.set_parent()``
so that stream output produced in background threads is attributed to the
captured cell.

That approach had several problems, fixed in this PR by resolving the
calling thread's *effective* stream parent and pinning it thread-scoped
with ContextVar tokens that ``__exit__`` resets, never touching the shell's
``set_parent`` (see widget_output.py).  Each test here asserts the correct
behavior; before the fix they failed as noted in the individual docstrings.

The threading tests emulate ipykernel's parent bookkeeping (verified against
ipykernel 6.29.5 sources and empirically against 7.3.0):

* ``shell.get_parent()`` / ``OutStream.parent_header`` read a per-thread
  ContextVar and fall back to a process-global value for threads that never
  set their own (a fresh thread's ContextVar lookup raises ``LookupError``).
* ``shell.set_parent(parent)`` fans out to the displayhook, display publisher
  and ``sys.stdout``/``sys.stderr``; each setter writes the calling thread's
  ContextVar *and* the process-global fallback (e.g.
  ``OutStream._parent_header_global``).

That global write is the crux: ``set_parent`` called from a worker thread is
visible to every thread that has not pinned its own parent.
"""

import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from types import SimpleNamespace

import pytest

from ipywidgets import widget_output


def request(msg_id):
    """A minimal parent request, as stored by ipykernel."""
    return {'header': {'msg_id': msg_id}}


class FakeInteractiveShell:
    """Stand-in for ZMQInteractiveShell's parent handling (ipykernel >= 7).

    ``get_parent`` resolves the calling thread's pinned parent, falling back
    to the process-global one; ``set_parent`` writes both, mirroring
    ipykernel's ContextVar-plus-global-fallback pattern described in the
    module docstring.
    """

    def __init__(self):
        self._thread_parent = threading.local()
        self._global_parent = None
        # Kernel fallback used by Output.__enter__ when the shell parent is
        # falsy; points 1-3 never reach it but the attribute must exist.
        self.kernel = SimpleNamespace(get_parent=lambda: self._global_parent)

    def get_parent(self):
        return getattr(self._thread_parent, 'value', None) or self._global_parent

    def set_parent(self, parent):
        self._thread_parent.value = parent
        self._global_parent = parent

    def resolve_output_parent(self):
        """The parent a print() in the calling thread is attributed to.

        ``OutStream.parent_header`` follows the same
        ContextVar-with-global-fallback rule as ``get_parent``.
        """
        return self.get_parent()

    def execute_request(self, parent):
        """Simulate the kernel dispatching a cell execution.

        ``Kernel.execute_request`` calls ``shell.set_parent(parent)`` on the
        shell thread before running the cell, which is what resets the
        global fallback each time a new cell starts.
        """
        self.set_parent(parent)

    def showtraceback(self, exc_tuple, *args, **kwargs):
        # Re-raise so exceptions inside `with widget:` surface in the test
        # instead of being swallowed by Output.__exit__.
        etype, evalue, tb = exc_tuple
        raise evalue.with_traceback(tb)


@contextmanager
def _patched_shell(shell):
    """Point widget_output's get_ipython/clear_output at our fakes."""
    original_get_ipython = widget_output.get_ipython
    original_clear_output = widget_output.clear_output
    widget_output.get_ipython = lambda: shell
    widget_output.clear_output = lambda *args, **kwargs: None
    try:
        yield
    finally:
        widget_output.get_ipython = original_get_ipython
        widget_output.clear_output = original_clear_output


@contextmanager
def _worker_threads(count):
    """Persistent single-threaded executors for deterministic interleaving.

    Each executor runs everything submitted to it on one long-lived thread,
    so a sequence of ``.result()`` calls acts out an exact schedule across
    threads.
    """
    executors = [ThreadPoolExecutor(max_workers=1) for _ in range(count)]
    try:
        yield executors
    finally:
        for executor in executors:
            executor.shutdown(wait=True)


def _capture_once(widget):
    """One `with widget:` block; returns the msg_id observed inside."""
    with widget:
        return widget.msg_id


# ---------------------------------------------------------------------------
# Point 1: capturing from a background thread must not rewrite the
# process-global parent fallback that *unrelated* threads resolve against.
# (Regression: ip.set_parent() from the capturing thread did exactly that.)
# ---------------------------------------------------------------------------

def test_capture_does_not_clobber_other_threads_parent():
    shell = FakeInteractiveShell()
    cell2, cell3 = request('cell2'), request('cell3')

    with _patched_shell(shell), _worker_threads(2) as (thread_a, thread_b):
        widget = widget_output.Output()

        # Cell 2 executes and starts thread A, which loops `with widget:`.
        shell.execute_request(cell2)
        assert thread_a.submit(_capture_once, widget).result() == 'cell2'

        # Cell 3 is dispatched on the shell thread.
        shell.execute_request(cell3)

        # Thread A keeps looping.  (The regression: re-entering rewrote the
        # global fallback back to cell 2 via ip.set_parent.)
        thread_a.submit(_capture_once, widget).result()

        # Thread B is unrelated to the widget and never pinned a parent, so
        # its print() must be attributed to the current cell, cell 3.
        observed = thread_b.submit(shell.resolve_output_parent).result()
        assert observed == cell3, (
            "output from an unrelated thread was attributed to the captured "
            "cell: %r" % (observed,)
        )


# ---------------------------------------------------------------------------
# Point 2: __exit__ must restore whatever __enter__ overrode; the override
# must not leak past the `with` block.
# ---------------------------------------------------------------------------

def test_parent_override_does_not_outlive_the_block():
    shell = FakeInteractiveShell()
    cell2, cell3 = request('cell2'), request('cell3')

    with _patched_shell(shell), _worker_threads(1) as (thread_a,):
        widget = widget_output.Output()

        # Cell 2 executes and starts thread A, which captures exactly once.
        shell.execute_request(cell2)
        assert thread_a.submit(_capture_once, widget).result() == 'cell2'

        # Cell 3 runs later.
        shell.execute_request(cell3)

        # A print() in thread A *after* the with block must behave as it did
        # before the block: the thread never pinned a parent itself, so
        # attribution follows the most recent cell.
        observed = thread_a.submit(shell.resolve_output_parent).result()
        assert observed == cell3, (
            "the parent pinned inside the with block leaked past __exit__: "
            "%r" % (observed,)
        )


# ---------------------------------------------------------------------------
# Point 3: a parent grabbed from a different, currently-executing cell must
# stay transient — it must not be pinned to the thread across blocks.
# ---------------------------------------------------------------------------

def test_foreign_cell_parent_is_not_pinned_across_blocks():
    shell = FakeInteractiveShell()
    cell3, cell4 = request('cell3'), request('cell4')

    with _patched_shell(shell), _worker_threads(1) as (ticker,):
        widget = widget_output.Output()

        # A slow foreground cell 3 is executing while a long-lived ticker
        # thread re-enters the context.  The ticker grabs cell 3's request —
        # a pre-existing (pre-#4021) transient misattribution.
        shell.execute_request(cell3)
        assert ticker.submit(_capture_once, widget).result() == 'cell3'

        # Cell 4 runs later.  The grab must be transient: the next tick
        # follows the newest cell.  (The regression: the set_parent pin made
        # the ticker re-read cell 3 from its own context forever.)
        shell.execute_request(cell4)
        observed = ticker.submit(_capture_once, widget).result()
        assert observed == 'cell4', (
            "the ticker thread is still attributed to the long-finished "
            "foreign cell: %r" % (observed,)
        )


# ---------------------------------------------------------------------------
# Point 4: a truthy, header-*shaped* shell parent (a header dict, not a full
# request — exactly what ipykernel display publishers store) must not shadow
# the working kernel fallback, and a block that captured nothing must not
# unbalance the enter/exit counter.
# ---------------------------------------------------------------------------

HEADER_ONLY = {'msg_id': 'cell-1', 'msg_type': 'execute_request'}
FULL_REQUEST = {'header': {'msg_id': 'cell-1'}}


def _reraise_traceback(exc_tuple, *args, **kwargs):
    etype, evalue, tb = exc_tuple
    raise evalue.with_traceback(tb)


def _shell_with_static_parents(shell_parent, kernel_parent):
    return SimpleNamespace(
        kernel=SimpleNamespace(get_parent=lambda: kernel_parent),
        get_parent=lambda: shell_parent,
        set_parent=lambda parent: None,
        showtraceback=_reraise_traceback,
    )


def test_header_shaped_shell_parent_does_not_block_kernel_fallback():
    shell = _shell_with_static_parents(HEADER_ONLY, FULL_REQUEST)

    with _patched_shell(shell):
        widget = widget_output.Output()
        with widget:
            observed = widget.msg_id
        # The header-shaped shell parent is not a usable request; the kernel
        # fallback holds a full request for the same cell and should have
        # been used.
        assert observed == 'cell-1', "capture was silently disabled"


def test_counter_stays_balanced_when_enter_does_not_capture():
    # No usable parent anywhere: the shell parent is header-shaped (truthy,
    # fails the "header" check) and the kernel has none.
    shell = _shell_with_static_parents(HEADER_ONLY, None)

    with _patched_shell(shell):
        widget = widget_output.Output()

        # Capture is disabled for this block, so __enter__ never increments
        # the counter — __exit__ must not decrement either.
        with widget:
            first = widget.msg_id
        assert first == ''

        # The shell recovers and returns a full request; the counter must
        # balance so the msg_id cleanup fires after the block.
        shell.get_parent = lambda: FULL_REQUEST
        with widget:
            second = widget.msg_id
        assert second == 'cell-1'
        assert widget.msg_id == '', "msg_id must be cleared after the block"


# ---------------------------------------------------------------------------
# Point 5: the kernel-fallback branch of __enter__ (no active shell parent).
# Capture must work from the kernel's parent request alone, and the widget
# must never call the shell-wide ip.set_parent — that mutation (which also
# rewrites ipykernel's process-global fallbacks) caused points 1-3.
# ---------------------------------------------------------------------------

def test_capture_works_without_shell_parent_api():
    """Kernels that are not ipykernel must keep working, with no set_parent.

    Mirrors the surface of a real xeus-python kernel (verified against
    xeus-python 0.19.0 / xeus 6.0.5): the shell is a plain IPython
    ``InteractiveShell`` subclass with **no** ``get_parent``/``set_parent``,
    and ``shell.kernel`` exposes ``get_parent()`` returning a full parent
    request.  Capture must work via the kernel fallback alone and must not
    require any parent-mutation API, so the thread-aware parent handling
    cannot regress non-ipykernel kernels.
    """
    kernel_parent = {'header': {'msg_id': 'xeus-cell-1'}}

    # No get_parent/set_parent on the shell -- only kernel.get_parent().
    shell = SimpleNamespace(
        kernel=SimpleNamespace(get_parent=lambda: kernel_parent),
        showtraceback=_reraise_traceback,
    )

    with _patched_shell(shell):
        widget = widget_output.Output()
        with widget:
            observed = widget.msg_id
        assert observed == 'xeus-cell-1'
        assert widget.msg_id == ''


def test_falls_back_to_kernel_parent_without_set_parent():
    kernel_parent = {'header': {'msg_id': 'kernel-msg-id'}}
    parent_calls = []

    shell = SimpleNamespace(
        kernel=SimpleNamespace(get_parent=lambda: kernel_parent),
        get_parent=lambda: None,  # no active shell parent
        set_parent=parent_calls.append,
        showtraceback=_reraise_traceback,
    )

    with _patched_shell(shell):
        widget = widget_output.Output()
        with widget:
            observed = widget.msg_id
        assert observed == 'kernel-msg-id'
        assert widget.msg_id == ''

    # The shell-wide set_parent must never be called.
    assert parent_calls == []


# ---------------------------------------------------------------------------
# The fix's pinning mechanics: the widget pins the calling thread's stream
# parent via the ContextVar ipykernel exposes on OutStream, and resets it
# with the saved token on exit — thread-scoped and exactly reversible.
# ---------------------------------------------------------------------------

class FakeOutStream:
    """Duck-types the parent handling of ipykernel's OutStream."""

    def __init__(self):
        self._parent_header = ContextVar('parent_header')

    @property
    def parent_header(self):
        try:
            return self._parent_header.get()
        except LookupError:
            return {}

    def flush(self):
        pass


@contextmanager
def _patched_stdout(stream):
    original = sys.stdout
    sys.stdout = stream
    try:
        yield
    finally:
        sys.stdout = original


@pytest.mark.skip(reason="Re-enable (with the widget-side support) once "
                         "ipython/ipykernel#1546 is merged")
def test_prefers_public_thread_parent_api():
    """With ipykernel's public thread-scoped parent API (ipykernel#1546),
    the widget delegates pinning entirely: ``ip.set_thread_parent(parent)``
    on enter (passing the full parent request), ``ip.reset_thread_parent``
    with the returned tokens on exit — and it never calls the shell-wide
    ``set_parent`` or touches ContextVars itself.
    """
    request_obj = {'header': {'msg_id': 'cell-1'}}
    tokens = object()
    calls = []

    shell = SimpleNamespace(
        kernel=SimpleNamespace(get_parent=lambda: request_obj),
        get_parent=lambda: request_obj,
        set_parent=lambda parent: calls.append(('set_parent', parent)),
        set_thread_parent=lambda parent: (calls.append(('set', parent)), tokens)[1],
        reset_thread_parent=lambda t: calls.append(('reset', t)),
        showtraceback=_reraise_traceback,
    )

    with _patched_shell(shell):
        widget = widget_output.Output()
        with widget:
            assert widget.msg_id == 'cell-1'
        assert widget.msg_id == ''

    # Full request in, same opaque tokens back out; set_parent never called.
    assert calls == [('set', request_obj), ('reset', tokens)]


def test_pins_and_restores_thread_stream_parent():
    stream = FakeOutStream()
    shell = _shell_with_static_parents(FULL_REQUEST, None)

    with _patched_shell(shell), _patched_stdout(stream):
        widget = widget_output.Output()
        with widget:
            # Inside the block the stream's per-thread parent is pinned to
            # the captured header, so this thread's output carries the same
            # parent msg_id the frontend hook matches on.
            assert stream.parent_header == FULL_REQUEST['header']
            assert widget.msg_id == 'cell-1'
        # On exit the pin is reverted exactly (ContextVar token reset):
        # the thread is back to its pre-block state, not overwritten with
        # some other value.
        assert stream.parent_header == {}


def test_prefers_thread_stream_parent_over_shell_parent():
    # The stream's per-thread parent (e.g. ipykernel 6's thread-ancestry
    # attribution) is what the thread's output actually carries, so it wins
    # over the shell's (potentially process-global, newest-cell) parent.
    stream = FakeOutStream()
    stream._parent_header.set({'msg_id': 'thread-own-cell'})
    shell = _shell_with_static_parents({'header': {'msg_id': 'newest-cell'}}, None)

    with _patched_shell(shell), _patched_stdout(stream):
        widget = widget_output.Output()
        with widget:
            assert widget.msg_id == 'thread-own-cell'
        assert widget.msg_id == ''
