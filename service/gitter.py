from Node import Node
from shutil import rmtree
# from config_creator import create_file_structure
from sesamutils import sesam_logger
from os import mkdir
from git import Repo
import subprocess
from json import dumps as dump_json


class Gitter:
    def __init__(self, url, username, password_or_token, folder, branch):
        self.url = url
        self.username = username
        self.password_or_token = password_or_token
        self.folder = folder
        self.branch = branch

        self.LOGGER = sesam_logger('Git')

        self.repo = self.clone_repo()

    def clone_repo(self):
        self.try_to_delete_dir(self.folder)
        url = f'https://{self.username}:{self.password_or_token}@{self.url}'
        repo = Repo.clone_from(url, self.folder, branch=self.branch)
        return repo

    def push_if_diff(self, dry_run=False):
        if self.is_there_a_diff():
            if dry_run:
                self.LOGGER.info('Dry run! Skipping push to repo.')
            else:
                self.push()
                self.LOGGER.info('Successfully pushed to git repo!')
        else:
            self.LOGGER.info('No current diff! Skipping push to repo.')

    def is_there_a_diff(self):
        import subprocess
        bashCommand = 'git status'
        process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE, cwd=self.repo.working_dir + '/node/')
        output, error = process.communicate()
        if output.endswith(b"working tree clean\n"):
            return False
        else:
            self.LOGGER.info(f'Git status result : "{output}"')
            return True

    def push(self):
        self.LOGGER.debug(f"Pushing to git repo {self.repo.remote}")
        self.repo.git.add([self.repo.working_dir])
        self.repo.index.commit(message='Update based on master node config')
        origin = self.repo.remote('origin')
        origin.push()

    def try_to_delete_dir(self, directory):
        try:
            self.LOGGER.debug(f'Deleting directory "{directory}"')
            rmtree(directory, ignore_errors=True)
        except FileNotFoundError:
            self.LOGGER.info(f'Did not delete "{directory}" because it does not exist!.')

    def try_to_make_dir(self, directory):
        try:
            self.LOGGER.debug(f'Creating directory "{directory}"')
            mkdir(directory)
        except FileExistsError:
            self.LOGGER.info(f'Did not create "{directory}" because it already exists!')

    def create_node_file_structure(self, node: Node, env):
        self.try_to_delete_dir(f'{self.repo.working_dir}/node')
        for p in [
            f'{self.repo.working_dir}/node/',
            f'{self.repo.working_dir}/node/pipes/',
            f'{self.repo.working_dir}/node/systems/',
            f'{self.repo.working_dir}/node/variables/'
        ]:
            self.try_to_make_dir(p)
        tmp_file = None
        for conf in node.conf:
            if conf['type'] == 'pipe':
                tmp_file = open(f'{self.repo.working_dir}/node/pipes/{conf["_id"]}.conf.json', 'w+')
            if 'system' in conf['type']:
                tmp_file = open(f'{self.repo.working_dir}/node/systems/{conf["_id"]}.conf.json', 'w+')
            if conf['type'] == 'metadata':
                tmp_file = open(f'{self.repo.working_dir}/node/node-metadata.conf.json', 'w+')
            tmp_file.write(dump_json(conf, indent=2))
        if len([key for key in node.upload_vars]) != 0:
            tmp_file = open(f'{self.repo.working_dir}/node/variables/variables-{env}.json', 'w+')
            tmp_file.write(dump_json(node.upload_vars, indent=2))
