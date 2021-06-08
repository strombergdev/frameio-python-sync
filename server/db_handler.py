
from threading import Thread
import queue
from logger import logger

db_queue = queue.Queue() 

class WriteQueueConsumer(Thread):
    def __init__(self, db, **kwargs):
        super().__init__(**kwargs)
        self.daemon = True
        self.db = db

    def run(self):
        while True:
            row, action = db_queue.get()
            
            if action == "save":
                row.save()
            elif action == "delete":
                row.delete_instance()
            else:
                logger.error('Bad DB write operation - Use save or delete')
                raise Exception

            self.db.close()
            db_queue.task_done()
