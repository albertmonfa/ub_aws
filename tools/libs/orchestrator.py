#!/usr/bin/python

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

import asyncio
import z_job, s3_uploader

from multiprocessing import Queue
from z_worker import z_worker


class z_orchestrator(object):

    __logger                = None
    __asyncio_loop          = None
    __workers               = 1
    __jobs                  = list()

    __jobs_queue            = None
    __jobs_success          = None
    __jobs_failed           = None

    __process_pool          = list()

    __finalized_with_errors = False
    __stats_jobs_failed     = 0
    __stats_jobs_success    = 0

    def __init__(self, jobs, logger, workers=1):
        self.__jobs_queue        = Queue()
        self.__jobs_success      = Queue()
        self.__jobs_failed       = Queue()
        self.__jobs              = jobs
        self.__workers           = workers
        self.__asyncio_loop      = asyncio.get_event_loop()
        self.__logger            = logger

        for job in jobs:
            self.__jobs_queue.put(job)

        self.__start_workers()
        super(z_orchestrator, self).__init__()

    def __start_workers(self):
        for num_worker in range(0,self.__workers):
            worker = z_worker(
                self.__jobs_queue,
                self.__jobs_success,
                self.__jobs_failed
            )
            self.__process_pool.append(worker)
            worker.start()

    def __is_someone_alive(self):
        for worker in self.__process_pool:
            if worker.is_alive():
                return True
        return False

    async def __async_monitor_success(self):
        job = self.__jobs_success.get()
        for msg in job.get_logging():
            self.__logger.info(msg)
            self.__stats_jobs_success += 1

    async def __async_monitor_failed(self):
        self.__finalized_with_errors = True
        job = self.__jobs_failed.get()
        for msg in job.get_logging():
            self.__logger.error(msg)
            self.__stats_jobs_failed += 1

    async def __async_monitor_finalize(self):
        if self.__jobs_success.qsize() > 0:
            await self.__async_monitor_success()
        if self.__jobs_failed.qsize() > 0:
            await self.__async_monitor_failed()
        if not self.__is_someone_alive():
            if self.__jobs_success.qsize() == 0 and \
                self.__jobs_failed.qsize() == 0:
                    asyncio.get_event_loop().stop()
        await asyncio.sleep(0.25)
        await self.__async_monitor_finalize()

    def monitor(self):
        asyncio.async(self.__async_monitor_finalize())
        self.__asyncio_loop.run_forever()

    def summary(self):
        self.__logger.info("--------------------------------------------------")
        self.__logger.info("{} Jobs Processed.".format(len(self.__jobs)))
        self.__logger.info("{} Jobs Failed.".format(self.__stats_jobs_failed))
        self.__logger.info("{} Jobs Successful.".format(self.__stats_jobs_success))
        if self.__finalized_with_errors:
            self.__logger.fatal("Application exited with errors.")
        else:
            self.__logger.info("SUCCESS - All Jobs Zipped and uploaded into S3 Repository")
