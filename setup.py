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
    packages=setuptools.find_packages("src"),
    package_dir={"": "src"},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
    use_scm_version=dict(write_to="src/pythonprojectstructure/version.py"),
    setup_requires=["setuptools_scm"],
    extras_require=dict(
        dev=[
            "pre-commit",
            "coverage",
            "flake8",
            "autoflake",
            "autopep8",
            "flake8-black",
        ]
    ),
)
