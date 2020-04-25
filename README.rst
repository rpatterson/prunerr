==============================================================================
python-project-structure
==============================================================================
Python project structure foundation or template
------------------------------------------------------------------------------

.. image:: https://github.com/rpatterson/python-project-structure/workflows/Run%20linter,%20tests%20and,%20and%20release/badge.svg

This repository is meant to be used as a minimal, yet opinionated baseline for `Python`_
software projects.  It includes:

- Basic `Python "distribution"/project`_ metadata
- A `Makefile`_ for local development build and maintenance tasks

The intended use is to add this repository as a VCS remote for your project.  Thus
developers can merge changes from this repository as we make changes related to Python
project structure and tooling.  As we add structure specific to certain types of
projects (e.g. CLI scripts, web development, etc.), frameworks (e.g. Flask, Pyramid,
Django, etc.), libraries and such, branches will be used for each such variation such
that structure common to different variations can be merged back into the branches for
those specific variations.


Installation
============

Install using any tool for installing standard Python 3 distributions such as `pip`_::

  $ sudo pip3 install python-project-structure


Usage
=====

See the command-line help for details on options and arguments::

  $ usage: python-project-structure [-h]

  Python project structure foundation or template, top-level package.

  optional arguments:
    -h, --help  show this help message and exit


Motivation
==========

There are many other Python project templates so why make another? I've been doing
Python development since 1998, so I've had plenty of time to develop plenty of opinions
of my own.

What I want in a template is complete tooling (e.g. test coverage, linting, formatting,
CI/CD, etc.) but minimal dependencies, structure, and opinion beyond complete tooling
(e.g. some non-Python build/task system, structure for frameworks/libraries not
necessarily being used, etc.).  I couldn't find a template that manages that balance so
here we are.

I also find it hard to discern from other templates why they made what choices the did.
As such, I also use this template as a way to try out various different options in the
Python development world and evaluate them for myself.  You can learn about my findings
and the reasons the choices I've made in the commit history.

Most importantly, however, I've never found a satisfactory approach to keeping project
structure up to date over time.  So the primary motivation is to use this repository as
a remote from which we can merge structure updates over the life of projects using the
template.


.. _Python: https://docs.python.org/3/library/logging.html
.. _Python "distribution"/project: https://docs.python.org/3/distributing/index.html
.. _pip: https://pip.pypa.io/en/stable/installing/

.. _Makefile: ./Makefile
