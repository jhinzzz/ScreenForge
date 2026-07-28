"""_reap_with_timeout must never block indefinitely on a stuck recording process.

Bare os.waitpid(pid, 0) hangs forever if the child ignores SIGINT; these tests
prove the bounded-wait + SIGKILL fallback with real child processes.
"""

import os
import signal
import subprocess
import sys
import time

import pytest

from cli.session import _reap_with_timeout


def test_reaps_a_process_that_exits_promptly():
    # A child already on its way out is reaped well within the timeout.
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.2)"])
    start = time.monotonic()
    _reap_with_timeout(proc.pid, timeout=5.0)
    assert time.monotonic() - start < 5.0
    # Reaped: a second waitpid raises ChildProcessError (no such child).
    with pytest.raises(ChildProcessError):
        os.waitpid(proc.pid, os.WNOHANG)


@pytest.mark.skipif(os.name != "posix", reason="POSIX signal semantics")
def test_sigkills_a_process_that_ignores_sigint():
    # Child ignores SIGINT and sleeps far longer than the timeout. Without the
    # SIGKILL fallback, a bare waitpid(pid, 0) would block for the full 30s.
    code = "import signal, time; signal.signal(signal.SIGINT, signal.SIG_IGN); time.sleep(30)"
    proc = subprocess.Popen([sys.executable, "-c", code])
    time.sleep(0.3)  # let the handler install
    os.kill(proc.pid, signal.SIGINT)  # ignored by the child

    start = time.monotonic()
    _reap_with_timeout(proc.pid, timeout=1.0)
    elapsed = time.monotonic() - start
    assert elapsed < 5.0, f"blocked {elapsed:.1f}s — did not bound the wait"
    with pytest.raises(ChildProcessError):
        os.waitpid(proc.pid, os.WNOHANG)
