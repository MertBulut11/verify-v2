"""Prevent inherited adapter logs from exposing provider exceptions or claims."""
import logging
from .resources import current_request_id


class SafeAdapterLog(logging.Filter):
    def filter(self, record):
        record.msg = "backend component event request_id=%s"
        record.args = (current_request_id.get(),)
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


class SafeOutputLog(SafeAdapterLog):
    def filter(self, record):
        if record.name in {"verify.api", "verify.security"}:
            return True
        return super().filter(record)


def install_safe_logging():
    for name in ("verify.llm", "verify.retrieval", "verify.pipeline"):
        logger = logging.getLogger(name)
        if not any(isinstance(item, SafeAdapterLog) for item in logger.filters):
            logger.addFilter(SafeAdapterLog())
    # HTTP access URLs may contain user-controlled query strings.
    for name in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(name).disabled = True
    for handler in logging.getLogger().handlers:
        if not any(isinstance(item, SafeOutputLog) for item in handler.filters):
            handler.addFilter(SafeOutputLog())
