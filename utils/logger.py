import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime

class Logger:
    _instance = None

    def __new__(cls, name="DoubanCrawler"):
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
            cls._instance._initialize(name)
        return cls._instance

    def _initialize(self, name):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)

        # 1. Ensure logs directory exists
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # 2. Formatters
        file_formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] - %(message)s',
            datefmt='%H:%M:%S'
        )

        # Check existing handlers
        has_file_handler = False
        has_console_handler = False
        for h in self.logger.handlers:
            if isinstance(h, TimedRotatingFileHandler):
                has_file_handler = True
            elif isinstance(h, logging.StreamHandler):
                has_console_handler = True

        # 3. File Handler (Rotate Daily)
        if not has_file_handler:
            log_file = os.path.join(log_dir, "crawler.log")
            file_handler = TimedRotatingFileHandler(
                log_file, when="midnight", interval=1, backupCount=30, encoding="utf-8"
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)

        # 4. Console Handler
        if not has_console_handler:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)

    def get_logger(self):
        return self.logger

# Global instance for easy import
# Usage: from utils.logger import logger
logger = Logger().get_logger()
