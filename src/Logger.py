import logging
from logging import LogRecord

class Logger(logging.Formatter):
    GREEN = "\033[32;20m"
    YELLOW = "\033[33;20m"
    RED = "\033[31;20m"
    BOLD_RED = "\033[31;1m"
    BLUE = "\033[36m"
    RESET = "\033[0m"
    FORMAT = f"%(levelname)s - %(asctime)s{RESET} - %(message)s"
    CLEAN_FORMAT = "%(levelname)s - %(asctime)s - %(message)s"
    DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    FORMATS = {
        logging.DEBUG: FORMAT,
        logging.INFO: GREEN + FORMAT,
        logging.WARN: YELLOW + FORMAT,
        logging.ERROR: RED + FORMAT,
        logging.CRITICAL: BOLD_RED + FORMAT,
    }

    def format(self, record: LogRecord) -> str:
        log_fmt = self.FORMATS.get(record.levelno, self.FORMAT)
        formatter = logging.Formatter(log_fmt, datefmt=self.DATE_FORMAT)
        return formatter.format(record)
