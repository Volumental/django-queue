from datetime import datetime
import logging
import socketserver
import multiprocessing

from .helpers import load_task
from . import helpers
import django

log = logging.getLogger(__name__)


def target(queue):
    django.setup()
    log.info('Worker Starts')
    done = False
    while not done:
        task_id = queue.get()
        if task_id is None:
            done = True
            break

        log.info('running task...')

        # Force this forked process to create its own db connection
        django.db.connection.close()

        task = load_task(task_id=task_id)
        t = helpers.unpack(task.pickled_task)
        try:
            task.started_at = datetime.now()
            task.save()
            r = t()
            task.finished_at = datetime.now()
            task.pickled_return = helpers.serialize(r)
            task.save()

            log.info('...successfully')
        except Exception as e:
            log.exception("...task failed")
            task.finished_at = datetime.now()
            task.exception = helpers.serialize(e)
            task.save()

    # workaround to solve problems with django + psycopg2
    # solution found here: https://stackoverflow.com/a/36580629/10385696
    django.db.connection.close()

    log.info('Worker stopped')


class Pool(object):
    def __init__(self):
        self.queue = multiprocessing.Queue()
        self.worker = multiprocessing.Process(target=target, args=(self.queue,))


class TaskSocketServer(socketserver.BaseRequestHandler):
    DEFAULT_POOL = 'default'
    # pools holds a mapping from pool names to process objects
    pools = {}

    def handle(self):
        try:
            data = self.request.recv(5000).strip()

            # assume a serialized task
            log.info('Got a task')
            try:
                task_id = int(data.decode())
                
                # Connection are closed by tasks, force it to reconnect
                django.db.connections.close_all()
                task = load_task(task_id=task_id)
                
                # Ensure pool got a worker processing it
                pool_name = task.pool or self.DEFAULT_POOL
                pool = self.pools.get(pool_name)
                if pool is None or not pool.worker.is_alive():
                    # Spawn new pool
                    log.info('Spawning new pool: {}'.format(pool_name))
                    self.pools[pool_name] = Pool()
                    self.pools[pool_name].worker.start()

                self.pools[pool_name].queue.put(task_id)

                response = (True, "sent")
                self.request.send(str(response).encode())
            except Exception as e:
                log.exception("failed to queue task")
                response = (False, "TaskServer Put: {}".format(e).encode(),)
                self.request.send(str(response).encode())

        except OSError as e:
            # in case of network error, just log
            log.exception("network error")

    def finish(self):
        for pool in self.pools.values():
            pool.queue.put(None)
