from json import loads as load_json
from os import getenv
from re import findall as regex_get_all
from sys import exit

from Vaulter import Vaulter
# from git import Repo
from requests import session as connection
from sesamutils import sesam_logger


class AppConfig(object):
    pass


config = AppConfig()

LOGGER = sesam_logger('Autodeployer')

REQUIRED_ENV_VARS = [
    'NODE_FOLDER',
    'WHITELIST_PATH',
    'VERIFY_SECRETS', 'UPLOAD_SECRETS',
    'VERIFY_VARIABLES_FROM_FILES', 'UPLOAD_VARIABLES_FROM_FILE',
    'NODE_URL', 'NODE_JWT']

LOAD_ENV_AS_JSON = ['VERIFY_SECRETS', 'UPLOAD_SECRETS', 'VERIFY_VARIABLES_FROM_FILES']
IGNORE_MISSING_ENV = ['VERIFY_SECRETS', 'UPLOAD_SECRETS',
                      'VERIFY_VARIABLES_FROM_FILES', 'UPLOAD_VARIABLES_FROM_FILE']

VERIFY_SECRET_REQUIRED_VARS = ['VAULT_GIT_TOKEN', 'VAULT_MOUNTING_POINT', 'VAULT_URL']
# Load env variables
missing_vars = []
for var in REQUIRED_ENV_VARS:
    curvar = getenv(var, None)
    if curvar is None:
        if var not in IGNORE_MISSING_ENV:
            missing_vars.append(var)
        else:
            setattr(config, var, curvar)
    else:
        if var in LOAD_ENV_AS_JSON:
            setattr(config, var, load_json(curvar))
        else:
            setattr(config, var, curvar)

if config.VERIFY_SECRETS is not None and config.VERIFY_SECRETS is True:
    for var in VERIFY_SECRET_REQUIRED_VARS:
        curvar = getenv(var, None)
        if curvar is None:
            missing_vars.append(var)
        else:
            setattr(config, var, curvar)

if len(missing_vars):
    LOGGER.critical(f'Missing env variables : {missing_vars}. Exiting.')
    exit(-1)


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


def get_node_info(node_path):
    node_config = []
    node_secrets = []
    node_env_vars_in_config = []
    node_env_var_file = {}
    node_upload_var_file = {}
    if config.VERIFY_VARIABLES_FROM_FILES is not None:
        for var_file in config.VERIFY_VARIABLES_FROM_FILES:
            node_env_var_file.update(load_json(open(f'{node_path}{var_file}', 'r').read()))

    if config.UPLOAD_VARIABLES_FROM_FILE is not None:
        node_upload_var_file = load_json(open(f'{node_path}{config.UPLOAD_VARIABLES_FROM_FILE}', 'r').read())

    whitelist = node_path + config.WHITELIST_PATH

    # Load config for each file in whitelist and get secrets
    for filename in list(filter(lambda x: x != '', open(whitelist, 'r').read().split('\n'))):  # f in whitelist
        try:
            curfile = open(f'{node_path}{filename}', 'r').read()

            node_secrets += regex_get_all(r'\$SECRET\((\S*?)\)', curfile)
            node_env_vars_in_config += regex_get_all(r'\$ENV\((\S*?)\)', curfile)
            node_config.append(load_json(curfile))
        except FileNotFoundError as e:
            LOGGER.critical(f'Could not find file {node_path}{filename} in config! Exiting.')
            exit(-1)
    return node_config, node_secrets, node_env_var_file, node_env_vars_in_config, node_upload_var_file


def verify_node_info():
    node_config, node_secret, node_env_vars_in_file, node_env_vars_in_config, node_upload_var_file = get_node_info(
        config.NODE_FOLDER)
    secrets_dict = None
    success = True
    if config.VERIFY_SECRETS is True:
        vault = Vaulter(url=config.VAULT_URL,
                        git_token=config.VAULT_GIT_TOKEN,
                        mount_point=config.VAULT_MOUNTING_POINT)
        secrets_dict = vault.get_secrets(node_secret)  # Get secret values from vault
        if not vault.verify():  # Check if we are missing a secret in vault.
            LOGGER.critical(f'Missing secrets: {vault.get_missing_secrets()} in vault.')
            success = False

    if config.VERIFY_VARIABLES_FROM_FILES is not None:
        for env_var in node_env_vars_in_config:
            if env_var not in node_env_vars_in_file:
                LOGGER.critical(
                    f'Missing env var "{env_var}" in node variable file(s) {config.VERIFY_VARIABLES_FROM_FILES}.')
                success = False
    if not success:
        LOGGER.critical('Failed to verify environment variables or secrets! Exiting.')
        exit(-5)
    return node_config, secrets_dict, node_upload_var_file


def deploy_to_node(node_config, secret, variables):
    session = connection()
    session.headers = {'Authorization': f'bearer {config.NODE_JWT}'}
    if config.UPLOAD_SECRETS is not None and config.UPLOAD_SECRETS is True:
        LOGGER.debug('Uploading secrets to node!')
        if do_put(session, f'https://{config.NODE_URL}/api/secrets', json=secret) != 0:  # Secrets
            exit(-3)
    else:
        LOGGER.debug('Skipping uploading of secrets!')

    if config.UPLOAD_VARIABLES_FROM_FILE is not None:
        LOGGER.debug('Uplading variables to node!')
        if do_put(session, f'https://{config.NODE_URL}/api/env', json=variables) != 0:  # Environment variables
            exit(-4)
    else:
        LOGGER.debug('Skipping uploading of variables!')

    LOGGER.debug('Uploading config to node')
    if do_put(session, f'https://{config.NODE_URL}/api/config', json=node_config, params={'force': True}) != 0:
        exit(-2)


def main():
    node_config, secrets_dict, node_upload_var_file = verify_node_info()
    deploy_to_node(node_config, secrets_dict, node_upload_var_file)
    LOGGER.info('Successfully deployed!')


if __name__ == '__main__':
    main()
    exit(0)
