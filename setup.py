#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""The setup script."""

from setuptools import setup, find_packages

with open('README.md') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read()

requirements = [
    'setuptools',
    'scikit-learn==0.19.2',
    'tensorflow<=1.13.1',
    'keras>=2.0.4,<=2.2.4',
    'pandas',
    'concise',
    'pybedtools',
    'kipoiseq==0.2.7',
    'pyfaidx',
    'tqdm',
    'click',
    'pyranges'
]

setup_requirements = ['pytest-runner', ]

test_requirements = ['pytest', 'pytest-benchmark']

setup(
    author="Jun Cheng",
    author_email='chengju@in.tum.de',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    description="Predict splicing variant effect from VCF",
    install_requires=requirements,
    license="MIT license",
    long_description=readme + '\n\n' + history,
    long_description_content_type='text/markdown',
    entry_points='''
        [console_scripts]
        mmsplice=mmsplice.main:cli
    ''',
    include_package_data=True,
    keywords='mmsplice',
    name='mmsplice',
    packages=find_packages(include=['mmsplice']),
    setup_requires=setup_requirements,
    test_suite='tests',
    tests_require=test_requirements,
    url='https://github.com/gagneurlab/mmsplice',
    version='1.0.3',
    zip_safe=False
)
