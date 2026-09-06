import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Writable location for runtime data, overridable via env. Serverless platforms
# expose only /tmp as writable; uploaded files are parsed and discarded within a
# single request, so ephemeral storage is sufficient there -- the extracted text
# and embeddings live in the database. Local runs keep using the project folder.
_DEFAULT_DATA_DIR = '/tmp' if os.environ.get('VERCEL') else BASE_DIR
DATA_DIR = os.environ.get('DATA_DIR', _DEFAULT_DATA_DIR)

SECRET_KEY = os.environ.get('SECRET_KEY', 'hiba-smart-doc-query-secret-key')
UPLOAD_FOLDER = os.path.join(DATA_DIR, 'uploads')
DATABASE = os.path.join(DATA_DIR, 'smart_doc.db')
ALLOWED_EXTENSIONS = {'pdf', 'txt'}
