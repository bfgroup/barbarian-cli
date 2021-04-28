# Copyright 2021 René Ferdinand Rivera Morell
# Distributed under the Boost Software License, Version 1.0.
# (See accompanying file LICENSE.txt or http://www.boost.org/LICENSE_1_0.txt)

from argparse import ArgumentParser
from os import environ
from shutil import rmtree
from subprocess import run, PIPE
import hashlib
import json
import os.path
import tarfile


class Barbarian(object):
    def __init__(self):
        ap = ArgumentParser("barbarian")
        ap_sub = ap.add_subparsers(dest="command")

        # Export command..
        ap_export = ap_sub.add_parser(
            "export",
            help="Copies the recipe (conanfile.py & associated files) to git branch."
        )
        ap_export.add_argument(
            "path",
            help="Path to a folder containing a conanfile.py or to a recipe file e.g., my_folder/conanfile.py")
        ap_export.add_argument(
            "reference",
            help="user/channel, Pkg/version@user/channel (if name and version are not declared in the conanfile.py) Pkg/version@ if user/channel is not relevant."
        )

        self.args = ap.parse_args()

        if self.args.command:
            if hasattr(self, "command_"+self.args.command):
                getattr(self, "command_"+self.args.command)()

    def exec(self, command, input=None, capture_output=False, env={}):
        input = input.encode() if input else None
        env.update(environ)
        result = run(command, input=input,
                     stdout=PIPE if capture_output else None, env=env,
                     text=True if capture_output else None)
        result.check_returncode()
        return result

    def command_export(self):
        recipe_path = os.path.abspath(self.args.path)
        root_path = recipe_path.partition("/recipes/")[0]
        # Inspect information on the recipe.
        recipe_nv = self.args.reference.split('@', 1)[0].split('/')
        recipe_n = self.exec(
            ["conan", "inspect", "--raw", "name", recipe_path], capture_output=True).stdout
        recipe_v = self.exec(["conan", "inspect", "--raw",
                             "version", recipe_path], capture_output=True).stdout
        if recipe_nv:
            if len(recipe_nv) == 1:
                recipe_v = recipe_nv[0]
            if len(recipe_nv) == 2:
                recipe_n = recipe_nv[0]
                recipe_v = recipe_nv[1]
        recipe_uc = self.args.reference.split('@', 1)[1].split('/')
        recipe_u = recipe_uc[0] if recipe_uc and len(
            recipe_uc) > 0 and len(recipe_uc[0]) > 0 else '_'
        recipe_c = recipe_uc[1] if recipe_uc and len(
            recipe_uc) > 1 and len(recipe_uc[1]) > 0 else '_'
        recipe_data_nv = os.path.join(
            root_path, ".conan", "data", recipe_n, recipe_v)
        recipe_data_nvuc = os.path.join(recipe_data_nv, recipe_u, recipe_c)
        print("[INFO] Exporting to %s" % (recipe_data_nvuc))
        # Remove old data.
        rmtree(recipe_data_nv, ignore_errors=True)
        # Do the basic export.
        env = {'CONAN_USER_HOME': root_path}
        self.exec(["conan", "export", self.args.path,
                  self.args.reference], env=env)
        # Generate the conan_export.tgz.
        conandata_yml = os.path.join(
            recipe_data_nvuc, "export", "conandata.yml")
        conan_export_tgz = os.path.join(recipe_data_nvuc, "conan_export.tgz")
        with tarfile.open(conan_export_tgz, 'w|gz') as tgz:
            tgz.add(conandata_yml, os.path.basename(conandata_yml))
        # Generate snapshot.json.
        snapshot = {}
        with open(conan_export_tgz, "rb") as f:
            snapshot[os.path.basename(conan_export_tgz)] = hashlib.md5(
                f.read()).hexdigest()
        with open(os.path.join(recipe_data_nvuc, "export", "conanmanifest.txt"), "rb") as f:
            snapshot["conanmanifest.txt"] = hashlib.md5(f.read()).hexdigest()
        with open(os.path.join(recipe_data_nvuc, "export", "conanfile.py"), "rb") as f:
            snapshot["conanfile.py"] = hashlib.md5(f.read()).hexdigest()
        with open(os.path.join(recipe_data_nvuc, "snapshot.json"), "w") as f:
            json.dump(snapshot, f)


def run():
    Barbarian()


if __name__ == '__main__':
    run()
