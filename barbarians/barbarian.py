# Copyright 2021 René Ferdinand Rivera Morell
# Distributed under the Boost Software License, Version 1.0.
# (See accompanying file LICENSE.txt or http://www.boost.org/LICENSE_1_0.txt)

from argparse import ArgumentParser
from os import environ, getcwd
from shutil import rmtree, copytree
from subprocess import run, PIPE
import hashlib
import json
import os.path
import tarfile
import datetime


class Barbarian(object):
    def __init__(self):
        ap = ArgumentParser("barbarian")
        ap_sub = ap.add_subparsers(dest="command")

        # Export command..
        ap_export = ap_sub.add_parser(
            "export",
            help="Copies the recipe (conanfile.py & associated files) to local repo cache."
        )
        ap_export.add_argument(
            "path",
            help="Path to a folder containing a conanfile.py or to a recipe file e.g., my_folder/conanfile.py")
        ap_export.add_argument(
            "reference",
            help="Pkg/version@user/channel, Pkg/version@ if user/channel is not relevant."
        )

        # Upload command..
        ap_upload = ap_sub.add_parser(
            "upload",
            help="Copies the current exported recipe to the local publish location."
        )
        ap_upload.add_argument(
            "reference",
            help="user/channel, Pkg/version@user/channel (if name and version are not declared in the conanfile.py) Pkg/version@ if user/channel is not relevant."
        )

        self.args = ap.parse_args()

        if self.args.command:
            if hasattr(self, "command_"+self.args.command):
                getattr(self, "command_"+self.args.command)()

    def exec(self, command, input=None, capture_output=False, env={}):
        input = input.encode() if input else None
        e = environ.copy()
        e.update(env)
        result = run(
            command,
            env=e,
            input=input,
            stdout=PIPE if capture_output else None,
            text=True if capture_output else None)
        result.check_returncode()
        return result

    _recipe_dir = None

    @property
    def recipe_dir(self):
        if not self._recipe_dir and hasattr(self.args, 'path'):
            self._recipe_dir = os.path.abspath(self.args.path)
        return self._recipe_dir

    _root_dir = None

    @property
    def root_dir(self):
        if not self._root_dir:
            dir = os.path.dirname(
                self.recipe_dir) if self.recipe_dir else getcwd()
            while not os.path.exists(os.path.join(dir, ".git")):
                dir = os.path.dirname(dir)
            self._root_dir = dir
            print("[INFO] root_dir =", self._root_dir)
        return self._root_dir

    _recipe_name_and_version = None

    @property
    def recipe_name_and_version(self):
        if not self._recipe_name_and_version:
            # Inspect information on the recipe.
            recipe_nv = self.args.reference.split('@', 1)[0].split('/')
            if self.recipe_dir:
                env = {'CONAN_USER_HOME': self.root_dir}
                recipe_n = self.exec(
                    ["conan", "inspect", "--raw", "name", self.recipe_dir],
                    env=env,
                    capture_output=True).stdout
                recipe_v = self.exec(
                    ["conan", "inspect", "--raw", "version", self.recipe_dir],
                    env=env,
                    capture_output=True).stdout
            if recipe_nv:
                if len(recipe_nv) == 1:
                    recipe_v = recipe_nv[0]
                if len(recipe_nv) == 2:
                    recipe_n = recipe_nv[0]
                    recipe_v = recipe_nv[1]
            self._recipe_name_and_version = [recipe_n, recipe_v]
        return self._recipe_name_and_version

    _recipe_data_dir = None

    @property
    def recipe_data_dir(self):
        if not self._recipe_data_dir:
            self._recipe_data_dir = os.path.join(
                self.root_dir, ".conan", "data", self.recipe_name_and_version[0], self.recipe_name_and_version[1])
        return self._recipe_data_dir

    _recipe_user_and_channel = None

    @property
    def recipe_user_and_channel(self):
        if not self._recipe_user_and_channel:
            recipe_uc = self.args.reference.split('@', 1)[1].split('/')
            recipe_u = recipe_uc[0] if recipe_uc and len(
                recipe_uc) > 0 and len(recipe_uc[0]) > 0 else '_'
            recipe_c = recipe_uc[1] if recipe_uc and len(
                recipe_uc) > 1 and len(recipe_uc[1]) > 0 else '_'
            self._recipe_user_and_channel = [recipe_u, recipe_c]
        return self._recipe_user_and_channel

    _recipe_export_dir = None

    @property
    def recipe_export_dir(self):
        if not self._recipe_export_dir:
            self._recipe_export_dir = os.path.join(
                self.recipe_data_dir, *self.recipe_user_and_channel)
        return self._recipe_export_dir

    def command_export(self):
        print("[INFO] Exporting to %s" % (self.recipe_export_dir))
        # Remove old data.
        rmtree(self.recipe_data_dir, ignore_errors=True)
        # Do the basic export.
        env = {'CONAN_USER_HOME': self.root_dir}
        self.exec(["conan", "export", self.args.path,
                  self.args.reference], env=env)

    _recipe_publish_dir = None

    @property
    def recipe_publish_dir(self):
        if not self._recipe_publish_dir:
            self._recipe_publish_dir = os.path.join(
                self.root_dir,
                ".barbarian",
                *self.recipe_name_and_version)
        return self._recipe_publish_dir

    _recipe_exported_revision = None

    @property
    def recipe_exported_revision(self):
        if not self._recipe_exported_revision:
            with open(os.path.join(self.recipe_export_dir, "metadata.json"), "r") as f:
                j = json.loads(f.read())
                self._recipe_exported_revision = j['recipe']['revision']
        return self._recipe_exported_revision

    _recipe_revision_pub_dir = None

    @property
    def recipe_revision_pub_dir(self):
        if not self._recipe_revision_pub_dir:
            self._recipe_revision_pub_dir = os.path.join(
                self.recipe_publish_dir, self.recipe_exported_revision)
        return self._recipe_revision_pub_dir

    def command_upload(self):
        print("[INFO] Uploading revision %s to %s" %
              (self.recipe_exported_revision, self.recipe_publish_dir))
        # Remove old data.
        rmtree(self.recipe_revision_pub_dir, ignore_errors=True)
        os.makedirs(self.recipe_revision_pub_dir)
        # Copy export data.
        copytree(
            os.path.join(self.recipe_export_dir, "export"),
            os.path.join(self.recipe_revision_pub_dir, "files"))
        # Generate the conan_export.tgz.
        conandata_yml = os.path.join(
            self.recipe_export_dir, "export", "conandata.yml")
        conan_export_tgz = os.path.join(
            self.recipe_revision_pub_dir, "files", "conan_export.tgz")
        with tarfile.open(conan_export_tgz, 'w|gz') as tgz:
            tgz.add(conandata_yml, os.path.basename(conandata_yml))
        # Generate snapshot.json (v1) and files.json (v2).
        snapshot = {}
        files = {'files': {}}
        with open(conan_export_tgz, "rb") as f:
            digest = hashlib.md5(f.read()).hexdigest()
            snapshot[os.path.basename(conan_export_tgz)] = digest
            files['files'][os.path.basename(conan_export_tgz)] = {}
        with open(os.path.join(self.recipe_export_dir, "export", "conanmanifest.txt"), "rb") as f:
            snapshot["conanmanifest.txt"] = hashlib.md5(f.read()).hexdigest()
            files['files']["conanmanifest.txt"] = {}
        with open(os.path.join(self.recipe_export_dir, "export", "conanfile.py"), "rb") as f:
            snapshot["conanfile.py"] = hashlib.md5(f.read()).hexdigest()
            files['files']["conanfile.py"] = {}
        with open(os.path.join(self.recipe_revision_pub_dir, "snapshot.json"), "w", encoding="utf-8") as f:
            json.dump(snapshot, f)
        with open(os.path.join(self.recipe_revision_pub_dir, "files.json"), "w", encoding="utf-8") as f:
            json.dump(files, f)
        # Update latest.json.
        latest = {
            'revision': self.recipe_exported_revision,
            'time': datetime.datetime.utcnow().isoformat()+"+0000"}
        with open(os.path.join(self.recipe_publish_dir, "latest.json"), "w", encoding="utf-8") as f:
            json.dump(latest, f)


def main():
    Barbarian()


if __name__ == '__main__':
    main()
