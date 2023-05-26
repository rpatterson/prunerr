.. SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
..
.. SPDX-License-Identifier: MIT

########################################################################################
Project structure
########################################################################################
Project structure foundation or template
****************************************************************************************

.. list-table::
   :class: borderless align-right

   * - .. figure:: https://api.reuse.software/badge/gitlab.com/rpatterson/project-structure
          :alt: Reuse license status
          :target: https://api.reuse.software/info/gitlab.com/rpatterson/project-structure

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


This is a minimal, yet opinionated baseline for software projects. It includes:

- A `Makefile`_ for local development, build, test, and maintenance
- A target that formats all source, including for style
- A kitchen sink linter configuration that runs all source checks
- `Version Control System (VCS) hooks`_ to enforce `conventional commits`_, successful
  build and test on commit and push, and `Towncrier`_ end-user oriented release notes on
  push
- Targets that automate releases
- Targets that automate dependency upgrades
- `Organize source by feature`_, for example ``\./src/foo/(template|view|model)\..*``,
  rather than by source type, for example
  ``\./src/(templates|views|models)/foo\..*``.

Add a VCS remote for this repository to a real project. When the template adds structure
specific to certain types of projects, for example command-line tools, web services, UI
apps, the it adds branches for each variant. When the template makes changes to
structure common to different variants it can merge those changes into those
variants. Real projects can also merge those changes.

.. _Makefile: https://gitlab.com/rpatterson/project-structure/-/blob/main/Makefile
.. _`Version Control System (VCS) hooks`:
   https://gitlab.com/rpatterson/project-structure/-/blob/main/.pre-commit-config.yaml
.. _`conventional commits`: https://www.conventionalcommits.org
.. _`Towncrier`: https://towncrier.readthedocs.io
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

   Is your project a command-line tool? A web app? Which programming language? Which
   project hosting provider or CI platform? Pick the branch for your project:

   - ``(py|js|ruby|…)``:

     Basic package metadata for a given language.

#. Merge into your project:

   If starting a fresh project::

     $ git clone --origin "template" --branch "${TEMPLATE_BRANCH:?}" \
     "https://gitlab.com/rpatterson/project-structure.git" "./foo-project"
     $ cd "./foo-project"
     $ git remote add "origin" "git@gitlab.com:foo-username/foo-project.git"
     $ git config remote.template.tagOpt --no-tags
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

Install by using any tool for installing packages for the project language::

  $ true "TEMPLATE: Always specific to the project type"


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
Contributing
****************************************************************************************

`GitLab hosts this project`_ and `mirrors it to GitHub`_ but use GitLab for reporting
issues, submitting pull or merge requests and any other development or maintenance
activity. See `the contributing documentation`_ for more details on how to get started
with development.


.. _`GitLab hosts this project`:
   https://gitlab.com/rpatterson/project-structure
.. _`mirrors it to GitHub`:
   https://github.com/rpatterson/project-structure
.. _`the contributing documentation`:
   https://gitlab.com/rpatterson/project-structure/-/blob/main/docs/contributing.rst
