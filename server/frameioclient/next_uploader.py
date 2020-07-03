import math
import requests
import threading
import concurrent.futures
import os
import psutil

thread_local = threading.local()


class FrameioUploader(object):
    def __init__(self, asset, file):
        self.asset = asset
        self.file = file
        self.chunk_size = None

    def _calculate_chunks(self, total_size, chunk_count):
        self.chunk_size = int(math.ceil(total_size / chunk_count))

        chunk_offsets = list()

        for index in range(chunk_count):
            offset_amount = index * self.chunk_size
            chunk_offsets.append(offset_amount)

        return chunk_offsets

    def _get_session(self):
        if not hasattr(thread_local, "session"):
            thread_local.session = requests.Session()
        return thread_local.session

    def _smart_read_chunk(self, chunk_offset):
        with open(os.path.realpath(self.file.name), "rb") as file:
            file.seek(chunk_offset, 0)
            data = file.read(self.chunk_size)
            return data

    def _upload_chunk(self, task):
        url = task[0]
        chunk_offset = task[1]

        session = self._get_session()
        chunk_data = self._smart_read_chunk(chunk_offset)

        try:
            session.put(url, data=chunk_data, headers={
                'content-type': self.asset['filetype'],
                'x-amz-acl': 'private'
            })
        except Exception as e:
            print(e)

    def upload(self):
        total_size = self.asset['filesize']
        upload_urls = self.asset['upload_urls']

        chunk_offsets = self._calculate_chunks(total_size,
                                               chunk_count=len(upload_urls))

        if psutil.virtual_memory().available < 3000000000:  # < 3GB
            for i in range(len(upload_urls)):
                url = upload_urls[i]
                chunk_offset = chunk_offsets[i]

                task = (url, chunk_offset)
                self._upload_chunk(task)
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                for i in range(len(upload_urls)):
                    url = upload_urls[i]
                    chunk_offset = chunk_offsets[i]

                    task = (url, chunk_offset)
                    executor.submit(self._upload_chunk, task)