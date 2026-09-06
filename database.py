import sqlite3
import config


def get_db():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript('''
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
    ''')

    conn.commit()

    try:
        conn.execute('ALTER TABLE DOCUMENT_SECTION ADD COLUMN embedding BLOB')
        conn.commit()
    except Exception:
        pass

    try:
        conn.execute('ALTER TABLE DOCUMENT_SECTION ADD COLUMN page_number INTEGER')
        conn.commit()
    except Exception:
        pass

    conn.close()


def query_db(sql, args=(), one=False):
    conn = get_db()
    cursor = conn.execute(sql, args)
    rows = cursor.fetchall()
    conn.close()
    return (rows[0] if rows else None) if one else rows


def insert_db(sql, args=()):
    conn = get_db()
    cursor = conn.execute(sql, args)
    conn.commit()
    last_id = cursor.lastrowid
    conn.close()
    return last_id
