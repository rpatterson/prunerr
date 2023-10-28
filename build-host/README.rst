.. SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
..
.. SPDX-License-Identifier: MIT

########################################
Projects build host
########################################
The container image that builds projects
****************************************

Use this directory to build a container image that can build, test, and release
projects. The project host CI/CD platforms run pipeline jobs in this image. Developers
can also use it to reproduce CI/CD issues locally.

The release processes of projects don't publish changes to this image. As such,
maintainers must push new versions of this image as it changes by using the project's
``../Makefile``::

  $ cd ..
  $ make bootstrap-project
