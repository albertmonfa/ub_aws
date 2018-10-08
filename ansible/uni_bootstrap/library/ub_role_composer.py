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

DOCUMENTATION = '''

'''

EXAMPLES = '''

'''

RETURN = '''

'''

ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'supported_by': 'community',
    'status': ['preview']
}

import re
import os
import sys
import boto3
import botocore
import json
import yaml
import time
import shutil
import tempfile
import zipfile
import ast

from ansible.module_utils.basic import *
from ansible.module_utils.urls import *
from ansible.module_utils._text import to_text
from pprint import pprint
from jsonschema import validate, ValidationError

global aws_session, s3_session

class s3_downloader(object):
    __s3_bucket = None
    __s3_key = None
    __dst = None
    __s3_session = None

    __msg_errors = None
    __failed = None

    def __init__(self, s3_session, s3_bucket, s3_key ,dst):
        self.__s3_session = s3_session
        self.__s3_bucket = s3_bucket
        self.__s3_key = s3_key
        self.__dst = dst
        self.__msg_errors = list()
        self.__failed = False

    def key_exist(self):
        try:
            self.__s3_session.Object(self.__s3_bucket, self.__s3_key).load()
            return True
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == "404":
                return False
            else:
                self.__msg_errors.append('S3 Object '+ str(self.__s3_key) + ' in bucket '  \
                                + str(self.__s3_bucket) + ' unhandled error: ' \
                                + str(e.message)
                            )
        except Exception as e:
            self.__msg_errors.append('Boto3 exception with message: '+str(e))
            return False

    def download_file(self):
        if not self.key_exist():
           self.__msg_errors.append('S3 Object '+ str(self.__s3_key) + ' in bucket ' \
                            + str(self.__s3_bucket) + ' doesn\'t exist'
                        )
           self.__failed = True
        try:
            bucket = self.__s3_session.Bucket(self.__s3_bucket)
            bucket.download_file(self.__s3_key, self.__dst)
        except Exception as e:
            self.__msg_errors.append('S3 problem in Bucket '+ self.__s3_bucket +\
                         ', with Key ' + self.__s3_key + ' msg: '+str(e)
                        )
            self.__failed = True

    def get_errors(self):
        return self.__msg_errors

    def is_failed(self):
        return self.__failed

class ModuleCommon(object):

    @staticmethod
    def gen_result():
        return {
                'status': True,
                'errors': []
            }

    @staticmethod
    def mk_directory(directory):
        result = ModuleCommon.gen_result()
        try:
            os.stat(directory)
            result['errors'].append('Directory {0} exists already'.format(directory))
            result['status'] = False
        except:
            try:
                os.mkdir(directory)
            except Exception as e:
                result['errors'].append('Error creating {0} directory: {1}' \
                    .format(directory, str(e)))
                result['status'] = False
        return result

    @staticmethod
    def unzip_file(zip_file, dst_path):
        result = ModuleCommon.gen_result()
        try:
            zip_ref = zipfile.ZipFile(zip_file, 'r')
            zip_ref.extractall(dst_path)
            zip_ref.close()
        except Exception as e:
            result['status'] = False
            result['errors'].append('Error unzipping file {0}, error: {1}' \
                .format(zip_file, str(e)))
        try:
            os.remove(zip_file)
        except Exception as e:
            result['status'] = False
            result['errors'].append('Error unzipping file {0}, error: {1}' \
                .format(zip_file, str(e)))
        return result

    @staticmethod
    def load_and_parse_json(json_file):
        result = ModuleCommon.gen_result()
        if not os.path.isfile(json_file):
            result['status'] = False
            result['errors'].append(str(json_file) + ' Not found!')
            return result
        try:
            with open(json_file) as file:
                f_dict = dict(json.load(file))
            result['status'] = True
            result['payload'] = f_dict
        except Exception as e:
            result['status'] = False
            result['errors'].append(e.message)
        return result

class DynConfigGen(object):
    __s3_bucket             = None
    __tmpfs_path            = None
    __roles_s3_key_path     = None
    __role_name             = None
    __role_version          = None

    __ansible_taskslist_s3_path     = None
    __ansible_roles_s3_path         = None
    __ansible_libraries_s3_path     = None
    __working_directory             = None

    __role_dict             = None
    __roles_map             = None

    def __init__(self, s3_bucket, tmpfs_path, roles_s3_key_path,
        roles_map_version, role_name, role_version, ansible_taskslist_s3_path,
        ansible_roles_s3_path, ansible_libraries_s3_path, working_directory):
        self.__s3_bucket                    = s3_bucket
        self.__tmpfs_path                   = tmpfs_path
        self.__roles_s3_key_path            = roles_s3_key_path
        self.__roles_map_version            = roles_map_version
        self.__role_name                    = role_name
        self.__role_version                 = role_version
        self.__ansible_roles_s3_path        = ansible_roles_s3_path
        self.__ansible_libraries_s3_path    = ansible_libraries_s3_path
        self.__ansible_taskslist_s3_path    = ansible_taskslist_s3_path
        self.__working_directory            = working_directory

        try:
            rm_result = self.__get_roles_map()
            if rm_result['status']:
                self.__roles_map = rm_result['payload']
            else:
                raise Exception(rm_result['errors'])

            role_result = self.__get_role_settings()
            if role_result['status']:
                self.__roles_dict = role_result['payload']
            else:
                raise Exception(role_result['errors'])

            val_result = self.__role_validator()
            if not val_result['status']:
                raise Exception(val_result['errors'])
        except Exception as e:
            raise Exception(e.message)

    def __get_role_settings(self):
        result = ModuleCommon.gen_result()

        if self.__role_name not in self.__roles_map and self.__role is not 'default':
            result['errors'].append('Role {0} not found, using \'default\' role' \
                .format(str(role)))
            self.__role_name = 'default'
            if self.__role not in self.__roles_map:
                result['status'] = False
                result['errors'].append('Default Role not found in roles_map.json')

        role_file = self.__roles_map[self.__role_name]
        roles_file_key = self.__roles_s3_key_path + '/' + role_file
        dst = self.__tmpfs_path + '/' + role_file
        s3_dl = s3_downloader(s3_session, self.__s3_bucket, roles_file_key ,dst)
        s3_dl.download_file()
        if s3_dl.is_failed():
            result['status'] = False
            result['errors'].append('Download file {0} failed'.format(roles_file_key))
            for s3_err in s3_dl.get_errors():
                result['errors'].append(s3_err)
        ModuleCommon.unzip_file(dst, self.__tmpfs_path)

        role_file_json = self.__tmpfs_path + '/' +  dst.replace(self.__tmpfs_path + \
                '/', '').replace('-' + self.__role_version + '.zip', '') + '.json'
        rf_result = ModuleCommon.load_and_parse_json(role_file_json)
        if len(rf_result['errors']) is not 0:
            result['status'] = False
            for rf_err in rf_result['errors']:
                result['errors'].append(rf_err)

        result['payload'] = rf_result['payload']
        return result

    def __get_roles_map(self):
        result = ModuleCommon.gen_result()

        roles_map_key = self.__roles_s3_key_path + '/roles_map-' + \
            self.__roles_map_version +'.zip'
        dst = self.__tmpfs_path + '/roles_map-' + self.__roles_map_version + '.zip'
        s3_dl = s3_downloader(s3_session, self.__s3_bucket, roles_map_key ,dst)
        s3_dl.download_file()

        if s3_dl.is_failed():
            result['status'] = False
            result['errors'].append('Download file {0} failed'.format(roles_map_key))
            for s3_err in s3_dl.get_errors():
                result['errors'].append(s3_err)
        ModuleCommon.unzip_file(dst, self.__tmpfs_path)
        rm_file_json = self.__tmpfs_path + '/roles_map.json'
        rm_result = ModuleCommon.load_and_parse_json(rm_file_json)
        if not rm_result['status']:
            result['status'] = False
            for lp_err in rm_result['errors']:
                result['errors'].append(lp_err)
            return result
        result['payload'] = rm_result['payload']
        return result

    def __role_validator(self):
        result = ModuleCommon.gen_result()

        role_sch  = {
            "type": "object",
            "required": [ "name", "roles", "libraries", "tasks", "vars"],
            "properties" : {
                "name"      : { "type": "string" },
                "roles"     : { "type": "object" },
                "libraries" : { "type": "object" },
                "tasks"     : { "type": "object" },
                "vars"      : { "type": "object" },
            },
        }
        item_sch  = {
           "type": "object",
           "required": [ "version" ],
           "properties" : {
             "version":  { "type": "string" },
           },
           "additionalProperties": False
        }
        vars_sch  = {
           "type": "object",
           "required": [ "value" ],
           "properties" : {
             "value":  { "type": "string" },
           },
           "additionalProperties": False
        }

        try:
            validate(self.__roles_dict,  role_sch)
            for section in ['roles', 'libraries', 'tasks']:
                for item in self.__roles_dict[section]:
                    validate(dict(self.__roles_dict[section][item]),  item_sch)
            for item in self.__roles_dict['vars']:
                validate(dict(self.__roles_dict['vars'][item]),  vars_sch)
            return result
        except Exception as e:
            result['status'] = False
            result['errors'] = 'Fatal error validating Role conf: {0} '.format(e.message)
            return result

    def __gen_tasks(self, ansible_tasklists):
        result = ModuleCommon.gen_result()
        tasklists_dir = self.__tmpfs_path + '/tasklists'
        ModuleCommon.mk_directory(tasklists_dir)
        for tasklist in ansible_tasklists:
            version = ansible_tasklists[tasklist]['version']
            dst = self.__tmpfs_path + '/' + tasklist + '-' + version + '.zip'
            tasklist_key = self.__ansible_libraries_s3_path + tasklist + '-' + version + '.zip'

            s3_dl = s3_downloader(s3_session, self.__s3_bucket, tasklist_key, dst)
            s3_dl.download_file()
            if s3_dl.is_failed():
                result['status'] = False
                result['errors'].append('Download file {0} failed'.format(tasklist_key))
                return result
            ModuleCommon.unzip_file(dst, tasklists_dir)
        return result

    def __gen_roles(self, ansible_roles):
        result = ModuleCommon.gen_result()
        roles_dir = self.__tmpfs_path + '/roles'
        ModuleCommon.mk_directory(roles_dir)
        for role in ansible_roles:
            version = ansible_roles[role]['version']
            dst = self.__tmpfs_path + '/' + role + '-' + version + '.zip'
            role_key = self.__ansible_roles_s3_path + role + '-' + version + '.zip'
            role_dir = roles_dir + '/' + role
            ModuleCommon.mk_directory(role_dir)

            s3_dl = s3_downloader(s3_session, self.__s3_bucket, role_key ,dst)
            s3_dl.download_file()
            if s3_dl.is_failed():
                result['status'] = False
                result['errors'].append('Download file {0} failed'.format(role_key))
                return result
            ModuleCommon.unzip_file(dst, role_dir)
        return result

    def __gen_libs(self, ansible_libraries):
        result = ModuleCommon.gen_result()
        libraries_dir = self.__tmpfs_path + '/library'
        ModuleCommon.mk_directory(libraries_dir)
        for library in ansible_libraries:
            version = ansible_libraries[library]['version']
            dst = self.__tmpfs_path + '/' + library + '-' + version + '.zip'
            library_key = self.__ansible_libraries_s3_path + library + '-' + version + '.zip'

            s3_dl = s3_downloader(s3_session, self.__s3_bucket, library_key ,dst)
            s3_dl.download_file()
            if s3_dl.is_failed():
                result['status'] = False
                result['errors'].append('Download file {0} failed'.format(library_key))
                return result
            ModuleCommon.unzip_file(dst, libraries_dir)
        return result

    def generate(self):
        result = ModuleCommon.gen_result()

        def item_processor(item, funct):
            item_result = funct(self.__roles_dict[item])
            if not item_result['status']:
                for err_msg in item_result['errors']:
                    result['errors'].append(err_msg)
                return False
            return True

        for item, funct in [ ('roles',      self.__gen_roles),
                             ('libraries',  self.__gen_libs),
                             ('tasks',      self.__gen_tasks)]:
            item_result = item_processor(item, funct)
            if not item_result:
                result['status'] = item_result
                return result

        includer_yml_file = [   {'connection': 'local',
                                'gather_facts': 'yes',
                                'become': 'yes',
                                'hosts': 'localhost',
                                'vars': [],
                                'tasks': []}
                            ]
        for var in self.__roles_dict['vars']:
            includer_yml_file[0]['vars'].append(
                { var : self.__roles_dict['vars'][var]['value']}
            )

        for role in self.__roles_dict['roles']:
            includer_yml_file[0]['tasks'].append({'include_role' : {'name': role}})

        for tasklist in self.__roles_dict['tasks']:
            includer_yml_file[0]['tasks'].append({'include' : tasklist})

        dst = self.__tmpfs_path + '/composer.yml'
        try:
            with open(dst, 'w') as yaml_file:
                yaml.safe_dump( includer_yml_file, yaml_file,
                    default_flow_style=False,
                    encoding='utf-8',
                    allow_unicode=True
                )
        except Exception as e:
            result['status'] = False
            result['errors'].append('Errors generating includer file in {0} with errors:' \
                .format(dst, str(e)))
            return result

        for item in ['/tasklists/','/roles/','/library/']:
            dst_dir = self.__working_directory + item
            try:
                os.stat(dst_dir)
            except:
                i_result = ModuleCommon.mk_directory(dst_dir)
                if not i_result['status']:
                    result['status'] = False
                    result['errors'] = i_result['errors']
                    return result
            try:
                for element in os.listdir(self.__tmpfs_path + item):
                    shutil.move(self.__tmpfs_path + item + element, dst_dir)
            except Exception as e:
                result['status'] = False
                result['errors'] = str(e)
                return result
        try:
            shutil.move(
                self.__tmpfs_path + '/composer.yml',
                self.__working_directory + 'composer.yml'
            )
        except Exception as e:
            result['status'] = False
            result['errors'] = str(e)
            return result

        result['status'] = True
        result['payload'] = self.__working_directory + 'composer.yml'
        return result


class ModuleHelper:

    def version_validator(self, version):
        if not re.match(r"^\d+\.\d+\.\d+$", version):
            raise Exception('Semantinc versioning is must, Example: 0.1.1')
        return version

    def get_abs_working_directory(self, module):
        working_directory = module.params['working_directory']
        try:
            os.stat(working_directory)
            working_directory = os.path.abspath(module.params['working_directory'])
        except Exception as e:
            raise Exception('Invalid working_directory: {0}'.format(str(e)))

        if not os.access(working_directory, os.W_OK):
            raise Exception('Working directory is not writable')
        return working_directory + '/'

    def create_if_not_exist_wd(self, module):
        working_directory = module.params['working_directory']
        result = ModuleCommon.mk_directory(working_directory)
        if not result['status']:
            raise Exception('Cannot create the working directory: {0}, Error: {1} ' \
                .format(str(working_directory), result['errors']))

    def param_discovery(self, module):
        if module.params['create_if_needed']:
            self.create_if_not_exist_wd(module)

        parameters = {}
        parameters['role'] = module.params['role']
        parameters['s3_bucket'] = module.params['s3_bucket']
        parameters['roles_s3_key_path'] = module.params['roles_s3_key_path']
        parameters['roles_map_version'] = self.version_validator(module.params['roles_map_version'])
        parameters['role_version'] = self.version_validator(module.params['role_version'])
        parameters['ansible_roles_s3_path'] = module.params['ansible_roles_s3_path']
        parameters['ansible_libraries_s3_path'] = module.params['ansible_libraries_s3_path']
        parameters['ansible_taskslist_s3_path'] = module.params['ansible_taskslist_s3_path']
        parameters['working_directory'] = self.get_abs_working_directory(module)

        return parameters


    def ansibilitze_responses(self, result, module):
        # TODO for V 1.1
        # check if in working directory exist the file .ub_role_composer
        # this file should contains the role_dict that will be useing
        # to decomisse the changes applied on the working_directory
        has_changed = True

        # Maybe we should generate a compatible json/dict response
        meta = result

        # The same as meta but exported as ansible fact
        ansible_facts = {
            'ub_role_composer_entrypoint' : str(result['payload']),
            'ub_role_composer_work_dir'   : str(self.get_abs_working_directory(module))
        }
        return (has_changed, meta, ansible_facts)


def main():
    global s3_bucket

    module = AnsibleModule(
          argument_spec = dict(
              role=dict(required=False, type='str', default="default"),
              s3_bucket=dict(required=False, type='str'),
              roles_s3_key_path=dict(required=False, type='str', default="ansible/iam-role-conf"),
              roles_map_version=dict(required=True, type='str'),
              role_version=dict(required=True, type='str'),
              ansible_roles_s3_path=dict(required=False, type='str', default="ansible/roles/"),
              ansible_libraries_s3_path=dict(required=False, type='str', default="ansible/library/"),
              ansible_taskslist_s3_path=dict(required=False, type='str', default="ansible/tasklists/"),
              working_directory=dict(required=False, type='str', default="../"),
              create_if_needed=dict(required=False, type='bool', default=False),
          ),
      )

    helper = ModuleHelper()
    parameters = helper.param_discovery(module)

    tmpfs_path = tempfile.mkdtemp()
    try:
        dyn_gen = DynConfigGen(
            s3_bucket=parameters['s3_bucket'],
            tmpfs_path=tmpfs_path,
            role_name=parameters['role'],
            roles_map_version=parameters['roles_map_version'],
            role_version=parameters['role_version'],
            roles_s3_key_path=parameters['roles_s3_key_path'],
            ansible_roles_s3_path=parameters['ansible_roles_s3_path'],
            ansible_taskslist_s3_path=parameters['ansible_taskslist_s3_path'],
            ansible_libraries_s3_path=parameters['ansible_libraries_s3_path'],
            working_directory=parameters['working_directory']
        )
    except Exception as e:
        error_dict = {'error' : str(e) }
        module.fail_json(msg='ub_role_composer failed', **error_dict)

    result = dyn_gen.generate()
    if not result['status']:
        module.fail_json(msg='ub_role_composer failed', **result)

    has_changed, meta, ansible_facts = helper.ansibilitze_responses(result, module)
    module.exit_json(changed=has_changed, meta=meta, ansible_facts=ansible_facts)

aws_session = boto3.session.Session()
s3_session = aws_session.resource('s3')

if __name__ == '__main__':
    main()
