.. SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
..
.. SPDX-License-Identifier: MIT

########################################################################################
Project Structure
########################################################################################
Project Structure foundation or template
****************************************************************************************

.. list-table::
   :class: borderless align-right

   * - .. figure:: https://img.shields.io/pypi/v/project-structure.svg?logo=pypi&label=PyPI&logoColor=gold
          :alt: PyPI latest release version
          :target: https://pypi.org/project/project-structure/
       .. figure:: https://img.shields.io/pypi/pyversions/project-structure.svg?logo=python&label=Python&logoColor=gold
          :alt: PyPI Python versions
          :target: https://pypi.org/project/project-structure/
       .. figure:: https://img.shields.io/badge/code%20style-black-000000.svg
          :alt: Python code style
          :target: https://github.com/psf/black
       .. figure:: https://api.reuse.software/badge/gitlab.com/rpatterson/project-structure
          :alt: Reuse license status
          :target: https://api.reuse.software/info/gitlab.com/rpatterson/project-structure

     - .. figure:: https://gitlab.com/rpatterson/project-structure/-/badges/release.svg
          :alt: GitLab latest release
          :target: https://gitlab.com/rpatterson/project-structure/-/releases
       .. figure:: https://gitlab.com/rpatterson/project-structure/badges/main/pipeline.svg
          :alt: GitLab CI/CD pipeline status
          :target: https://gitlab.com/rpatterson/project-structure/-/commits/main
       .. figure:: https://gitlab.com/rpatterson/project-structure/badges/main/coverage.svg
          :alt: GitLab coverage report
          :target: https://gitlab.com/rpatterson/project-structure/-/commits/main
       .. figure:: https://img.shields.io/gitlab/stars/rpatterson/project-structure?gitlab_url=https%3A%2F%2Fgitlab.com&logo=gitlab
          :alt: GitLab repository stars
          :target: https://gitlab.com/rpatterson/project-structure

     - .. figure:: https://img.shields.io/github/v/release/rpatterson/project-structure?logo=github
          :alt: GitHub release (latest SemVer)
          :target: https://github.com/rpatterson/project-structure/releases
       .. figure:: https://github.com/rpatterson/project-structure/actions/workflows/build-test.yml/badge.svg
          :alt: GitHub Actions status
          :target: https://github.com/rpatterson/project-structure/actions/workflows/build-test.yml
       .. figure:: https://codecov.io/github/rpatterson/project-structure/branch/main/graph/badge.svg?token=GNKVQ8VYOU
          :alt: Codecov test coverage
          :target: https://app.codecov.io/github/rpatterson/project-structure
       .. figure:: https://img.shields.io/github/stars/rpatterson/project-structure?logo=github
          :alt: GitHub repository stars
          :target: https://github.com/rpatterson/project-structure/

     - .. figure:: https://img.shields.io/docker/v/merpatterson/project-structure?sort=semver&logo=docker
          :alt: Docker Hub image version
          :target: https://hub.docker.com/r/merpatterson/project-structure
       .. figure:: https://img.shields.io/docker/pulls/merpatterson/project-structure?logo=docker
          :alt: Docker Hub image pulls count
          :target: https://hub.docker.com/r/merpatterson/project-structure
       .. figure:: https://img.shields.io/docker/stars/merpatterson/project-structure?logo=docker
          :alt: Docker Hub stars
          :target: https://hub.docker.com/r/merpatterson/project-structure
       .. figure:: https://img.shields.io/docker/image-size/merpatterson/project-structure?logo=docker
          :alt: Docker Hub image size
          :target: https://hub.docker.com/r/merpatterson/project-structure

     - .. figure:: https://img.shields.io/keybase/pgp/rpatterson?logo=keybase
          :alt: KeyBase Pretty Good Privacy (PGP) key ID
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


This repository provides a minimal, yet opinionated baseline for `Python`_ software
projects. It includes:

- Basic `Python "distribution"/project`_ metadata
- Command-line console script with subcommand boilerplate
- A `Docker`_ container image for end users
- A Docker image for development, which runs tests
- A `Makefile`_ for local development, build, test, and maintenance
- A target that formats all source, including `Black`_ for Python code style
- A `kitchen sink linter configuration`_ for `Prospector`_ that runs all available
  Python code checks
- A `tox.ini`_ configuration for `Tox`_ to run all tests and linters across supported
  Python versions, including some checks not provided by Prospector.
- `Version Control System (VCS) hooks`_ to enforce `conventional commits`_, successful
  build and test on commit and push, and `Towncrier`_ end-user oriented release notes on
  push
- Targets that automate releases
- Targets that automate dependency upgrades
- Targets used for both local development and on CI/CD platforms
- A `GitLab CI/CD`_ pipeline integrating those CI/CD recipes and targets
- A `GitHub Actions`_ workflow integrating those CI/CD recipes and targets
- `Organize source by feature`_, for example ``\./src/foo/(template|view|model)\..*``,
  rather than by source type, for example
  ``\./src/(templates|views|models)/foo\..*``.

Add a VCS remote for this repository to a real project. When the template adds structure
specific to certain types of projects, for example command-line tools, web services, UI
apps, the it adds branches for each variant. When the template makes changes to
structure common to different variants it can merge those changes into those
variants. Real projects can also merge those changes.

.. _Python: https://docs.python.org/3/library/logging.html
.. _Python "distribution"/project: https://docs.python.org/3/distributing/index.html
.. _`Docker`: https://docs.docker.com/
.. _Makefile: https://gitlab.com/rpatterson/project-structure/-/blob/main/Makefile
.. _`Black`: https://github.com/psf/black
.. _`kitchen sink linter configuration`:
   https://gitlab.com/rpatterson/project-structure/-/blob/main/.prospector.yaml
.. _`Prospector`: https://prospector.landscape.io/en/master/
.. _`tox.ini`: https://gitlab.com/rpatterson/project-structure/-/blob/main/tox.ini
.. _`Tox`: https://tox.wiki/en/stable/
.. _`Version Control System (VCS) hooks`:
   https://gitlab.com/rpatterson/project-structure/-/blob/main/.pre-commit-config.yaml
.. _`conventional commits`: https://www.conventionalcommits.org
.. _`Towncrier`: https://towncrier.readthedocs.io/en/stable/
.. _`GitLab CI/CD`: https://docs.gitlab.com/ee/ci/
.. _`GitHub Actions`: https://docs.github.com/en/actions
.. _`Organize source by feature`:
   https://www.seancdavis.com/posts/organize-components-by-keeping-related-files-close/

.. include-end-before
.. contents:: Table of Contents
.. include-start-after


****************************************************************************************
Template usage
****************************************************************************************

This is a rough guide for how to use this template in your project. This isn't widely
tested. Such tests are meta and wasteful to create and support. Report any issues you
have or better yet submit a PR with corrections.

#. Pick the branch to use:

   Pick the branch for your project type:

   - ``py``:

     Basic Python distribution metadata and packaging.

   - ``docker``:

     Docker images for development and end-users or deployments.

   - ``py-docker``:

     The preceding Docker images with the Python package installed.

   - ``ci``:

     The preceding plus GitLab CI/CD pipelines that run tests and linters as CI and
     publish releases from ``develop`` and ``main`` as CD.

   - ``py-ci``:

     All the preceding combined together.

   It's important to use one of the preceding branches to merge into your project and
   *not* the ``develop`` or ``main`` branches from the template. Template developers use
   those branches to test the release process. They contain bumped versions, release
   notes, and other release artifacts that real projects shouldn't merge into their code
   or history.

#. Merge into your project:

   If starting a fresh project::

     $ git clone --origin "template" --branch "${TEMPLATE_BRANCH:?}" \
     "https://gitlab.com/rpatterson/project-structure.git" "./foo-project"
     $ cd "./foo-project"
     $ git config remote.template.tagOpt --no-tags
     $ git remote add "origin" "git@gitlab.com:foo-username/foo-project.git"
     $ git switch -C "main" --track "origin/main"

   If merging into an existing project::

     $ git remote add "template" \
     "https://gitlab.com/rpatterson/project-structure.git"
     $ git config remote.template.tagOpt --no-tags
     $ git merge --allow-unrelated-histories "template/${TEMPLATE_BRANCH:?}"

#. Rename files and directories derived from the project name::

     $ git ls-files | grep -iE 'project.?structure'

#. Rename project name and template creator identity strings::

     $ git grep -iE 'project.?structure|ross|Patterson'

#. Make changes described in ``# TEMPLATE:`` comments:

   These bits need the developer's attention and reasoning. Read the comments and follow
   them with care::

     $ git grep "TEMPLATE"

Lastly, remove this `Template usage`_ section and update the rest of this
``./README.rst`` for your project. When the template adds fixes and features, merge them
into your project and repeat steps 3--5.

This template publishes pre-releases on push to the ``develop`` branch and final
releases on push to the ``main`` branch. Project owners can decide the types of changes
that require a pre-release before final release and the types of changes that go
straight to final release. For example they can decide that:

- Merge public contributions into ``develop``. See `the contributing documentation`_ for
  an example public contributions policy and workflow.

- Optionally commit fixes for bugs in final releases to a branch off ``main``. After
  passing all tests and checks, merge back into ``main`` to publish final releases
  directly.

- Optionally also merge version upgrades for security updates directly to ``main``.


****************************************************************************************
Installation
****************************************************************************************

Install locally or use the Docker container image:

Local Installation
========================================================================================

Install by using any tool for installing standard Python 3 distributions such as
`pip`_::

  $ pip3 install --user project-structure

Docker Container Image
========================================================================================

The recommended way to use the container image is by using `Docker Compose`_. See `the
example ./docker-compose.yml file`_. Write your configuration and run the container::

  $ docker compose up

You can also use the image directly. Pull `the Docker image`_. Use it to create and run
a container::

  $ docker pull "registry.gitlab.com/rpatterson/project-structure"
  $ docker run --rm -it "registry.gitlab.com/rpatterson/project-structure" ...

Use image variant tags to control when the image updates. Releases publish tags for the
branch and for major and minor versions. For example, to keep up to date with a specific
branch, use a tag such as
``registry.gitlab.com/rpatterson/project-structure:main``. Releases from ``develop``
publish pre-releases. Releases from ``main`` publish final releases. Releases from
``main`` also publish tags without a branch, for example
``registry.gitlab.com/rpatterson/project-structure``. Releases from ``main`` also
publish tags for the major and minor version, for example
``registry.gitlab.com/rpatterson/project-structure:v0.8``.

Releases publish multi-platform images for the following platforms:

- ``linux/amd64``
- ``linux/arm64``
- ``linux/arm/v7``


****************************************************************************************
Usage
****************************************************************************************

See the command-line help for details on options and arguments::

  $ project-structure --help
  usage: project-structure [-h]

  Project structure foundation or template, top-level package.

  optional arguments:
    -h, --help  show this help message and exit


****************************************************************************************
Contributing
****************************************************************************************

`GitLab hosts this project`_ and `mirrors it to GitHub`_ but use GitLab for reporting
issues, submitting pull or merge requests and any other development or maintenance
activity. See `the contributing documentation`_ for more details on how to get started
with development.


****************************************************************************************
Motivation
****************************************************************************************

.. vale off

Plenty other project templates exists. Why make another? I've been a full-stack web
developer from 1998 on. I've had plenty of time to develop plenty of opinions of my
own. From a template I want a full tool set (for example test coverage, linting,
formatting, CI). Conversely, I want minimal dependencies, structure, and opinion beyond
a full tool set (for example some build or task system, structure for unused frameworks
or libraries). I couldn't find a template that manages that balance and I created this
one.

I also find it hard to discern from other templates why they made what choices the did.
As such, I also use this template to try out different options and learn for myself. You
can learn about my findings and the reasons the choices I've made in the commit history.

Most importantly I've never found a satisfactory approach to keeping project structure
up to date over time. As such, the primary motivation is providing a template upstream
remote, merging structure updates into real projects over their lifetime.

.. vale on


****************************************************************************************
References
****************************************************************************************

.. target-notes::

.. _`the contributing documentation`:
   https://gitlab.com/rpatterson/project-structure/-/blob/main/docs/contributing.rst

.. _pip: https://pip.pypa.io/en/stable/installation/

.. _`Docker Compose`: https://docs.docker.com/compose/
.. _`the example ./docker-compose.yml file`:
   https://gitlab.com/rpatterson/project-structure/-/blob/main/docker-compose.yml
.. _the Docker image: https://hub.docker.com/r/merpatterson/project-structure

.. _`GitLab hosts this project`:
   https://gitlab.com/rpatterson/project-structure
.. _`mirrors it to GitHub`:
   https://github.com/rpatterson/project-structure
