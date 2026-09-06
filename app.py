import os
from datetime import datetime
from functools import wraps

from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash)
from werkzeug.utils import secure_filename

import config
import database
import document_processor
import retrieval

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER

os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
database.init_db()
retrieval.initialize_models()


@app.context_processor
def inject_sidebar_data():
    if 'user_id' in session:
        docs = database.query_db(
            'SELECT * FROM DOCUMENT WHERE user_id = ? ORDER BY upload_date DESC',
            (session['user_id'],)
        )
        recent_queries = database.query_db(
            'SELECT query_id, query_text FROM QUERY WHERE user_id = ? ORDER BY query_id DESC LIMIT 10',
            (session['user_id'],)
        )
        return {'sidebar_docs': docs, 'sidebar_queries': recent_queries}
    return {}


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


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('query'))
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email    = request.form['email'].strip()
        password = request.form['password'].strip()

        if not username or not email or not password:
            flash('All fields are required.', 'danger')
            return render_template('register.html')

        existing = database.query_db(
            'SELECT user_id FROM USER WHERE username = ? OR email = ?',
            (username, email), one=True
        )
        if existing:
            flash('Username or email already exists.', 'danger')
            return render_template('register.html')

        database.insert_db(
            'INSERT INTO USER (username, email, password) VALUES (?, ?, ?)',
            (username, email, password)
        )
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()

        user = database.query_db(
            'SELECT * FROM USER WHERE username = ? AND password = ?',
            (username, password), one=True
        )
        if user:
            session['user_id']  = user['user_id']
            session['username'] = user['username']
            session['email']    = user['email']
            return redirect(url_for('query'))

        flash('Invalid username or password.', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/upload', methods=['POST'])
@login_required
def upload():
    if 'file' not in request.files:
        flash('No file part in the request.', 'danger')
        return redirect(url_for('query'))

    file = request.files['file']
    if file.filename == '':
        flash('No file selected.', 'danger')
        return redirect(url_for('query'))

    if not allowed_file(file.filename):
        flash('Only PDF and TXT files are allowed.', 'danger')
        return redirect(url_for('query'))

    filename = secure_filename(file.filename)
    file_type = filename.rsplit('.', 1)[1].lower()
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    doc_id = database.insert_db(
        'INSERT INTO DOCUMENT (user_id, document_name, upload_date, file_type) VALUES (?, ?, ?, ?)',
        (session['user_id'], filename, datetime.now().strftime('%Y-%m-%d'), file_type)
    )

    if file_type == 'pdf':
        pages = document_processor.extract_pages_from_pdf(filepath)
        page_chunks = document_processor.chunk_pages(pages)
    else:
        txt = document_processor.extract_text_from_txt(filepath)
        page_chunks = [(None, c) for c in document_processor.chunk_text(txt)]

    if not page_chunks:
        flash('Could not extract text from the file.', 'danger')
        return redirect(url_for('query'))

    for page_num, chunk in page_chunks:
        embedding_blob = retrieval.embed_to_blob(chunk)
        database.insert_db(
            'INSERT INTO DOCUMENT_SECTION (document_id, section_text, embedding, page_number) VALUES (?, ?, ?, ?)',
            (doc_id, chunk, embedding_blob, page_num)
        )

    flash(f'"{filename}" uploaded and processed successfully ({len(page_chunks)} sections).', 'success')
    return redirect(url_for('query', just_uploaded=doc_id))


@app.route('/document/<int:document_id>/delete', methods=['POST'])
@login_required
def delete_document(document_id):
    doc = database.query_db(
        'SELECT * FROM DOCUMENT WHERE document_id = ? AND user_id = ?',
        (document_id, session['user_id']), one=True
    )
    if not doc:
        flash('Document not found.', 'danger')
        return redirect(url_for('query'))

    conn = database.get_db()
    try:
        affected_query_ids = [row['query_id'] for row in conn.execute(
            '''SELECT DISTINCT rr.query_id
               FROM RETRIEVAL_RESULT rr
               JOIN DOCUMENT_SECTION ds ON ds.section_id = rr.section_id
               WHERE ds.document_id = ?''',
            (document_id,)
        ).fetchall()]

        conn.execute(
            '''DELETE FROM RETRIEVAL_RESULT
               WHERE section_id IN (
                   SELECT section_id FROM DOCUMENT_SECTION WHERE document_id = ?
               )''',
            (document_id,)
        )

        for qid in affected_query_ids:
            still_has_results = conn.execute(
                'SELECT 1 FROM RETRIEVAL_RESULT WHERE query_id = ? LIMIT 1', (qid,)
            ).fetchone()
            if not still_has_results:
                conn.execute('DELETE FROM ANSWER WHERE query_id = ?', (qid,))
                conn.execute('DELETE FROM QUERY WHERE query_id = ?', (qid,))

        conn.execute('DELETE FROM DOCUMENT_SECTION WHERE document_id = ?', (document_id,))
        conn.execute(
            'DELETE FROM DOCUMENT WHERE document_id = ? AND user_id = ?',
            (document_id, session['user_id'])
        )
        conn.commit()
    finally:
        conn.close()

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], doc['document_name'])
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except OSError:
            pass

    flash(f'"{doc["document_name"]}" deleted.', 'success')
    return redirect(url_for('query'))


@app.route('/query/<int:query_id>/delete', methods=['POST'])
@login_required
def delete_query(query_id):
    owned = database.query_db(
        'SELECT query_id FROM QUERY WHERE query_id = ? AND user_id = ?',
        (query_id, session['user_id']), one=True
    )
    if not owned:
        flash('Query not found.', 'danger')
        return redirect(url_for('query'))

    conn = database.get_db()
    try:
        conn.execute('DELETE FROM RETRIEVAL_RESULT WHERE query_id = ?', (query_id,))
        conn.execute('DELETE FROM ANSWER WHERE query_id = ?', (query_id,))
        conn.execute('DELETE FROM QUERY WHERE query_id = ?', (query_id,))
        conn.commit()
    finally:
        conn.close()

    flash('Query deleted.', 'success')
    return redirect(url_for('query'))


@app.route('/clear-history', methods=['POST'])
@login_required
def clear_history():
    conn = database.get_db()
    try:
        conn.execute(
            '''DELETE FROM RETRIEVAL_RESULT WHERE query_id IN
               (SELECT query_id FROM QUERY WHERE user_id = ?)''',
            (session['user_id'],)
        )
        conn.execute(
            '''DELETE FROM ANSWER WHERE query_id IN
               (SELECT query_id FROM QUERY WHERE user_id = ?)''',
            (session['user_id'],)
        )
        conn.execute('DELETE FROM QUERY WHERE user_id = ?', (session['user_id'],))
        conn.commit()
    finally:
        conn.close()
    session.pop('last_context', None)
    flash('Chat history cleared.', 'success')
    return redirect(url_for('query'))


@app.route('/query', methods=['GET', 'POST'])
@login_required
def query():
    if request.method == 'POST':
        query_text = request.form['query_text'].strip()
        if not query_text:
            flash('Please enter a question.', 'danger')
            return render_template('query.html')

        raw_ids = request.form.get('document_ids', '').strip()
        document_ids = None
        if raw_ids:
            requested = [int(x) for x in raw_ids.split(',') if x.strip().isdigit()]
            if requested:
                placeholders = ','.join('?' * len(requested))
                owned = database.query_db(
                    f'SELECT document_id FROM DOCUMENT WHERE user_id = ? AND document_id IN ({placeholders})',
                    (session['user_id'], *requested)
                )
                document_ids = [row['document_id'] for row in owned] or None

        query_id = database.insert_db(
            'INSERT INTO QUERY (user_id, query_text, query_date) VALUES (?, ?, ?)',
            (session['user_id'], query_text, datetime.now().strftime('%Y-%m-%d'))
        )

        sections = retrieval.get_relevant_sections(query_text, document_ids=document_ids)

        for sec in sections:
            database.insert_db(
                'INSERT INTO RETRIEVAL_RESULT (query_id, section_id, similarity_score) VALUES (?, ?, ?)',
                (query_id, sec['section_id'], sec['score'])
            )

        result = retrieval.generate_answer(query_text, sections)
        answer_text = result['answer']
        context_text = result.get('context', '')

        database.insert_db(
            'INSERT INTO ANSWER (query_id, answer_text) VALUES (?, ?)',
            (query_id, answer_text)
        )

        session['last_context'] = context_text

        return redirect(url_for('answer', query_id=query_id))

    return render_template('query.html')


@app.route('/answer/<int:query_id>')
@login_required
def answer(query_id):
    query_row = database.query_db(
        'SELECT * FROM QUERY WHERE query_id = ? AND user_id = ?',
        (query_id, session['user_id']), one=True
    )
    if not query_row:
        flash('Query not found.', 'danger')
        return redirect(url_for('query'))

    answer_row = database.query_db(
        'SELECT * FROM ANSWER WHERE query_id = ?', (query_id,), one=True
    )

    context = session.pop('last_context', '')

    chat_history = database.query_db(
        '''SELECT q.query_id, q.query_text, a.answer_text
           FROM QUERY q LEFT JOIN ANSWER a ON q.query_id = a.query_id
           WHERE q.user_id = ? AND q.query_id <= ?
           ORDER BY q.query_id DESC LIMIT 5''',
        (session['user_id'], query_id)
    )
    chat_history = list(reversed(chat_history))

    enriched_history = []
    for item in chat_history:
        rows = database.query_db(
            '''SELECT d.document_id, d.document_name, d.file_type, ds.page_number
               FROM RETRIEVAL_RESULT rr
               JOIN DOCUMENT_SECTION ds ON rr.section_id = ds.section_id
               JOIN DOCUMENT d ON ds.document_id = d.document_id
               WHERE rr.query_id = ?''',
            (item['query_id'],)
        )
        by_doc = {}
        for r in rows:
            entry = by_doc.setdefault(r['document_id'], {
                'document_name': r['document_name'],
                'file_type': r['file_type'],
                'pages': set(),
            })
            if r['page_number'] is not None:
                entry['pages'].add(r['page_number'])
        source_docs = []
        for entry in by_doc.values():
            pages = sorted(entry['pages'])
            source_docs.append({
                'document_name': entry['document_name'],
                'file_type': entry['file_type'],
                'pages': pages,
                'pages_label': _format_page_label(pages),
            })
        enriched_history.append({
            'query_id': item['query_id'],
            'query_text': item['query_text'],
            'answer_text': item['answer_text'],
            'source_docs': source_docs
        })

    return render_template('answer.html',
                           query=query_row,
                           answer=answer_row,
                           context=context,
                           chat_history=enriched_history)


if __name__ == '__main__':
    app.run(debug=True, port=5001)
