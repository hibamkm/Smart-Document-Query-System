import PyPDF2
import re


def _clean_text(text):
    if not text:
        return ''

    text = text.replace('\ufffd', '')
    text = re.sub(r'[▯□●▪▸❖❑✓✗\u2022\u2023\u2043\uf0a7\uf0b7\uf0a8\uf0fc\uf0a4\uf0d8]', '• ', text)
    text = re.sub(r'(?m)^\s*\d{1,3}\s*$', '', text)
    text = re.sub(r'\s*\([AB]\)\s*', ' ', text)

    # Fix broken words
    broken_word_fixes = {
        r'\bat t he\b': 'at the',
        r'\balg orithm\b': 'algorithm',
        r'\be -mail\b': 'email',
        r'\bradix -64\b': 'radix-64',
        r'\bkey -exchange\b': 'key-exchange',
        r'\bPhase -1\b': 'Phase-1',
        r'\bPhase -2\b': 'Phase-2',
        r'\bChange -cipher\b': 'Change-cipher',
        r'\bnon -threatening\b': 'non-threatening',
        r'\bmalici ous\b': 'malicious',
    }
    for pattern, replacement in broken_word_fixes.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    text = re.sub(
        r'\b(soft|hard|fire|net|data|mal|cyber)\s+(ware|wall|work|base|icious|security)\b',
        r'\1\2', text, flags=re.IGNORECASE
    )
    text = re.sub(r'(\w)\s+-\s+(\w)', r'\1-\2', text)
    text = re.sub(r'(\w)\s+-(\w)', r'\1-\2', text)
    text = re.sub(r'(\w)-\s+(\w)', r'\1-\2', text)
    text = re.sub(r' {2,}', ' ', text)
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)

    return text.strip()


def extract_text_from_pdf(filepath):
    pages = extract_pages_from_pdf(filepath)
    return _clean_text('\n'.join(pt for _, pt in pages))


def extract_pages_from_pdf(filepath):
    pages = []
    with open(filepath, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        for i, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ''
            cleaned = _clean_text(page_text)
            if cleaned.strip():
                pages.append((i, cleaned))
    return pages


def extract_text_from_txt(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        return _clean_text(f.read())


def extract_text_from_docx(filepath):
    """Paragraphs and table cells of a .docx file, in reading order."""
    import docx  # imported lazily so the app still starts without python-docx
    document = docx.Document(filepath)
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        rows = [[c.text.strip() for c in row.cells] for row in table.rows]
        if not rows:
            continue
        header = rows[0]
        for row in rows[1:] if len(rows) > 1 else rows:
            # "Waterfall. Use: Fixed requirements." reads better to the search
            # than a bare "Waterfall | Fixed requirements" row.
            pairs = [f'{h}: {c}' if h and len(rows) > 1 and i else c
                     for i, (h, c) in enumerate(zip(header, row)) if c]
            if pairs:
                parts.append('. '.join(pairs) + '.')
    return _clean_text('\n'.join(parts))


def _mark_headings(text):
    """End short unpunctuated lines (headings) with a full stop.

    Plain-text and Word files put each paragraph on its own line, so a heading
    would otherwise be glued onto the first sentence that follows it.
    """
    out = []
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped and stripped[-1] not in '.!?:;' and len(stripped.split()) <= 12:
            stripped += '.'
        out.append(stripped)
    return '\n'.join(out)


def extract_chunks(filepath, file_type):
    """Return ``(page_count, [(page_number_or_None, chunk_text), ...])``."""
    if file_type == 'pdf':
        pages = extract_pages_from_pdf(filepath)
        return count_pdf_pages(filepath), chunk_pages(pages)
    if file_type == 'docx':
        text = extract_text_from_docx(filepath)
    else:  # txt / md
        text = extract_text_from_txt(filepath)
        if file_type == 'md':
            text = _strip_markdown(text)
    return 0, [(None, c) for c in chunk_text(_mark_headings(text))]


def count_pdf_pages(filepath):
    try:
        with open(filepath, 'rb') as f:
            return len(PyPDF2.PdfReader(f).pages)
    except Exception:
        return 0


def _strip_markdown(text):
    text = re.sub(r'```.*?```', ' ', text, flags=re.DOTALL)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'(?m)^\s{0,3}#{1,6}\s*', '', text)
    text = re.sub(r'(\*\*|__)(.*?)\1', r'\2', text)
    return text


def _split_sentences(text):
    # Don't break after list numbers such as "1." or "12." - otherwise short
    # items of an inline numbered list are split apart and dropped.
    raw = re.split(r'(?<=[.?!])(?<!\b\d\.)(?<!\b\d\d\.)\s+', text.replace('\n', ' '))
    return [s.strip() for s in raw if len(s.strip()) > 10]


def chunk_text(text):
    sentences = _split_sentences(text)
    if not sentences:
        return []

    chunks = []
    chunk_size = 150
    overlap = 50
    current_chunk = []
    current_words = 0

    for sentence in sentences:
        word_count = len(sentence.split())

        if current_words + word_count > chunk_size and current_chunk:
            chunk_text_str = ' '.join(current_chunk)
            chunks.append(chunk_text_str.strip())

            overlap_sentences = []
            overlap_words = 0
            for s in reversed(current_chunk):
                s_words = len(s.split())
                if overlap_words + s_words <= overlap:
                    overlap_sentences.insert(0, s)
                    overlap_words += s_words
                else:
                    break

            current_chunk = overlap_sentences
            current_words = overlap_words

        current_chunk.append(sentence)
        current_words += word_count

    if current_chunk:
        chunk_text_str = ' '.join(current_chunk)
        if chunk_text_str.strip():
            chunks.append(chunk_text_str.strip())

    return chunks


def chunk_pages(pages):
    out = []
    for page_num, page_text in pages:
        for chunk in chunk_text(page_text):
            out.append((page_num, chunk))
    return out
