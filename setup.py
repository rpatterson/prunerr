"""
Python project structure foundation or template, distribution/package metadata.
"""

import sys
import os

import setuptools

sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
import pythonprojectstructure  # noqa

with open("README.rst", "r") as readme:
    LONG_DESCRIPTION = readme.read()

setuptools.setup(
    name="python-project-structure",
    version=pythonprojectstructure.__version__,
    author="Ross Patterson",
    author_email="me@rpatterson.net",
    description="Python project structure foundation or template",
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/x-rst",
    url="https://github.com/rpatterson/python-project-structure",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
    extras_require=dict(
        dev=[
            "pre-commit",
            "coverage",
        ]
    ),
)
