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

import boto3
import botocore
import os
import shutil

from threading import Thread

class s3_uploader(Thread):

    __job       = None

    __s3_key    = None
    __s3_bucket = None
    __src_file  = None

    def __init__(self, job):
        Thread.__init__(self)
        self.__job = job
        self.start()

    def get_job(self):
        return self.__job

    def s3_key_exist(self):
        try:
            self.s3.Object(
                self.__s3_bucket,
                self.__s3_key
            ).load()
            return True
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == "404":
                return False
            else:
                self.__job.add_log_msg('S3 Object '+ str(self.__s3_key) + ' in bucket '  \
                                + str(self.__s3_bucket) + ' unhandled error: ' \
                                + str(e.message)
                            )
                self.__job.set_status_failed()
        except Exception as e:
            self.__job.add_log_msg('Boto3 exception with message: '+str(e))
            self.__job.set_status_failed()
            return False

    def s3_upload_file(self):
        if self.s3_key_exist():
           self.__job.add_log_msg('S3 Object '+ str(self.__s3_key) + ' in bucket ' \
                            + str(self.__s3_bucket) + ' already uploaded!'
                        )
           self.__job.set_status_success()
           return False
        try:
            bucket = self.s3.Bucket(self.__s3_bucket)
            data = open(self.__src_file, 'rb')
            bucket.put_object( Key=self.__s3_key,
                               ACL='private',
                               Metadata={
                                'foo' : 'bar'
                               },
                               Body=data
                             )
            return True
        except Exception as e:
            self.__job.add_log_msg('S3 problem in Bucket '+ self.__s3_bucket +\
                         ', with Key ' + self.__s3_key + ' msg: '+str(e)
                        )
            self.__job.set_status_failed()
            return False

    def purge_tmpfs(self, tmpfs_path):
        shutil.rmtree(os.path.dirname(tmpfs_path))

    def run(self):
        self.session = boto3.session.Session()
        self.s3 = self.session.resource('s3')
        self.__s3_bucket    = self.__job.get_s3_bucket()
        self.__src_file     = self.__job.get_uploader_path()
        self.__s3_key       = self.__job.get_s3_path() + self.__job.get_filename() + '.zip'
        if self.s3_upload_file():
           self.__job.set_status_success()
           self.__job.add_log_msg('Uploading file from Bucket: '+ self.__s3_bucket +\
                       ', Key: ' + self.__s3_key + ' from ' + self.__src_file
                      )
        self.purge_tmpfs(self.__job.get_uploader_path())
