"""Dump latest log records from db to console."""

from db_models import init_log_model, init_sync_models
from peewee import SqliteDatabase
import os
from os.path import dirname, abspath
import config

PARENT_DIR = dirname(dirname(abspath(__file__)))

sync_db = SqliteDatabase(os.path.join(PARENT_DIR, config.DB_FOLDER, 'sync.db'),
                         pragmas={'journal_mode': 'wal'})
Login, Project, Asset, IgnoreFolder = init_sync_models(sync_db)

log_db = SqliteDatabase(os.path.join(PARENT_DIR, config.DB_FOLDER, 'log.db'),
                        pragmas={'journal_mode': 'wal'})
LogMessage = init_log_model(log_db)

if __name__ == '__main__':
    for project in Project.select():
        print(project.name)
        print('    path: {}'.format(project.local_path))
        print('    sync: {}'.format(project.sync))

    for message in LogMessage.select().order_by(LogMessage.created_at):
        print(message.text)
