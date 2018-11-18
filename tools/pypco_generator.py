"""PyPCO Generator.

Dynamically generates PyPCO endpoint and model classes from PCO API docs.

Usage:
    pypco_generator.py: --doc-url=<doc-url> --endpoint-path=<endpoint-path> --model-path=<model-path> [--verbose]
    pypco_generator.py: --app=<app> --version=<version> --endpoint-path=<endpoint-path> --model-path=<model-path> [--verbose]
    pypco_generator.py: (-h | --help)

Options:
    -h --help                        Show this help information.
    --app=<app>                      The app for which documentation should be built. "all" for all apps or
                                     one of: "check-ins", "giving", "people", "services", "resources", or "webhooks".
    --doc-url=<doc-url>              The URL to PCO documentation graph (and version) for the desired app.
    --endpoint-path=<endpoint-path>  Path to a folder into which the generated endpoint file should be placed.
                                     Should not be the same as model-path!
    --model-path=<model-path>        Path to a folder into which the generated model file should be placed.
                                     Should not be the same as endpoint-path!
    --verbose                        Enable verbose output.
    --version=<version>              The api version you would like to use (yyyy-mm-dd).
"""

import os
import logging
import base64
import json
import codecs
import requests
import jinja2
from docopt import docopt

# Vars
PCO_DOC_URL_PATTERN = 'https://api.planningcenteronline.com/{app}/v2/documentation/{version}'

PCO_ALL_APPS = [
    'check-ins',
    'giving',
    'people',
    'services',
    'resources',
    'webhooks'
]

# Template for endpoint classes
#region
ENDPOINT_TEMPLATE = """\"\"\"PCO {{ app }} endpoints.

Generated by pypco_generator tool. Manual changes not recommended.
\"\"\"

#pylint: disable=C0304,R0903,C0111,C0321

from .base_endpoint import BaseEndpoint

# The base {{ app }} endpoint
class {{ app }}Endpoint(BaseEndpoint): pass

# All {{ app }} endpoints
{%- for endpoint in endpoints %}
class {{ endpoint['name'] }}({{ app }}Endpoint):
    \"\"\"{{ endpoint['description'] }}\"\"\"
    pass
{% endfor -%}

"""
#endregion

# Template for model classes
#region
MODEL_TEMPlATE="""\"\"\"PCO {{ app }} models.

Generated by pypco_generator tool. Manual changes not recommended.
\"\"\"

#pylint: disable=C0321,R0903,C0111

from .base_model import BaseModel

# The base {{ app }} model
class {{ app }}Model(BaseModel): pass

# {{ app }} Models
{%- for model in models %}
class {{ model['name'] }}({{ app }}Model): 
    \"\"\"{{ model['description'] }}\"\"\"
    ENDPOINT_NAME='{{ model['endpoint'] }}'
{% endfor -%}
"""
#endregion

def generate(
        doc_url,
        endpoint_path,
        model_path
    ):
    '''Generate PyPCO endpoints and models.

    Args:
        doc_url (str): The URL of PCO documentation for which code should be generated.
        endpoint_path (str): Output path for the generated endpoint file.
        model_path (str): Output path for the generated model file.
    '''



    # Determine what app we are building for
    #region
    logging.debug("Finding app we're building for...")
    logging.debug("Doc URL is: {}".format(doc_url))

    url_split = doc_url.split('/')
    app = url_split[url_split.index('v2') - 1]

    logging.info("Building endpoints and models for: {}".format(app.upper()))
    #endregion

    # Get the docs root for the app
    #region
    logging.debug("Accessing {} documentation graph.".format(app.upper()))

    response = requests.get(doc_url)

    if response.status_code != 200:
        logging.debug("Raw response error: {}".format(response.text))

    doc_json = json.loads(response.text)
    #endregion

    # Get model classes for the app
    #region

    vertices = doc_json['data']['relationships']['vertices']['data']
    logging.debug("Found {} vertices for {}.".format(len(vertices), app.upper()))

    models = []

    # This will be used to add descriptions to endpoint class docstrings.
    description_dict = {}

    for vertex in vertices:
        if vertex['id'] == 'organization':
            continue

        response = requests.get("{}/vertices/{}".format(doc_url, vertex['id']))

        if response.status_code != 200:
            logging.debug("Raw response error: {}".format(response.text))

        vertex_json = json.loads(response.text)

        path = vertex_json['data']['attributes']['path'].split('/')

        models.append(
            {
                'name': vertex['attributes']['name'],
                'endpoint': '' if path[-1] == 'v2' else path[path.index('v2') + 1],
                'description': vertex_json['data']['attributes']['description']
            }
        )

        description_dict[vertex_json['data']['id']] = models[-1]['description']

    logging.debug("Results of model resolution: {}".format(models))
    #endregion

    # Output model class
    #region

    model_vars = {
        'app': _underscore_to_camelcase(app, repl_char='-'),
        'models': models
    }

    model_template = jinja2.Template(MODEL_TEMPlATE)

    model_output = model_template.render(model_vars)

    with codecs.open("{}{}{}.py".format(model_path, os.sep, app.replace('-', '_')), 'w', 'utf-8') as model_output_file:
        model_output_file.write(model_output)

    #endregion

    # Get the endpoints for the app
    #region

    outbound_edges = doc_json['data']['relationships']['entry']['data']['relationships']['outbound_edges']['data']

    endpoints = []

    for edge in outbound_edges:
        if edge['relationships']['head']['data']['id'] == 'organization':
            continue

        endpoints.append(
            {
                'name': _underscore_to_camelcase(edge['attributes']['name']),
                'description': description_dict[edge['relationships']['head']['data']['id']]
            }
        )

    logging.debug("Endpoint output is: {}".format(endpoints))

    #endregion

    # Output endpoint class
    #region

    endpoint_vars = {
        'app': _underscore_to_camelcase(app, repl_char='-'),
        'endpoints': endpoints
    }

    logging.debug("Vars for Endpoint template: {}".format(endpoint_vars))

    endpoint_template = jinja2.Template(ENDPOINT_TEMPLATE)

    endpoint_output = endpoint_template.render(endpoint_vars)

    with codecs.open("{}{}{}.py".format(endpoint_path, os.sep, app.replace('-', '_')), 'w', 'utf-8') as endpoint_output_file:
        endpoint_output_file.write(endpoint_output)

    #endregion

def _underscore_to_camelcase(underscore_str, repl_char = '_'):
    '''Convert underscore style string to camel case.

    Args:
        underscore_str (str): A string in underscore style
        repl_char (str): The indicating text that should be transformed to camel case.
                         default is '_'

    Returns:
        string (str): The string converted to camel case.
    '''

    string = list(underscore_str)
    string[0] = string[0].upper()

    try:
        while True:
            under_ndx = string.index(repl_char)
            del string[under_ndx]
            string[under_ndx] = string[under_ndx].upper()
    except ValueError:
        pass

    return ''.join(string)

if __name__ == '__main__':
    arguments = docopt(__doc__)

    logging.basicConfig(
        format = '%(levelname)s >> %(message)s',
        level = logging.DEBUG if arguments['--verbose'] else logging.INFO
    )

    if arguments['--doc-url']:
        logging.info("Running for doc url: {}".format(arguments['--doc-url']))

        generate(
            arguments['--doc-url'],
            arguments['--endpoint-path'],
            arguments['--model-path']
        )
    elif arguments['--app'] != 'all':
        logging.info("Running for app {} and version {}".format(arguments['--app'], arguments['--version']))

        generate(
            PCO_DOC_URL_PATTERN.format(app=arguments['--app'], version=arguments['--version']),
            arguments['--endpoint-path'],
            arguments['--model-path']
        )
    elif arguments['--app'] == 'all':
        logging.info("Running for all apps and version {}".format(arguments['--version']))

        for app in PCO_ALL_APPS:
            generate(
                PCO_DOC_URL_PATTERN.format(app=app, version=arguments['--version']),
                arguments['--endpoint-path'],
                arguments['--model-path']
            )
