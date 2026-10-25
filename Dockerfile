# Container image for the News App (Django).
FROM python:3.14-slim

# Don't write .pyc files, and print logs straight to the terminal.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Defaults so the container runs on any machine without MariaDB.
# Override any of these at run time with -e or --env-file.
ENV DB_ENGINE=sqlite \
    DJANGO_ALLOWED_HOSTS=* \
    DJANGO_DEBUG=True

WORKDIR /app

# System libraries needed to build mysqlclient (for MariaDB).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc pkg-config default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages first so this layer is cached between builds.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project code.
COPY . .

EXPOSE 8000

# Apply migrations (this also creates the role groups), then start
# the development server on all interfaces so the host can reach it.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py runserver 0.0.0.0:8000"]
