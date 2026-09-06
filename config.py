import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Writable location for runtime data, overridable via env for deployments where
# the code directory itself is not writable. Defaults to the project directory.
DATA_DIR = os.environ.get('DATA_DIR', BASE_DIR)

SECRET_KEY = os.environ.get('SECRET_KEY', 'hiba-smart-doc-query-secret-key')
UPLOAD_FOLDER = os.path.join(DATA_DIR, 'uploads')
DATABASE = os.path.join(DATA_DIR, 'smart_doc.db')
ALLOWED_EXTENSIONS = {'pdf', 'txt'}
