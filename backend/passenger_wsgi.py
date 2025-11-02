import os

from main import app as application  # noqa: F401

# Ensure the ADMIN_TOKEN is set, otherwise default to a placeholder to avoid runtime errors.
os.environ.setdefault("ADMIN_TOKEN", "changeme")
