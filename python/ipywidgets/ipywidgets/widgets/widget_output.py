# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

"""Output class.

Represents a widget that can be used to display output within the widget area.
"""

import sys
import threading
from contextvars import ContextVar
from functools import wraps

from .domwidget import DOMWidget
from .trait_types import TypedTuple
from .widget import register
from .._version import __jupyter_widgets_output_version__

from traitlets import Unicode, Dict
from IPython.core.interactiveshell import InteractiveShell
from IPython.display import clear_output
from IPython import get_ipython
import traceback

@register
class Output(DOMWidget):
    """Widget used as a context manager to display output.

    This widget can capture and display stdout, stderr, and rich output.  To use
    it, create an instance of it and display it.

    You can then use the widget as a context manager: any output produced while in the
    context will be captured and displayed in the widget instead of the standard output
    area.

    You can also use the .capture() method to decorate a function or a method. Any output
    produced by the function will then go to the output widget. This is useful for
    debugging widget callbacks, for example.

    Example::
        import ipywidgets as widgets
        from IPython.display import display
        out = widgets.Output()
        display(out)

        print('prints to output area')

        with out:
            print('prints to output widget')

        @out.capture()
        def func():
            print('prints to output widget')
    """
    _view_name = Unicode('OutputView').tag(sync=True)
    _model_name = Unicode('OutputModel').tag(sync=True)
    _view_module = Unicode('@jupyter-widgets/output').tag(sync=True)
    _model_module = Unicode('@jupyter-widgets/output').tag(sync=True)
    _view_module_version = Unicode(__jupyter_widgets_output_version__).tag(sync=True)
    _model_module_version = Unicode(__jupyter_widgets_output_version__).tag(sync=True)

    msg_id = Unicode('', help="Parent message id of messages to capture").tag(sync=True)
    outputs = TypedTuple(trait=Dict(), help="The output messages synced from the frontend.").tag(sync=True)

    __counter = 0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__counter_lock = threading.Lock()
        # Per-thread stack of capture records so nested/threaded enter/exit
        # pairs stay balanced and each thread restores exactly what it set.
        self.__records = threading.local()

    def clear_output(self, *pargs, **kwargs):
        """
        Clear the content of the output widget.

        Parameters
        ----------

        wait: bool
            If True, wait to clear the output until new output is
            available to replace it. Default: False
        """
        with self:
            clear_output(*pargs, **kwargs)

    # PY3: Force passing clear_output and clear_kwargs as kwargs
    def capture(self, clear_output=False, *clear_args, **clear_kwargs):
        """
        Decorator to capture the stdout and stderr of a function.

        Parameters
        ----------

        clear_output: bool
            If True, clear the content of the output widget at every
            new function call. Default: False

        wait: bool
            If True, wait to clear the output until new output is
            available to replace it. This is only used if clear_output
            is also True.
            Default: False
        """
        def capture_decorator(func):
            @wraps(func)
            def inner(*args, **kwargs):
                if clear_output:
                    self.clear_output(*clear_args, **clear_kwargs)
                with self:
                    return func(*args, **kwargs)
            return inner
        return capture_decorator

    @staticmethod
    def _resolve_parent_header(ip, kernel):
        """The parent header to capture for the calling thread, or None.

        Prefer the parent the calling thread's stream output will actually
        be attributed to: ``OutStream.parent_header`` resolves per-thread
        state on ipykernel >= 6 (thread-ancestry map on ipykernel 6, a
        per-thread ContextVar with a process-global fallback on 7). Fall
        back to the shell's parent request, then the kernel's, for streams
        that do not expose a parent (non-ipykernel kernels, redirected
        stdout).
        """
        header = getattr(sys.stdout, "parent_header", None)
        if isinstance(header, dict) and header.get("msg_id"):
            return header

        parent_request = None
        if ip is not None and hasattr(ip, "get_parent"):
            shell_parent = ip.get_parent()
            # Only accept a full parent *request*; ipykernel display
            # publishers store bare header dicts, which must not shadow the
            # kernel fallback below.
            if isinstance(shell_parent, dict) and shell_parent.get("header"):
                parent_request = shell_parent
        if parent_request is None:
            if hasattr(kernel, "get_parent"):
                # ipykernel >= 6 keeps parent requests on the kernel.
                parent_request = kernel.get_parent()
            elif hasattr(kernel, "_parent_header"):
                # ipykernel < 6: kernel._parent_header is the parent *request*
                parent_request = kernel._parent_header

        if isinstance(parent_request, dict):
            header = parent_request.get("header")
            if isinstance(header, dict) and header.get("msg_id"):
                return header
        return None

    @staticmethod
    def _thread_parent_vars(ip):
        """ContextVars holding the calling thread's output parent.

        ipykernel's ``OutStream`` (>= 6.18) and ``ZMQDisplayPublisher``
        (>= 7) keep the per-thread parent in a ``_parent_header``
        ContextVar. Setting it affects only the current thread and is
        exactly reversible with the returned token — unlike
        ``shell.set_parent``, which also rewrites process-global state
        shared with every other thread. Objects without such a ContextVar
        (other kernels such as xeus-python, redirected streams) are
        skipped, leaving their behavior unchanged.
        """
        candidates = [sys.stdout, sys.stderr]
        if ip is not None:
            candidates.append(getattr(ip, "display_pub", None))
        return [
            var for var in
            (getattr(obj, "_parent_header", None) for obj in candidates)
            if isinstance(var, ContextVar)
        ]

    def __enter__(self):
        """Called upon entering output widget context manager."""
        self._flush()
        ip = get_ipython()
        kernel = None
        if ip and getattr(ip, "kernel", None) is not None:
            kernel = ip.kernel
        elif self.comm is not None and getattr(self.comm, 'kernel', None) is not None:
            kernel = self.comm.kernel

        record = {'tokens': (), 'captured': False}
        if kernel:
            header = self._resolve_parent_header(ip, kernel)
            if header:
                # Pin the calling thread's stream/display parents to the
                # captured parent for the duration of the block, so output
                # produced in this thread carries the same parent msg_id the
                # frontend hook matches on.
                record['tokens'] = tuple(
                    (var, var.set(header)) for var in self._thread_parent_vars(ip)
                )
                record['captured'] = True
                with self.__counter_lock:
                    self.__counter += 1
                self.msg_id = header['msg_id']
        stack = getattr(self.__records, 'stack', None)
        if stack is None:
            stack = self.__records.stack = []
        stack.append(record)

    def __exit__(self, etype, evalue, tb):
        """Called upon exiting output widget context manager."""
        kernel = None
        if etype is not None:
            ip = get_ipython()
            if ip:
                kernel = ip
                ip.showtraceback((etype, evalue, tb), tb_offset=0)
            elif (self.comm is not None and
                    getattr(self.comm, "kernel", None) is not None and
                    # Check if it's ipykernel
                    getattr(self.comm.kernel, "send_response", None) is not None):
                kernel = self.comm.kernel
                kernel.send_response(kernel.iopub_socket,
                                     u'error',
                                     {
                    u'traceback': ["".join(traceback.format_exception(etype, evalue, tb))],
                    u'evalue': repr(evalue.args),
                    u'ename': etype.__name__
                    })
        self._flush()
        stack = getattr(self.__records, 'stack', None)
        record = stack.pop() if stack else {'tokens': (), 'captured': False}
        # Restore the thread's previous parents exactly; the override must
        # not outlive the block.
        for var, token in reversed(record['tokens']):
            var.reset(token)
        if record['captured']:
            # Only decrement when the matching __enter__ captured, so the
            # counter stays balanced and msg_id cleanup always fires.
            with self.__counter_lock:
                self.__counter -= 1
                if self.__counter == 0:
                    self.msg_id = ''
        # suppress exceptions when in IPython, since they are shown above,
        # otherwise let someone else handle it
        return True if kernel else None

    def _flush(self):
        """Flush stdout and stderr buffers."""
        sys.stdout.flush()
        sys.stderr.flush()

    def _append_stream_output(self, text, stream_name):
        """Append a stream output."""
        self.outputs += (
            {'output_type': 'stream', 'name': stream_name, 'text': text},
        )

    def append_stdout(self, text):
        """Append text to the stdout stream."""
        self._append_stream_output(text, stream_name='stdout')

    def append_stderr(self, text):
        """Append text to the stderr stream."""
        self._append_stream_output(text, stream_name='stderr')

    def append_display_data(self, display_object):
        """Append a display object as an output.

        Parameters
        ----------
        display_object : IPython.core.display.DisplayObject
            The object to display (e.g., an instance of
            `IPython.display.Markdown` or `IPython.display.Image`).
        """
        fmt = InteractiveShell.instance().display_formatter.format
        data, metadata = fmt(display_object)
        self.outputs += (
            {
                'output_type': 'display_data',
                'data': data,
                'metadata': metadata
            },
        )
