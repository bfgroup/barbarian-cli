# Copyright 2021 René Ferdinand Rivera Morell
# Distributed under the Boost Software License, Version 1.0.
# (See accompanying file LICENSE.txt or http://www.boost.org/LICENSE_1_0.txt)

from setuptools import setup, find_namespace_packages
import os

VERSION = '0.3.0'

print("TEST_VERSION:", os.getenv('TEST_VERSION'))
if os.getenv('GHA_TEST_VERSION'):
    VERSION = VERSION + '.dev' + os.getenv('GITHUB_RUN_NUMBER')

setup(
    # metadata
    name='barbarian',
    version=VERSION,
    description='Utility tool for managing Conan recipes for the Barbarian Conan server.',
    url='https://barbarian.bfgroup.xyz',
    author='René Ferdinand Rivera Morell',
    author_email='grafikrobot@gmail.com',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: Boost Software License 1.0 (BSL-1.0)',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3'
    ],
    keywords=[
        'package', 'libraries', 'developer', 'manager', 'dependency', 'tool',
        'c', 'c++', 'cpp', 'conan'],
    license='BSL 1.0',
    long_description='''\
# Barbarian

Utility tool for managing Conan recipes for the Barbarian Conan server.

You can find information on how to use this tool to create Conan packages for
the Barbarian server at the [website](https://barbarian.bfgroup.xyz/).
''',
    long_description_content_type="text/markdown",
    # options
    install_requires=['conan >= 1.41', 'sty >= 1.0.0rc2'],
    package_data={'barbarians': []},
    package_dir={"": "src"},
    packages=find_namespace_packages(where="src"),
    python_requires=">=3.6",
    entry_points={
        'console_scripts': [
            'barbarian=barbarians.barbarian:main'
        ]
    }
)
