import os
# Enable offline mode BEFORE importing HuggingFace libraries
# This prevents checking huggingface.co when models are cached
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_DATASETS_OFFLINE'] = '1'

import re
import pickle
import numpy as np
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModelForQuestionAnswering
import torch
import database

embedding_model = None
_qa_tokenizer = None
_qa_model = None
_qa_model_name = 'distilbert-base-cased-distilled-squad'


def initialize_models():
    global embedding_model, _qa_tokenizer, _qa_model

    if embedding_model is not None and _qa_tokenizer is not None:
        return

    # Check if models are cached (for true offline mode)
    cache_dir = os.path.expanduser('~/.cache/huggingface/hub')
    models_cached = os.path.exists(cache_dir) and len(os.listdir(cache_dir)) > 0

    try:
        print("Initializing AI models...")

        if embedding_model is None:
            if models_cached:
                print("  → Loading sentence transformer model from cache...")
            else:
                print("  → Loading sentence transformer model (first run: ~80MB download)...")

            # SentenceTransformer will automatically use cache if available
            embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

            print("  ✓ Sentence transformer ready")

        if _qa_tokenizer is None:
            if models_cached:
                print("  → Loading question answering model from cache...")
            else:
                print("  → Loading question answering model (first run: ~250MB download)...")

            # Try offline first if cached, otherwise allow download
            try:
                _qa_tokenizer = AutoTokenizer.from_pretrained(_qa_model_name, local_files_only=True)
                _qa_model = AutoModelForQuestionAnswering.from_pretrained(_qa_model_name, local_files_only=True)
            except Exception:
                # First run - need to download
                _qa_tokenizer = AutoTokenizer.from_pretrained(_qa_model_name)
                _qa_model = AutoModelForQuestionAnswering.from_pretrained(_qa_model_name)

            print("  ✓ Question answering model ready")

        print("✓ All models initialized and cached for offline use\n")

    except Exception as e:
        error_msg = str(e)
        if 'Connection' in error_msg or 'timeout' in error_msg.lower() or 'network' in error_msg.lower() or 'offline' in error_msg.lower():
            print("\n" + "="*70)
            print("ERROR: Cannot download models - Internet connection required")
            print("="*70)
            print("\nThis application requires AI models (~330MB total) that need to be")
            print("downloaded from HuggingFace on first run. After the first successful")
            print("run, the models are cached locally and the app works offline.")
            print("\nPlease connect to the internet and restart the application.")
            print("="*70 + "\n")
            raise SystemExit(1)
        else:
            print(f"\nERROR initializing models: {error_msg}")
            raise


def _extract_answer(question, context):
    inputs = _qa_tokenizer(question, context, return_tensors='pt',
                           truncation='only_second', max_length=512)

    with torch.no_grad():
        outputs = _qa_model(**inputs)

    # Only allow answer spans that lie inside the context, never the question.
    seq_ids = inputs.sequence_ids(0)
    ctx_mask = torch.tensor([sid == 1 for sid in seq_ids])
    neg_inf = torch.finfo(outputs.start_logits.dtype).min
    start_logits = outputs.start_logits[0].masked_fill(~ctx_mask, neg_inf)
    end_logits = outputs.end_logits[0].masked_fill(~ctx_mask, neg_inf)

    start_idx = int(torch.argmax(start_logits))
    end_idx = int(torch.argmax(end_logits))
    if end_idx < start_idx:
        end_idx = start_idx

    start_prob = float(torch.softmax(start_logits, dim=0)[start_idx])
    end_prob = float(torch.softmax(end_logits, dim=0)[end_idx])
    confidence = max(0.0, min(1.0, (start_prob * end_prob) ** 0.5))

    input_ids = inputs['input_ids'][0]
    answer = _qa_tokenizer.decode(input_ids[start_idx:end_idx + 1],
                                  skip_special_tokens=True).strip()

    if answer and len(answer) < 60:
        expanded = _expand_to_sentence(answer, context)
        if expanded and len(expanded) > len(answer):
            answer = expanded

    return answer, confidence


def _expand_to_sentence(answer_fragment, context):
    if not answer_fragment or not context:
        return answer_fragment

    lower_ctx = context.lower()
    lower_frag = answer_fragment.lower()
    pos = lower_ctx.find(lower_frag)
    if pos == -1:
        return answer_fragment

    start = pos
    while start > 0:
        prev = context[start - 1]
        if prev in '.!?\n' and (start == len(context) or context[start] == ' ' or start < pos):
            break
        start -= 1

    while start < len(context) and context[start] in ' \t\n':
        start += 1

    end = pos + len(answer_fragment)
    while end < len(context):
        ch = context[end]
        if ch in '.!?':
            end += 1
            break
        end += 1

    sentence = context[start:end].strip()
    return sentence if sentence else answer_fragment

NOT_FOUND_MSG = 'The uploaded documents do not contain enough information to answer this question.'


def embed_to_blob(text):
    initialize_models()
    vector = embedding_model.encode(text)
    return np.asarray(vector, dtype=np.float32).tobytes()


def embed_many_to_blobs(texts, batch_size=32):
    """Embed many chunks at once - much faster than one call per chunk."""
    initialize_models()
    if not texts:
        return []
    vectors = embedding_model.encode(texts, batch_size=batch_size,
                                     show_progress_bar=False)
    return [np.asarray(v, dtype=np.float32).tobytes() for v in vectors]


def blob_to_array(blob):
    # Older databases stored pickled arrays; new ones store raw float32 bytes.
    if blob[:1] == b'\x80':
        return np.asarray(pickle.loads(blob), dtype=np.float32)
    return np.frombuffer(blob, dtype=np.float32)


_DEFINITION_QUERY_PATTERN = re.compile(
    r'^\s*(what\s+is|what\s+are|what\s+does|define|meaning\s+of|definition\s+of)\b',
    re.IGNORECASE
)
_DEFINITION_PHRASE_PATTERN = re.compile(
    r'\b(stands?\s+for|means?|refers?\s+to|definition\s+of|meaning\s+of)\b',
    re.IGNORECASE
)


def _is_definition_query(query_text):
    if not query_text:
        return False
    if _DEFINITION_QUERY_PATTERN.match(query_text):
        return True
    return bool(_DEFINITION_PHRASE_PATTERN.search(query_text))


_DEFINITION_VERB_PATTERNS = [
    r'stands?\s+for',
    r'refers?\s+to',
    r'can\s+be\s+defined\s+as',
    r'means?',
    r'is\s+a\b|is\s+an\b|is\s+the\b|is\s+defined',
    r'are\s+a\b|are\s+the\b|are\s+defined',
    r'is|are',
]


def _find_definition_sentence(section_text, key_term):
    if not section_text or not key_term:
        return None, None
    term = re.escape(key_term)

    colon_re = re.compile(
        rf'(?:^|(?<=[\s\-–—.!?(]))\b{term}\b\s*:\s*([^\n.!?]{{5,250}})',
        re.IGNORECASE
    )
    m = colon_re.search(section_text)
    if m:
        sentence = f"{key_term}: {m.group(1).strip()}"
        return sentence, 0

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', section_text)
                 if s.strip() and not _is_header_like(s.strip())]
    for priority, verb_pattern in enumerate(_DEFINITION_VERB_PATTERNS, start=1):
        full_pattern = re.compile(
            rf'\b{term}\b[^.!?\n]{{0,80}}?\b(?:{verb_pattern})\b',
            re.IGNORECASE
        )
        for sentence in sentences:
            if full_pattern.search(sentence):
                return sentence, priority
    return None, None


def _extract_key_term(query_text):
    if not query_text:
        return ''
    q = query_text.strip().rstrip('?!.').strip()

    q = re.sub(
        r'^\s*(what\s+is|what\s+are|what\s+does|define|meaning\s+of|definition\s+of)\s+',
        '', q, flags=re.IGNORECASE
    )
    q = re.sub(r'^\s*(a|an|the)\s+', '', q, flags=re.IGNORECASE)
    q = re.sub(r'\s+(stand\s+for|stands\s+for|mean|means|refer\s+to|refers\s+to).*$',
               '', q, flags=re.IGNORECASE)
    q = re.sub(r'\s+(?:in|inside|within|used\s+in|used\s+by)\s+\w+(?:\s+\w+)?\s*$',
               '', q, flags=re.IGNORECASE)

    q = q.strip().strip('"\'').strip()

    acronym_match = re.search(r'\b([A-Z]{2,6})\b', q)
    if acronym_match:
        return acronym_match.group(1)

    words = q.split()
    if not words:
        return ''
    if words[0].lower() in ('a', 'an', 'the'):
        words = words[1:]
    return ' '.join(words[:3]).strip()


def _definition_boost(section_text, key_term):
    if not key_term or not section_text:
        return 0.0
    term = re.escape(key_term)
    patterns = [
        rf'\b{term}\s+is\b',
        rf'\b{term}\s+are\b',
        rf'\b{term}\s+stands\s+for\b',
        rf'\b{term}\s+refers\s+to\b',
        rf'\b{term}\s+can\s+be\s+defined\s+as\b',
        rf'\b{term}\s+means\b',
    ]
    for p in patterns:
        if re.search(p, section_text, flags=re.IGNORECASE):
            return 0.1
    return 0.0


def _list_boost(section_text):
    if not section_text:
        return 0.0
    numbered = len(re.findall(r'(?:^|\s)\d{1,2}[.)]\s+[A-Z]', section_text))
    bulleted = len(re.findall(r'(?:^|\n|\s)•\s+\S', section_text))
    o_artifact = len(re.findall(r'(?:^|\n|\s)o\s+[A-Z]', section_text))
    if numbered >= 2 or bulleted >= 2 or o_artifact >= 2:
        return 0.1
    return 0.0


_WORD_RE = re.compile(r"[a-z0-9]+")
_STOP = {
    'what', 'is', 'are', 'the', 'a', 'an', 'of', 'in', 'on', 'at', 'for', 'to',
    'and', 'or', 'how', 'do', 'does', 'did', 'why', 'which', 'who', 'when',
    'where', 'with', 'by', 'from', 'this', 'that', 'it', 'its', 'be', 'as',
    'about', 'explain', 'define', 'tell', 'me', 'list', 'give',
}


def _keywords(text):
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOP and len(w) > 2}


def _lexical_boost(query_words, section_text):
    """Small bonus when the chunk literally contains the question's key terms."""
    if not query_words:
        return 0.0
    hits = len(query_words & _keywords(section_text))
    return 0.08 * (hits / len(query_words))


def get_relevant_sections(query_text, top_k=8, document_ids=None, user_id=None):
    """Rank stored chunks against the question.

    ``user_id`` restricts the search to that user's own documents, and
    ``document_ids`` narrows it further to a chosen subset.
    """
    initialize_models()
    query_vec = np.asarray(embedding_model.encode(query_text), dtype=np.float32)

    sql = (
        'SELECT ds.section_id, ds.document_id, ds.section_text, ds.embedding, '
        '       ds.page_number, d.document_name, d.file_type '
        'FROM DOCUMENT_SECTION ds JOIN DOCUMENT d ON d.document_id = ds.document_id '
        'WHERE 1=1'
    )
    args = []
    if user_id is not None:
        sql += ' AND d.user_id = ?'
        args.append(user_id)
    if document_ids:
        sql += ' AND ds.document_id IN (%s)' % ','.join('?' * len(document_ids))
        args.extend(document_ids)
    rows = database.query_db(sql, tuple(args))
    if not rows:
        return []

    # Build one matrix and score every chunk with a single matrix product.
    vectors = []
    for row in rows:
        if row['embedding'] is None:
            vectors.append(np.asarray(embedding_model.encode(row['section_text']),
                                      dtype=np.float32))
        else:
            vectors.append(blob_to_array(row['embedding']))
    matrix = np.vstack(vectors)
    norms = np.linalg.norm(matrix, axis=1) * (np.linalg.norm(query_vec) or 1.0)
    norms[norms == 0] = 1.0
    sims = (matrix @ query_vec) / norms

    is_def_query = _is_definition_query(query_text)
    is_list_q = _is_list_query(query_text)
    key_term = _extract_key_term(query_text) if is_def_query else ''
    query_words = _keywords(query_text)

    results = []
    for row, sim in zip(rows, sims):
        score = float(sim)
        if is_def_query and key_term:
            score += _definition_boost(row['section_text'], key_term)
        if is_list_q:
            score += _list_boost(row['section_text'])
        score += _lexical_boost(query_words, row['section_text'])

        results.append({
            'section_id':    row['section_id'],
            'document_id':   row['document_id'],
            'document_name': row['document_name'],
            'file_type':     row['file_type'],
            'page_number':   row['page_number'],
            'section_text':  row['section_text'],
            'score':         score,
        })

    results.sort(key=lambda x: x['score'], reverse=True)

    seen = set()
    deduplicated = []
    for r in results:
        fingerprint = re.sub(r'\s+', ' ', r['section_text'][:100]).strip().lower()
        fingerprint = re.sub(r'^\d{1,3}\s+', '', fingerprint)
        if fingerprint not in seen:
            seen.add(fingerprint)
            deduplicated.append(r)

    filtered = [r for r in deduplicated if r['score'] >= 0.25]

    return filtered[:top_k]


def _clean_text(text):
    if not text:
        return ''

    text = text.replace('\ufffd', '')
    text = re.sub(r'^\d{1,3}\s+(?=[A-Z])', '', text.strip())
    text = re.sub(r'[▯□●▪▸❖❑✓✗\u2022\u2023\u2043\uf0a7\uf0b7\uf0a8\uf0fc\uf0a4\uf0d8]', '• ', text)
    text = re.sub(r'\s*\([AB]\)\s*', ' ', text)
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


_LIST_QUERY_PATTERN = re.compile(
    r'\b(what\s+are|list|types?\s+of|kinds?\s+of|examples?\s+of|categories\s+of|approaches\s+to|steps\s+(?:in|of|to|taken|that|which|the)|phases\s+of|ways\s+to|services\s+of|benefits?\s+of|symptoms?\s+of|disadvantages\s+of|advantages\s+of|requirements\s+(?:in|of|for))\b',
    re.IGNORECASE
)
_IMPLICIT_LIST_SUFFIX = re.compile(
    r'\b(protocols|services|types|kinds|examples|approaches|phases|benefits|methods|techniques|ways|requirements|symptoms|disadvantages|advantages|features|categories|properties|functionalities|aspects|fields|steps)\s*\??\s*$',
    re.IGNORECASE
)


def _is_list_query(query_text):
    if not query_text:
        return False
    if _LIST_QUERY_PATTERN.search(query_text):
        return True
    return bool(_IMPLICIT_LIST_SUFFIX.search(query_text))


def _is_header_like(sentence):
    if not sentence:
        return True
    s = sentence.strip()
    if len(s) < 20:
        return True
    if re.search(r'\([AB]\)\s*$', s):
        return True
    letters = [c for c in s if c.isalpha()]
    if letters:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_ratio > 0.7:
            return True
    return False


_LIST_STOP_WORDS = {
    'what', 'are', 'is', 'the', 'a', 'an', 'of', 'in', 'at', 'on', 'for',
    'with', 'and', 'or', 'how', 'do', 'does', 'to', 'list', 'kinds',
    'examples', 'taken', 'takes', 'take', 'by', 'that', 'which', 'some',
    'few', 'this', 'these', 'those',
}


_HEADING_KEYWORDS_RE = re.compile(
    r'(?:^|(?<=\n))'
    r'('
    # Branch 1: single keyword + optional connector ("of"/"to"/"for") + 1-5 words
    r'(?:Types?|Kinds?|Examples?|Categories|Services|Phases?|Steps?|Stages?|'
    r'Benefits?|Symptoms?|Disadvantages?|Advantages?|Methods?|Techniques?|'
    r'Functionalities|Requirements?)'
    r'(?:\s+(?:of|to|for|in|the))?'
    r'\s+\w[\w\-/&()]*'
    r'(?:\s+\w[\w\-/&()]*){0,4}'
    r'|'
    # Branch 2: multi-word keyword phrases (preposition baked in)
    r'(?:Approaches\s+to|Need\s+for|Importance\s+of|Working\s+of|'
    r'How\s+It\s+Works|How\s+\w+\s+Works)'
    r'(?:\s+\w[\w\-/&()]*){0,5}'
    r')'
    r'(?=\s*\n|\s+(?=•|\d+[.)]\s|o\s+[A-Z]))'
)


def _select_relevant_segment(text, query_text):
    colon_anchor_re = re.compile(
        r'(?:^|(?<=[.!?]\s)|(?<=\n))([A-Z][^\n.!?]{4,150}?):\s+'
    )
    anchors = []
    for m in colon_anchor_re.finditer(text):
        preamble = m.group(1)
        if re.search(r'\b\d+[.)]\s', preamble):
            continue
        anchors.append((m.start(), m.end(), preamble))
    for m in _HEADING_KEYWORDS_RE.finditer(text):
        preamble = m.group(1)
        if re.search(r'\b\d+[.)]\s', preamble):
            continue
        anchors.append((m.start(), m.end(), preamble))
    anchors.sort(key=lambda a: a[0])
    if not anchors:
        return None

    query_words = {w for w in re.findall(r'\w+', query_text.lower())
                   if w not in _LIST_STOP_WORDS and len(w) > 2}
    if not query_words:
        return None

    best_score = 0
    best_idx = -1
    for i, (_, _, preamble) in enumerate(anchors):
        preamble_words = {w for w in re.findall(r'\w+', preamble.lower())
                          if w not in _LIST_STOP_WORDS and len(w) > 2}
        overlap = len(query_words & preamble_words)
        if overlap > best_score:
            best_score = overlap
            best_idx = i

    if best_score < 1:
        return None

    seg_start = anchors[best_idx][1]
    seg_end = anchors[best_idx + 1][0] if best_idx + 1 < len(anchors) else len(text)
    return text[seg_start:seg_end]


def _extract_list_items(text, query_text=''):
    if not text:
        return []

    items = []
    normalized = re.sub(r'(^|\s)o\s+(?=[A-Z])', r'\1• ', text)
    scoped = normalized
    if query_text:
        segment = _select_relevant_segment(normalized, query_text)
        if segment is not None:
            scoped = segment
    chunks = re.split(r'(?:\n|(?<=\S)\s+(?=•|\d+[.)]\s))', scoped)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.match(r'^(?:•|[-*]|\d+[.)])\s*(.+)$', chunk)
        if m:
            raw = m.group(1).strip()
            sub_anchor = re.search(
                r'\s+([A-Z][a-z][\w\-/]*(?:\s+[A-Za-z][\w\-/]*){0,4})\s*:\s+[A-Z]',
                raw
            )
            if sub_anchor and sub_anchor.start() >= 5:
                raw = raw[:sub_anchor.start()].strip()
            cut = re.match(r'^(.{5,250}?[.!?])(?:\s+[A-Z]|\s*$)', raw)
            item = (cut.group(1) if cut else raw).strip().rstrip('.,;:')
            if 2 < len(item) < 250:
                items.append(item)
    if len(items) >= 2:
        return items

    anchor_re = re.compile(
        r'\b(?:'
        r'(?:some\s+)?types?\s+of\s+\w+|'
        r'kinds?\s+of\s+\w+|'
        r'examples?\s+of\s+\w+|'
        r'categories\s+of\s+\w+|'
        r'services\s+of\s+\S+|'
        r'phases?\s+of\s+\w+|'
        r'steps?\s+of\s+\w+|'
        r'benefits?\s+of\s+\w+|'
        r'symptoms?\s+of\s+\w+|'
        r'disadvantages?\s+of\s+\w+|'
        r'advantages?\s+of\s+\w+|'
        r'methods?\s+of\s+\w+|'
        r'approaches\s+to\s+\w+(?:\s+\w+)?|'
        r'requirements?\s+(?:in|of|for)\s+\w+|'
        r'are\s+as\s+follows|include[s]?|are'
        r')\s*:\s*',
        re.IGNORECASE
    )
    matches = list(anchor_re.finditer(text))
    body = text[matches[-1].end():] if matches else text

    item_re = re.compile(
        r'(?:^|(?<=[.!?]\s))([A-Z][A-Za-z][\w\s\-/]{1,40}):\s+([^.!?]{10,250}?[.!?])'
    )
    inline_items = []
    for m in item_re.finditer(body):
        title = m.group(1).strip()
        desc = m.group(2).strip().rstrip('.!?').rstrip()
        if len(title.split()) > 6:
            continue
        item = f'{title}: {desc}'
        if 8 < len(item) < 280:
            inline_items.append(item)
        if len(inline_items) >= 10:
            break
    if len(inline_items) >= 2:
        return inline_items
    return items


def _pick_best_section(query_text, sections, fallback_context):
    if not sections:
        return fallback_context

    top_score = sections[0]['score']
    if _is_list_query(query_text):
        threshold = top_score * 0.70
        relevant = [s for s in sections[:8] if s['score'] >= threshold]
    else:
        threshold = top_score * 0.80
        relevant = [s for s in sections[:5] if s['score'] >= threshold]
    if not relevant:
        relevant = [sections[0]]

    if _is_list_query(query_text):
        fallback_chunks = []
        for s in relevant:
            text = _clean_text(s['section_text'])
            normalized = re.sub(r'(^|\s)o\s+(?=[A-Z])', r'\1• ', text)
            scoped = _select_relevant_segment(normalized, query_text)
            if scoped is None:
                fallback_chunks.append(s)
                continue
            items = _extract_list_items(text, query_text)
            if len(items) < 2:
                # The segment is prose, not bullets: show its sentences as points.
                items = []
                for x in re.split(r'(?<=[.!?])\s+', scoped):
                    x = x.strip()
                    if _is_header_like(x):
                        continue
                    # a much longer sentence usually starts a new topic
                    if len(items) >= 2 and len(x) > max(100, 2 * sum(map(len, items)) / len(items)):
                        break
                    items.append(x)
                items = items[:8]
            if len(items) >= 2:
                return '\n'.join(f'• {item}' for item in items[:10])
        for s in fallback_chunks:
            text = _clean_text(s['section_text'])
            items = _extract_list_items(text, query_text)
            if len(items) >= 2:
                return '\n'.join(f'• {item}' for item in items[:10])

    list_sections = []
    other_sections = []
    for s in relevant:
        text = _clean_text(s['section_text'])
        if re.search(r'\b[1-9][.)]\s', text):
            list_sections.append(text)
        else:
            other_sections.append(text)
    ordered_texts = list_sections + other_sections

    # Collect candidate sentences, then keep the ones that best match the
    # question (falling back to document order when nothing overlaps).
    candidates = []
    seen_sentences = set()
    for text in ordered_texts:
        for sentence in re.split(r'(?<=[.!?])\s+', text):
            sentence = sentence.strip()
            if _is_header_like(sentence):
                continue
            fingerprint = re.sub(r'\s+', ' ', sentence[:80]).lower()
            if fingerprint in seen_sentences:
                continue
            seen_sentences.add(fingerprint)
            candidates.append(sentence)

    query_words = _keywords(query_text)
    if query_words and candidates:
        scored = [(len(query_words & _keywords(c)), -i, i, c)
                  for i, c in enumerate(candidates)]
        best = sorted(scored, reverse=True)[:3]
        if best[0][0] > 0:
            # drop zero-overlap filler when something better exists
            parts = [c for score, _, _, c in sorted(best, key=lambda t: t[2]) if score > 0]
        else:
            parts = candidates[:3]
    else:
        parts = candidates[:3]

    return ' '.join(parts) if parts else fallback_context


def _polish_answer(answer):
    if not answer:
        return answer

    answer = _clean_text(answer)
    answer = re.sub(r'(^|\n|\s{2,})o\s+(?=[A-Za-z])', r'\1• ', answer)
    is_bullet_list = len(re.findall(r'(?:^|\n)\s*•\s', answer)) >= 2
    answer = re.sub(r'^[\s•\-\*]+', '', answer).strip()
    if is_bullet_list:
        answer = '• ' + answer

    if not answer:
        return answer

    if answer[0].isalpha() and answer[0].islower():
        answer = answer[0].upper() + answer[1:]

    stripped = answer.rstrip()
    if stripped and stripped[-1] not in '.!?':
        if '•' not in stripped.split('\n')[-1]:
            answer = stripped + '.'

    return answer.strip()


def _relevance_confidence(sections):
    """Map the best retrieval score (0.25 threshold .. ~0.7) onto 0..1."""
    if not sections:
        return 0.0
    return max(0.0, min(1.0, (sections[0]['score'] - 0.25) / 0.45))


def generate_answer(query_text, sections):
    """Return ``{'answer', 'context', 'confidence'}`` for a question."""
    if not sections:
        return {'answer': NOT_FOUND_MSG, 'context': '', 'confidence': 0.0}

    relevance = _relevance_confidence(sections)

    # A weak retrieval score AND missing key terms means the documents most
    # likely don't cover the question - say so rather than guess.
    query_words = _keywords(query_text)
    if query_words and relevance < 0.25:
        seen_words = set()
        for s in sections[:3]:
            seen_words |= _keywords(s['section_text'])
        if len(query_words & seen_words) < len(query_words):
            return {'answer': NOT_FOUND_MSG, 'context': '', 'confidence': 0.0}

    # Build context from top retrieved sections (cleaned)
    context_parts = []
    total_words = 0
    for section in sections[:5]:
        cleaned = _clean_text(section['section_text'])
        words = len(cleaned.split())
        if total_words + words > 1500:
            break
        context_parts.append(cleaned)
        total_words += words

    context = ' '.join(context_parts)
    full_section = _clean_text(sections[0]['section_text'])

    if not context or len(context) < 20:
        return {'answer': NOT_FOUND_MSG, 'context': '', 'confidence': 0.0}

    if _is_list_query(query_text):
        best = _pick_best_section(query_text, sections, context)
        return {'answer': _polish_answer(best), 'context': full_section,
                'confidence': relevance}

    if _is_definition_query(query_text):
        key_term = _extract_key_term(query_text)
        if key_term:
            best_def = None
            best_priority = None
            for section in sections[:5]:
                cleaned = _clean_text(section['section_text'])
                sentence, priority = _find_definition_sentence(cleaned, key_term)
                if sentence is not None and (best_priority is None or priority < best_priority):
                    best_def = sentence
                    best_priority = priority
                    if priority == 0:
                        break
            if best_def:
                return {'answer': _polish_answer(best_def), 'context': full_section,
                        'confidence': min(1.0, relevance + 0.1)}

    try:
        answer, qa_conf = _extract_answer(query_text, context)

        if len(answer) > 10:
            return {'answer': _polish_answer(answer), 'context': full_section,
                    'confidence': 0.5 * relevance + 0.5 * qa_conf}
        best = _pick_best_section(query_text, sections, context)
        return {'answer': _polish_answer(best), 'context': '',
                'confidence': 0.7 * relevance}

    except Exception:
        best = _pick_best_section(query_text, sections, context)
        return {'answer': _polish_answer(best), 'context': '',
                'confidence': 0.7 * relevance}
