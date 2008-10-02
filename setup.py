#!/usr/bin/env python

from setuptools import setup

setup(name='transmission',
      version='0.1',
      description='Transmission control library including vxl cli.',
      author='Erik Svensson',
      author_email='erik.public@gmail.com',
      url='http://coldstar.net',
      packages=['transmission'],
      install_requires = ['simplejson>=1.7.1'],
      entry_points = {
        'console_scripts': [
            'vxl = transmission.vxl:main',
            ],
        }
      
     )
