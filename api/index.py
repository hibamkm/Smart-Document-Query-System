import os
import sys

# The Flask app lives at the project root, one level above this file.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402  (path setup must run first)

# Vercel's Python runtime serves the WSGI callable named `app`.
__all__ = ['app']
