import hmac
import os
import re
import secrets
import time
import uuid
from datetime import datetime
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify, abort, send_from_directory, Response)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

import config
import database
import document_processor
import retrieval

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
database.init_db()
retrieval.initialize_models()

HISTORY_LIMIT = 50
MAX_QUERY_CHARS = 500
USERNAME_RE = re.compile(r'^[A-Za-z0-9_.-]{3,30}$')
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_HASH_PREFIXES = ('pbkdf2:', 'scrypt:')

# username -> (failed_attempts, locked_until). In-memory is fine for a
# single-process app; it only slows down password guessing.
_login_failures = {}
MAX_FAILED_LOGINS = 5
LOCKOUT_SECONDS = 60


# ── Helpers ───────────────────────────────────────────────────────────────

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in config.ALLOWED_EXTENSIONS


def _format_page_label(pages):
    if not pages:
        return ''
    runs = []
    start = prev = pages[0]
    for p in pages[1:]:
        if p == prev + 1:
            prev = p
        else:
            runs.append((start, prev))
            start = prev = p
    runs.append((start, prev))
    parts = [str(a) if a == b else f'{a}-{b}' for a, b in runs]
    prefix = 'p.' if len(pages) == 1 else 'pp.'
    return f'{prefix} ' + ', '.join(parts)


def _human_size(n):
    n = n or 0
    for unit in ('B', 'KB', 'MB'):
        if n < 1024:
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} GB'


def _confidence_label(value):
    if value is None:
        return None
    if value >= 0.66:
        return 'high'
    if value >= 0.33:
        return 'medium'
    return 'low'


def _is_hashed(stored):
    return stored.startswith(_HASH_PREFIXES)


def _verify_password(user, password):
    """Check a password, transparently upgrading legacy plain-text rows."""
    stored = user['password']
    if _is_hashed(stored):
        return check_password_hash(stored, password)
    if hmac.compare_digest(stored.encode(), password.encode()):
        database.execute_db('UPDATE USER SET password = ? WHERE user_id = ?',
                            (generate_password_hash(password), user['user_id']))
        return True
    return False


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify(error='Please log in again.'), 401
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def _stored_path(doc):
    name = doc['stored_name'] or doc['document_name']   # legacy rows have no stored_name
    return os.path.join(app.config['UPLOAD_FOLDER'], name)


# ── CSRF protection ───────────────────────────────────────────────────────

def _csrf_token():
    if '_csrf' not in session:
        session['_csrf'] = secrets.token_hex(16)
    return session['_csrf']


@app.before_request
def check_csrf():
    if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
        sent = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token', '')
        expected = session.get('_csrf', '')
        if not expected or not hmac.compare_digest(sent, expected):
            if request.path.startswith('/api/'):
                return jsonify(error='Session expired. Please refresh the page.'), 400
            flash('Your session expired. Please try again.', 'warning')
            return redirect(request.referrer or url_for('login'))


@app.errorhandler(413)
def too_large(_e):
    if request.path.startswith('/api/'):
        return jsonify(error='That upload is too large.'), 413
    flash(f'Upload too large. Files can be up to {config.MAX_UPLOAD_MB} MB each.', 'danger')
    return redirect(url_for('query'))


@app.context_processor
def inject_globals():
    data = {'csrf_token': _csrf_token}
    if 'user_id' in session:
        docs = database.query_db(
            '''SELECT d.*, (SELECT COUNT(*) FROM DOCUMENT_SECTION s
                            WHERE s.document_id = d.document_id) AS section_count
               FROM DOCUMENT d WHERE d.user_id = ? ORDER BY d.document_id DESC''',
            (session['user_id'],)
        )
        recent_queries = database.query_db(
            'SELECT query_id, query_text FROM QUERY WHERE user_id = ? '
            'ORDER BY query_id DESC LIMIT 15',
            (session['user_id'],)
        )
        data.update(sidebar_docs=docs, sidebar_queries=recent_queries,
                    human_size=_human_size)
    return data


# ── Auth ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('query'))
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', password)

        error = None
        if not username or not email or not password:
            error = 'All fields are required.'
        elif not USERNAME_RE.match(username):
            error = 'Username must be 3-30 characters: letters, numbers, dot, dash or underscore.'
        elif not EMAIL_RE.match(email):
            error = 'Please enter a valid email address.'
        elif len(password) < config.MIN_PASSWORD_LENGTH:
            error = f'Password must be at least {config.MIN_PASSWORD_LENGTH} characters.'
        elif password != confirm:
            error = 'The two passwords do not match.'
        else:
            existing = database.query_db(
                'SELECT user_id FROM USER WHERE lower(username) = lower(?) OR lower(email) = ?',
                (username, email), one=True)
            if existing:
                error = 'Username or email already exists.'

        if error:
            flash(error, 'danger')
            return render_template('register.html', form=request.form), 400

        database.insert_db(
            'INSERT INTO USER (username, email, password) VALUES (?, ?, ?)',
            (username, email, generate_password_hash(password))
        )
        flash('Registration successful! Please sign in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html', form={})


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        key = username.lower()

        fails, locked_until = _login_failures.get(key, (0, 0))
        if locked_until > time.time():
            wait = int(locked_until - time.time()) + 1
            flash(f'Too many attempts. Try again in {wait} seconds.', 'danger')
            return render_template('login.html'), 429

        user = database.query_db(
            'SELECT * FROM USER WHERE lower(username) = lower(?)', (username,), one=True)
        if user and _verify_password(user, password):
            _login_failures.pop(key, None)
            session.clear()
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['email'] = user['email']
            return redirect(url_for('query'))

        fails += 1
        _login_failures[key] = (fails, time.time() + LOCKOUT_SECONDS
                                if fails >= MAX_FAILED_LOGINS else 0)
        flash('Invalid username or password.', 'danger')
        return render_template('login.html'), 401

    return render_template('login.html')


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    flash('You have been signed out.', 'info')
    return redirect(url_for('login'))


# ── Documents ─────────────────────────────────────────────────────────────

def _ingest_file(file_storage, user_id):
    """Save, parse and index one upload. Returns (doc_id, section_count)."""
    original = secure_filename(file_storage.filename) or 'document'
    if not allowed_file(original):
        raise ValueError(f'"{file_storage.filename}": unsupported file type.')

    ext = original.rsplit('.', 1)[1].lower()
    stored_name = f'{uuid.uuid4().hex}.{ext}'
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], stored_name)
    file_storage.save(filepath)

    try:
        size = os.path.getsize(filepath)
        if size > config.MAX_UPLOAD_MB * 1024 * 1024:
            raise ValueError(f'"{original}" is larger than {config.MAX_UPLOAD_MB} MB.')
        if size == 0:
            raise ValueError(f'"{original}" is empty.')

        try:
            page_count, chunks = document_processor.extract_chunks(filepath, ext)
        except ValueError:
            raise
        except Exception:
            raise ValueError(f'"{original}" could not be read. It may be corrupted or password-protected.')
        if not chunks:
            raise ValueError(f'No readable text found in "{original}". Scanned PDFs need OCR.')

        # Keep display names unique per user: "notes.pdf", "notes (2).pdf", ...
        taken = {r['document_name'] for r in database.query_db(
            'SELECT document_name FROM DOCUMENT WHERE user_id = ?', (user_id,))}
        display, stem, n = original, original.rsplit('.', 1)[0], 2
        while display in taken:
            display = f'{stem} ({n}).{ext}'
            n += 1

        blobs = retrieval.embed_many_to_blobs([c for _, c in chunks])

        conn = database.get_db()
        try:
            cur = conn.execute(
                'INSERT INTO DOCUMENT (user_id, document_name, upload_date, file_type, '
                'stored_name, size_bytes, page_count) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (user_id, display, datetime.now().strftime('%Y-%m-%d'), ext,
                 stored_name, size, page_count))
            doc_id = cur.lastrowid
            conn.executemany(
                'INSERT INTO DOCUMENT_SECTION (document_id, section_text, embedding, page_number) '
                'VALUES (?, ?, ?, ?)',
                [(doc_id, text, blob, page) for (page, text), blob in zip(chunks, blobs)])
            conn.commit()
        finally:
            conn.close()
        return doc_id, display, len(chunks)
    except Exception:
        if os.path.exists(filepath):
            os.remove(filepath)
        raise


@app.route('/upload', methods=['POST'])
@login_required
def upload():
    files = [f for f in request.files.getlist('files') + request.files.getlist('file')
             if f and f.filename]
    if not files:
        flash('No file selected.', 'danger')
        return redirect(url_for('query'))

    last_id, ok = None, 0
    for f in files:
        try:
            last_id, display, sections = _ingest_file(f, session['user_id'])
            ok += 1
            flash(f'"{display}" added ({sections} sections).', 'success')
        except ValueError as exc:
            flash(str(exc), 'danger')
        except Exception:
            app.logger.exception('Upload failed for %s', f.filename)
            flash(f'Something went wrong while processing "{f.filename}".', 'danger')

    if ok:
        return redirect(url_for('query', just_uploaded=last_id))
    return redirect(url_for('query'))


@app.route('/document/<int:document_id>/file')
@login_required
def document_file(document_id):
    doc = database.query_db(
        'SELECT * FROM DOCUMENT WHERE document_id = ? AND user_id = ?',
        (document_id, session['user_id']), one=True)
    if not doc:
        abort(404)
    path = _stored_path(doc)
    if not os.path.exists(path):
        abort(404)
    return send_from_directory(os.path.dirname(path), os.path.basename(path),
                               download_name=doc['document_name'],
                               as_attachment=request.args.get('download') == '1')


@app.route('/document/<int:document_id>/delete', methods=['POST'])
@login_required
def delete_document(document_id):
    doc = database.query_db(
        'SELECT * FROM DOCUMENT WHERE document_id = ? AND user_id = ?',
        (document_id, session['user_id']), one=True)
    if not doc:
        flash('Document not found.', 'danger')
        return redirect(url_for('query'))

    conn = database.get_db()
    try:
        affected = [r['query_id'] for r in conn.execute(
            '''SELECT DISTINCT rr.query_id FROM RETRIEVAL_RESULT rr
               JOIN DOCUMENT_SECTION ds ON ds.section_id = rr.section_id
               WHERE ds.document_id = ?''', (document_id,)).fetchall()]
        conn.execute(
            '''DELETE FROM RETRIEVAL_RESULT WHERE section_id IN
               (SELECT section_id FROM DOCUMENT_SECTION WHERE document_id = ?)''',
            (document_id,))
        for qid in affected:
            if not conn.execute('SELECT 1 FROM RETRIEVAL_RESULT WHERE query_id = ? LIMIT 1',
                                (qid,)).fetchone():
                conn.execute('DELETE FROM ANSWER WHERE query_id = ?', (qid,))
                conn.execute('DELETE FROM QUERY WHERE query_id = ?', (qid,))
        conn.execute('DELETE FROM DOCUMENT_SECTION WHERE document_id = ?', (document_id,))
        conn.execute('DELETE FROM DOCUMENT WHERE document_id = ? AND user_id = ?',
                     (document_id, session['user_id']))
        conn.commit()
    finally:
        conn.close()

    path = _stored_path(doc)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass

    flash(f'"{doc["document_name"]}" deleted.', 'success')
    return redirect(url_for('query'))


# ── History ───────────────────────────────────────────────────────────────

@app.route('/query/<int:query_id>/delete', methods=['POST'])
@login_required
def delete_query(query_id):
    if not database.query_db('SELECT 1 FROM QUERY WHERE query_id = ? AND user_id = ?',
                             (query_id, session['user_id']), one=True):
        flash('Question not found.', 'danger')
        return redirect(url_for('query'))
    conn = database.get_db()
    try:
        conn.execute('DELETE FROM RETRIEVAL_RESULT WHERE query_id = ?', (query_id,))
        conn.execute('DELETE FROM ANSWER WHERE query_id = ?', (query_id,))
        conn.execute('DELETE FROM QUERY WHERE query_id = ?', (query_id,))
        conn.commit()
    finally:
        conn.close()
    flash('Question deleted.', 'success')
    return redirect(url_for('query'))


@app.route('/clear-history', methods=['POST'])
@login_required
def clear_history():
    uid = session['user_id']
    conn = database.get_db()
    try:
        sub = '(SELECT query_id FROM QUERY WHERE user_id = ?)'
        conn.execute(f'DELETE FROM RETRIEVAL_RESULT WHERE query_id IN {sub}', (uid,))
        conn.execute(f'DELETE FROM ANSWER WHERE query_id IN {sub}', (uid,))
        conn.execute('DELETE FROM QUERY WHERE user_id = ?', (uid,))
        conn.commit()
    finally:
        conn.close()
    flash('Chat history cleared.', 'success')
    return redirect(url_for('query'))


def _load_history(user_id, limit=HISTORY_LIMIT, only_query_id=None):
    """Questions with their answers and top sources, oldest first."""
    sql = '''SELECT q.query_id, q.query_text, q.created_at, q.query_date,
                    a.answer_text, a.confidence, a.rating
             FROM QUERY q LEFT JOIN ANSWER a ON a.query_id = q.query_id
             WHERE q.user_id = ?'''
    args = [user_id]
    if only_query_id:
        sql += ' AND q.query_id = ?'
        args.append(only_query_id)
    sql += ' ORDER BY q.query_id DESC LIMIT ?'
    args.append(limit)
    rows = list(reversed(database.query_db(sql, tuple(args))))
    if not rows:
        return []

    ids = [r['query_id'] for r in rows]
    src_rows = database.query_db(
        f'''SELECT rr.query_id, rr.similarity_score, ds.section_text, ds.page_number,
                   d.document_id, d.document_name, d.file_type
            FROM RETRIEVAL_RESULT rr
            JOIN DOCUMENT_SECTION ds ON ds.section_id = rr.section_id
            JOIN DOCUMENT d ON d.document_id = ds.document_id
            WHERE rr.query_id IN ({','.join('?' * len(ids))})
            ORDER BY rr.similarity_score DESC''', tuple(ids))
    by_query = {}
    for r in src_rows:
        by_query.setdefault(r['query_id'], []).append(r)

    return [_serialize(r, by_query.get(r['query_id'], [])) for r in rows]


def _serialize(row, source_rows):
    sources = []
    for s in source_rows[:3]:
        text = retrieval._clean_text(s['section_text'])
        sources.append({
            'document_id': s['document_id'],
            'document_name': s['document_name'],
            'file_type': s['file_type'],
            'page': s['page_number'],
            'excerpt': text if len(text) <= 520 else text[:520].rsplit(' ', 1)[0] + '…',
            'match': max(0, min(100, round(s['similarity_score'] * 100))),
        })

    pages_by_doc = {}
    for s in source_rows:
        entry = pages_by_doc.setdefault(s['document_id'], {
            'document_id': s['document_id'], 'document_name': s['document_name'],
            'file_type': s['file_type'], 'pages': set()})
        if s['page_number'] is not None:
            entry['pages'].add(s['page_number'])
    docs = []
    for e in pages_by_doc.values():
        pages = sorted(e['pages'])
        docs.append({'document_id': e['document_id'], 'document_name': e['document_name'],
                     'file_type': e['file_type'], 'pages_label': _format_page_label(pages)})

    conf = row['confidence']
    return {
        'query_id': row['query_id'],
        'query_text': row['query_text'],
        'answer_text': row['answer_text'] or 'No answer could be generated.',
        'confidence': None if conf is None else round(conf * 100),
        'confidence_label': _confidence_label(conf),
        'rating': row['rating'] or 0,
        'created': row['created_at'] or row['query_date'],
        'sources': sources,
        'source_docs': docs,
        'not_found': (row['answer_text'] or '') == retrieval.NOT_FOUND_MSG,
    }


@app.route('/query')
@login_required
def query():
    history = _load_history(session['user_id'])
    return render_template('query.html', history=history)


@app.route('/answer/<int:query_id>')
@login_required
def answer(query_id):
    return redirect(url_for('query') + f'#q-{query_id}')


# ── Asking questions (JSON API used by the chat page) ─────────────────────

def _owned_document_ids(raw):
    if isinstance(raw, str):
        raw = [x for x in raw.split(',')]
    requested = [int(x) for x in (raw or []) if str(x).strip().isdigit()]
    if not requested:
        return None
    owned = database.query_db(
        'SELECT document_id FROM DOCUMENT WHERE user_id = ? AND document_id IN (%s)'
        % ','.join('?' * len(requested)), (session['user_id'], *requested))
    return [r['document_id'] for r in owned] or None


@app.route('/api/ask', methods=['POST'])
@login_required
def api_ask():
    payload = request.get_json(silent=True) or {}
    text = (payload.get('query_text') or '').strip()
    if not text:
        return jsonify(error='Please type a question.'), 400
    if len(text) > MAX_QUERY_CHARS:
        return jsonify(error=f'Questions are limited to {MAX_QUERY_CHARS} characters.'), 400

    uid = session['user_id']
    if not database.query_db('SELECT 1 FROM DOCUMENT WHERE user_id = ? LIMIT 1', (uid,), one=True):
        return jsonify(error='Upload a document first, then ask your question.'), 400

    document_ids = _owned_document_ids(payload.get('document_ids'))

    sections = retrieval.get_relevant_sections(text, document_ids=document_ids, user_id=uid)
    result = retrieval.generate_answer(text, sections)

    now = datetime.now()
    conn = database.get_db()
    try:
        cur = conn.execute(
            'INSERT INTO QUERY (user_id, query_text, query_date, created_at) VALUES (?, ?, ?, ?)',
            (uid, text, now.strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d %H:%M')))
        qid = cur.lastrowid
        conn.executemany(
            'INSERT INTO RETRIEVAL_RESULT (query_id, section_id, similarity_score) VALUES (?, ?, ?)',
            [(qid, s['section_id'], s['score']) for s in sections])
        conn.execute('INSERT INTO ANSWER (query_id, answer_text, confidence) VALUES (?, ?, ?)',
                     (qid, result['answer'], result.get('confidence', 0.0)))
        conn.commit()
    finally:
        conn.close()

    item = _load_history(uid, limit=1, only_query_id=qid)[0]
    return jsonify(item)


@app.route('/api/answer/<int:query_id>/rating', methods=['POST'])
@login_required
def api_rate(query_id):
    payload = request.get_json(silent=True) or {}
    rating = payload.get('rating')
    if rating not in (-1, 0, 1):
        return jsonify(error='Invalid rating.'), 400
    changed = database.execute_db(
        '''UPDATE ANSWER SET rating = ? WHERE query_id = ? AND query_id IN
           (SELECT query_id FROM QUERY WHERE user_id = ?)''',
        (rating, query_id, session['user_id']))
    if not changed:
        return jsonify(error='Not found.'), 404
    return jsonify(ok=True, rating=rating)


@app.route('/export')
@login_required
def export_history():
    items = _load_history(session['user_id'], limit=1000)
    lines = ['# Smart Document Query - Q&A export', '',
             f'Exported {datetime.now():%Y-%m-%d %H:%M} for {session["username"]}', '']
    for it in items:
        lines += [f'## {it["query_text"]}', '', it['answer_text'], '']
        if it['source_docs']:
            srcs = ', '.join(d['document_name'] + (f' ({d["pages_label"]})' if d['pages_label'] else '')
                             for d in it['source_docs'][:3])
            lines += [f'*Sources: {srcs}*', '']
        if it['confidence'] is not None:
            lines += [f'*Confidence: {it["confidence"]}%*', '']
    return Response('\n'.join(lines), mimetype='text/markdown',
                    headers={'Content-Disposition': 'attachment; filename=qa-export.md'})


if __name__ == '__main__':
    app.run(debug=config.DEBUG, port=config.PORT)
