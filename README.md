# The Daily Ledger: Django News Application

A news platform where independent journalists and publishers' staff
write articles, editors review and approve them, and readers subscribe
to the journalists and publishers they follow. Approved articles are
emailed to subscribers and logged through the project's own REST API.

Built with **Django 5.2**, **Django REST Framework** and **MariaDB**,
documented with **Sphinx** and containerised with **Docker**.

![Stack](https://img.shields.io/badge/Django-5.2-0c4b33)
![Tests](https://img.shields.io/badge/tests-100%20passing-2f6b3a)

## Contents

- [Features](#features)
- [Project structure](#project-structure)
- [Secrets and configuration](#secrets-and-configuration)
- [Run with a virtual environment](#run-with-a-virtual-environment)
- [Run with Docker](#run-with-docker)
- [Documentation (Sphinx)](#documentation-sphinx)
- [Running the tests](#running-the-tests)
- [REST API](#rest-api)
- [Design decisions](#design-decisions)

## Features

- **Custom user model** with three roles (Reader, Editor, Journalist).
  Each user is automatically placed in the matching group, and each
  group holds the model permissions its role needs.
- **Editorial workflow**: journalists submit articles (independent or
  for a publisher they belong to); editors approve them from a review
  queue.
- **Approval side effects via Django signals**: on approval, the
  article is emailed to subscribers (BCC) and POSTed with `requests`
  to `/api/approved/`, which stores a log record.
- **Subscriptions**: readers follow publishers and journalists and get
  a personal feed.
- **Newsletters**: journalists curate collections of approved articles.
- **REST API** with token authentication and role-based permissions.
- **100 automated tests** covering every role, success and failure
  cases, with email and HTTP mocked.

Design notes (requirements, ERD, normalisation, UI plan) are in
[`docs/planning.md`](docs/planning.md).

## Project structure

```
news-app-capstone/
├── manage.py
├── requirements.txt
├── Dockerfile                container image definition
├── .dockerignore             keeps secrets and local files out of the image
├── .env.example              template for your own .env (no real secrets)
├── docs/
│   ├── conf.py, *.rst        Sphinx configuration and source pages
│   ├── _build/html/          generated HTML documentation
│   └── planning.md           requirements, ERD, normalisation, UI plan
├── news_project/             settings and root URLs
└── news/
    ├── models.py             CustomUser, Publisher, Article, Newsletter,
    │                         ApprovedArticleLog
    ├── roles.py              roles, groups and permissions
    ├── signals.py            approval signal, subscription guard
    ├── services.py           email + POST to /api/approved/
    ├── permissions.py        DRF permission classes
    ├── serializers.py        DRF serializers
    ├── api_views.py          REST API
    ├── views.py, forms.py    website
    ├── templates/, static/   front end
    ├── management/commands/  setup_groups, seed_demo
    └── tests/                automated tests
```

## Secrets and configuration

No secrets are committed to this repository. All settings come from
environment variables, normally kept in a `.env` file next to
`manage.py`. `.env` is listed in `.gitignore` and `.dockerignore`, so
it never reaches GitHub or a Docker image.

1. Copy the template:

   ```bash
   cp .env.example .env          # macOS / Linux
   copy .env.example .env        # Windows PowerShell
   ```

2. Generate a secret key and paste it into `.env` as
   `DJANGO_SECRET_KEY`:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(50))"
   ```

3. Set the remaining values in `.env`:

   | Variable | What to put there |
   |----------|-------------------|
   | `DJANGO_SECRET_KEY` | The key generated above |
   | `DB_ENGINE` | `mariadb`, or `sqlite` to skip MariaDB entirely |
   | `DB_PASSWORD` | The password you give `news_user` in MariaDB |
   | `APPROVED_API_KEY` | Any long random string (generate one the same way) |
   | `EMAIL_*` | Only needed for real email; the default prints emails in the terminal |

## Run with a virtual environment

### 1. Database

**Quick option:** set `DB_ENGINE=sqlite` in `.env` and skip to step 2.

**MariaDB:** install it from <https://mariadb.org/download/> (or
`brew install mariadb` on macOS), open the client with
`mariadb -u root -p`, and run:

```sql
CREATE DATABASE news_app CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'news_user'@'localhost' IDENTIFIED BY 'choose-a-password';
GRANT ALL PRIVILEGES ON news_app.* TO 'news_user'@'localhost';
-- Lets Django create the temporary database used by the tests:
GRANT ALL PRIVILEGES ON test_news_app.* TO 'news_user'@'localhost';
FLUSH PRIVILEGES;
```

Put the same password in `.env` as `DB_PASSWORD`.

### 2. Install

macOS / Linux:

```bash
git clone https://github.com/novaofc/news-app-capstone.git
cd news-app-capstone
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
git clone https://github.com/novaofc/news-app-capstone.git
cd news-app-capstone
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Then create your `.env` as described in
[Secrets and configuration](#secrets-and-configuration).

`mysqlclient` needs the MariaDB/MySQL client libraries. On macOS:
`brew install mariadb pkg-config`.

### 3. Create the tables and groups

```bash
python manage.py migrate
python manage.py createsuperuser
```

`migrate` also creates the Reader, Editor and Journalist groups with
their permissions. Run `python manage.py setup_groups` at any time to
rebuild them.

### 4. (Optional) Load demo data

```bash
python manage.py seed_demo
```

Creates `reader1`, `editor1`, `journalist1` and `journalist2`
(password `DemoPass123!`), a publisher, articles and a newsletter.

### 5. Run

```bash
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. The admin is at `/admin/`. Emails print
in the terminal (console backend) unless you configure SMTP in `.env`.

> The approval signal POSTs to `http://127.0.0.1:8000/api/approved/`,
> so keep the server on port 8000 (or change
> `APPROVED_ARTICLE_ENDPOINT`).

## Run with Docker

Install Docker Desktop (<https://www.docker.com/products/docker-desktop/>)
or use Play with Docker (<https://labs.play-with-docker.com/>).

By default the container uses **SQLite**, so it runs on any machine
without MariaDB. Migrations, including the role groups, run
automatically each time the container starts.

### 1. Build the image

From the project root (the folder containing the `Dockerfile`):

```bash
docker build -t news-app .
```

### 2. Run the container

Pass your secrets in at run time. They are never stored in the image.

Using your `.env` file:

```bash
docker run --rm -p 8000:8000 --env-file .env --name news-app news-app
```

Or without a `.env` file (for example on Play with Docker):

```bash
docker run --rm -p 8000:8000 \
  -e DJANGO_SECRET_KEY="paste-a-generated-key-here" \
  -e APPROVED_API_KEY="paste-another-random-string-here" \
  --name news-app news-app
```

Open <http://localhost:8000/>. On Play with Docker, click the **8000**
link that appears at the top of the session instead.

> Use `localhost`, not `0.0.0.0`, in your browser. If `.env` sets
> `DJANGO_ALLOWED_HOSTS`, only the hosts listed there are accepted.

### 3. (Optional) Demo data and an admin user

With the container running, in a second terminal:

```bash
docker exec news-app python manage.py seed_demo
docker exec -it news-app python manage.py createsuperuser
```

The SQLite database lives inside the container, so data is reset each
time the container is removed.

### 4. Stop

Press `Ctrl + C` in the terminal running the container.

### Using MariaDB with Docker

To connect the container to a MariaDB server on your machine, set
these in `.env` (or pass them with `-e`):

```
DB_ENGINE=mariadb
DB_HOST=host.docker.internal
DB_NAME=news_app
DB_USER=news_user
DB_PASSWORD=your-database-password
```

The MariaDB user must be allowed to connect from the container, for
example `CREATE USER 'news_user'@'%' ...` instead of `@'localhost'`.

## Documentation (Sphinx)

The generated HTML documentation is committed in `docs/_build/html`.
Open `docs/_build/html/index.html` in a browser to read it.

To rebuild it after changing docstrings (with the virtual environment
active and a `.env` file present):

```bash
cd docs
make clean html
```

## Running the tests

```bash
python manage.py test news
```

Coverage includes authenticated access per role, readers only seeing
subscribed content, journalists creating articles, editors approving
and deleting, newsletters, and the signal logic (email and
`/api/approved/` mocked). With `DB_ENGINE=sqlite` in `.env`, the tests
run without MariaDB.

Style check (PEP 8):

```bash
pip install flake8
flake8 --exclude venv,migrations,docs/_build .
```

## REST API

Get a token, then send it as `Authorization: Token <token>`.

```bash
curl -X POST http://127.0.0.1:8000/api/token/ -d "username=reader1" -d "password=DemoPass123!"
curl http://127.0.0.1:8000/api/articles/subscribed/ -H "Authorization: Token <token>"
```

| Method | Endpoint | Who | Description |
|--------|----------|-----|-------------|
| POST | `/api/token/` | anyone | Obtain a token |
| GET | `/api/users/me/` | any role | Current user |
| GET | `/api/articles/` | any role | All approved articles |
| GET | `/api/articles/subscribed/` | reader | Articles from subscriptions |
| GET | `/api/articles/pending/` | editor | Articles awaiting approval |
| GET | `/api/articles/<id>/` | any role | One article |
| POST | `/api/articles/` | journalist | Create an article |
| PUT/PATCH | `/api/articles/<id>/` | editor, own journalist | Update |
| DELETE | `/api/articles/<id>/` | editor, own journalist | Delete |
| POST | `/api/articles/<id>/approve/` | editor | Approve (triggers signal) |
| GET | `/api/newsletters/` | any role | List newsletters |
| POST | `/api/newsletters/` | journalist | Create a newsletter |
| PUT/PATCH/DELETE | `/api/newsletters/<id>/` | editor, own journalist | Update / delete |
| GET | `/api/publishers/` | any role | Publishers (read-only) |
| POST | `/api/approved/` | `X-Api-Key` header | Log an approved article (used by the signal) |
| GET | `/api/approved/` | editor | View the approval log |

Readers get `403 Forbidden` on any write; unauthenticated requests get
`401 Unauthorized`.

### Example: create an article as a journalist

```json
POST /api/articles/
{
  "title": "Harbour upgrade opens",
  "content": "The new walkway opened this morning...",
  "publisher": 1
}
```

Omit `publisher` (or send `null`) for an independent article.

## Design decisions

- **Signals (Option 1)** were chosen because approval can happen from
  the website, the API and the admin. One `post_save` handler covers
  all three, and it only fires when an article changes to approved,
  so edits never re-send emails.
- **Permissions over role checks**: views and API permissions check
  Django model permissions granted by the role groups, so changing a
  group's permissions changes behaviour without code changes.
- **Everything happens on the website**: anyone can sign up as a
  Reader, Journalist or Editor, and editors create publishers and
  assign their staff from the Publishers page. The Django admin is
  only needed for superuser maintenance.
- **Failure-safe approval**: email or HTTP errors are logged and never
  roll back an approval.
- **Configuration from the environment**: the same code runs locally,
  in Docker, and against SQLite or MariaDB, with secrets supplied at
  run time rather than committed.
