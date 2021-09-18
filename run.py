import os
import logging
import sys

from gunicorn.app.base import BaseApplication
from gunicorn.glogging import Logger
from loguru import logger

from app.main import app


LOG_LEVEL = logging.getLevelName(os.environ.get("LOG_LEVEL", "INFO").upper())
GUNICORN_SHOW_ERRORS = os.environ.get('GUNICORN_SHOW_ERRORS')
JSON_LOGS = True if os.environ.get("JSON_LOGS", "0") == "1" else False
WORKERS = int(os.environ.get("GUNICORN_WORKERS", "5"))


class StubbedGunicornLogger(Logger):
    def setup(self, cfg):
        self.error_logger = logging.getLogger("gunicorn.error")
        self.error_log.setLevel(LOG_LEVEL)
        self.access_log.setLevel(LOG_LEVEL)
        if not GUNICORN_SHOW_ERRORS:
            handler = logging.NullHandler()
            self.error_logger.addHandler(handler)


class StandaloneApplication(BaseApplication):
    """Our Gunicorn application."""

    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super().__init__()

    def load_config(self):
        config = {
            key: value for key, value in self.options.items()
            if key in self.cfg.settings and value is not None
        }
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


if __name__ == '__main__':
    logging.root.setLevel(LOG_LEVEL)

    seen = set()

    logger.configure(handlers=[{"sink": sys.stdout, "serialize": JSON_LOGS}])

    options = {
        "bind": "0.0.0.0:80",
        "workers": WORKERS,
        "accesslog": "",
        "errorlog": "",
        "worker_class": "uvicorn.workers.UvicornWorker",
        "logger_class": StubbedGunicornLogger
    }

    StandaloneApplication(app, options).run()