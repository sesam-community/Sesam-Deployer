from Node import Node
from os import listdir
from json import loads as load_json, dumps as dump_json
from copy import deepcopy
from sesamutils import sesam_logger

LOGGER = sesam_logger('config-creator')

class ConfigTemplates:
    def __init__(self, path):
        self.pipe_on_extra_from_extra_to_master = None
        self.pipe_on_extra_from_master_to_extra = None
        self.system_on_extra_from_extra_to_master = None
        self.system_on_extra_from_master_to_extra = None

        self.pipe_on_master_from_extra_to_master = None
        self.pipe_on_master_from_master_to_extra = None
        self.system_on_master_from_extra_to_master = None
        self.system_on_master_from_master_to_extra = None

        self.node_metadata = None
        self.get_templates(path)

    def get_templates(self, path):
        for f in listdir(path):
            if f == 'node-metadata.conf.json':
                self.node_metadata = load_json(open(f'{path}{f}', 'r').read())

            # Extra pipes
            if f == 'pipe_on_extra_from_extra_to_master.json':
                self.pipe_on_extra_from_extra_to_master = load_json(open(f'{path}{f}', 'r').read())
            if f == 'pipe_on_extra_from_master_to_extra.json':
                self.pipe_on_extra_from_master_to_extra = load_json(open(f'{path}{f}', 'r').read())
            # Extra systems
            if f == 'system_on_extra_from_extra_to_master.json':
                self.system_on_extra_from_extra_to_master = load_json(open(f'{path}{f}', 'r').read())
            if f == 'system_on_extra_from_master_to_extra.json':
                self.system_on_extra_from_master_to_extra = load_json(open(f'{path}{f}', 'r').read())

            # Master pipes
            if f == 'pipe_on_master_from_extra_to_master.json':
                self.pipe_on_master_from_extra_to_master = load_json(open(f'{path}{f}', 'r').read())
            if f == 'pipe_on_master_from_master_to_extra.json':
                self.pipe_on_master_from_master_to_extra = load_json(open(f'{path}{f}', 'r').read())
            # Master systems
            if f == 'system_on_master_from_extra_to_master.json':
                self.system_on_master_from_extra_to_master = load_json(open(f'{path}{f}', 'r').read())
            if f == 'system_on_master_from_master_to_extra.json':
                self.system_on_master_from_master_to_extra = load_json(open(f'{path}{f}', 'r').read())


def generate_config(master_node: Node, extra_node: Node, template_path):
    templates = ConfigTemplates(template_path)
    from_extra_to_master(master_node, extra_node, templates)
    from_master_to_extra(master_node, extra_node, templates)
    extra_node.conf.append(templates.node_metadata)


def get_vars_from_master(master_node: Node, extra_node: Node):
    extra_node.find_variables_and_secrets()
    for var in extra_node.config_vars:
        if var in master_node.upload_vars:
            extra_node.upload_vars[var] = master_node.upload_vars[var]


def get_output_pipes_on_extra(master_node: Node, extra_node: Node):
    output = []
    for outgoing_pipe in a_writes_to_b(master_node, extra_node):
        for endpoint in extra_node.pipes:
            if 'source' in extra_node.pipes[endpoint]:
                if outgoing_pipe in extra_node.pipes[endpoint]['source']:
                    LOGGER.debug(f'Changing source for endpoint {endpoint} to binary from {outgoing_pipe}')
                    output.append((endpoint, outgoing_pipe))
    return output


def from_extra_to_master(master_node: Node, extra_node: Node, templates: ConfigTemplates):
    pipes = None
    if extra_node.proxy_node:
        pipes = [pipe for pipe in extra_node.pipes if pipe not in [endpoint
                                                                   for endpoint, outgoing in
                                                                   get_output_pipes_on_extra(master_node, extra_node)]]
    else:
        pipes = a_writes_to_b(extra_node, master_node)

    for p in pipes:
        master_template = templates.pipe_on_master_from_extra_to_master
        if master_template is not None:
            master_node.conf.append(load_json(dump_json(master_template).replace('##REPLACE_ID##', p)))
        else:
            LOGGER.warning('Missing template pipe_on_master_from_extra_to_master')

        extra_template = templates.pipe_on_extra_from_extra_to_master
        if extra_template is not None:
            extra_node.conf.append(load_json(dump_json(extra_template).replace('##REPLACE_ID##', p)))
        else:
            LOGGER.warning('Missing template pipe_on_extra_from_extra_to_master.')

    extra_systems = [templates.system_on_extra_from_extra_to_master, templates.system_on_extra_from_master_to_extra]
    for e_s in extra_systems:
        if e_s is not None:
            extra_node.conf.append(load_json(dump_json(e_s).replace('##REPLACE_ID##', master_node.name)))



def from_master_to_extra(master_node: Node, extra_node: Node, templates: ConfigTemplates):
    pipes = a_writes_to_b(master_node, extra_node)
    for p in pipes:
        master_template = templates.pipe_on_master_from_master_to_extra
        if not extra_node.proxy_node:
            if master_template is not None:
                master_node.conf.append(load_json(dump_json(master_template).replace('##REPLACE_ID##', p)))
            else:
                LOGGER.warning('Missing template pipe_on_master_from_master_to_extra')

        extra_template = templates.pipe_on_extra_from_master_to_extra
        if extra_template is not None:
            extra_node.conf.append(load_json(dump_json(extra_template).replace('##REPLACE_ID##', p)))
        else:
            LOGGER.warning('Missing template pipe_on_extra_from_master_to_extra')
    if not extra_node.proxy_node:
        master_systems = [templates.system_on_master_from_master_to_extra, templates.system_on_master_from_extra_to_master]
        for m_s in master_systems:
            if m_s is not None:
                master_node.conf.append(load_json(dump_json(m_s).replace('##REPLACE_ID##', extra_node.name)))


def a_writes_to_b(a, b):
    output = []
    for a_pipe in a.pipes:
        for b_pipe in b.pipes:
            if 'source' in b.pipes[b_pipe]:
                if a.pipes[a_pipe]['sink'] in b.pipes[b_pipe]['source']:
                    output.append(a_pipe)
                    break
    return output
