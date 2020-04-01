from json import loads as load_json, dumps as dump_json
from sesamutils import sesam_logger
from re import findall as regex_findall
from sys import exit
from Vaulter import Vaulter

class Node:

    def __init__(self,
                 path: str, name: str, whitelist_path: str,
                 verify_vars: bool, verify_secrets: bool,
                 upload_vars_from_file: str,
                 verify_vars_from_files: list,
                 proxy_node=False):
        self.path: str = path  # sesam-master-node-config/
        self.name: str = name  # master||extra
        self.node_path = path + '/node'
        self.whitelist_path: str = self.node_path + '/' + whitelist_path
        self.verify_vars: bool = verify_vars
        self.verify_secrets: bool = verify_secrets
        self.proxy_node=proxy_node

        self.read_variables_file = None
        self.upload_vars_from_file = None
        if upload_vars_from_file is not None:
            self.read_variables_file = True
            self.upload_vars_from_file: str = self.node_path + '/' + upload_vars_from_file
        self.verify_vars_from_files: list = [self.node_path + '/' + f for f in verify_vars_from_files]

        self.pipes = {}
        self.conf = []
        self.config_vars = []
        self.config_secrets = []
        self.upload_vars = {}
        self.upload_secrets = {}

        self.LOGGER = sesam_logger(f'Node {self.name}')

    def get_node_info(self):
        care_about_node = self.name is not None
        for filename in list(
                filter(
                    lambda x: x != '',
                    open(self.whitelist_path, 'r').read().split('\n')
                )
        ):  # for file in whitelist
            try:
                care_about_this_file = care_about_node is not True
                curfile = load_json(open(f'{self.node_path}/{filename}', 'r').read())
                if care_about_node:
                    file_belongs_to_node = recursive_getter(curfile, "metadata.node")
                    if file_belongs_to_node is not None:  # if path ^ is not in file
                        care_about_this_file = file_belongs_to_node == self.name  # true if node is correct and is same
                    else:
                        care_about_this_file = self.name == 'master'  # if master True if other False

                if care_about_this_file:
                    self.conf.append(curfile)

                    # Tests to add pipe flows to node. {<pipe_name> : {source: str, sink: str}}
                    pipe_source_type = recursive_getter(curfile, 'source.type')
                    if pipe_source_type is not None:
                        self.add_pipe_flow(curfile)

            except FileNotFoundError as e:
                self.LOGGER.critical(f'Could not find file {self.node_path}{filename} in config! Exiting.')
                exit(-1)
        if self.read_variables_file:
            self.upload_vars = load_json(open(self.upload_vars_from_file, 'r').read())

    def verify_node_info(self, vault: Vaulter, search_conf=False, verify_secrets=False, verify_vars=False):
        if search_conf:
            self.find_variables_and_secrets()
        if verify_secrets:
            if self.secret_verification(vault) is False:
                exit(-1)
        if verify_vars:
            if self.variable_verification() is False:
                exit(-2)

    def variable_verification(self):
        if self.verify_vars is True:
            if len(self.verify_vars_from_files) == 0:
                self.LOGGER.critical('Verify vars is true but files to verify from is not specified!')
                exit(-4)
            else:
                all_vars = {}
                for f in self.verify_vars_from_files:
                    all_vars.update(load_json(open(f).read()))
                missing_vars = []
                for var in self.config_vars:
                    if var not in all_vars:
                        missing_vars.append(var)
                if len(missing_vars) != 0:
                    self.LOGGER.critical(f'Variables verification failed! Missing vars: "{missing_vars}"')
                    return False
                else:
                    self.LOGGER.info(f'Variables verification succeeded :)')

                    return True
        return True  # If verify vars is false

    def secret_verification(self, vault: Vaulter):
        self.upload_secrets = vault.get_secrets(self.config_secrets)
        if vault.verify() is False:
            self.LOGGER.critical(f'Secrets verification failed! Missing secrets: "{vault.get_missing_secrets()}"')
            return False
        else:
            self.LOGGER.info(f'Secrets verification succeeded :)')
            return True

    def find_variables_and_secrets(self):
        str_conf = dump_json(self.conf)
        self.config_vars = regex_findall(r'\$ENV\((\S*?)\)', str_conf)
        self.config_secrets = regex_findall(r'\$SECRET\((\S*?)\)', str_conf)

    def add_pipe_flow(self, pipe_conf):

        pipe_id = pipe_conf['_id']
        self.pipes[pipe_id] = {}

        # Get pipe sources
        source_type = recursive_getter(pipe_conf, 'source.type')
        true_source = None
        if source_type == 'dataset':
            true_source = recursive_getter(pipe_conf, 'source.dataset')
        elif source_type == 'merge':
            true_source = recursive_getter(pipe_conf, 'source.datasets')

        if true_source is not None:
            if type(true_source) == list:
                self.pipes[pipe_id]['source'] = [e.split(" ")[0] for e in true_source]
            else:
                self.pipes[pipe_id]['source'] = [true_source]

        sink_type = recursive_getter(pipe_conf, 'sink.type')
        true_sink = None
        if sink_type is not None:
            if sink_type == 'dataset':
                true_sink = recursive_getter(pipe_conf, 'sink.dataset')
        if true_sink is None:  # because pipe can have sink type dataset without specifying dataset name.
            true_sink = pipe_id

        self.pipes[pipe_id]['sink'] = true_sink  # Either specified dataset or same as pipe id

        self.LOGGER.debug(f'Flow for "{pipe_id}" is: "{self.pipes[pipe_id]}"')

    def pipe_flow_from_conf(self):
        self.pipes = {}
        for entity in self.conf:
            if recursive_getter("type") == 'Pipe':
                self.add_pipe_flow(entity)


def recursive_getter(entity, key_str):
    keys = key_str.split('.')
    len_keys = len(keys)

    def iter_recursive_getter(cur_entity, index=0):
        if index == len_keys:
            return cur_entity
        elif keys[index] in cur_entity:
            return iter_recursive_getter(cur_entity[keys[index]], index + 1)
        else:
            return None

    return iter_recursive_getter(entity)
