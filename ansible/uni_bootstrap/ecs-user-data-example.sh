#!/bin/bash -ex
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1

echo Begin: user-data

echo Begin: Bootstraping EC2
yum install -y epel-release yum-utils
yum-config-manager --enable epel
until yum makecache; do
  sleep 5
done
yum install -y yum-python26 wget s3cmd ansible unzip
s3cmd get s3://PUT_HERE_YOUR_S3_BUCKET/ansible/uni_bootstrap/uni_bootstrap-0.0.1.zip /tmp/uni_bootstrap-0.0.1.zip
mkdir /tmp/universal_bootstrap
unzip /tmp/uni_bootstrap-0.0.1.zip -d /tmp/universal_bootstrap/
until ansible-playbook /tmp/universal_bootstrap/uni_bootstrap.yml; do
  sleep 30
  rm -rf /tmp/ansible_composer
done
if [ $? -ne 0 ]
then
    echo Bootstraping failed!! composer couln\'t be starting. Skipping.
else
    sudo ansible-playbook /tmp/ansible_composer/composer.yml
fi
echo End: Bootstraping EC2

echo Begin: start ECS
echo ECS_CLUSTER=YOUR_ECS_CLUSTER >> /etc/ecs/ecs.config
start ecs
yum update -y ecs-init
until $(curl --output /dev/null --silent --head --fail http://localhost:51678/v1/metadata); do
  printf '.'
  sleep 1
done
echo End: start ECS

echo End: user-data
