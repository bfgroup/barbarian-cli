# Copyright 2021 René Ferdinand Rivera Morell
# Distributed under the Boost Software License, Version 1.0.
# (See accompanying file LICENSE.txt or http://www.boost.org/LICENSE_1_0.txt)

'''
Hook to clean the conandata.yml information for Barbarian style packages.
'''

import os.path
import yaml
import conans.tools


def post_export(output, conanfile, conanfile_path, reference, **args):
    conandata_yml_path = os.path.join(
        os.path.dirname(conanfile_path), "conandata.yml")
    if not os.path.exists(conandata_yml_path):
        return
    conandata_yml_in = yaml.safe_load(conans.tools.load(conandata_yml_path))
    conandata_yml_out = {}
    # Filter the data to only keep the sections and subkeys that match the
    # exported version.
    version = str(conanfile.version)
    for section in conandata_yml_in:
        if version in conandata_yml_in[section]:
            conandata_yml_out[section] = {
                version: conandata_yml_in[section][version]
            }
    # Overwrite out the conandata.yml with the updated info.
    conans.tools.save(conandata_yml_path, yaml.safe_dump(conandata_yml_out))
