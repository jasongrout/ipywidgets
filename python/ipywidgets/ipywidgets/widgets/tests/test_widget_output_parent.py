# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

"""Regression tests for the parent-request handling added in ipywidgets#4021.

https://github.com/jupyter-widgets/ipywidgets/pull/4021 made
``Output.__enter__`` resolve a parent request (shell parent, falling back to
the kernel parent) and pin it on the calling thread via ``ip.set_parent()``
so that stream output produced in background threads is attributed to the
captured cell.

These tests document problems with that change.  Each test asserts the
*correct* behavior and is marked ``xfail(strict=True)`` where current main
gets it wrong, so the suite stays green while the bugs are open and fails
loudly (XPASS) once a fix lands, prompting removal of the marker.

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

import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
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
# Point 1: ip.set_parent() from a background thread rewrites the
# process-global parent fallback, so output from *unrelated* threads is
# attributed to the captured cell.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="ipywidgets#4021: Output.__enter__ calls ip.set_parent() from the "
           "capturing thread; ipykernel's set_parent also rewrites the "
           "process-global fallback, misattributing other threads' output",
)
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

        # Thread A keeps looping; its own pinned context still holds cell 2,
        # and re-entering rewrites the global fallback back to cell 2.
        thread_a.submit(_capture_once, widget).result()

        # Thread B is unrelated to the widget and never pinned a parent, so
        # its print() must be attributed to the current cell, cell 3.
        observed = thread_b.submit(shell.resolve_output_parent).result()
        assert observed == cell3, (
            "output from an unrelated thread was attributed to the captured "
            "cell: %r" % (observed,)
        )


# ---------------------------------------------------------------------------
# Point 2: __exit__ never restores the parent that __enter__ overrode, so the
# override leaks past the `with` block.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="ipywidgets#4021: __exit__ only decrements the counter and clears "
           "msg_id; the ip.set_parent() override from __enter__ is never "
           "undone, so it outlives the with block",
)
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

        # A print() in thread A *after* the with block should behave as it
        # did before the block: the thread never pinned a parent itself, so
        # attribution follows the most recent cell.  Instead the pin from
        # __enter__ is still in place.
        observed = thread_a.submit(shell.resolve_output_parent).result()
        assert observed == cell3, (
            "the parent pinned inside the with block leaked past __exit__: "
            "%r" % (observed,)
        )


# ---------------------------------------------------------------------------
# Point 3: a parent grabbed from a different, currently-executing cell gets
# pinned to the thread instead of staying transient.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="ipywidgets#4021: a foreign cell's parent captured at __enter__ is "
           "pinned to the thread by ip.set_parent(), so the misattribution "
           "outlives the foreign cell instead of correcting itself",
)
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

        # Cell 4 runs later.  Before #4021 the grab was transient: the next
        # tick follows the newest cell.  With the set_parent pin, the ticker
        # re-reads cell 3 from its own context forever.
        shell.execute_request(cell4)
        observed = ticker.submit(_capture_once, widget).result()
        assert observed == 'cell4', (
            "the ticker thread is still attributed to the long-finished "
            "foreign cell: %r" % (observed,)
        )


# ---------------------------------------------------------------------------
# Point 4: a truthy, header-*shaped* shell parent (a header dict, not a full
# request — exactly what ipykernel display publishers store) is committed
# before the `.get("header")` shape check, which (a) blocks the working
# kernel fallback and (b) unbalances the enter/exit counter.
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


@pytest.mark.xfail(
    strict=True,
    reason="ipywidgets#4021: a truthy shell parent is committed before the "
           "'header' shape check, so a header-shaped parent blocks the "
           "working kernel fallback and capture is silently disabled",
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


@pytest.mark.xfail(
    strict=True,
    reason="ipywidgets#4021: __exit__ decrements unconditionally even when "
           "__enter__ did not increment; the counter goes negative and "
           "msg_id is never cleared again",
)
def test_counter_stays_balanced_when_enter_does_not_capture():
    # No usable parent anywhere: the shell parent is header-shaped (truthy,
    # fails the "header" check) and the kernel has none.
    shell = _shell_with_static_parents(HEADER_ONLY, None)

    with _patched_shell(shell):
        widget = widget_output.Output()

        # Capture is (silently) disabled for this block, so __enter__ never
        # increments the counter — but __exit__ still decrements it.
        with widget:
            first = widget.msg_id
        assert first == ''

        # The shell recovers and returns a full request.
        shell.get_parent = lambda: FULL_REQUEST
        with widget:
            second = widget.msg_id
        assert second == 'cell-1'
        # On main the counter went 0 -> -1 -> 0 -> -1, so the
        # `if self.__counter == 0` cleanup never fires again and msg_id is
        # stuck at 'cell-1' forever: every cell-1-parented message keeps
        # being captured by the widget.
        assert widget.msg_id == '', "msg_id must be cleared after the block"


# ---------------------------------------------------------------------------
# Point 5: the kernel-fallback branch of __enter__ was untested — the new
# test added by #4021 mocks kernel.get_parent but its shell get_parent always
# returns a truthy parent, so the fallback is never entered.  This test
# passes on main; it adds the missing coverage (no xfail).
# ---------------------------------------------------------------------------

def test_set_parent_falls_back_to_kernel_parent():
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

    # set_parent received the kernel's parent request.
    assert parent_calls == [kernel_parent]
