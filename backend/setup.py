from setuptools import setup, find_packages
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

setup(
    name='demoinstance',

    version='2.1.1',

    description='Web interface for on-demand virtual machines instances deployment with lifetime limits.',
    url='https://github.com/pmsipilot/demoinstance',
    author='PMSIpilot',
    author_email='cyprien.diot@pmsipilot.com',
    license='MIT',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
    ],

    keywords='demo virtual machines deployment web',
    packages=find_packages(exclude=['contrib', 'docs', 'tests*']),
    install_requires=['python-novaclient==7.1.0', 'sqlalchemy==1.3.24', 'mysql-python', 'python-ldap==3.3.1', 'slackclient==1.3.1', 'requests==2.27.1'],
    package_data={
    },
    extras_require={
    },

    # To provide executable scripts, use entry points in preference to the
    # "scripts" keyword. Entry points provide cross-platform support and allow
    # pip to create the appropriate form of executable for the target platform.
    entry_points={
        'console_scripts': [
            'demoinstance=demoinstance.cli:cli_entrypoint',
        ],
    },
)
