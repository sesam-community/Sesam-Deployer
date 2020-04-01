from json import loads as load_json
from os import getenv, listdir
from sys import exit
from requests import session as connection
from sesamutils import sesam_logger

# Local imports
from Vaulter import Vaulter
from Node import Node
from config_creator import generate_config, get_vars_from_master
from gitter import Gitter


class AppConfig(object):
    pass


config = AppConfig()

LOGGER = sesam_logger('Autodeployer')
LOGGER.debug(listdir())
ENV_VARS = [
    ('NODE_FOLDER', str, None),
    ('ENVIRONMENT', str, None),
    ('VERIFY_SECRETS', bool,
     [('VAULT_GIT_TOKEN', str, None),
      ('VAULT_MOUNTING_POINT', str, None),
      ('VAULT_URL', str, None)]),
    ('VERIFY_VARIABLES', bool, None),
    ('MASTER_NODE', dict, {"URL": str, "JWT": str, "UPLOAD_VARIABLES": bool, "UPLOAD_SECRETS": bool}),
    ('EXTRA_NODES', dict, None)
]

OPTIONAL_ENV_VARS = ['EXTRA_NODES']

missing_vars = []


def recursive_set_env_var(triple_tuple_env_var):
    for var, t, child_required_vars in triple_tuple_env_var:
        curvar = getenv(var, None)
        if curvar is None:
            if var not in OPTIONAL_ENV_VARS:
                missing_vars.append(var)
        else:
            if t == bool:
                curvar = curvar.lower() == 'true'
                setattr(config, var, curvar)
                if curvar and child_required_vars is not None:
                    recursive_set_env_var(child_required_vars)
            elif t == list:
                setattr(config, var, curvar.split(sep=';'))
            elif t == dict:
                jsoned_curvar = load_json(curvar.replace('`', ''))
                if child_required_vars is not None:
                    for k in child_required_vars:
                        if k not in jsoned_curvar:
                            missing_vars.append(f'{var}->{k}')
                        else:
                            curtype = child_required_vars[k]
                            if curtype == bool:
                                jsoned_curvar[k] = jsoned_curvar[k].lower() == 'true'
                setattr(config, var, jsoned_curvar)
            else:
                setattr(config, var, curvar)


recursive_set_env_var(ENV_VARS)
if len(missing_vars) != 0:
    LOGGER.error(f'Missing variables: {missing_vars}\nExiting.')
    exit(-1)

env = config.ENVIRONMENT.lower()
path = config.NODE_FOLDER
GIT_REPO_BASE_FOLDERS = 'GIT_REPOS'
verify_variables = config.VERIFY_VARIABLES
verify_secrets = config.VERIFY_SECRETS


def do_put(ses, url, json, params=None):
    retries = 4
    try:
        for tries in range(retries):
            request = ses.put(url=url, json=json, params=params)
            if request.ok:
                LOGGER.info(f'Succesfully PUT request to "{url}"')
                return 0
            else:
                LOGGER.warning(
                    f'Could not PUT request to url "{url}". Response:{request.content}. Try {tries} of {retries}')
        LOGGER.critical(f'Each PUT request failed to "{url}".')
        return -1
    except Exception as e:
        LOGGER.critical(f'Got exception "{e}" while doing PUT request to url "{url}"')
        return -2


def deploy(url, jwt, upload_variables, upload_secrets, node: Node):
    session = connection()
    session.headers = {'Authorization': f'bearer {jwt}'}
    if upload_secrets:
        if do_put(session, f'https://{url}/api/secrets', json=node.upload_secrets) != 0:  # Secrets
            exit(-3)
    if upload_variables:
        if do_put(session, f'https://{url}/api/env', json=node.upload_vars) != 0:  # Environment variables
            exit(-4)
    if do_put(session, f'https://{url}/api/config', json=node.conf,
              params={'force': True}) != 0:  # Node config
        exit(-5)


def main():
    variables_filename = None
    verify_variables_from_files = None
    whitelist_filename = None
    name = None
    if env == 'prod' or env == 'test':
        variables_filename = f'variables/variables-{env}.json'
        verify_variables_from_files = [variables_filename]
        whitelist_filename = f'deployment/whitelist-{env}.txt'
        name = 'master'
    elif env == 'ci':
        variables_filename = f'test-env.json'
        whitelist_filename = f'deployment/whitelist-master.txt'
        verify_variables_from_files = ['variables/variables-test.json', 'variables/variables-prod.json']
        name = None
    else:
        LOGGER.critical(f'Environment "{env}" is not test, prod or test')
    LOGGER.info(f'Running with options: env: "{env}" | Verify Variables: "{config.VERIFY_VARIABLES}" | Verify Secrets: "{config.VERIFY_SECRETS}"')
    master_node = Node(path=path, name=name, whitelist_path=whitelist_filename,
                       verify_vars=verify_variables, verify_secrets=verify_secrets,
                       upload_vars_from_file=variables_filename,
                       verify_vars_from_files=verify_variables_from_files)
    master_node.get_node_info()
    vault = None
    if config.VERIFY_SECRETS is True:
        vault = Vaulter(url=config.VAULT_URL,
                        git_token=config.VAULT_GIT_TOKEN,
                        mount_point=config.VAULT_MOUNTING_POINT)

    if getenv("EXTRA_NODES", None) is not None and env != 'ci':
        for extra_node in config.EXTRA_NODES:
            is_proxy = False
            if 'PROXY_NODE' in config.EXTRA_NODES[extra_node]:
                if type(config.EXTRA_NODES[extra_node]['PROXY_NODE']) != bool:
                    is_proxy = config.EXTRA_NODES[extra_node]['PROXY_NODE'].lower() == 'true'
                else:
                    is_proxy = config.EXTRA_NODES[extra_node]['PROXY_NODE']

            current_xtra_node = Node(path=path, name=extra_node,
                                     whitelist_path=whitelist_filename,
                                     verify_vars=verify_variables, verify_secrets=verify_secrets,
                                     upload_vars_from_file=None,
                                     verify_vars_from_files=verify_variables_from_files,
                                     proxy_node=is_proxy)
            current_xtra_node.get_node_info()

            generate_config(master_node, current_xtra_node, f'{path}/extra_nodes/{extra_node}/')
            get_vars_from_master(master_node, current_xtra_node)
            current_xtra_node.verify_node_info(vault,
                                               search_conf=False,
                                               verify_vars=config.VERIFY_VARIABLES,
                                               verify_secrets=config.VERIFY_SECRETS)
            git_repo = Gitter(config.EXTRA_NODES[extra_node]['EXTRA_NODE_GIT_URL'],
                              config.EXTRA_NODES[extra_node]['EXTRA_NODE_GIT_USERNAME'],
                              config.EXTRA_NODES[extra_node]['EXTRA_NODE_GIT_TOKEN'],
                              folder=GIT_REPO_BASE_FOLDERS + '/' + extra_node + '/',
                              branch='master')
            git_repo.create_node_file_structure(current_xtra_node, 'test')
            git_repo.push_if_diff()
    master_node.verify_node_info(vault,
                                 search_conf=True,
                                 verify_vars=config.VERIFY_VARIABLES,
                                 verify_secrets=config.VERIFY_SECRETS)
    deploy(config.MASTER_NODE['URL'],
           config.MASTER_NODE['JWT'],
           config.MASTER_NODE['UPLOAD_VARIABLES'],
           config.MASTER_NODE['UPLOAD_SECRETS'],
           node=master_node)
    LOGGER.info('Successfully deployed!')


if __name__ == '__main__':
    main()
    exit(0)
