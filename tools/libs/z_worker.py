#!/usr/bin/python3

'''
Author: Albert Monfa 2018

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
'''

import os
import shutil
import tempfile
import asyncio

from zipfile import ZipFile
from multiprocessing import Process, Queue

from libs.z_job import z_job_status
from libs.s3_uploader import s3_uploader

class z_worker(Process):

    __jobs_queue        = None
    __asyncio_loop      = None

    __threadpool        = None

    __jobs_success      = None
    __jobs_failed       = None

    def __init__(self, jobs_queue, jobs_success, jobs_failed):
        self.__jobs_queue       = jobs_queue
        self.__jobs_success     = jobs_success
        self.__jobs_failed      = jobs_failed
        self.__asyncio_loop     = asyncio.get_event_loop()
        self.__threadpool       = dict()
        super(z_worker, self).__init__()

    def gen_tmpfs(self, filename):
        self.__tmp_path = tempfile.mkdtemp()
        self.__tmp_file = os.path.join(self.__tmp_path, filename)

    async def zipper(self, job):
        try:
            if os.path.isfile(job.get_src_path()):
                path, target = os.path.split(job.get_src_path())
                target_zipped = ZipFile(self.__tmp_file, 'w')
                target_zipped.write(os.path.abspath(job.get_src_path()), target)
                target_zipped.close()
                job.set_uploader_path(self.__tmp_file)
            else:
                data = open(shutil.make_archive(
                            self.__tmp_file, 'zip', job.get_src_path()
                        ),
                    'rb').read()
                job.set_uploader_path(self.__tmp_file + '.zip')
        except Exception as e:
            job.add_log_msg("Can't Zipping "+ str(job.get_src_path()) + ' with message: ' \
                            + str(e)
                        )
            job.set_status_failed()

    def wait_all_threads_finished(self):
        for thread in self.__threadpool:
            self.__threadpool[thread].join()
            job = self.__threadpool[thread].get_job()
            if job.get_status() == z_job_status.SUCCESS:
                self.__jobs_success.put(job)
            elif job.get_status() == z_job_status.FAILED:
                self.__jobs_failed.put(job)

    async def process_job(self):
        if self.__jobs_queue.empty():
            self.wait_all_threads_finished()
            asyncio.get_event_loop().stop()
            return True

        job = self.__jobs_queue.get()
        job.set_status_running()
        self.gen_tmpfs(job.get_filename())
        await self.zipper(job)
        if job.get_status() == z_job_status.RUNNING:
            uploader_thread = s3_uploader(job)
            self.__threadpool[uploader_thread.getName()] = uploader_thread
        elif job.get_status() == z_job_status.FAILED:
            self.__jobs_failed.put(job)

        await self.process_job()

    def run(self):
        asyncio.async(self.process_job())
        self.__asyncio_loop.run_forever()
