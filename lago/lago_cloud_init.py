import functools
import logging
import os
from os import path
import yaml
from textwrap import dedent
from jinja2 import Environment, PackageLoader

import log_utils
import utils

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)


class LagoCloudInits(object):
    def __init__(self, vms, iso_dir, ssh_public_key):
        self._vms = vms
        self._iso_dir = iso_dir
        self._ssh_public_key = ssh_public_key

    def generate(self, collect_only=False, with_threads=False):
        self._validate_iso_dir_exist()
        jinja_env = Environment(loader=PackageLoader('lago', 'templates'))

        with LogTask('Creating cloud-init iso images'):
            handlers = [
                LagoCloudInit(
                    vm, self._iso_dir, dev, self._ssh_public_key, jinja_env
                ) for vm, dev in self._vms
            ]

            if with_threads:
                iso_specs = utils.invoke_different_funcs_in_parallel(
                    *list(handlers)
                )
            else:
                iso_specs = []
                for handler in handlers:
                    iso_specs.append(handler(collect_only))

        return dict(iso_specs)

    def _validate_iso_dir_exist(self):
        if not path.isdir(self._iso_dir):
            os.mkdir(self._iso_dir)


class LagoCloudInit(object):
    def __init__(self, vm, iso_dir, free_dev, ssh_public_key, jinja_env):
        self._vm = vm
        self._cloud_spec = self._vm.spec['cloud-init'] or {}
        self._iso_dir = path.join(iso_dir, self._vm.name())
        self._iso_path = path.join(
            self._iso_dir, '{}.iso'.format(self._vm.name())
        )
        self._free_dev = free_dev
        self._ssh_public_key = ssh_public_key
        self._jinja_env = jinja_env
        self._mapping = None
        self._validate_iso_dir_exist()
        self._set_mapping()

    def _validate_iso_dir_exist(self):
        if not path.isdir(self._iso_dir):
            os.mkdir(self._iso_dir)

    def _set_mapping(self):
        self._mapping = {
            'user-data':
                {
                    'root_password': self._vm.root_password(),
                    'public_key': self._ssh_public_key
                },
            'meta-data': {
                'hostname': self._vm.name()
            },
        }

    def generate(self, collect_only=False):
        with LogTask('Creating cloud-init iso for {}'.format(self._vm.name())):
            normalized_spec = self._normalize_spec()
            if not collect_only:

                write_to_iso = []
                user_data = normalized_spec.pop('user-data')
                if user_data:
                    user_data_dir = path.join(self._iso_dir, 'user-data')
                    self._write_user_data_to_file(user_data, user_data_dir)
                    write_to_iso.append(user_data_dir)

                for spec_type, spec in normalized_spec.viewitems():
                    out_dir = path.join(self._iso_dir, spec_type)
                    self._write_yaml_to_file(spec, out_dir)
                    write_to_iso.append(out_dir)

                if write_to_iso:
                    self.gen_iso_image(self._iso_path, write_to_iso)
                else:
                    LOGGER.debug(
                        '{}: no specs were found', format(self._vm.name())
                    )
            else:
                print yaml.safe_dump(normalized_spec)

        iso_spec = self._vm.name(), self._gen_iso_spec()
        LOGGER.debug(iso_spec)

        return iso_spec

    def _normalize_spec(self):
        """
        For all spec type in 'self._mapping', load the default and user
        given spec and merge them.

        Returns:
            dict: the merged default and user spec
        """

        normalized_spec = {}

        for spec_type, mapping in self._mapping.viewitems():
            normalized_spec[spec_type] = utils.deep_update(
                self._load_default_spec(spec_type, **mapping),
                self._load_given_spec(
                    self._cloud_spec.get(spec_type, {}), spec_type
                )
            )

        return normalized_spec

    def _load_given_spec(self, given_spec, spec_type):
        """
        Load spec_type given from the user.
        If 'path' is in the spec, the file will be loaded from 'path',
        otherwise the spec will be returned without a change.

        Args:
            dict or list: which represents the spec
            spec_type(dict): the type of the spec

        Returns:
            dict or list: which represents the spec
        """
        if not spec_type:
            LOGGER.debug('{} spec is empty'.format(spec_type))
            return given_spec

        if 'path' in given_spec:
            LOGGER.debug(
                'loading {} spec from {}'.
                format(spec_type, given_spec['path'])
            )
            given_spec = self._load_spec_from_file(given_spec['path'])

        return given_spec

    def _load_default_spec(self, spec_type, **kwargs):
        """
        Load default spec_type template from lago.templates
        and render it with jinja2

        Args:
            spec_type(dict): the type of the spec
            kwargs(dict): k, v for jinja2

        Returns:
            dict or list: which represnets the spec
        """
        template_name = 'cloud-init-{}-{}.j2'.format(
            spec_type, self._vm.distro()
        )

        base_template_name = 'cloud-init-{}-base.j2'.format(spec_type)

        template = self._jinja_env.select_template(
            [template_name, base_template_name]
        )

        default_spec = template.render(**kwargs)
        LOGGER.debug(
            'default spec for {}:\n{}'.format(spec_type, default_spec)
        )

        return yaml.safe_load(default_spec)

    def _gen_iso_spec(self):
        return {
            'type': 'file',
            'path': self._iso_path,
            'dev': self._free_dev,
            'format': 'iso',
            'name': '{}-cloud-init'.format(self._vm.name())
        }

    def __call__(self, *args, **kwargs):
        return self.generate(*args, **kwargs)

    @staticmethod
    def _load_spec_from_file(path_to_file):
        try:
            with open(path_to_file, mode='rt') as f:
                return yaml.safe_load(f)
        except yaml.YAMLError:
            raise LagoCloudInitParseError(path_to_file)

    @staticmethod
    def _write_user_data_to_file(user_data, out_dir):
        with open(out_dir, mode='wt') as f:
            f.write('#cloud-config')
            f.write('\n')
            yaml.safe_dump(user_data, f)

    @staticmethod
    def _write_yaml_to_file(spec, out_dir):
        with open(out_dir, mode='wt') as f:
            yaml.safe_dump(spec, f)

    @staticmethod
    def gen_iso_image(out_file_name, files):
        cmd = [
            'genisoimage',
            '-output',
            out_file_name,
            '-volid',
            'cidata',
            '-joliet',
            '-rock',
        ]

        cmd.extend(files)

        utils.run_command_with_validation(cmd)


class LagoCloudInitException(utils.LagoException):
    pass


class LagoCloudInitParseError(LagoCloudInitException):
    def __init__(self, file_path):
        super(LagoCloudInitParseError, self).__init__(
            dedent(
                """
                    Failed to parse yaml file {}.
                    """.format(file_path)
            )
        )
