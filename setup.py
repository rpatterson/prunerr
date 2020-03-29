"""
Python project structure foundation or template, distribution/package metadata.
"""

import setuptools

with open("README.rst", "r") as readme:
    LONG_DESCRIPTION = readme.read()

setuptools.setup(
    name="python-project-structure",
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
    use_scm_version=dict(
        write_to="src/pythonprojectstructure/version.py",
        local_scheme="no-local-version",
    ),
    setup_requires=["setuptools_scm"],
    extras_require=dict(
        dev=[
            "pytest",
            "pre-commit",
            "coverage",
            "flake8",
            "autoflake",
            "autopep8",
            "flake8-black",
        ]
    ),
    entry_points=dict(
        console_scripts=[
            "python-project-structure=pythonprojectstructure:main",
        ]
    ),
)
