# Copyright 2021 The Kubeflow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Common module for creating GCP launchers based on the AI Platform SDK."""

import json
import logging
import os
from os import path
import re
import time
from typing import Optional

from google.api_core import gapic_v1
from google.cloud import aiplatform
from google.cloud.aiplatform.compat.types import job_state as gca_job_state
from google.protobuf import json_format
from google_cloud_pipeline_components.proto.gcp_resources_pb2 import GcpResources

_POLLING_INTERVAL_IN_SECONDS = 20
_CONNECTION_ERROR_RETRY_LIMIT = 5

_JOB_COMPLETE_STATES = (
    gca_job_state.JobState.JOB_STATE_SUCCEEDED,
    gca_job_state.JobState.JOB_STATE_FAILED,
    gca_job_state.JobState.JOB_STATE_CANCELLED,
    gca_job_state.JobState.JOB_STATE_PAUSED,
)

_JOB_ERROR_STATES = (
    gca_job_state.JobState.JOB_STATE_FAILED,
    gca_job_state.JobState.JOB_STATE_CANCELLED,
    gca_job_state.JobState.JOB_STATE_PAUSED,
)


class JobRemoteRunner():
  """Common module for creating and poll jobs on the Vertex Platform."""

  def __init__(self, job_type, project, location, gcp_resources):
    """Initlizes a job client and other common attributes."""
    self.job_type = job_type
    self.project = project
    self.location = location
    self.gcp_resources = gcp_resources
    self.client_options = {
        'api_endpoint': location + '-aiplatform.googleapis.com'
    }
    self.client_info = gapic_v1.client_info.ClientInfo(
        user_agent='google-cloud-pipeline-components',)
    self.job_uri_prefix = f"https://{self.client_options['api_endpoint']}/v1/"
    self.job_client = self.create_job_client(
        client_options=self.client_options, client_info=self.client_info)

  def create_job_client(self, client_options,
                        client_info) -> aiplatform.gapic.JobServiceClient:
    """Creates a job client using the google.cloud.aiplatform library."""
    return aiplatform.gapic.JobServiceClient(
        client_options=client_options, client_info=client_info)

  def create_gcp_resources(self):
    """Instantiate GCPResources Proto."""
    return GcpResources()

  def check_if_job_exists(self, job_resources) -> Optional[str]:
    """Check if the job already exists."""
    if path.exists(
        self.gcp_resources) and os.stat(self.gcp_resources).st_size != 0:
      with open(self.gcp_resources) as f:
        serialized_gcp_resources = f.read()
        job_resources = json_format.Parse(serialized_gcp_resources,
                                          GcpResources())
        # Resources should only contain one item.
        if len(job_resources.resources) != 1:
          raise ValueError(
              f'gcp_resources should contain one resource, found {len(job_resources.resources)}'
          )

        job_name_group = re.findall(
            job_resources.resources[0].resource_uri,
            f'{self.job_uri_prefix}(.*)')

        if not job_name_group or not job_name_group[0]:
          raise ValueError(
              'Job Name in gcp_resource is not formatted correctly or is empty.'
          )
        job_name = job_name_group[0]

        logging.info('%s name already exists: %s. Continue polling the status',
                     self.job_type, job_name)
      return job_name
    else:
      return None

  def create_job(self, create_job_fn, job_resources, payload) -> str:
    """Create a job."""
    parent = f'projects/{self.project}/locations/{self.location}'
    # TODO(kevinbnaughton) remove empty fields from the spec temporarily.
    job_spec = json.loads(payload, strict=False)
    create_job_response = create_job_fn(self.job_client, parent, job_spec)
    job_name = create_job_response.name

    # Write the job proto to output.
    job_resource = job_resources.resources.add()
    job_resource.resource_type = self.job_type
    job_resource.resource_uri = f'{self.job_uri_prefix}{job_name}'

    with open(self.gcp_resources, 'w') as f:
      f.write(json_format.MessageToJson(job_resources))

    return job_name

  def poll_job(self, get_job_fn, job_name: str):
    """Poll the job status."""
    retry_count = 0
    while True:
      try:
        get_job_response = get_job_fn(self.job_client, job_name)
        retry_count = 0
      # Handle transient connection error.
      except ConnectionError as err:
        retry_count += 1
        if retry_count < _CONNECTION_ERROR_RETRY_LIMIT:
          logging.warning(
              'ConnectionError (%s) encountered when polling job: %s. Trying to '
              'recreate the API client.', err, job_name)
          # Recreate the Python API client.
          self.job_client = self.get_job_client(self.client_options,
                                                self.client_info)
        else:
          logging.error('Request failed after %s retries.',
                        _CONNECTION_ERROR_RETRY_LIMIT)
          # TODO(ruifang) propagate the error.
          raise

      if get_job_response.state == gca_job_state.JobState.JOB_STATE_SUCCEEDED:
        logging.info('Get%s response state =%s', self.job_type,
                     get_job_response.state)
        return
      elif get_job_response.state in _JOB_ERROR_STATES:
        # TODO(ruifang) propagate the error.
        raise RuntimeError('Job failed with error state: {}.'.format(
            get_job_response.state))
      else:
        logging.info(
            'Job %s is in a non-final state %s.'
            ' Waiting for %s seconds for next poll.', job_name,
            get_job_response.state, _POLLING_INTERVAL_IN_SECONDS)
        time.sleep(_POLLING_INTERVAL_IN_SECONDS)
