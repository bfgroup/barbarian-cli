# Copyright 2021 René Ferdinand Rivera Morell
# Distributed under the Boost Software License, Version 1.0.
# (See accompanying file LICENSE.txt or http://www.boost.org/LICENSE_1_0.txt)

from argparse import ArgumentParser, Action
from os import environ, getcwd, chdir, listdir
from shutil import rmtree, copytree, copy
from subprocess import run, PIPE, CalledProcessError
import hashlib
import json
import os.path
import tarfile
import datetime
import yaml
from conans import tools
import conans.client.conan_api
from sty import fg


class UsageError(RuntimeError):
    def __init__(self, reason):
        super().__init__()
        self.reason = reason


class Barbarian(object):
    def __init__(self):
        ap = ArgumentParser("barbarian")

        # General options..
        ap.add_argument(
            "--remote",
            help="The remote Barbarian repo to use specified as `<URL>@<NAME>."
            + " Defaults to `https://barbarian.bfgroup.xyz/github@barbarian-github`.",
            default="https://barbarian.bfgroup.xyz/github@barbarian-github"
        )

        # Sub-commands..
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
            help="Pkg/version@user/channel"
        )

        # Upload command..
        ap_upload = ap_sub.add_parser(
            "upload",
            help="Copies the current exported recipe to the local publish location."
        )
        ap_upload.add_argument(
            "reference",
            help="Pkg/version@user/channel"
        )

        # Upload branch..
        ap_branch = ap_sub.add_parser(
            "branch",
            help="Create, if needed, the 'barbarian' branch for uploading exported recipes to.")
        ap_branch.add_argument(
            "action",
            help="What action to apply to the upload branch.",
            choices=['create', 'push']
        )

        # Create new recipe and/or other support files.
        ap_new = ap_sub.add_parser(
            "new",
            help="Creates a new package recipe template and/or support files.")
        ap_new.add_argument(
            "reference",
            help="name/version@user/channel")
        ap_new.add_argument(
            "--overwrite",
            help="Overwrite existing files, if present, with new files.",
            action="store_true")
        ap_new.add_argument(
            "--recipe",
            help="The style of package recipe to generate, and flag to generate recipe.",
            choices=['standalone', 'collection'],
            action=ChoiceArgAction)
        ap_new.add_argument(
            "--header-only",
            help="Create a header only package recipe.",
            action="store_true")
        ap_new.add_argument(
            "--ci",
            help="Create setup, i.e. scripts, for testing in CI for the given service.",
            choices=["github"],
            action=ChoiceArgAction)

        self.args = ap.parse_args()

        # Synthesize some info from general arguments..
        self.args.remote_url = self.args.remote.split('@')[0]
        self.args.remote_name = self.args.remote.split('@')[1]

        if self.args.command:
            if hasattr(self, "command_"+self.args.command):
                try:
                    getattr(self, "command_"+self.args.command)(self.args)
                except UsageError as error:
                    print(fg.red + error.reason + fg.rs)
                    exit(1)

    def exec(self, command, input=None, capture_output=False, env={}):
        try:
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
        except FileNotFoundError as error:
            raise UsageError('''[ERROR] \
Failed to find a "{0}" program. Using Barbarian requires the "{0}" program. \
'''.format(command[0]))

    # Root dir, calculated from recipe dir.

    _root_dir = None

    @property
    def root_dir(self):
        return self._root_dir

    @root_dir.setter
    def root_dir(self, args):
        self.recipe_dir = args
        if not self._root_dir:
            dir = self.recipe_dir if self.recipe_dir else getcwd()
            while not os.path.exists(os.path.join(dir, ".git")):
                parent = os.path.dirname(dir)
                if parent == dir:
                    raise UsageError('''[ERROR] \
Failed to find a git repo for the project. Using Barbarian requires \
a git repo to be initialized, and linked to a remote, ahead of time.\
''')
                dir = parent
            self._root_dir = dir
            print("[INFO] root_dir =", self._root_dir, flush=True)

    # Recipe dir, calculated from "path" arg.

    _recipe_dir = None

    @property
    def recipe_dir(self):
        return self._recipe_dir

    @recipe_dir.setter
    def recipe_dir(self, args):
        if not self._recipe_dir and hasattr(args, "path"):
            self._recipe_dir = os.path.abspath(args.path)
            # print("[INFO] recipe_dir =", self._recipe_dir, flush=True)

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
                recipe_props = self.conan_api.inspect(
                    self.recipe_dir,
                    ['name', 'version'])
                recipe_n = recipe_props['name']
                recipe_v = recipe_props['version']
            if recipe_nv:
                if len(recipe_nv) == 1:
                    recipe_v = recipe_nv[0]
                if len(recipe_nv) == 2:
                    recipe_n = recipe_nv[0]
                    recipe_v = recipe_nv[1]
            self._recipe_name_and_version = [recipe_n, recipe_v]
            # print("[INFO] recipe_name_and_version =",
            #       self._recipe_name_and_version, flush=True)

    # Recipe data dir where the export puts information. This is locally
    # controlled to be relative to the root dir. And calculated from root dir
    # and "self.recipe_name_and_version".

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
            # print("[INFO] recipe_data_dir =", self._recipe_data_dir, flush=True)

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
            # print("[INFO] recipe_user_and_channel =", self._recipe_user_and_channel, flush=True)

    # Recipe export dir, where conan puts the exported recipe data, calculated
    # from "self.recipe_data_dir" and "self.recipe_user_and_channel".

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
            # print("[INFO] recipe_export_dir =", self._recipe_export_dir, flush=True)

    # Recipe publish dir, is where we create the published/uploaded recipe
    # data. Calculated from "self.root_dir" and "self.recipe_name_and_version".

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
                ".barbarian_upload",
                *self.recipe_name_and_version)
            # print("[INFO] recipe_publish_dir =", self._recipe_publish_dir, flush=True)

    # Recipe exported revision, which is the revision in the generated export
    # data. Uses "self.recipe_export_dir".

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
            # print("[INFO] recipe_exported_revision =", self._recipe_exported_revision, flush=True)

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
            # print("[INFO] recipe_revision_pub_dir =", self._recipe_revision_pub_dir, flush=True)

    # Utilities..

    _conan_api: conans.client.conan_api.Conan = None

    @property
    def conan_api(self):
        if not self._conan_api:
            self._conan_api = conans.client.conan_api.Conan(
                cache_folder=os.path.join(self.root_dir, '.conan'))
            # Create local conan config, if needed.
            self._conan_api.config_init()
            # Barbarian only works with recipe revisions.
            self._conan_api.config_set("general.revisions_enabled", "True")
            # Install hooks for manipulating and checking packages.
            hooks_dir_src = os.path.join(os.path.dirname(
                os.path.abspath(__file__)), "hooks")
            hooks_dir_dst = os.path.join(self.root_dir, '.conan', 'hooks')
            # Need to make sure the hooks dst dir exists to copy into.
            if not os.path.exists(hooks_dir_dst):
                os.mkdir(hooks_dir_dst)
            # Copy all the hooks we have so we can register them as needed.
            for name in os.listdir(hooks_dir_src):
                if name.endswith('.py'):
                    copy(os.path.join(hooks_dir_src, name),
                         os.path.join(hooks_dir_dst, name))
            # Add the Barbarian remote so we can find dependencies.
            self.conan_api.remote_add(
                self.args.remote_name,
                self.args.remote_url,
                force=True)
        return self._conan_api

    def have_branch(self, branch):
        branch_list = self.exec(
            ["git", "branch", "--list", branch], capture_output=True).stdout.strip("\n\t *+")
        return branch_list == branch

    def make_empty_branch(self, branch, message):
        if not self.have_branch(branch):
            # The branch may exists in the upstream but not locally. So we try
            # and fetch it from the origin. We ignore the errors, as it just
            # means we already have the remote branch locally available.
            print("[INFO] Optionally fetching '{0}' branch from origin.".format(
                branch), flush=True)
            try:
                self.exec(["git", "fetch", "--quiet", "origin", "barbarian"])
            except CalledProcessError:
                pass
            print("[INFO] Optionally creating local '{0}' branch from origin.".format(
                branch), flush=True)
            try:
                self.exec(["git", "branch", "--quiet",
                          "barbarian", "origin/barbarian"])
            except CalledProcessError:
                pass
        if not self.have_branch(branch):
            # Do a git dance to create a fresh truly detached branch.
            print("[INFO] Creating local '{0}' branch.".format(
                branch), flush=True)
            cwd = getcwd()
            try:
                self.exec(["git", "worktree", "add", "--quiet", "-b",
                           branch+"-tmp", os.path.join(cwd, "."+branch+".tmp")])
            except CalledProcessError:
                raise UsageError('''[ERROR] \
Uploading requires the git repo to have a HEAD revision to create upload \
branch.\
''')
            chdir(os.path.join(cwd, "."+branch+".tmp"))
            self.exec(["git", "checkout", "--quiet", "--orphan", branch])
            self.exec(["git", "rm", "--quiet", "-rf", "."])
            self.exec(["git", "commit", "--allow-empty", "-m", message])
            self.exec(["git", "branch", "--quiet", "-D", branch+"-tmp"])
            chdir(cwd)
            self.exec(["git", "worktree", "remove",
                      os.path.join(cwd, "."+branch+".tmp")])

    def make_barbarian_branch(self):
        self.make_empty_branch("barbarian", "Barbarian upload branch.")

    def push_barbarian_branch(self):
        self.make_barbarian_branch()
        self.exec(["git", "push", "origin", "barbarian"])

    bpt_package_reference = "git+https://github.com/bfgroup/bincrafters-package-tools@develop"

    def render_template(self, template, path):
        text = template
        text = text.replace(
            "<<<USER>>>", self.recipe_user_and_channel[0])
        text = text.replace(
            "<<<GROUP>>>", self.recipe_user_and_channel[1])
        text = text.replace(
            "<<<NAME>>>", self._recipe_name_and_version[0])
        text = text.replace(
            "<<<VERSION>>>", self._recipe_name_and_version[1])
        text = text.replace(
            "<<<BPT_PACKAGE>>>", self.bpt_package_reference)
        text = text.replace(
            "<<<REMOTE_URL>>>", self.args.remote_url)
        text = text.replace(
            "<<<REMOTE_NAME>>>", self.args.remote_name)
        with open(path, "w") as file:
            file.write(text)

    # Commands..

    def command_export(self, args):
        # Compute state.
        self.root_dir = args
        self.recipe_data_dir = args
        self.recipe_export_dir = args
        self.recipe_name_and_version = args
        self.recipe_user_and_channel = args
        # Info.
        print("[INFO] Exporting to %s" % (self.recipe_export_dir), flush=True)
        # Remove old data.
        rmtree(self.recipe_data_dir, ignore_errors=True)
        # Tweak gitignore to blank out temp conan data.
        gitignore_path = os.path.join(self.root_dir, ".gitignore")
        gitignore = ""
        if os.path.exists(gitignore_path):
            gitignore = tools.load(gitignore_path)
        if not '/.conan/' in gitignore:
            gitignore = "/.conan/\n" + gitignore
            tools.save(gitignore_path, gitignore)
        # Enable needed hooks.
        self.conan_api.config_set('hooks.barbarian_clean_conandata_yml', "")
        # Do the basic export.
        self.conan_api.export(
            args.path,
            self.recipe_name_and_version[0],
            self.recipe_name_and_version[1],
            self.recipe_user_and_channel[0],
            self.recipe_user_and_channel[1])

    def command_upload(self, args):
        # Compute state.
        self.recipe_export_dir = args
        self.recipe_exported_revision = args
        self.recipe_publish_dir = args
        self.recipe_revision_pub_dir = args
        self.recipe_name_and_version = args
        self.recipe_user_and_channel = args
        print("[INFO] Uploading revision %s to %s" %
              (self.recipe_exported_revision, self.recipe_publish_dir), flush=True)
        # Check prerequisites.
        try:
            self.exec(["git", "remote", "show", "origin"])
        except CalledProcessError:
            raise UsageError('''[ERROR] \
Upload requires an existing git remote origin to push new packages to. Please \
set a remote to push to with "git remote add origin <url>".\
''')
        # Checkout the upload branch.
        self.make_barbarian_branch()
        worktree_dir = os.path.join(self.root_dir, ".barbarian_upload")
        cwd = getcwd()
        self.exec(["git", "worktree", "add", worktree_dir, "barbarian"])
        try:
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
                if os.path.exists(conandata_yml):
                    tgz.add(conandata_yml, os.path.basename(conandata_yml))
            # Generate the conan_sources.tgz.
            export_source_dir = os.path.join(
                self.recipe_export_dir, "export_source")
            conan_sources_tgz = os.path.join(
                self.recipe_revision_pub_dir, "files", "conan_sources.tgz")
            with tarfile.open(conan_sources_tgz, 'w|gz') as tgz:
                for source in os.listdir(export_source_dir):
                    tgz.add(os.path.join(export_source_dir, source), source)
            # Generate snapshot.json (v1), and files.json (v2).
            snapshot = {}
            files = {'files': {}}
            for export_file in listdir(os.path.join(self.recipe_revision_pub_dir, "files")):
                with open(os.path.join(self.recipe_revision_pub_dir, "files", export_file), "rb") as f:
                    digest = hashlib.md5(f.read()).hexdigest()
                    snapshot[export_file] = digest
                    files['files'][export_file] = {}
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
            # Commit changes.
            chdir(worktree_dir)
            self.exec(["git", "add", "."])
            self.exec(["git", "status"])
            self.exec(["git", "commit", "-m", "Upload %s/%s revision %s." % (
                self.recipe_name_and_version[0], self.recipe_name_and_version[1],
                self.recipe_exported_revision)])
            # Upload, aka push, the branch.
            self.push_barbarian_branch()
            # Fetch the exported data to "register" the new recipe revision with the server.
            recipe_ref = "%s/%s@%s/%s#%s" % (
                *self.recipe_name_and_version, *self.recipe_user_and_channel, self.recipe_exported_revision)
            print("[INFO] Register recipe", recipe_ref, flush=True)
            conan_export_tgz = self.conan_api.get_path(
                recipe_ref,
                path="conan_export.tgz",
                remote_name=self.args.remote_name)
        finally:
            # Clean up the upload tree.
            chdir(cwd)
            self.exec(["git", "worktree", "remove", "-f", worktree_dir])

    def command_branch(self, args):
        if args.action == "create":
            self.make_barbarian_branch()
        elif args.action == "push":
            self.push_barbarian_branch()

    def command_new(self, args):
        # Compute state.
        self.root_dir = args
        self.recipe_name_and_version = args
        self.recipe_user_and_channel = args
        # While config files to generate.
        to_generate = set()
        if args.recipe:
            to_generate.add('recipe')
        if args.ci:
            to_generate.add('ci')
        # print("[DEBUG] to_generate:", *to_generate)
        # exit(1)

        if 'recipe' in to_generate:
            # Create recipe.
            package_dir = None
            if args.recipe == "standalone":
                package_dir = self.root_dir
            elif args.recipe == "collection":
                package_dir = os.path.join(
                    self.root_dir, "recipes", self._recipe_name_and_version[0], "all")
            conanfile_py_path = os.path.join(package_dir, "conanfile.py")
            if os.path.exists(conanfile_py_path) and not args.overwrite:
                print("[INFO] Skipped overwrite of existing recipe %s" %
                      (conanfile_py_path), flush=True)
            else:
                print("[INFO] Creating recipe %s" %
                      (conanfile_py_path), flush=True)
                conanfile_py_text = self.conanfile_py_base_template
                if args.header_only:
                    conanfile_py_text += self.conanfile_py_header_only_template
                else:
                    conanfile_py_text += self.conanfile_py_build_template
                os.makedirs(os.path.dirname(conanfile_py_path), exist_ok=True)
                self.render_template(conanfile_py_text, conanfile_py_path)
            conandata_yml_path = os.path.join(package_dir, "conandata.yml")
            if os.path.exists(conandata_yml_path) and not args.overwrite:
                print("[INFO] Skipped overwrite of existing recipe data %s" %
                      (conandata_yml_path), flush=True)
            else:
                print("[INFO] Creating recipe data %s" %
                      (conandata_yml_path), flush=True)
                self.render_template(
                    self.conandata_yml_template, conandata_yml_path)
            # Update recipe index.
            if args.recipe == "collection":
                config_yml_path = os.path.join(
                    os.path.dirname(os.path.dirname(conanfile_py_path)), "config.yml")
                config_yml_data = {}
                if os.path.exists(config_yml_path):
                    with open(config_yml_path, "r") as config_yml:
                        config_yml_data = yaml.safe_load(config_yml)
                config_yml_data['versions'] = {
                    self.recipe_name_and_version[1]: {
                        'folder': 'all'}}
                print("[INFO] Updating recipe info %s" %
                      (config_yml_path), flush=True)
                with open(config_yml_path, "w") as config_yml:
                    yaml.dump(config_yml_data, config_yml)
        if 'ci' in to_generate:
            # Create CI setup.
            if args.ci == "github":
                ga_conan_workflow_path = os.path.join(
                    self.root_dir, ".github", "workflows", "barbarian.yml")
                if os.path.exists(ga_conan_workflow_path) and not args.overwrite:
                    print("[INFO] Skipped overwrite of existing GitHub Actions setup %s" %
                          (ga_conan_workflow_path), flush=True)
                else:
                    print("[INFO] Creating GitHub Actions setup %s" %
                          (ga_conan_workflow_path), flush=True)
                    os.makedirs(os.path.dirname(
                        ga_conan_workflow_path), exist_ok=True)
                    self.render_template(
                        self.ga_conan_workflow_template, ga_conan_workflow_path)

    ga_conan_workflow_template = '''\
env:
    CONAN_REMOTES: "<<<REMOTE_URL>>>@True@<<<REMOTE_URL>>>"
    CONAN_BUILD_POLICY: "missing"
    BPT_NO_UPLOAD: yes
    BPT_CONFIG_FILE_VERSION: "11"

on:
    push:
        branches: ["main", "develop"]
    pull_request:

name: conan

jobs:
    generate-matrix:
        name: Generate Job Matrix
        runs-on: ubuntu-latest
        outputs:
            matrix: ${{ steps.set-matrix.outputs.matrix }}
        steps:
            - { uses: actions/checkout@v2, with: { fetch-depth: "0" } }
            - { uses: actions/setup-python@v2, with: { python-version: "3.x" } }
            - name: Install Package Tools
              run: |
                  pip install <<<BPT_PACKAGE>>>
                  conan user
            - name: Generate Job Matrix
              id: set-matrix
              run: |
                  MATRIX=$(bincrafters-package-tools generate-ci-jobs --platform gha)
                  echo "${MATRIX}"
                  echo "::set-output name=matrix::${MATRIX}"
    conan:
        needs: generate-matrix
        runs-on: ${{ matrix.config.os }}
        strategy:
            fail-fast: false
            matrix: ${{fromJson(needs.generate-matrix.outputs.matrix)}}
        name: ${{ matrix.config.name }}
        steps:
            - { uses: actions/checkout@v2, with: { fetch-depth: "0" } }
            - { uses: actions/setup-python@v2, with: { python-version: "3.x" } }
            - name: Install Conan
              env:
                  BPT_MATRIX: ${{toJson(matrix.config)}}
              run: |
                  pip install git+https://github.com/bfgroup/bincrafters-package-tools@develop
                  # remove newlines from matrix first
                  matrix=$(echo ${BPT_MATRIX})
                  bincrafters-package-tools prepare-env --platform gha --config "${matrix}"
              shell: bash
            - name: Run
              run: |
                  bincrafters-package-tools --auto
'''
    conanfile_py_base_template = '''\
from conans import ConanFile, tools
import os


class Package(ConanFile):
    name = "<<<NAME>>>"
    homepage = "https://github.com/<<<USER>>>/<<<GROUP>>>"
    description = "<<<SHORT_DESCRIPTION>>>"
    topics = ("<<<TOPICS>>>")
    license = "<<<LICENSE>>>"
    url = "https://github.com/<<<USER>>>/<<<GROUP>>>"
    barbarian = {
        "description": {
            "format": "asciidoc",
            "text": \'\'\'\\
<<<LONG_DESCRIPTION>>>
\'\'\'
        }
    }
    source_subfolder = "source_subfolder"

    def source(self):
        tools.get(
            **self.conan_data["sources"][self.version],
            strip_root=True, destination=self.source_subfolder)
'''

    conanfile_py_header_only_template = '''
    no_copy_source = True

    def package_id(self):
        self.info.header_only()

    def package(self):
        self.copy(
            pattern="LICENSE.txt", dst="licenses",
            src=self.source_subfolder)
        for pattern in ["*.h", "*.hpp", "*.hxx"]:
            self.copy(
                pattern=pattern, dst="include",
                src=os.path.join(self.source_subfolder, "include"))
'''

    conanfile_py_build_template = '''
    settings = "os", "compiler", "build_type", "arch"
    options = {"shared": [True, False], "fPIC": [True, False]}
    default_options = {"shared": False, "fPIC": True}

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC

    def build(self):
        pass

    def package(self):
        self.copy(
            pattern="LICENSE.txt", dst="licenses",
            src=self.source_subfolder)
        for pattern in ["*.h", "*.hpp", "*.hxx"]:
            self.copy(
                pattern=pattern, dst="include",
                src=os.path.join(self.source_subfolder, "include"))
        for pattern in ["*.lib", "*.so", "*.dylib", "*.a"]:
            self.copy(pattern=pattern, dst="lib", keep_path=False)
        for pattern in ["*.dll", "*.exe"]:
            self.copy(pattern=pattern, dst="bin", keep_path=False)
'''

    conandata_yml_template = '''\
sources:
  "<<<VERSION>>>":
    url: "https://github.com/<<<USER>>>/<<<GROUP>>>/archive/refs/tags/<<<VERSION>>>.tar.gz"
'''


class CollectArgAction(Action):
    def __init__(self, option_strings, dest, default=set(), **kwargs):
        if not isinstance(default, set):
            default = set([default])
        super().__init__(option_strings, dest, default=default, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        dest = getattr(namespace, self.dest)
        dest.add(values)
        setattr(namespace, self.dest, dest)


class ChoiceArgAction(Action):
    def __init__(self, option_strings, dest, default=None, nargs=None, **kwargs):
        super().__init__(option_strings, dest, nargs="?", **kwargs)
        self.flag_default = default

    def __call__(self, parser, namespace, values, option_string=None):
        values = self.choices[0] if not values else values
        setattr(namespace, self.dest, values)


def main():
    Barbarian()


if __name__ == '__main__':
    main()
