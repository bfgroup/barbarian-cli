# Copyright 2021 René Ferdinand Rivera Morell
# Distributed under the Boost Software License, Version 1.0.
# (See accompanying file LICENSE.txt or http://www.boost.org/LICENSE_1_0.txt)

from argparse import ArgumentParser
from os import environ, getcwd, chdir
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

        # Create upload branch..
        ap_branch = ap_sub.add_parser(
            "branch",
            help="Create, if needed, the 'barbarian' branch for uploading exported recipes to.")
        ap_branch.add_argument(
            "action",
            help="What action to apply to the upload branch.",
            choices=['create', 'push']
        )

        self.args = ap.parse_args()

        if self.args.command:
            if hasattr(self, "command_"+self.args.command):
                getattr(self, "command_"+self.args.command)(self.args)

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

    # Root dir, calculated from recipe dir.

    _root_dir = None

    @property
    def root_dir(self):
        return self._root_dir

    @root_dir.setter
    def root_dir(self, args):
        self.recipe_dir = args
        if not self._root_dir:
            dir = os.path.dirname(
                self.recipe_dir) if self.recipe_dir else getcwd()
            while not os.path.exists(os.path.join(dir, ".git")):
                dir = os.path.dirname(dir)
            self._root_dir = dir
            print("[INFO] root_dir =", self._root_dir)

    # Recipe dir, calculated from "path" arg.

    _recipe_dir = None

    @property
    def recipe_dir(self):
        return self._recipe_dir

    @recipe_dir.setter
    def recipe_dir(self, args):
        if not self._recipe_dir and hasattr(args, "path"):
            self._recipe_dir = os.path.abspath(args.path)
            # print("[INFO] recipe_dir =", self._recipe_dir)

    # Recipe name and version, as a list, calculated from conan inspection "reference" arg.

    _recipe_name_and_version = None

    @property
    def recipe_name_and_version(self):
        return self._recipe_name_and_version

    @recipe_name_and_version.setter
    def recipe_name_and_version(self, args):
        self.recipe_dir = args
        self.root_dir = args
        if not self._recipe_name_and_version:
            recipe_nv = args.reference.split('@', 1)[0].split('/')
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
            # print("[INFO] recipe_name_and_version =", self._recipe_name_and_version)

    # Recipe data dir where the export puts information. This is locally controlled to be relative to
    # the root dir. And calculated from root dir and "self.recipe_name_and_version".

    _recipe_data_dir = None

    @property
    def recipe_data_dir(self):
        return self._recipe_data_dir

    @recipe_data_dir.setter
    def recipe_data_dir(self, args):
        self.root_dir = args
        self.recipe_name_and_version = args
        if not self._recipe_data_dir:
            self._recipe_data_dir = os.path.join(
                self.root_dir, ".conan", "data", self.recipe_name_and_version[0], self.recipe_name_and_version[1])
            # print("[INFO] recipe_data_dir =", self._recipe_data_dir)

    _recipe_user_and_channel = None

    # Recipe user and channel, calculated from "reference" arg.

    @property
    def recipe_user_and_channel(self):
        return self._recipe_user_and_channel

    @recipe_user_and_channel.setter
    def recipe_user_and_channel(self, args):
        if not self._recipe_user_and_channel:
            recipe_uc = args.reference.split('@', 1)[1].split('/')
            recipe_u = recipe_uc[0] if recipe_uc and len(
                recipe_uc) > 0 and len(recipe_uc[0]) > 0 else '_'
            recipe_c = recipe_uc[1] if recipe_uc and len(
                recipe_uc) > 1 and len(recipe_uc[1]) > 0 else '_'
            self._recipe_user_and_channel = [recipe_u, recipe_c]
            # print("[INFO] recipe_user_and_channel =", self._recipe_user_and_channel)

    # Recipe export dir, where conan puts the exported recipe data, calculated from "self.recipe_data_dir"
    # and "self.recipe_user_and_channel".

    _recipe_export_dir = None

    @property
    def recipe_export_dir(self):
        return self._recipe_export_dir

    @recipe_export_dir.setter
    def recipe_export_dir(self, args):
        self.recipe_data_dir = args
        self.recipe_user_and_channel = args
        if not self._recipe_export_dir:
            self._recipe_export_dir = os.path.join(
                self.recipe_data_dir, *self.recipe_user_and_channel)
            # print("[INFO] recipe_export_dir =", self._recipe_export_dir)

    # Recipe publish dir, is where we create the published/uploaded recipe data. Calculated from
    # "self.root_dir" and "self.recipe_name_and_version".

    _recipe_publish_dir = None

    @property
    def recipe_publish_dir(self):
        return self._recipe_publish_dir

    @recipe_publish_dir.setter
    def recipe_publish_dir(self, args):
        self.root_dir = args
        self.recipe_name_and_version = args
        if not self._recipe_publish_dir:
            self._recipe_publish_dir = os.path.join(
                self.root_dir,
                ".barbarian",
                *self.recipe_name_and_version)
            # print("[INFO] recipe_publish_dir =", self._recipe_publish_dir)

    # Recipe exported revision, which is the revision in the generated export data.
    # Uses "self.recipe_export_dir".

    _recipe_exported_revision = None

    @property
    def recipe_exported_revision(self):
        return self._recipe_exported_revision

    @recipe_exported_revision.setter
    def recipe_exported_revision(self, args):
        self.recipe_export_dir = args
        if not self._recipe_exported_revision:
            with open(os.path.join(self.recipe_export_dir, "metadata.json"), "r") as f:
                j = json.loads(f.read())
                self._recipe_exported_revision = j['recipe']['revision']
            # print("[INFO] recipe_exported_revision =", self._recipe_exported_revision)

    # Recipe revision specific publish dir.

    _recipe_revision_pub_dir = None

    @property
    def recipe_revision_pub_dir(self):
        return self._recipe_revision_pub_dir

    @recipe_revision_pub_dir.setter
    def recipe_revision_pub_dir(self, args):
        self.recipe_publish_dir = args
        self.recipe_exported_revision = args
        if not self._recipe_revision_pub_dir:
            self._recipe_revision_pub_dir = os.path.join(
                self.recipe_publish_dir, self.recipe_exported_revision)
            # print("[INFO] recipe_revision_pub_dir =", self._recipe_revision_pub_dir)

    # Utilities..

    def have_branch(self, branch):
        return self.exec(["git", "branch", "--list", branch], capture_output=True).stdout.strip() == branch

    def make_empty_branch(self, branch, message):
        if not self.have_branch(branch):
            cwd = getcwd()
            self.exec(["git", "worktree", "add", "--quiet", "-b",
                       branch+"-tmp", os.path.join(cwd, "."+branch+".tmp")])
            chdir(os.path.join(cwd, "."+branch+".tmp"))
            self.exec(["git", "checkout", "--quiet", "--orphan", branch])
            self.exec(["git", "rm", "--quiet", "-rf", "."])
            self.exec(["git", "commit", "--allow-empty", "-m", message])
            self.exec(["git", "branch", "--quiet", "-D", branch+"-tmp"])
            chdir(cwd)
            self.exec(["git", "worktree", "remove",
                      os.path.join(cwd, "."+branch+".tmp")])

    def make_barbarian_branch(self):
        if not self.have_branch("barbarian"):
            print("[INFO] Creating 'barbarian' branch.")
            self.make_empty_branch("barbarian", "Barbarian upload branch.")

    # Commands..

    def command_export(self, args):
        # Compute state.
        self.root_dir = args
        self.recipe_data_dir = args
        self.recipe_export_dir = args
        # Info.
        print("[INFO] Exporting to %s" % (self.recipe_export_dir))
        # Remove old data.
        rmtree(self.recipe_data_dir, ignore_errors=True)
        # Do the basic export.
        env = {'CONAN_USER_HOME': self.root_dir}
        self.exec(["conan", "export", args.path, args.reference], env=env)

    def command_upload(self, args):
        # Compute state.
        self.recipe_export_dir = args
        self.recipe_exported_revision = args
        self.recipe_publish_dir = args
        self.recipe_revision_pub_dir = args
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

    def command_branch(self, args):
        self.make_barbarian_branch()


def main():
    Barbarian()


if __name__ == '__main__':
    main()
