import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv(path=None):
    """Minimal .env loader so secrets stay out of source control.

    Only sets a key if it isn't already present in the real environment,
    so an explicitly exported variable always wins. Resolves the file
    relative to this module so it is found regardless of the working
    directory the WSGI server starts in.
    """
    if path is None:
        path = os.path.join(BASE_DIR, '.env')
    if not os.path.exists(path):
        return
    with open(path, 'r', encoding='utf-8') as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_dotenv()


def _env_flag(name, default):
    return os.environ.get(name, str(default)).strip().lower() in {'1', 'true', 'yes', 'on'}


def _database_uri():
    uri = os.environ.get('DATABASE_URL', 'sqlite:///clouddrive.db')
    # SQLAlchemy 2.x rejects the legacy 'postgres://' scheme some hosts hand out.
    if uri.startswith('postgres://'):
        uri = uri.replace('postgres://', 'postgresql://', 1)
    return uri


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-only-insecure-key')
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Absolute so uploads land in the same place no matter the working directory.
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(BASE_DIR, 'static', 'uploads'))
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max size for a single upload request

    # Session cookie hardening. SESSION_COOKIE_SECURE is on by default; set it to
    # false only when testing over plain http locally.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = _env_flag('SESSION_COOKIE_SECURE', True)

    # Total storage allowance per user account.
    USER_STORAGE_LIMIT = int(os.environ.get('USER_STORAGE_LIMIT', 3 * 1024 * 1024 * 1024))  # 3 GB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'txt', 'mp4', 'mp3', 'zip'}
    MAX_FILES_PER_UPLOAD = 10

    # AI image generation (Gemini). Set GEMINI_API_KEY in the environment or in a
    # local .env file; leaving it unset simply disables the feature.
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
    GEMINI_IMAGE_MODEL = os.environ.get('GEMINI_IMAGE_MODEL', 'gemini-2.5-flash-image')

    # Default top-level sections. New content is filed under one of these rather
    # than the archive root. Seeded on startup and protected from deletion.
    DEFAULT_SECTIONS = [
        'Lighting Plot',
        'Instrument Schedule',
        'Lighting Cue',
        'Final Design',
        'Analysis of Design',
    ]
