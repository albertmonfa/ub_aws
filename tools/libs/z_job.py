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

from collections import OrderedDict
from enum import Enum


class z_job_status(Enum):
  FAILED         = -1
  RUNNING        = 0
  SUCCESS        = 1


class z_job(object):

    __name              = None
    __src_path          = None
    __version           = None
    __filename          = None
    __uploader_path     = None

    __s3_bucket         = None
    __s3_path           = None

    __status            = None
    __logging           = None

    def __init__(self, name, src_path, version, s3_bucket, s3_path):
        self.__name         = name
        self.__src_path     = src_path
        self.__version      = version
        self.__s3_bucket    = s3_bucket
        self.__s3_path      = s3_path

        self.__filename     = name+'-'+version
        self.__logging      = list()

    def get_name(self):
        return self.__name

    def get_filename(self):
        return self.__filename

    def get_src_path(self):
        return self.__src_path

    def get_version(self):
        return self.__version

    def get_s3_bucket(self):
        return self.__s3_bucket

    def get_s3_path(self):
        return self.__s3_path

    def get_uploader_path(self):
        return self.__uploader_path

    def set_uploader_path(self, uploader_path):
        self.__uploader_path = uploader_path

    def add_log_msg(self, msg):
        self.__logging.append(msg)

    def get_logging(self):
        return self.__logging

    def get_status(self):
        return self.__status

    def set_status_failed(self):
        self.__status = zin_job_status.FAILED

    def set_status_running(self):
        self.__status = zin_job_status.RUNNING

    def set_status_success(self):
        self.__status = zin_job_status.SUCCESS
