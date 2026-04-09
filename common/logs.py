import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
import sys
from loguru import logger

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
_STDERR_SINK_ID = None
_STDERR_PROXY = None


class _SafeStderrProxy:
    def __init__(self):
        self._mute_depth = 0

    def _resolve_stream(self):
        stream = getattr(sys, "stderr", None)
        if stream is not None and not getattr(stream, "closed", False):
            return stream

        fallback = getattr(sys, "__stderr__", None)
        if fallback is not None and not getattr(fallback, "closed", False):
            return fallback
        return None

    def write(self, message):
        if self._mute_depth > 0:
            return

        stream = self._resolve_stream()
        if stream is None:
            return

        try:
            stream.write(message)
        except ValueError:
            fallback = getattr(sys, "__stderr__", None)
            if fallback is not None and fallback is not stream and not getattr(fallback, "closed", False):
                fallback.write(message)

    def flush(self):
        if self._mute_depth > 0:
            return

        stream = self._resolve_stream()
        if stream is None:
            return

        try:
            stream.flush()
        except ValueError:
            fallback = getattr(sys, "__stderr__", None)
            if fallback is not None and fallback is not stream and not getattr(fallback, "closed", False):
                fallback.flush()

    @contextmanager
    def muted(self):
        self._mute_depth += 1
        try:
            yield
        finally:
            self._mute_depth = max(0, self._mute_depth - 1)


def _add_stderr_sink():
    global _STDERR_SINK_ID, _STDERR_PROXY
    if _STDERR_SINK_ID is not None:
        return

    if _STDERR_PROXY is None:
        _STDERR_PROXY = _SafeStderrProxy()

    _STDERR_SINK_ID = logger.add(
        _STDERR_PROXY,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        level="INFO",
        colorize=True,
    )


def _generate_logs_dir():
    cur_time = time.strftime("%Y-%m-%d")
    dirname = os.path.join(LOGS_DIR, cur_time)
    try:
        if not os.path.exists(dirname):
            os.makedirs(dirname)
    except OSError as e:
        print(f"创建目录 {dirname} 时出错: {e}")
    return dirname


def _init_logger():
    log_dir = _generate_logs_dir()
    log_time = datetime.now().strftime("%H:%M:%S")
    log_id = str(uuid.uuid4())[:8]
    log_file = f"{log_dir}/test_{log_time}_{log_id}.log"

    logger.remove()
    global _STDERR_SINK_ID, _STDERR_PROXY
    _STDERR_SINK_ID = None
    _STDERR_PROXY = None
    _add_stderr_sink()

    logger.add(
        log_file,
        level="DEBUG",
        rotation="1 day",
        retention="7 days",
        compression="zip",
        enqueue=True,
        catch=True,
        serialize=False
    )


_init_logger()


@contextmanager
def mute_stderr_logs():
    global _STDERR_PROXY
    if _STDERR_PROXY is None:
        yield
        return

    with _STDERR_PROXY.muted():
        yield


class Logger:
    def __init__(self, name: str = None):
        self.name = name

    def info(self, msg):
        if self.name:
            logger.bind(name=self.name).info(msg)
        else:
            logger.info(msg)

    def debug(self, msg):
        if self.name:
            logger.bind(name=self.name).debug(msg)
        else:
            logger.debug(msg)

    def warning(self, msg):
        if self.name:
            logger.bind(name=self.name).warning(msg)
        else:
            logger.warning(msg)

    def error(self, msg):
        if self.name:
            logger.bind(name=self.name).error(msg)
        else:
            logger.error(msg)


log = Logger()
