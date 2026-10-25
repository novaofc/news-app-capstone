News App documentation
======================

News App is a Django news platform where journalists write articles
and newsletters, editors review and approve them, and readers
subscribe to the publishers and journalists they follow. Approved
articles are emailed to subscribers and exposed through a REST API.

User roles
----------

Every account has exactly one role:

* **Reader** - reads approved articles and newsletters, and subscribes
  to publishers and journalists.
* **Journalist** - writes articles and newsletters, and can edit or
  delete only their own work.
* **Editor** - reviews and approves articles, edits or deletes any
  article or newsletter, and manages publishers.

Each role maps to a Django group with matching model permissions, so
access is checked with ``user.has_perm(...)`` throughout the project.

Getting started
---------------

See ``README.md`` in the project root for how to install and run the
app with a virtual environment or with Docker.

.. toctree::
   :maxdepth: 2
   :caption: Contents

   modules