"""

Miscellaneous utility functions for user applications.

"""

import base64
import json
import os
import ssl

import boto3
from pyhive import hive

from hops import constants

# ! Needed for hops library backwards compatability
try:
    import requests
except:
    pass

try:
    import http.client as http
except ImportError:
    import httplib as http


def project_id():
    """
    Get the Hopsworks project id from environment variables

    Returns: the Hopsworks project id

    """
    return os.environ[constants.ENV_VARIABLES.HOPSWORKS_PROJECT_ID_ENV_VAR]

def project_name():
    """
    Extracts the project name from the environment

    Returns:
        project name
    """
    return os.environ[constants.ENV_VARIABLES.HOPSWORKS_PROJECT_NAME_ENV_VAR]

def _get_hopsworks_rest_endpoint():
    """

    Returns:
        The hopsworks REST endpoint for making requests to the REST API

    """
    return os.environ[constants.ENV_VARIABLES.REST_ENDPOINT_END_VAR]


hopsworks_endpoint = None
try:
    hopsworks_endpoint = _get_hopsworks_rest_endpoint()
except:
    pass


def _get_host_port_pair():
    """
    Removes "http or https" from the rest endpoint and returns a list
    [endpoint, port], where endpoint is on the format /path.. without http://

    Returns:
        a list [endpoint, port]
    """
    endpoint = _get_hopsworks_rest_endpoint()
    if 'http' in endpoint:
        last_index = endpoint.rfind('/')
        endpoint = endpoint[last_index + 1:]
    host_port_pair = endpoint.split(':')
    return host_port_pair


def _get_http_connection(https=False):
    """
    Opens a HTTP(S) connection to Hopsworks

    Args:
        https: boolean flag whether to use Secure HTTP or regular HTTP

    Returns:
        HTTP(S)Connection
    """
    host_port_pair = _get_host_port_pair()
    if (https):
        PROTOCOL = ssl.PROTOCOL_TLSv1_2
        ssl_context = ssl.SSLContext(PROTOCOL)
        connection = http.HTTPSConnection(str(host_port_pair[0]), int(host_port_pair[1]), context=ssl_context)
    else:
        connection = http.HTTPConnection(str(host_port_pair[0]), int(host_port_pair[1]))
    return connection


def set_auth_header(headers):
    headers[constants.HTTP_CONFIG.HTTP_AUTHORIZATION] = "ApiKey " + _get_api_key(project_name())


def send_request(connection, method, resource, body=None, headers=None):
    """
    Sends a request to Hopsworks. In case of Unauthorized response, submit the request once more as jwt might not
    have been read properly from local container.

    Args:
        connection: HTTP connection instance to Hopsworks
        method: HTTP(S) method
        resource: Hopsworks resource
        body: HTTP(S) body
        headers: HTTP(S) headers

    Returns:
        HTTP(S) response
    """
    if headers is None:
        headers = {}
    set_auth_header(headers)
    connection.request(method, resource, body, headers)
    response = connection.getresponse()
    if response.status == constants.HTTP_CONFIG.HTTP_UNAUTHORIZED:
        set_auth_header(headers)
        connection.request(method, resource, body, headers)
        response = connection.getresponse()
    return response

def _create_hive_connection(featurestore):
    """Returns Hive connection

    Args:
        :featurestore: featurestore to which connection will be established
    """
    # get host without port
    host = os.environ[constants.ENV_VARIABLES.REST_ENDPOINT_END_VAR].split(':')[0]
    hive_conn = hive.Connection(host=host,
                                port=9085,
                                database=featurestore,
                                auth='CERTIFICATES',
                                truststore='trustStore.jks',
                                keystore='keyStore.jks',
                                keystore_password=os.environ["CERT_KEY"])

    return hive_conn


def _parse_rest_error(response_dict):
    """
    Parses a JSON response from hopsworks after an unsuccessful request

    Args:
        response_dict: the JSON response represented as a dict

    Returns:
        error_code, error_msg, user_msg
    """
    error_code = -1
    error_msg = ""
    user_msg = ""
    if constants.REST_CONFIG.JSON_ERROR_CODE in response_dict:
        error_code = response_dict[constants.REST_CONFIG.JSON_ERROR_CODE]
    if constants.REST_CONFIG.JSON_ERROR_MSG in response_dict:
        error_msg = response_dict[constants.REST_CONFIG.JSON_ERROR_MSG]
    if constants.REST_CONFIG.JSON_USR_MSG in response_dict:
        user_msg = response_dict[constants.REST_CONFIG.JSON_USR_MSG]
    return error_code, error_msg, user_msg


def _get_api_key(project_name, secret_key='api-key'):
    """
    Returns secret value from AWS Secrets Manager

    Args:
        :project_name (str): name of project
        :secret_type (str): key for the secret value, e.g. `api-key`, `cert-key`, `trust-store`, `key-store`
    Returns:
        :str: secret value
    """

    def assumed_role():
        client = boto3.client('sts')
        response = client.get_caller_identity()
        # arns for assumed roles in SageMaker follow the following schema
        # arn:aws:sts::123456789012:assumed-role/my-role-name/my-role-session-name
        local_identifier = response['Arn'].split(':')[-1].split('/')
        if len(local_identifier) != 3 or local_identifier[0] != 'assumed-role':
            raise Exception('Failed to extract assumed role from arn: ' + response['Arn'])
        return local_identifier[1]

    secret_name = 'hopsworks/project/' + project_name + '/role/' + assumed_role()

    session = boto3.session.Session()
    if (os.environ[constants.ENV_VARIABLES.REGION_NAME_ENV_VAR] != constants.AWS.DEFAULT_REGION):
        region_name = os.environ[constants.ENV_VARIABLES.REGION_NAME_ENV_VAR]
    else:
        region_name = session.region_name

    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )
    get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    return json.loads(get_secret_value_response['SecretString'])[secret_key]


def write_b64_cert_to_bytes(b64_string, path):
    """Converts b64 encoded certificate to bytes file .

    Args:
        :b64_string (str): b64 encoded string of certificate
        :path (str): path where file is saved, including file name. e.g. /path/key-store.jks
    """

    with open(path, 'wb') as f:
        cert_b64 = base64.b64decode(b64_string)
        f.write(cert_b64)


def abspath(hdfs_path):
    return hdfs_path
