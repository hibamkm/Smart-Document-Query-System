import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Writable location for runtime data, overridable via env for deployments where
# the code directory itself is not writable. Defaults to the project directory.
DATA_DIR = os.environ.get('DATA_DIR', BASE_DIR)


def _load_secret_key():
    """Use SECRET_KEY from the environment, else create and persist a random one.

    A random key stored next to the database means sessions survive restarts
    without a secret ever being committed to the repository.
    """
    env_key = os.environ.get('SECRET_KEY')
    if env_key:
        return env_key
    key_path = os.path.join(DATA_DIR, '.secret_key')
    try:
        with open(key_path) as f:
            key = f.read().strip()
            if key:
                return key
    except OSError:
        pass
    key = secrets.token_hex(32)
    try:
        with open(key_path, 'w') as f:
            f.write(key)
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    return key


SECRET_KEY = _load_secret_key()
UPLOAD_FOLDER = os.path.join(DATA_DIR, 'uploads')
DATABASE = os.path.join(DATA_DIR, 'smart_doc.db')
ALLOWED_EXTENSIONS = {'pdf', 'txt', 'md', 'docx'}
MAX_UPLOAD_MB = 25
MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024 * 4   # whole request (several files)
MIN_PASSWORD_LENGTH = 6
DEBUG = os.environ.get('FLASK_DEBUG', '0') == '1'
PORT = int(os.environ.get('PORT', '5001'))
