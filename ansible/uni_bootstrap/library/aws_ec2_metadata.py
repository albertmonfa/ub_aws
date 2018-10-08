#!/usr/bin/python
'''
Author: Albert Monfa 2017

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

class AWSMetadata:

    AWS_METADATA = None
    AWS_METADATA_ROLE = None
    AWS_METADATA_SUCCESS = False
    AWS_INSTANCE_ID = False
    AWS_REGION = False

    def __init__( self, metadata_url):
        self.metadata_url = metadata_url

        try:
           self.set_aws_metadata( self.get_metadata() )
        except Exception:
           raise Exception("Impossible to obtain metadata. Is it running in an EC2 instance?")

        if not self.validate_permissions():
           raise Exception('Cannot access to EC2 Metadata, Review the role assigned to the EC2 Instance')

        else:
           self.AWS_METADATA_ROLE = self.get_role()
           self.AWS_METADATA_SUCCESS = True
           self.AWS_REGION = self.get_region()
           self.AWS_INSTANCE_ID = self.get_instance_id()

    def __url( self, path ):
        return "{0}{1}" . format (self.metadata_url, path)


    def discover_url( self ):
        url = self.__url("/latest/meta-data/iam/security-credentials/")
        response = requests.get(url)
        if response.status_code == 200:
           url = str(url) + str(response.text)
           return url
        else:
           sys.exit("Problem recieving security credentials")

    def get_region( self ):
        url = self.__url("/latest/dynamic/instance-identity/document")
        response = requests.get(url)
        if response.status_code == 200:
           return response.json()['region']
        return None

    def get_instance_id( self ):
        url = self.__url("/latest/meta-data/instance-id")
        response = requests.get(url)
        if response.status_code == 200:
           return response.text
        return None

    def get_role( self ):
        url = self.__url("/latest/meta-data/iam/security-credentials/")
        response = requests.get(url)
        if response.status_code == 200:
           return response.text
        return None

    def get_metadata( self ):
        url = self.discover_url()
        return requests.get(url).json()

    def set_aws_metadata( self, metadata ):
        self.AWS_METADATA = metadata

    def validate_permissions( self ):
        metadata = self.get_metadata()
        if "Code" in metadata:
           if metadata['Code'] == "Success":
              return True
        return False


class ModuleHelper:

    def param_discovery(self, module):

        aws_endpoint = module.params['aws_endpoint']
        tags = module.params['tags']
        return aws_endpoint, tags

    def get_response( self, response ):
        has_changed = True
        meta = response

        return (has_changed, meta)


def getTags( region, instance_id):
    try:
        import boto3
        ec2 = boto3.resource('ec2', region_name=region)
        ec2instance = ec2.Instance(instance_id)
        return ec2instance.tags
    except Exception:
        return dict()

def main():
  module = AnsibleModule(
        argument_spec = dict(
            aws_endpoint=dict(required=False, type='str', default="http://169.254.169.254"),
            tags=dict(required=False, type='bool', default=True)
        ),
    )

  helper = ModuleHelper()
  aws_endpoint, tags = helper.param_discovery(module)

  metadata = AWSMetadata(aws_endpoint)

  response = {}

  response['z_aws_iam_role'] = metadata.AWS_METADATA_ROLE
  response['z_aws_ec2_instance_id'] = metadata.AWS_INSTANCE_ID
  response['z_aws_region'] = metadata.AWS_REGION
  if tags:
      response['z_aws_ec2_instance_tags'] = getTags(metadata.AWS_REGION,metadata.AWS_INSTANCE_ID)
  else:
      response['z_aws_ec2_instance_tags'] = {}

  has_changed, meta = helper.get_response(response)
  module.exit_json(changed=has_changed, meta=meta, ansible_facts=dict(
                                                                       z_aws_iam_role=metadata.AWS_METADATA_ROLE,
                                                                       z_aws_ec2_instance_id=metadata.AWS_INSTANCE_ID,
                                                                       z_aws_region=metadata.AWS_REGION,
                                                                       z_aws_ec2_instance_tags= response['z_aws_ec2_instance_tags']
                                                                     )
                  )

from ansible.module_utils.basic import *
from ansible.module_utils.urls import *
from ansible.module_utils._text import to_text
from pprint import pprint
import json, requests


global aws_endpoint

if __name__ == '__main__':
    main()
