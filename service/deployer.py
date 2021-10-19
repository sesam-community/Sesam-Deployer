from difflib import context_diff
from json import loads as load_json, dumps as dump_json
from os import getenv, listdir
from sys import exit
from time import sleep

from requests import session as connection
from sesamutils import sesam_logger
from slack import WebClient
from slack.errors import SlackApiError

# Local imports
from Node import Node
from Vaulter import Vaulter
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
    ('MASTER_NODE', dict,
     {"URL": str, "JWT": str, "UPLOAD_VARIABLES": bool, "UPLOAD_SECRETS": bool, "CONFIG_GROUP": str}),
    ('EXTRA_NODES', dict, None),
    ('DRY_RUN', bool, None),
    ('SLACK_API_TOKEN', str, None),
    ('SLACK_CHANNEL', str, None),
    ('RELEASE_URL', str, None),
    ('VAULT_PATH_PREFIX', str, None),
    ('UPLOAD_VARIABLES_FROM_FILE', str, None),
    ('VERIFY_VARIABLES_FROM_FILES', list, None),
    ('WHITELIST_FILE_PATH', str, None)
]

OPTIONAL_ENV_VARS = ['EXTRA_NODES', 'SLACK_API_TOKEN', 'SLACK_CHANNEL', 'CONFIG_GROUP', 'RELEASE_URL',
                     'VAULT_PATH_PREFIX', 'VERIFY_VARIABLES_FROM_FILES','UPLOAD_VARIABLES_FROM_FILE',
                     'WHITELIST_FILE_PATH']

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
                            if k not in OPTIONAL_ENV_VARS:
                                missing_vars.append(f'{var}->{k}')
                        else:
                            curtype = child_required_vars[k]
                            if curtype == bool:
                                jsoned_curvar[k] = jsoned_curvar[k].lower() == 'true'
                setattr(config, var, jsoned_curvar)
            else:
                setattr(config, var, curvar)


recursive_set_env_var(ENV_VARS)

env = getattr(config, 'ENVIRONMENT', '').lower()
path = getattr(config, 'NODE_FOLDER', None)
GIT_REPO_BASE_FOLDERS = 'GIT_REPOS'
verify_variables = getattr(config, 'VERIFY_VARIABLES', None)
verify_secrets = getattr(config, 'VERIFY_SECRETS', None)
dry_run = getattr(config, 'DRY_RUN', None)

if len(missing_vars) != 0:
    if missing_vars == ['MASTER_NODE'] and dry_run and env == 'ci':
        LOGGER.info('Only verifying config, not talking to any nodes.')
        pass
    else:
        LOGGER.error(f'Missing variables: {missing_vars}\nExiting.')
        exit(-1)

RETRY_TIMER = 30
RETRIES = 5


def send_slack_file(msg):
    client = WebClient(token=getattr(config, 'SLACK_API_TOKEN', None))
    channel = config.SLACK_CHANNEL
    filepath = f'./{env}-diff.txt'
    diff_file = open(filepath, 'w')
    diff_file.write(msg)
    diff_file.close()

    try:
        response = client.files_upload(
            channels=channel,
            file=filepath)
        assert response["file"]  # the uploaded file
        LOGGER.info('Successfully posted file to slack.')
    except SlackApiError as e:
        # You will get a SlackApiError if "ok" is False
        assert e.response["ok"] is False
        assert e.response["error"]  # str like 'invalid_auth', 'channel_not_found'
        LOGGER.warning(f"Got an error while uploading file to slack: {e.response['error']}")


def send_slack_message(msg):
    client = WebClient(token=getattr(config, 'SLACK_API_TOKEN', None))
    channel = config.SLACK_CHANNEL
    try:
        response = client.chat_postMessage(
            channel=channel,
            text=msg)
    except SlackApiError as e:
        # You will get a SlackApiError if "ok" is False
        assert e.response["ok"] is False
        assert e.response["error"]  # str like 'invalid_auth', 'channel_not_found'
        LOGGER.warning(f"Got an error while sending message to slack: {e.response['error']}")



def do_put(ses, url, json, params=None):
    try:
        for tries in range(RETRIES):
            request = ses.put(url=url, json=json, params=params)
            if request.ok:
                LOGGER.info(f'Succesfully PUT request to "{url}"')
                return 0
            else:
                LOGGER.warning(
                    f'Could not PUT request to url "{url}". Response:{request.content}. Try {tries} of {RETRIES}')
                sleep(RETRY_TIMER)
        LOGGER.critical(f'Each PUT request failed to "{url}".')
        return -1
    except Exception as e:
        LOGGER.critical(f'Got exception "{e}" while doing PUT request to url "{url}"')
        return -2


def do_get(ses, url, params=None):
    try:
        for tries in range(RETRIES):
            request = ses.get(url=url, params=params)
            if request.ok:
                LOGGER.info(f'Successfully GOT request from "{url}"')
                return load_json(request.content.decode('UTF-8'))
            else:
                LOGGER.warning(
                    f'Could not GET request from url "{url}". Response:{request.content}. Try {tries} of {RETRIES}')
                sleep(RETRY_TIMER)
        LOGGER.critical(f'Each GET request failed to "{url}".')
    except Exception as e:
        LOGGER.critical(f'Got exception "{e}" while doing GET request to url "{url}"')


def do_post(ses, url, json, params=None):
    try:
        for tries in range(RETRIES):
            request = ses.post(url=url, json=json, params=params)
            if request.ok:
                LOGGER.info(f'Successful POST request to "{url}"')
                return request.content.decode('UTF-8')
            else:
                LOGGER.warning(
                    f'Could not POST request to url "{url}". Response:{request.content}. Try {tries} of {RETRIES}')
                sleep(RETRY_TIMER)
        LOGGER.critical(f'Each POST request failed to "{url}".')
        return None
    except Exception as e:
        LOGGER.critical(f'Got exception "{e}" while doing POST request to url "{url}"')
        return None


def deploy(url, jwt, upload_variables, upload_secrets, node: Node, config_group=None):
    session = connection()
    session.headers = {'Authorization': f'bearer {jwt}'}
    if config_group is None:
        if upload_secrets:
            if do_put(session, f'https://{url}/api/secrets', json=node.upload_secrets) != 0:  # Secrets
                exit(-3)
        if upload_variables:
            if do_put(session, f'https://{url}/api/env', json=node.upload_vars) != 0:  # Environment variables
                exit(-4)
        if do_put(session, f'https://{url}/api/config', json=node.conf,
                  params={'force': True}) != 0:  # Node config
            exit(-5)
    else:
        for f in node.conf:
            if f['type'] == 'metadata':
                node.conf.remove(f)
                LOGGER.warning('Removing node metadata from upload config because CONFIG_GROUP is set!')

        if upload_secrets:
            if do_put(session, f'https://{url}/api/secrets', json=node.upload_secrets) != 0:  # Secrets
                exit(-3)
        if upload_variables:
            if do_put(session, f'https://{url}/api/env', json=node.upload_vars) != 0:  # Environment variables
                exit(-4)
        if do_put(session, f'https://{url}/api/config/{config_group}', json=node.conf,
                  params={'force': True}) != 0:  # Node config
            exit(-6)


def do_context_diff(original, new, dump_as_json=False):
    if dump_as_json:
        return ''.join(context_diff(dump_json(original, indent=2).splitlines(True),
                                    dump_json(new, indent=2).splitlines(True),
                                    'Original', 'New'))
    return ''.join(context_diff(original.splitlines(True),
                                new.splitlines(True),
                                'Original', 'New'))


def a_not_in_b(a, b):
    output = []
    for af in a:
        found_file = False
        for bf in b:
            if af['_id'] == bf['_id']:
                found_file = True
                break
        if not found_file:
            output.append(af['_id'])
    return output


def do_diff(url, jwt, node: Node, config_group=None):
    session = connection()
    session.headers = {'Authorization': f'bearer {jwt}'}
    total_string = ''

    # Do config diff
    config_url = f'https://{url}/api/config'
    if config_group is not None:
        config_url += f'/{config_group}'
    running_node_conf = sorted(do_get(session, config_url), key=lambda k: k['_id'])
    new_node_config = sorted(node.conf, key=lambda k: k['_id'])


    LOGGER.info('Running config diff!')
    removed_files = []
    new_files = a_not_in_b(new_node_config, running_node_conf)

    for rf in running_node_conf:
        found_file = False
        for nf in new_node_config:
            if nf['_id'] == rf['_id']:
                found_file = True
                if rf != nf:
                    rf_formatted = do_post(session, url=f'https://{url}/api/utils/reformat-config', json=rf)
                    nf_formatted = do_post(session, url=f'https://{url}/api/utils/reformat-config', json=nf)
                    LOGGER.info(f'{nf["_id"]}\n{do_context_diff(rf_formatted, nf_formatted)}')
                    total_string += f'{nf["_id"]}\n{do_context_diff(rf_formatted, nf_formatted)}\n'
                break
        if not found_file:
            removed_files.append(rf['_id'])

    LOGGER.info(f'New files!: {new_files}')
    LOGGER.info(f'Removed files!: {removed_files}')
    total_string += f'New files!: {new_files}\n'
    total_string += f'Removed files!: {removed_files}\n'

    # Do variable diff
    if config_group is None:
        running_node_vars = do_get(session, f'https://{url}/api/env')
        new_node_vars = node.upload_vars
        LOGGER.info(f'Running variables diff!\n{do_context_diff(running_node_vars, new_node_vars, dump_as_json=True)}')
        total_string += f'Running variables diff!\n{do_context_diff(running_node_vars, new_node_vars, dump_as_json=True)}\n'

    if getattr(config, 'SLACK_API_TOKEN', None) is not None:
        release_url = getattr(config, 'RELEASE_URL', None)
        if release_url:
            send_slack_message(f'This release can be found at: {release_url}')
        send_slack_file(total_string)


def main():
    variables_filename = None
    verify_variables_from_files = None
    whitelist_filename = None
    name = None
    if env == 'prod' or env == 'test':
        variables_filename = getattr(config, 'UPLOAD_VARIABLES_FROM_FILE', f'variables/variables-{env}.json')
        verify_variables_from_files = [variables_filename]
        whitelist_filename = getattr(config, 'WHITELIST_FILE_PATH', f'deployment/whitelist-{env}.txt')
        name = 'master'
    elif env == 'ci':
        variables_filename = getattr(config, 'UPLOAD_VARIABLES_FROM_FILE', f'test-env.json')
        whitelist_filename = getattr(config, 'WHITELIST_FILE_PATH', f'deployment/whitelist-master.txt')
        verify_variables_from_files = getattr(config, 'VERIFY_VARIABLES_FROM_FILES',
                                              ['variables/variables-test.json', 'variables/variables-prod.json'])
        name = None
    else:
        LOGGER.critical(f'Environment "{env}" is not test, prod or test')
    LOGGER.info(
        f'Running with options: env: "{env}" | Verify Variables: "{config.VERIFY_VARIABLES}" | Verify Secrets: "{config.VERIFY_SECRETS}" | Dry Run: "{dry_run}"')
    master_node = Node(path=path, name=name, whitelist_path=whitelist_filename,
                       verify_vars=verify_variables, verify_secrets=verify_secrets,
                       upload_vars_from_file=variables_filename,
                       verify_vars_from_files=verify_variables_from_files)
    master_node.get_node_info()
    vault = None
    if config.VERIFY_SECRETS is True:
        if getattr(config, "VAULT_PATH_PREFIX", None):
            vault = Vaulter(url=config.VAULT_URL,
                            git_token=config.VAULT_GIT_TOKEN,
                            mount_point=config.VAULT_MOUNTING_POINT,
                            vault_path_prefix=config.VAULT_PATH_PREFIX)
        else:
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
            if is_proxy:
                LOGGER.debug(f'Extra node {extra_node} is a proxy node!')
            else:
                LOGGER.debug(f'Extra node {extra_node} is NOT a proxy node!')



            current_xtra_node = Node(path=path, name=extra_node,
                                     whitelist_path=whitelist_filename,
                                     verify_vars=verify_variables, verify_secrets=verify_secrets,
                                     upload_vars_from_file=None,
                                     verify_vars_from_files=verify_variables_from_files,
                                     proxy_node=is_proxy)
            current_xtra_node.get_node_info()

            generate_config(master_node, current_xtra_node,
                            f'{path}/{config.EXTRA_NODES[extra_node]["EXTRA_NODE_TEMPLATE_PATH"]}')
            get_vars_from_master(master_node, current_xtra_node)
            current_xtra_node.verify_node_info(vault,
                                               search_conf=False,
                                               verify_vars=config.VERIFY_VARIABLES,
                                               verify_secrets=config.VERIFY_SECRETS)
            git_repo = Gitter(config.EXTRA_NODES[extra_node]['EXTRA_NODE_GIT_URL'],
                              config.EXTRA_NODES[extra_node]['EXTRA_NODE_GIT_USERNAME'],
                              config.EXTRA_NODES[extra_node]['EXTRA_NODE_GIT_TOKEN'],
                              folder=GIT_REPO_BASE_FOLDERS + '/' + extra_node + '/',
                              branch=config.EXTRA_NODES[extra_node]['EXTRA_NODE_GIT_BRANCH'])
            git_repo.create_node_file_structure(current_xtra_node, env)
            git_repo.push_if_diff(dry_run)
    master_node.verify_node_info(vault,
                                 search_conf=True,
                                 verify_vars=config.VERIFY_VARIABLES,
                                 verify_secrets=config.VERIFY_SECRETS)
    if env != 'ci':
        do_diff(config.MASTER_NODE['URL'],
                config.MASTER_NODE['JWT'],
                master_node,
                config_group=config.MASTER_NODE.get('CONFIG_GROUP', None))
    if dry_run:
        LOGGER.info('Succesfully completed dry run!')
    else:
        deploy(config.MASTER_NODE['URL'],
               config.MASTER_NODE['JWT'],
               config.MASTER_NODE['UPLOAD_VARIABLES'],
               config.MASTER_NODE['UPLOAD_SECRETS'],
               node=master_node,
               config_group=config.MASTER_NODE.get('CONFIG_GROUP', None))
        LOGGER.info('Successfully deployed!')


if __name__ == '__main__':
    main()
    exit(0)
