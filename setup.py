#!/usr/bin/env python

from setuptools import setup

setup(
    name='transmission',
    version='0.2',
    description='Python module that implements the Transmission bittorent client RPC protocol.',
    author='Erik Svensson',
    author_email='erik.public@gmail.com',
    url='http://coldstar.net/transmission',
    keywords='transmission',
    packages=['transmission'],
    install_requires = ['simplejson>=1.7.1'],
    zip_safe=True,
    classifiers = [
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Topic :: Communications :: File Sharing',
        'Topic :: Internet'
        ],
    )
