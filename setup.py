#!/usr/bin/env python

from setuptools import setup

setup(name='vxl',
      version='0.1',
      description='Transmission daemon control cli.',
      author='Erik Svensson',
      author_email='erik.public@gmail.com',
      url='http://coldstar.net',
      packages=['vxl'],
      install_requires = ['simplejson>=1.7.1'],
      entry_points = {
        'console_scripts': [
            'vxl = vxl.vxl:main',
            ],
        }
      
     )
