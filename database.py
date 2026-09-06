import os
import re

import config

# Postgres is used when DATABASE_URL is set (serverless deployments have no
# persistent disk); otherwise fall back to the local SQLite file so the app
# still runs unchanged during development.
DATABASE_URL = os.environ.get('DATABASE_URL', '')
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg
    from psycopg.rows import dict_row
else:
    import sqlite3


# "USER" is a reserved word in Postgres and must be quoted.
_USER_TABLE_RE = re.compile(r'\b(FROM|INTO|UPDATE|JOIN)\s+USER\b')
_INSERT_TABLE_RE = re.compile(r'INSERT\s+INTO\s+"?(\w+)"?', re.IGNORECASE)

_PRIMARY_KEYS = {
    'USER': 'user_id',
    'DOCUMENT': 'document_id',
    'DOCUMENT_SECTION': 'section_id',
    'QUERY': 'query_id',
    'RETRIEVAL_RESULT': 'result_id',
    'ANSWER': 'answer_id',
}


def _translate(sql):
    """Rewrite the SQLite-flavoured SQL used across the app for Postgres."""
    return _USER_TABLE_RE.sub(r'\1 "USER"', sql.replace('?', '%s'))


def get_db():
    if USE_POSTGRES:
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


_SQLITE_SCHEMA = '''
    CREATE TABLE IF NOT EXISTS USER (
        user_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        username  VARCHAR(100) NOT NULL UNIQUE,
        email     VARCHAR(100) NOT NULL UNIQUE,
        password  VARCHAR(100) NOT NULL
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
        page_number  INTEGER,
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
'''

_POSTGRES_SCHEMA = '''
    CREATE TABLE IF NOT EXISTS "USER" (
        user_id   SERIAL PRIMARY KEY,
        username  VARCHAR(100) NOT NULL UNIQUE,
        email     VARCHAR(100) NOT NULL UNIQUE,
        password  VARCHAR(100) NOT NULL
    );
    CREATE TABLE IF NOT EXISTS DOCUMENT (
        document_id   SERIAL PRIMARY KEY,
        user_id       INTEGER NOT NULL REFERENCES "USER"(user_id),
        document_name VARCHAR(150) NOT NULL,
        upload_date   DATE NOT NULL,
        file_type     VARCHAR(20) NOT NULL
    );
    CREATE TABLE IF NOT EXISTS DOCUMENT_SECTION (
        section_id   SERIAL PRIMARY KEY,
        document_id  INTEGER NOT NULL REFERENCES DOCUMENT(document_id),
        section_text TEXT NOT NULL,
        embedding    BYTEA,
        page_number  INTEGER
    );
    CREATE TABLE IF NOT EXISTS QUERY (
        query_id   SERIAL PRIMARY KEY,
        user_id    INTEGER NOT NULL REFERENCES "USER"(user_id),
        query_text TEXT NOT NULL,
        query_date DATE NOT NULL
    );
    CREATE TABLE IF NOT EXISTS RETRIEVAL_RESULT (
        result_id        SERIAL PRIMARY KEY,
        query_id         INTEGER NOT NULL REFERENCES QUERY(query_id),
        section_id       INTEGER NOT NULL REFERENCES DOCUMENT_SECTION(section_id),
        similarity_score FLOAT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS ANSWER (
        answer_id   SERIAL PRIMARY KEY,
        query_id    INTEGER NOT NULL REFERENCES QUERY(query_id),
        answer_text TEXT NOT NULL
    );
'''

_initialized = False


def init_db():
    # Serverless invocations re-import this module on every cold start; only
    # pay for the schema round trip once per process.
    global _initialized
    if _initialized:
        return

    conn = get_db()
    try:
        if USE_POSTGRES:
            with conn.cursor() as cursor:
                cursor.execute(_POSTGRES_SCHEMA)
        else:
            conn.cursor().executescript(_SQLITE_SCHEMA)
            for column in ('embedding BLOB', 'page_number INTEGER'):
                try:
                    conn.execute(f'ALTER TABLE DOCUMENT_SECTION ADD COLUMN {column}')
                except Exception:
                    pass
        conn.commit()
    finally:
        conn.close()

    _initialized = True


def query_db(sql, args=(), one=False):
    conn = get_db()
    try:
        if USE_POSTGRES:
            with conn.cursor() as cursor:
                cursor.execute(_translate(sql), args)
                rows = cursor.fetchall()
        else:
            rows = conn.execute(sql, args).fetchall()
    finally:
        conn.close()
    return (rows[0] if rows else None) if one else rows


def insert_db(sql, args=()):
    conn = get_db()
    try:
        if USE_POSTGRES:
            match = _INSERT_TABLE_RE.search(sql)
            table = match.group(1).upper() if match else ''
            primary_key = _PRIMARY_KEYS.get(table)

            statement = _translate(sql)
            if primary_key:
                statement += f' RETURNING {primary_key}'

            with conn.cursor() as cursor:
                cursor.execute(statement, args)
                row = cursor.fetchone() if primary_key else None
            conn.commit()
            return row[primary_key] if row else None

        cursor = conn.execute(sql, args)
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()
