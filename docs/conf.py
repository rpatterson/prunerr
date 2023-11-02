# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'Prunerr'
copyright = '2023, Ross Patterson'
author = 'Ross Patterson'
release = '0.0.0'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.duration',
    'sphinx_copybutton',
    'sphinxext.opengraph',
]

templates_path = ['_templates']
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'alabaster'
html_static_path = ['_static']

# -- Linter options ----------------------------------------------------------
# Disallow redirects:
linkcheck_allowed_redirects = {}
linkcheck_anchors_ignore = [
    # The default from the Sphinx extension:
    "^!",
    # Tolerate links to source code lines in VCS provider web UIs:
    "^L[0-9]+",
]
linkcheck_ignore = ["https://liberapay.com/.*"]

# -- Extension options -------------------------------------------------------
ogp_site_url = 'http://project-structure.readthedocs.io/'
