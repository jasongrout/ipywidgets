# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

"""Real-kernel regression tests for the Output widget's parent handling.

Unlike test_widget_output_parent.py (which emulates ipykernel with mocks),
these tests start an actual ipykernel via jupyter_client, replay the
multi-threaded notebook scenarios that broke with the ``ip.set_parent()``
approach of ipywidgets#4021, and assert on the parent attribution of the
iopub messages the kernel really publishes.

The scenarios are driven by threading.Events set from later cells, so the
interleaving of cells and background threads is exact — no sleeps, no timing
races.

ipykernel 6 and 7 attribute background-thread output differently, and the
assertions account for both:

* ipykernel >= 7: ``OutStream.parent_header`` is a per-thread ContextVar
  falling back to a process-global value.  A fresh thread resolves the
  global (the newest cell); the widget pins the thread's ContextVar only
  for the duration of a capture block and restores it on exit.
* ipykernel 6: additionally tracks, for every thread, the cell that spawned
  it (``OutStream._thread_to_parent_header``, populated by a
  ``threading.Thread`` monkeypatch) and attributes thread output to that
  cell.  Outside capture blocks that correct ancestry attribution must be
  left untouched.
"""

import time
from queue import Empty

import pytest

jupyter_client = pytest.importorskip('jupyter_client')
ipykernel = pytest.importorskip('ipykernel')

IPYKERNEL_MAJOR = int(ipykernel.__version__.split('.')[0])
TIMEOUT = 60


class KernelHarness:
    """A real kernel plus bookkeeping mapping msg_ids to cell labels."""

    def __init__(self):
        from jupyter_client.manager import start_new_kernel
        self.km, self.kc = start_new_kernel(startup_timeout=120)
        self.cells = {}     # execute_request msg_id -> label
        self.msgs = []      # every iopub message seen so far

    def shutdown(self):
        self.kc.stop_channels()
        self.km.shutdown_kernel(now=True)

    def run(self, label, code):
        """Execute a cell and wait for its execute_reply."""
        msg_id = self.kc.execute(code)
        self.cells[msg_id] = label
        deadline = time.monotonic() + TIMEOUT
        while True:
            timeout = max(0.1, deadline - time.monotonic())
            reply = self.kc.get_shell_msg(timeout=timeout)
            if reply['parent_header'].get('msg_id') == msg_id:
                if reply['content']['status'] != 'ok':
                    raise AssertionError(
                        'cell %s failed: %r' % (label, reply['content']))
                return msg_id

    def msg_id_of(self, label):
        for msg_id, l in self.cells.items():
            if l == label:
                return msg_id
        raise KeyError(label)

    def drain_until_stream(self, needle):
        """Pull iopub messages until a stream message containing needle."""
        deadline = time.monotonic() + TIMEOUT
        while time.monotonic() < deadline:
            try:
                m = self.kc.get_iopub_msg(timeout=1)
            except Empty:
                continue
            self.msgs.append(m)
            if m['msg_type'] == 'stream' and needle in m['content']['text']:
                return
        raise AssertionError('never saw %r on iopub' % needle)

    def settle(self, quiet=0.5):
        """Drain iopub until it has been quiet for `quiet` seconds."""
        while True:
            try:
                m = self.kc.get_iopub_msg(timeout=quiet)
            except Empty:
                return
            self.msgs.append(m)

    def stream_parent(self, needle):
        """Label of the cell a stream output containing needle is parented to."""
        for m in self.msgs:
            if m['msg_type'] == 'stream' and needle in m['content']['text']:
                parent_id = m['parent_header'].get('msg_id')
                return self.cells.get(parent_id, parent_id)
        raise AssertionError('no stream message containing %r' % needle)

    def output_comm_id(self, creating_label):
        """comm_id of the Output widget created in the given cell."""
        for m in self.msgs:
            if m['msg_type'] != 'comm_open':
                continue
            state = m['content'].get('data', {}).get('state', {})
            parent_id = m['parent_header'].get('msg_id')
            if (state.get('_model_name') == 'OutputModel'
                    and self.cells.get(parent_id) == creating_label):
                return m['content']['comm_id']
        raise AssertionError('no Output comm opened in cell %r' % creating_label)

    def msg_id_updates(self, comm_id):
        """All values the widget's msg_id trait was set to, in order."""
        values = []
        for m in self.msgs:
            if (m['msg_type'] == 'comm_msg'
                    and m['content'].get('comm_id') == comm_id):
                data = m['content'].get('data', {})
                state = data.get('state') or {}
                if data.get('method') == 'update' and 'msg_id' in state:
                    values.append(state['msg_id'])
        return values

    def stream_captured_by(self, needle, comm_id):
        """Whether the frontend Output hook would capture the stream message.

        Replays the iopub messages in order (as a frontend would) tracking
        the widget's synced msg_id; the message is captured iff its parent
        equals the widget's msg_id when it arrives.
        """
        active = ''
        for m in self.msgs:
            if (m['msg_type'] == 'comm_msg'
                    and m['content'].get('comm_id') == comm_id):
                data = m['content'].get('data', {})
                state = data.get('state') or {}
                if data.get('method') == 'update' and 'msg_id' in state:
                    active = state['msg_id']
            elif (m['msg_type'] == 'stream'
                    and needle in m['content']['text']):
                return bool(active) and m['parent_header'].get('msg_id') == active
        raise AssertionError('no stream message containing %r' % needle)


@pytest.fixture(scope='module')
def kernel():
    harness = KernelHarness()
    try:
        yield harness
    finally:
        harness.shutdown()


@pytest.fixture(scope='module')
def clobber_scenario(kernel):
    """Point 1/2 scenario: a capturing thread vs. an unrelated thread.

    cell-a spawns worker A, which captures into the widget once while cell-a
    is current, then waits.  cell-b spawns unrelated worker B, which waits.
    cell-c releases A; A re-enters the context (a loop iteration) and then
    releases B, which prints.  Every hand-off is an Event, so B's print
    happens strictly after A's re-enter and strictly before any further cell.
    """
    kernel.run('s1-setup', '''
import threading
from ipywidgets import Output
out1 = Output()
evt_first = threading.Event()
evt_reenter = threading.Event()
evt_b = threading.Event()
''')
    kernel.run('s1-cell-a', '''
def worker_a():
    with out1:
        print("A first", flush=True)
    evt_first.set()
    evt_reenter.wait(60)
    with out1:
        print("A second", flush=True)
    evt_b.set()
threading.Thread(target=worker_a, daemon=True).start()
evt_first.wait(60)   # guarantee A's first capture happens during this cell
''')
    kernel.run('s1-cell-b', '''
def worker_b():
    evt_b.wait(60)
    print("hello from B", flush=True)
threading.Thread(target=worker_b, daemon=True).start()
''')
    kernel.run('s1-cell-c', 'evt_reenter.set()')
    kernel.drain_until_stream('hello from B')
    kernel.settle()

    # Scenario sanity: A's first capture is attributed to the cell that was
    # executing when it entered the context.  This holds on every
    # ipykernel/ipywidgets combination; if it breaks, the scenario itself
    # (not the behavior under test) is broken.
    assert kernel.stream_parent('A first') == 's1-cell-a'
    return kernel


def test_unrelated_thread_output_not_attributed_to_captured_cell(clobber_scenario):
    kernel = clobber_scenario
    # Worker B has nothing to do with the widget.  Its print must not be
    # attributed to the cell worker A is capturing for.  (On ipykernel 6 B
    # is protected by the thread-ancestry attribution; on ipykernel 7 B
    # resolves the global fallback, which capturing must not rewrite.)
    assert kernel.stream_parent('hello from B') != 's1-cell-a', (
        "unrelated thread output was attributed to the captured cell"
    )


def test_capturing_thread_output_lands_in_widget(clobber_scenario):
    kernel = clobber_scenario
    # The point of `with out:` from a thread: whatever parent the capture
    # resolves, the thread's output inside the block must carry it, so the
    # frontend hook routes the output into the widget.
    comm_id = kernel.output_comm_id('s1-setup')
    assert kernel.stream_captured_by('A first', comm_id)
    assert kernel.stream_captured_by('A second', comm_id)
    if IPYKERNEL_MAJOR < 7:
        # ipykernel 6 knows the thread's own cell (ancestry); the capture
        # must respect it rather than override it with the newest cell.
        assert kernel.stream_parent('A second') == 's1-cell-a'
    else:
        # ipykernel 7 has no per-thread ancestry: a re-entered capture
        # resolves the current global parent (the cell executing at
        # re-entry) — transient by design, never pinned past the block.
        assert kernel.stream_parent('A second') == 's1-cell-c'


@pytest.fixture(scope='module')
def pin_scenario(kernel):
    """Point 2/3 scenario: a thread whose first capture happens while an
    unrelated foreground cell is executing.

    s2-spawn starts the worker, which waits.  s2-foreign releases it and
    blocks until the worker's first `with out:` block — executed *during*
    s2-foreign — completes.  s2-later releases the worker again; still during
    s2-later, the worker prints outside any context block, then captures a
    second time.
    """
    kernel.run('s2-setup', '''
import threading
from ipywidgets import Output
out3 = Output()
evt_go = threading.Event()
evt_first_done = threading.Event()
evt_late = threading.Event()
evt_done = threading.Event()
''')
    kernel.run('s2-spawn', '''
def late_worker():
    evt_go.wait(60)
    with out3:
        print("tick 1", flush=True)
    evt_first_done.set()
    evt_late.wait(60)
    print("late print", flush=True)
    with out3:
        print("tick 2", flush=True)
    evt_done.set()
threading.Thread(target=late_worker, daemon=True).start()
''')
    kernel.run('s2-foreign', 'evt_go.set(); evt_first_done.wait(60)')
    kernel.run('s2-later', 'evt_late.set(); evt_done.wait(60)')
    kernel.drain_until_stream('tick 2')
    kernel.settle()

    # Scenario sanity: the first capture happened while s2-foreign (or, with
    # ancestry-aware attribution, s2-spawn) was the resolvable parent.
    assert kernel.stream_parent('tick 1') in ('s2-foreign', 's2-spawn')
    return kernel


def test_parent_override_does_not_outlive_the_block(pin_scenario):
    kernel = pin_scenario
    # "late print" happens outside any context block, after the foreign cell
    # finished.  It must not still be attributed to the foreign cell the
    # widget captured earlier.  (Correct attribution is s2-spawn under
    # ipykernel 6's thread ancestry, or the currently-executing s2-later via
    # the global fallback on ipykernel 7.)
    assert kernel.stream_parent('late print') != 's2-foreign', (
        "output after the with block is still attributed to the foreign "
        "cell captured inside it"
    )


def test_foreign_cell_parent_is_not_pinned_across_blocks(pin_scenario):
    kernel = pin_scenario
    comm_id = kernel.output_comm_id('s2-setup')
    updates = [v for v in kernel.msg_id_updates(comm_id) if v]
    # The last non-empty msg_id update corresponds to the second capture
    # ("tick 2"), which ran during s2-later, well after s2-foreign finished.
    # The widget must not still be capturing the foreign cell's msg_id.
    assert updates, 'the widget never synced a msg_id'
    assert updates[-1] != kernel.msg_id_of('s2-foreign'), (
        "a later capture is still pinned to the long-finished foreign cell"
    )
