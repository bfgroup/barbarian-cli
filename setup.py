# Copyright 2021 René Ferdinand Rivera Morell
# Distributed under the Boost Software License, Version 1.0.
# (See accompanying file LICENSE.txt or http://www.boost.org/LICENSE_1_0.txt)

from setuptools import setup

setup(
    name='barbarian',
    description='Utility tool for managing Conan recipes for the Barbarian Conan server.',
    version='0.1',
    url='https://barbarian.bfgroup.xyz',
    author='René Ferdinand Rivera Morell',
    author_email='grafikrobot@gmail.com',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: Boost Software License 1.0',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8'
    ],
    keywords=['C/C++', 'package', 'libraries', 'developer', 'manager',
              'dependency', 'tool', 'c', 'c++', 'cpp'],
    license='BSL 1.0',

    install_requires=['conan >= 1.36'],
    package_data={'barbarians': []},
    packages=['barbarians'],

    entry_points={
        'console_scripts': [
            'barbarian=barbarians.barbarian:run'
        ]
    }
)
