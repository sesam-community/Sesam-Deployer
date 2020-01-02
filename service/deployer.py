from json import loads as load_json
from os import getenv, path, listdir
from re import findall as regex_get_all
from sys import exit
from logging import Logger
from shutil import rmtree

from git import Repo
from requests import session as connection
from Vaulter import Vaulter
from emailsender import Emailsender


class AppConfig(object):
    pass


config = AppConfig()

log_history = []

LOGGER = Logger('Deployer', getenv('LOG_LEVEL', 'WARNING'))
CLONE_TO_FOLDER = 'tmp'
REQUIRED_ENV_VARS = [
    'VAULT_GIT_TOKEN', 'VAULT_MOUNTING_POINT', 'VAULT_URL',
    'GIT_USERNAME', 'GIT_PASSWORD', 'GIT_REPOSITORIES',
    'NODE_URL', 'NODE_ENV', 'NODE_JWT']
EMAIL_ENV_VARS = [
    'SMTP_USERNAME',
    'SMTP_PASSWORD',
    'SMTP_HOST',
    'SMTP_SENDER',
    'SMTP_SUBJECT',
    'SMTP_RECIPIENTS'
]
LOAD_JSON_VARS = ['GIT_REPOSITORIES', 'SMTP_RECIPIENTS']

# Load env variables
missing_vars = []
for var in REQUIRED_ENV_VARS:
    curvar = getenv(var)
    if curvar is None:
        missing_vars.append(var)
    else:
        setattr(config, var, curvar)

missing_email_vars = []
for var in EMAIL_ENV_VARS:
    curvar = getenv(var)
    if curvar is None:
        missing_email_vars.append(var)
    else:
        setattr(config, var, curvar)

for var in LOAD_JSON_VARS:
    setattr(config, var, load_json(getenv(var)))

some_email_vars_set = len(EMAIL_ENV_VARS) != len(missing_email_vars)

if len(missing_vars) != 0 or (some_email_vars_set and len(missing_email_vars) != 0):
    if some_email_vars_set:
        LOGGER.critical(f'Missing env variables : {missing_vars + missing_email_vars}. Exiting.')
    else:
        LOGGER.critical(f'Missing env variables : {missing_vars}. Exiting.')
    exit(-1)


def log_error(error):
    log_history.append(error)
    LOGGER.error(error)


def exit_with_email(emailer):
    emailstring = '\n'.join(log_history)
    emailer.send_mail(config.SMTP_RECIPIENTS, config.SMTP_SUBJECT, emailstring)
    exit(-1)


def clone_repo(url, username, password_or_token, branch, outputfolder):
    url = f'https://{username}:{password_or_token}@{url}'
    Repo.clone_from(url,
                    outputfolder,
                    branch=branch)


def get_node_info(env, folder_name):
    base_path = folder_name + '/node/'
    whitelist_filename = f'{base_path}deployment/whitelist-{env}.txt'
    variables_filename = f'{base_path}variables/variables-{env}.json'

    node_config = []
    node_secrets = []
    node_env_vars_in_config = []
    node_env_var_file = load_json(open(variables_filename, 'r').read())

    # Load config for each file in whitelist and get secrets
    for filename in list(filter(lambda x: x != '', open(whitelist_filename, 'r').read().split('\n'))):  # f in whitelist
        curfile = open(f'{base_path}{filename}', 'r').read()
        node_secrets += regex_get_all(r'\$SECRET\((\S*?)\)', curfile)
        node_env_vars_in_config += regex_get_all(r'\$ENV\((\S*?)\)', curfile)
        node_config.append(load_json(curfile))

    return node_config, node_secrets, node_env_var_file, node_env_vars_in_config


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
                    f'Could not PUT request to url "{url}". Got response {request.content}. Current try {tries} of {retries}')
        log_error(f'Each PUT request failed to "{url}".')
        return -1
    except Exception as e:
        log_error(f'Got exception "{e}" while doing PUT request to url "{url}"')
        return -2


def main():
    tmp_dirs = [directory for directory in listdir(".") if CLONE_TO_FOLDER in directory and path.isdir(directory)]
    for dir in tmp_dirs:
        rmtree(dir)

    if some_email_vars_set:
        emailer = Emailsender(config.SMTP_HOST, config.SMTP_USERNAME, config.SMTP_PASSWORD, config.SMTP_SENDER)

    vault = Vaulter(url=config.VAULT_URL,
                    git_token=config.VAULT_GIT_TOKEN,
                    mount_point=config.VAULT_MOUNTING_POINT)
    node_configs = []
    node_secrets = []
    node_env_vars_in_files = {}
    node_env_vars_in_configs = []

    for i, repo in enumerate(config.GIT_REPOSITORIES):
        folder_name = CLONE_TO_FOLDER + str(i)
        clone_repo(url=repo['URL'],
                   username=config.GIT_USERNAME,
                   password_or_token=config.GIT_PASSWORD,
                   branch=repo['BRANCH'],
                   outputfolder=folder_name)
        try:
            node_config, node_secret, node_env_vars_in_file, node_env_vars_in_config = get_node_info(config.NODE_ENV,
                                                                                                     folder_name)
            node_configs += node_config
            node_secrets += node_secret
            node_env_vars_in_files.update(node_env_vars_in_file)
            node_env_vars_in_configs += node_env_vars_in_config

        except Exception as e:
            LOGGER.critical(
                f'Failed to get config, secrets & variables from local git repo. because of error "{e}"\nExiting')
            exit(-1)

    secrets_dict = vault.get_secrets(node_secrets)  # Get secret values from vault
    if not vault.verify():  # Check if we are missing a secret in vault.
        log_error(f'Missing secrets: {vault.get_missing_secrets()}. Exiting.')

    for env_var in node_env_vars_in_configs:  # Check if we are using a variable which is not added to env file.
        if env_var not in node_env_vars_in_files:
            log_error(f'Missing environment variable {env_var} in variables file!')

    if len(log_history) != 0:  # Exit if there has been logged errors.
        if some_email_vars_set:
            exit_with_email(emailer)
        else:
            exit(-3)

    # Create requests.session to PUT secrets, variables and config to Sesam Node.
    session = connection()
    session.headers = {'Authorization': f'bearer {config.NODE_JWT}'}

    if do_put(session, f'https://{config.NODE_URL}/api/secrets', json=secrets_dict) != 0:        # Secrets
        if some_email_vars_set:
            exit_with_email(emailer)
        else:
            exit(-2)
    if do_put(session, f'https://{config.NODE_URL}/api/env', json=node_env_vars_in_files) != 0:  # Environment variables
        if some_email_vars_set:
            exit_with_email(emailer)
        else:
            exit(-2)
    if do_put(session, f'https://{config.NODE_URL}/api/config', json=node_configs,               # Node config
              params={'force': True}) != 0:
        if some_email_vars_set:
            exit_with_email(emailer)
        else:
            exit(-2)


if __name__ == '__main__':
    main()
    exit(0)
