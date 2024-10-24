# Variables
PYTHON=./.venv/bin/python
MANAGE=./manage.py
HOST=0.0.0.0
PORT=8000
EMAIL=admin@example.com
PASSWORD=P@ssword

# Collect static
static:
	$(PYTHON) $(MANAGE) collectstatic

# Run migrations
migrate:
	$(PYTHON) $(MANAGE) migrate

# Run dev
run:
	$(PYTHON) $(MANAGE) runserver $(HOST):$(PORT)

# Set up venv
setup:
	$(PYTHON) -m venv .venv

# Start with migrations
start: migrate runserver

### Dev helpers

# Create admin
dev_admin:
	$(PYTHON) $(MANAGE) shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); \
	User.objects.filter(email='$(EMAIL)').exists() or \
	User.objects.create_superuser(email='$(EMAIL)', password='$(PASSWORD)')"

# Drop all users
dev_reset_users:
	$(PYTHON) $(MANAGE) shell -c "from django.contrib.auth import get_user_model; \
	User = get_user_model(); \
	User.objects.all().delete();"
