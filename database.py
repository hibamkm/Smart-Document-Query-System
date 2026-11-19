import sqlite3
import config


def get_db():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# Columns added after the first release. Each is applied only if missing, so an
# existing smart_doc.db keeps working after an upgrade.
_MIGRATIONS = [
    ('DOCUMENT_SECTION', 'embedding', 'BLOB'),
    ('DOCUMENT_SECTION', 'page_number', 'INTEGER'),
    ('DOCUMENT', 'stored_name', 'VARCHAR(200)'),
    ('DOCUMENT', 'size_bytes', 'INTEGER DEFAULT 0'),
    ('DOCUMENT', 'page_count', 'INTEGER DEFAULT 0'),
    ('ANSWER', 'confidence', 'FLOAT'),
    ('ANSWER', 'rating', 'INTEGER DEFAULT 0'),
    ('QUERY', 'created_at', 'VARCHAR(30)'),
]


def init_db():
    conn = get_db()

    conn.executescript('''
        CREATE TABLE IF NOT EXISTS USER (
            user_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            username  VARCHAR(100) NOT NULL UNIQUE,
            email     VARCHAR(100) NOT NULL UNIQUE,
            password  VARCHAR(255) NOT NULL
        );

        CREATE TABLE IF NOT EXISTS DOCUMENT (
            document_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            document_name VARCHAR(150) NOT NULL,
            upload_date   DATE NOT NULL,
            file_type     VARCHAR(20) NOT NULL,
            FOREIGN KEY (user_id) REFERENCES USER(user_id)
        );

        CREATE TABLE IF NOT EXISTS DOCUMENT_SECTION (
            section_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id  INTEGER NOT NULL,
            section_text TEXT NOT NULL,
            embedding    BLOB,
            FOREIGN KEY (document_id) REFERENCES DOCUMENT(document_id)
        );

        CREATE TABLE IF NOT EXISTS QUERY (
            query_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            query_text TEXT NOT NULL,
            query_date DATE NOT NULL,
            FOREIGN KEY (user_id) REFERENCES USER(user_id)
        );

        CREATE TABLE IF NOT EXISTS RETRIEVAL_RESULT (
            result_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            query_id         INTEGER NOT NULL,
            section_id       INTEGER NOT NULL,
            similarity_score FLOAT NOT NULL,
            FOREIGN KEY (query_id)   REFERENCES QUERY(query_id),
            FOREIGN KEY (section_id) REFERENCES DOCUMENT_SECTION(section_id)
        );

        CREATE TABLE IF NOT EXISTS ANSWER (
            answer_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            query_id    INTEGER NOT NULL,
            answer_text TEXT NOT NULL,
            FOREIGN KEY (query_id) REFERENCES QUERY(query_id)
        );

        CREATE INDEX IF NOT EXISTS idx_doc_user      ON DOCUMENT(user_id);
        CREATE INDEX IF NOT EXISTS idx_section_doc   ON DOCUMENT_SECTION(document_id);
        CREATE INDEX IF NOT EXISTS idx_query_user    ON QUERY(user_id);
        CREATE INDEX IF NOT EXISTS idx_result_query  ON RETRIEVAL_RESULT(query_id);
        CREATE INDEX IF NOT EXISTS idx_answer_query  ON ANSWER(query_id);
    ''')
    conn.commit()

    for table, column, decl in _MIGRATIONS:
        existing = {r['name'] for r in conn.execute(f'PRAGMA table_info({table})')}
        if column not in existing:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {decl}')
    conn.commit()
    conn.close()


def query_db(sql, args=(), one=False):
    conn = get_db()
    try:
        rows = conn.execute(sql, args).fetchall()
    finally:
        conn.close()
    return (rows[0] if rows else None) if one else rows


def insert_db(sql, args=()):
    conn = get_db()
    try:
        cursor = conn.execute(sql, args)
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def execute_db(sql, args=()):
    conn = get_db()
    try:
        cursor = conn.execute(sql, args)
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()
