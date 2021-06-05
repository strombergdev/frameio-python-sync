import logging
import os
import sys
from threading import Thread
from time import sleep, time

from peewee import OperationalError, SqliteDatabase

import config
from db_models import init_log_model


class DBLogHandler(logging.Handler):
    """Save log message to db."""

    def __init__(self, *args, **kwargs):
        logging.Handler.__init__(self, *args, **kwargs)
        self.db = SqliteDatabase(
            os.path.join(config.DB_FOLDER, "log.db"), pragmas={"journal_mode": "wal"}
        )
        self.LogMessage = init_log_model(self.db)

    def emit(self, record):
        # Wait for DB write lock from other threads.
        done = False
        while not done:
            try:
                self.LogMessage(
                    text=self.format(record).rstrip("\n"), created_at=time()
                ).save()
                done = True
            except OperationalError:
                sleep(0.5)

        self.db.close()


class PurgeOldLogMessages(Thread):
    """Periodically remove old records from DB to keep size down."""

    def __init__(self):
        super().__init__()
        self.daemon = True
        self.db = SqliteDatabase(
            os.path.join(config.DB_FOLDER, "log.db"), pragmas={"journal_mode": "wal"}
        )
        self.LogMessage = init_log_model(self.db)

        self.log_ttl = 259200  # 3 days
        self.check_interval = 1800  # 30 mins

    def run(self):
        while True:
            old_messages = self.LogMessage.select().where(
                (time() - self.LogMessage.created_at) > self.log_ttl
            )

            count = 0
            for message in old_messages:
                deleted = False
                count += 1
                # Wait for DB write lock from other threads.
                while not deleted:
                    try:
                        message.delete_instance()
                        deleted = True
                    except OperationalError:
                        sleep(1)

            if count != 0:
                logger.info("Deleted {} log messages".format(count))
            self.db.close()
            sleep(self.check_interval)


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(message)s")

if config.CONSOLE_LOG:
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    logger.addHandler(console)

# DB log
db = DBLogHandler()
db.setLevel(logging.INFO)
db.setFormatter(formatter)
logger.addHandler(db)


# Send exceptions to logger for writing to file/console
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
