# The Daily Ledger: Django News Application

A news platform where independent journalists and publishers' staff
write articles, editors review and approve them, and readers subscribe
to the journalists and publishers they follow. Approved articles are
emailed to subscribers and logged through the project's own REST API.

Built with **Django 5.2**, **Django REST Framework** and **MariaDB**.

![Stack](https://img.shields.io/badge/Django-5.2-0c4b33)
![Tests](https://img.shields.io/badge/tests-95%20passing-2f6b3a)

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
- **95 automated tests** covering every role, success and failure
  cases, with email and HTTP mocked.

Design notes (requirements, ERD, normalisation, UI plan) are in
[`docs/planning.md`](docs/planning.md).

## Project structure

```
news_app/
├── manage.py
├── requirements.txt
├── .env.example
├── docs/planning.md          requirements, ERD, normalisation, UI plan
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

## Setup (Windows PowerShell)

### 1. Install MariaDB and create the database

Install MariaDB from <https://mariadb.org/download/>, then open the
MariaDB client (`mariadb -u root -p`) and run:

```sql
CREATE DATABASE news_app CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'news_user'@'localhost' IDENTIFIED BY 'choose-a-password';
GRANT ALL PRIVILEGES ON news_app.* TO 'news_user'@'localhost';
-- Lets Django create the temporary database used by the tests:
GRANT ALL PRIVILEGES ON test_news_app.* TO 'news_user'@'localhost';
FLUSH PRIVILEGES;
```

### 2. Install the project

```powershell
git clone <your-repo-url>
cd news_app
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Open `.env` and set `DB_PASSWORD` (and a new `DJANGO_SECRET_KEY` and
`APPROVED_API_KEY`).

On macOS/Linux use `source venv/bin/activate` and `cp` instead of
`copy`. `mysqlclient` may need the MariaDB/MySQL client libraries
(`brew install mariadb pkg-config` on macOS).

### 3. Create the tables and groups

```powershell
python manage.py migrate
python manage.py createsuperuser
```

`migrate` also creates the Reader, Editor and Journalist groups with
their permissions. Run `python manage.py setup_groups` at any time to
rebuild them.

### 4. (Optional) Load demo data

```powershell
python manage.py seed_demo
```

Creates `reader1`, `editor1`, `journalist1` and `journalist2`
(password `DemoPass123!`), a publisher, articles and a newsletter.

### 5. Run

```powershell
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. Admin is at `/admin/`. Emails print in
the terminal (console backend) unless you configure SMTP in `.env`.

> The approval signal POSTs to `http://127.0.0.1:8000/api/approved/`,
> so keep the server on port 8000 (or change
> `APPROVED_ARTICLE_ENDPOINT`).

## Running the tests

```powershell
python manage.py test news
```

Coverage includes authenticated access per role, readers only seeing
subscribed content, journalists creating articles, editors approving
and deleting, newsletters, and the signal logic (email and
`/api/approved/` mocked). For a quick run without MariaDB:

```powershell
$env:DB_ENGINE="sqlite"; python manage.py test news
```

Style check: `flake8 --exclude=migrations,venv`.

## REST API

Get a token, then send it as `Authorization: Token <token>`.

```powershell
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
