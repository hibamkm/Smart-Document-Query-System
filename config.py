import os

SECRET_KEY = 'hiba-smart-doc-query-secret-key'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
DATABASE = os.path.join(BASE_DIR, 'smart_doc.db')
ALLOWED_EXTENSIONS = {'pdf', 'txt'}
