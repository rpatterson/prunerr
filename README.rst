########################################################################################
python-project-structure
########################################################################################
Python project structure foundation or template
****************************************************************************************

.. list-table::
   :class: borderless align-right

   * - .. figure:: https://img.shields.io/pypi/v/python-project-structure.svg?logo=pypi&label=PyPI&logoColor=gold
          :alt: PyPI latest release version
          :target: https://pypi.org/project/python-project-structure/
       .. figure:: https://img.shields.io/pypi/dm/python-project-structure.svg?color=blue&label=Downloads&logo=pypi&logoColor=gold
          :alt: PyPI downloads per month
          :target: https://pypi.org/project/python-project-structure/
       .. figure:: https://img.shields.io/pypi/pyversions/python-project-structure.svg?logo=python&label=Python&logoColor=gold
          :alt: PyPI Python versions
          :target: https://pypi.org/project/python-project-structure/
       .. figure:: https://img.shields.io/badge/code%20style-black-000000.svg
          :alt: Python code style
          :target: https://github.com/psf/black

     - .. figure:: https://gitlab.com/rpatterson/python-project-structure/-/badges/release.svg
	  :alt: GitLab latest release
	  :target: https://gitlab.com/rpatterson/python-project-structure/-/releases
       .. figure:: https://gitlab.com/rpatterson/python-project-structure/badges/main/pipeline.svg
          :alt: GitLab CI/CD pipeline status
          :target: https://gitlab.com/rpatterson/python-project-structure/-/commits/main
       .. figure:: https://gitlab.com/rpatterson/python-project-structure/badges/main/coverage.svg
          :alt: GitLab coverage report
	  :target: https://gitlab.com/rpatterson/python-project-structure/-/commits/main
       .. figure:: https://img.shields.io/gitlab/stars/rpatterson/python-project-structure?gitlab_url=https%3A%2F%2Fgitlab.com&logo=gitlab
	  :alt: GitLab repo stars
	  :target: https://gitlab.com/rpatterson/python-project-structure

     - .. figure:: https://img.shields.io/github/v/release/rpatterson/python-project-structure?logo=github
	  :alt: GitHub release (latest SemVer)
	  :target: https://github.com/rpatterson/python-project-structure/releases
       .. figure:: https://github.com/rpatterson/python-project-structure/actions/workflows/build-test.yml/badge.svg
          :alt: GitHub Actions status
          :target: https://github.com/rpatterson/python-project-structure/actions/workflows/build-test.yml
       .. figure:: https://codecov.io/github/rpatterson/python-project-structure/branch/main/graph/badge.svg?token=GNKVQ8VYOU
          :alt: Codecov test coverage
	  :target: https://codecov.io/github/rpatterson/python-project-structure
       .. figure:: https://img.shields.io/github/stars/rpatterson/python-project-structure?logo=github
	  :alt: GitHub repo stars
	  :target: https://github.com/rpatterson/python-project-structure/

     - .. figure:: https://img.shields.io/docker/v/merpatterson/python-project-structure/main?sort=semver&logo=docker
          :alt: Docker Hub image version (latest semver)
          :target: https://hub.docker.com/r/merpatterson/python-project-structure
       .. figure:: https://img.shields.io/docker/pulls/merpatterson/python-project-structure?logo=docker
          :alt: Docker Hub image pulls count
          :target: https://hub.docker.com/r/merpatterson/python-project-structure
       .. figure:: https://img.shields.io/docker/stars/merpatterson/python-project-structure?logo=docker
	  :alt: Docker Hub stars
          :target: https://hub.docker.com/r/merpatterson/python-project-structure
       .. figure:: https://img.shields.io/docker/image-size/merpatterson/python-project-structure?logo=docker
	  :alt: Docker Hub image size (latest semver)
          :target: https://hub.docker.com/r/merpatterson/python-project-structure

     - .. figure:: https://img.shields.io/keybase/pgp/rpatterson?logo=keybase
          :alt: KeyBase PGP key ID
          :target: https://keybase.io/rpatterson
       .. figure:: https://img.shields.io/github/followers/rpatterson?style=social
          :alt: GitHub followers count
          :target: https://github.com/rpatterson
       .. figure:: https://img.shields.io/liberapay/receives/rpatterson.svg?logo=liberapay
          :alt: LiberaPay donated per week
          :target: https://liberapay.com/rpatterson/donate
       .. figure:: https://img.shields.io/liberapay/patrons/rpatterson.svg?logo=liberapay
          :alt: LiberaPay patrons count
          :target: https://liberapay.com/rpatterson/donate


This repository is meant to be used as a minimal, yet opinionated baseline for `Python`_
software projects.  It includes:

- Basic `Python "distribution"/project`_ metadata
- Command-line console script with sub-command boilerplate
- A `Makefile`_ for local development build, test and maintenance tasks
- `Docker`_ container images for users and development
- Targets/recipes in the `Makefile`_ to automate releases
- `Makefile`_ recipes/targets used for both local development and on CI/CD platforms
- A `GitLab CI/CD`_ pipeline integrating those CI/CD recipes/targets
- A `GitHub Actions`_ workflow/pipeline integrating those CI/CD recipes/targets

The intended use is to add this repository as a VCS remote for your project.  Thus
developers can merge changes from this repository as we make changes related to Python
project structure and tooling.  As we add structure specific to certain types of
projects (e.g. CLI scripts, web development, etc.), frameworks (e.g. Flask, Pyramid,
Django, etc.), libraries and such, branches will be used for each such variation such
that structure common to different variations can be merged back into the branches for
those specific variations.

.. contents:: Table of Contents


****************************************************************************************
Template Usage
****************************************************************************************

This is a rough guide to applying this project template to your project.  This is not
thoroughly tested as such tests would be so meta as to be extremely wasteful of
developer time to create and maintain.  So report any issues you have or better yet
figure it out and submit a PR with corrections to this section.

#. Choose the right branch to use:

   Is your project a CLI utility?  A web application?  Which project hosting provider
   and/or CI/CD platform will you use?  Choose the appropriate branch for your project:

   - ``dist``:

     Basic Python distribution with build, tests, linters, code formatting and release
     publishing from local developer checkouts.

   - ``cli``:

     The above plus support for project's that provide an executable CLI.

   - ``docker``:

     The ``dist`` branch plus Docker containers for both development and
     end-users/deployments.

   - ``ci``:

     The above plus GitLab CI/CD pipelines that run tests and linters as CI and
     publish releases from ``develop`` and ``main`` as CD.

   - ``ci-cli``:

     The above plus the ``cli`` branch.

   - etc.

   Do not use the ``develop`` or ``main`` branches in your project as those branches
   are used to test the CI/CD automatic releases process and as such contain bumped
   versions, release notes, and other release artifacts that shouldn't be merged into
   real projects.

#. Reconcile VCS history:

   If starting a fresh project::

     $ git clone --origin "template" --branch "ci-cli" \
     "https://gitlab.com/rpatterson/python-project-structure.git" "./foo-project"
     $ cd "./foo-project"
     $ git config remote.template.tagOpt --no-tags
     $ git remote add "origin" "git@gitlab.com:foo-username/foo-project.git"
     $ git config remote.template.tagOpt --no-tags
     $ git switch -C "main" --track "origin/main"

   If merging into an existing project::

     $ git remote add "template" \
     "https://gitlab.com/rpatterson/python-project-structure.git"
     $ git config remote.template.tagOpt --no-tags
     $ git merge --allow-unrelated-histories "template/ci-cli"

#. Rename file and directory paths derived from the project name::

     $ git ls-files | grep -iE 'python.?project.?structure'

#. Rename strings derived from the project name and template author identity in project
   files::

     $ git grep -iE 'python.?project.?structure|ross|Patterson'

#. Examine ``# TEMPLATE:`` comments and change as appropriate:

   These are the bits that need the developer's attention and reasoning to take the
   correct action.  So read the comments and address them with care and attention::

     $ git grep "TEMPLATE"

Finally, remove this section from this ``./README.rst`` and update the rest of it's
content as appropriate for your project.  As fixes and features are added to the
upstream template, you can merge them into your project and repeat steps 3-5 above as
needed.

This template publishes pre-releases on all pushes to the ``develop`` branch and final
releases on all pushes to the ``main`` branch.  Project owners may decide which types
of changes should go through pre-release before final release and which types of changes
should go straight to final release.  For example they may decide that:

- Contributions from those who are not maintainers or owners should be merged into
  ``develop``.  See `the ./CONTRIBUTING.rst file`_ for such an example public
  contributions policy and workflow.

- Fixes for bugs in final releases may be committed to a branch off of ``main`` and,
  after passing all tests and checks, merged back into ``main`` to publish final
  releases immediately.

- Routine version upgrades for security updates may also be merged to ``main`` as
  above for bug fixes.


****************************************************************************************
Installation
****************************************************************************************

Install and use either via a local, native installation or a Docker container image:

Local/Native Installation
========================================================================================

Install using any tool for installing standard Python 3 distributions such as `pip`_::

  $ pip3 install --user python-project-structure

Optional shell tab completion is available via `argcomplete`_.

Docker Container Image Installation
========================================================================================

The recommended way to use the Docker container image is via `Docker Compose`_.  See
`the example ./docker-compose.yml file`_ for an example configuration.  Once you have
your configuration, you can create and run the container::

  $ docker compose up

Alternatively, you make use the image directly.  Pull `the Docker image`_::

  $ docker pull "registry.gitlab.org/rpatterson/python-project-structure"

And then use the image to create and run a container::

  $ docker run --rm -it "registry.gitlab.org/rpatterson/python-project-structure" ...

Images variant tags are published for the Python version, branch, and major/minor
versions so that users can control when they get new images over time,
e.g. ``docker.io/merpatterson/python-project-structure:py310-main``.  The canonical
Python version is 3.10 which is the version used in tags without ``py###``,
e.g. ``docker.io/merpatterson/python-project-structure:main``.  Pre-releases are from
``develop`` and final releases are from ``main`` which is also the default for tags
without a branch, e.g. ``docker.io/merpatterson/python-project-structure:py310``. The
major/minor version tags are only applied to the final release images and without the
corresponding ``main`` branch tag,
e.g. ``docker.io/merpatterson/python-project-structure:py310-v0.8``.

Multi-platform Docker images are published containing images for the following
platforms or architectures in the Python 3.10 ``py310`` variant:

- ``linux/amd64``
- ``linux/arm64``
- ``linux/arm/v7``


****************************************************************************************
Usage
****************************************************************************************

See the command-line help for details on options and arguments::

  $ python-project-structure --help
  usage: python-project-structure [-h]

  Python project structure foundation or template, top-level package.

  optional arguments:
    -h, --help  show this help message and exit

If using the Docker container image, the container can be run from the command-line as
well::

  $ docker compose run "python-project-structure" python-project-structure --help
  usage: python-project-structure [-h]

  Python project structure foundation or template, top-level package.

  optional arguments:
    -h, --help  show this help message and exit


****************************************************************************************
Contributing
****************************************************************************************

NOTE: `This project is hosted on GitLab`_.  There's `a mirror on GitHub`_ but please use
GitLab for reporting issues, submitting PRs/MRs and any other development or maintenance
activity.

See `the ./CONTRIBUTING.rst file`_ for more details on how to get started with
development.


****************************************************************************************
Motivation
****************************************************************************************

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
.. _pip: https://pip.pypa.io/en/stable/installation/
.. _argcomplete: https://kislyuk.github.io/argcomplete/#installation

.. _`This project is hosted on GitLab`:
   https://gitlab.com/rpatterson/python-project-structure
.. _`a mirror on GitHub`:
   https://github.com/rpatterson/python-project-structure
.. _`Docker`: https://docs.docker.com/
.. _`Docker Compose`: https://docs.docker.com/compose/
.. _the Docker image: https://hub.docker.com/r/merpatterson/python-project-structure

.. _`GitLab CI/CD`: https://docs.gitlab.com/ee/ci/

.. _`GitHub Actions`: https://docs.github.com/en/actions

.. _Makefile:
   https://gitlab.com/rpatterson/python-project-structure/blob/main/Makefile
.. _`the example ./docker-compose.yml file`:
   https://gitlab.com/rpatterson/python-project-structure/blob/main/docker-compose.yml
.. _`the ./CONTRIBUTING.rst file`:
   https://gitlab.com/rpatterson/python-project-structure/blob/main/CONTRIBUTING.rst
