"""
Python project structure foundation or template, distribution/package metadata.
"""

import setuptools

with open("README.rst", "r") as readme:
    LONG_DESCRIPTION = readme.read()

tests_require = ["six", 'contextlib2;python_version<"3"']

setuptools.setup(
    name="python-project-structure",
    author="Ross Patterson",
    author_email="me@rpatterson.net",
    description="Python project structure foundation or template",
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/x-rst",
    url="https://github.com/rpatterson/python-project-structure",
    license="MIT",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Topic :: Utilities",
    ],
    python_requires=">=2.7",
    packages=setuptools.find_packages("src"),
    package_dir={"": "src"},
    use_scm_version=dict(
        write_to="src/pythonprojectstructure/version.py",
        local_scheme="no-local-version",
    ),
    setup_requires=[
        'setuptools_scm;python_version>="3"',
        # BBB: Python 2.7 compatibility
        'setuptools_scm<6;python_version<"3"',
    ],
    tests_require=tests_require,
    extras_require=dict(
        dev=tests_require
        + [
            "pytest",
            "pre-commit",
            "coverage",
            "flake8",
            "autoflake",
            "autopep8",
            'flake8-black;python_version>="3"',
            "rstcheck",
        ]
    ),
    entry_points=dict(
        console_scripts=["python-project-structure=pythonprojectstructure:main"]
    ),
)
