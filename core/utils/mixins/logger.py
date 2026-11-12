import logging
from functools import cached_property


class LoggerMixin:
    @cached_property
    def logger(self) -> logging.Logger:
        return logging.getLogger(self.__class__.__name__)