"""Sphinx configuration for the News App documentation.

Sets up Django before Sphinx imports the project's modules, so
autodoc can read the docstrings in models, views and permissions.
"""

import os
import sys

import django

# -- Django setup ------------------------------------------------------
# Make the project root importable and load the Django settings.
sys.path.insert(0, os.path.abspath(".."))
os.environ["DJANGO_SETTINGS_MODULE"] = "news_project.settings"
django.setup()

# -- Project information -----------------------------------------------
project = "News App"
copyright = "2026, Lance Landore"
author = "Lance Landore"
release = "1.0"

# -- General configuration ---------------------------------------------
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

# List members in the same order as they appear in the source files.
autodoc_member_order = "bysource"

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "planning.md"]
language = "en"

# -- Options for HTML output -------------------------------------------
html_theme = "alabaster"
html_static_path = ["_static"]
