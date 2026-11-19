/* Chat page: renders the thread and talks to /api/ask.
   All user- and document-derived text goes in through textContent, never
   innerHTML, so nothing from an answer or a question can inject markup. */
(function () {
    'use strict';

    var $ = function (s, r) { return (r || document).querySelector(s); };
    var inner = $('#threadInner'), thread = $('#thread'), hero = $('#hero');
    var form = $('#askForm'), input = $('#askInput'), send = $('#sendBtn');
    var hasDocs = JSON.parse($('#docData').textContent).length > 0;
    var busy = false;

    function el(tag, cls, text) {
        var e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text !== undefined && text !== null) e.textContent = text;
        return e;
    }
    function icon(id, cls) {
        var s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        s.setAttribute('class', 'ico' + (cls ? ' ' + cls : ''));
        var u = document.createElementNS('http://www.w3.org/2000/svg', 'use');
        u.setAttribute('href', '#' + id);
        s.appendChild(u);
        return s;
    }
    function scrollDown(smooth) {
        thread.scrollTo({ top: thread.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
    }

    /* ── Answer text: "• item" lines become a bullet list ── */
    function renderAnswerText(text) {
        var box = el('div', 'answer-text');
        var lines = text.split('\n'), list = null;
        lines.forEach(function (line) {
            var m = line.match(/^\s*[•\-*]\s+(.*)$/);
            if (m) {
                if (!list) { list = el('ul'); box.appendChild(list); }
                list.appendChild(el('li', null, m[1]));
            } else if (line.trim()) {
                list = null;
                box.appendChild(el('p', null, line));
            }
        });
        if (!box.firstChild) box.appendChild(el('p', null, text));
        return box;
    }

    /* ── Highlight the question's key words inside an excerpt ── */
    var STOP = /^(what|are|the|and|for|how|does|did|why|which|who|when|where|with|from|this|that|about|explain|define|tell|list|give|types?|of|is|in|on|to|an|a|or|by|it|as|be)$/i;
    function highlight(container, text, query) {
        var words = (query.toLowerCase().match(/[a-z0-9]+/g) || [])
            .filter(function (w) { return w.length > 2 && !STOP.test(w); });
        if (!words.length) { container.textContent = text; return; }
        var re = new RegExp('\\b(' + words.map(function (w) { return w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }).join('|') + ')\\w*', 'gi');
        var last = 0, m;
        while ((m = re.exec(text)) !== null) {
            if (m.index > last) container.appendChild(document.createTextNode(text.slice(last, m.index)));
            container.appendChild(el('mark', null, m[0]));
            last = m.index + m[0].length;
        }
        container.appendChild(document.createTextNode(text.slice(last)));
    }

    function fileHref(src, page) {
        var base = '/document/' + src.document_id + '/file';
        return base + (page && src.file_type === 'pdf' ? '#page=' + page : '');
    }

    /* ── One Q&A pair ── */
    function renderItem(item) {
        var wrap = el('article', 'qa');
        wrap.id = 'q-' + item.query_id;

        var q = el('div', 'msg user');
        q.appendChild(el('div', 'bubble', item.query_text));
        wrap.appendChild(q);

        var a = el('div', 'msg bot');
        a.appendChild(el('div', 'bot-avatar')).appendChild(icon('i-spark'));
        var card = el('div', 'card' + (item.not_found ? ' muted' : ''));

        card.appendChild(renderAnswerText(item.answer_text));

        // Meta row: confidence + files used
        var meta = el('div', 'meta');
        if (item.confidence !== null && !item.not_found) {
            var pill = el('span', 'pill conf-' + item.confidence_label);
            pill.appendChild(el('i'));
            pill.appendChild(document.createTextNode(item.confidence_label + ' confidence · ' + item.confidence + '%'));
            pill.title = 'How well the retrieved passages match your question';
            meta.appendChild(pill);
        }
        (item.source_docs || []).slice(0, 3).forEach(function (d) {
            var c = el('a', 'src-chip');
            c.href = '/document/' + d.document_id + '/file';
            c.target = '_blank'; c.rel = 'noopener';
            c.setAttribute('data-view', ''); c.setAttribute('data-doc-id', d.document_id);
            c.setAttribute('data-name', d.document_name); c.setAttribute('data-type', d.file_type);
            c.appendChild(el('span', 'doc-badge sm t-' + d.file_type, d.file_type.toUpperCase()));
            c.appendChild(el('span', 'src-name', d.document_name));
            if (d.pages_label) c.appendChild(el('span', 'src-pages', d.pages_label));
            meta.appendChild(c);
        });
        if (meta.firstChild) card.appendChild(meta);

        // Evidence (expandable)
        if (item.sources && item.sources.length && !item.not_found) {
            var det = el('details', 'evidence');
            var sum = el('summary');
            sum.appendChild(icon('i-chevron', 'caret'));
            sum.appendChild(document.createTextNode('Evidence from your documents (' + item.sources.length + ')'));
            det.appendChild(sum);
            item.sources.forEach(function (s) {
                var row = el('div', 'ev');
                var head = el('div', 'ev-head');
                head.appendChild(el('strong', null, s.document_name));
                if (s.page) head.appendChild(el('span', 'ev-page', 'p. ' + s.page));
                head.appendChild(el('span', 'ev-match', s.match + '% match'));
                var open = el('a', 'ev-open'); open.href = fileHref(s, s.page);
                open.target = '_blank'; open.rel = 'noopener'; open.title = 'View in the side panel';
                open.setAttribute('data-view', ''); open.setAttribute('data-doc-id', s.document_id);
                open.setAttribute('data-name', s.document_name); open.setAttribute('data-type', s.file_type);
                if (s.page) open.setAttribute('data-page', s.page);
                open.setAttribute('data-quote', s.excerpt.slice(0, 160));
                open.appendChild(icon('i-external'));
                head.appendChild(open);
                row.appendChild(head);
                var bar = el('div', 'bar'); var fill = el('i'); fill.style.width = s.match + '%';
                bar.appendChild(fill); row.appendChild(bar);
                var ex = el('blockquote'); highlight(ex, s.excerpt, item.query_text);
                row.appendChild(ex);
                det.appendChild(row);
            });
            card.appendChild(det);
        }

        // Actions
        var acts = el('div', 'actions');
        var copy = el('button', 'icon-btn sm'); copy.type = 'button'; copy.title = 'Copy answer';
        copy.appendChild(icon('i-copy'));
        copy.addEventListener('click', function () {
            (navigator.clipboard ? navigator.clipboard.writeText(item.answer_text) : Promise.reject())
                .then(function () { SDQ.toast('Answer copied', 'success'); },
                      function () { SDQ.toast('Copy is not available in this browser.', 'danger'); });
        });
        acts.appendChild(copy);

        function rate(value, btn, other) {
            var next = item.rating === value ? 0 : value;
            fetch('/api/answer/' + item.query_id + '/rating', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': SDQ.csrf },
                body: JSON.stringify({ rating: next })
            }).then(function (r) { if (!r.ok) throw 0; item.rating = next;
                btn.classList.toggle('on', next === value); other.classList.remove('on');
            }).catch(function () { SDQ.toast('Could not save your feedback.', 'danger'); });
        }
        var up = el('button', 'icon-btn sm' + (item.rating === 1 ? ' on' : '')); up.type = 'button';
        up.title = 'Helpful'; up.appendChild(icon('i-up'));
        var down = el('button', 'icon-btn sm' + (item.rating === -1 ? ' on' : '')); down.type = 'button';
        down.title = 'Not helpful'; down.appendChild(icon('i-down'));
        up.addEventListener('click', function () { rate(1, up, down); });
        down.addEventListener('click', function () { rate(-1, down, up); });
        acts.appendChild(up); acts.appendChild(down);
        if (item.created) acts.appendChild(el('time', null, item.created));
        card.appendChild(acts);

        a.appendChild(card);
        wrap.appendChild(a);
        return wrap;
    }

    function typingRow() {
        var a = el('div', 'msg bot');
        a.appendChild(el('div', 'bot-avatar')).appendChild(icon('i-spark'));
        var card = el('div', 'card');
        var t = el('div', 'typing');
        t.appendChild(el('i')); t.appendChild(el('i')); t.appendChild(el('i'));
        card.appendChild(t);
        card.appendChild(el('div', 'typing-label', 'Searching your documents…'));
        a.appendChild(card);
        return a;
    }

    function errorRow(message) {
        var a = el('div', 'msg bot');
        a.appendChild(el('div', 'bot-avatar err')).appendChild(icon('i-x'));
        a.appendChild(el('div', 'card error', message));
        return a;
    }

    /* ── Initial history ── */
    var history = JSON.parse($('#historyData').textContent);
    history.forEach(function (item) { inner.appendChild(renderItem(item)); });

    SDQ.focusHash = function () {
        if (!location.hash) return false;
        var target = document.getElementById(location.hash.slice(1));
        if (!target) return false;
        target.scrollIntoView({ block: 'center' });
        target.classList.remove('flash'); void target.offsetWidth; target.classList.add('flash');
        return true;
    };
    if (!SDQ.focusHash()) scrollDown(false);
    window.addEventListener('hashchange', SDQ.focusHash);

    /* ── Composer ── */
    function autosize() {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 160) + 'px';
        send.disabled = busy || !input.value.trim();
    }
    input.addEventListener('input', autosize);
    input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
            e.preventDefault();
            if (!send.disabled) form.requestSubmit();
        }
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === '/' && document.activeElement !== input &&
            !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) {
            e.preventDefault(); input.focus();
        }
    });
    Array.prototype.forEach.call(document.querySelectorAll('[data-prompt]'), function (b) {
        b.addEventListener('click', function () {
            input.value = b.getAttribute('data-prompt'); autosize(); input.focus();
        });
    });
    if (!hasDocs) input.placeholder = 'Add a document first, then ask a question…';

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        var text = input.value.trim();
        if (!text || busy) return;
        if (!hasDocs) { SDQ.toast('Upload a document first.', 'info'); $('[data-open-upload]').click(); return; }

        busy = true;
        if (hero) hero.hidden = true;

        var pending = el('article', 'qa');
        var u = el('div', 'msg user'); u.appendChild(el('div', 'bubble', text));
        pending.appendChild(u);
        var typing = typingRow();
        pending.appendChild(typing);
        inner.appendChild(pending);
        input.value = ''; autosize(); scrollDown(true);

        fetch('/api/ask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': SDQ.csrf },
            body: JSON.stringify({ query_text: text, document_ids: SDQ.getSelectedDocs() })
        }).then(function (r) {
            return r.json().catch(function () { return {}; }).then(function (data) {
                if (!r.ok) throw new Error(data.error || 'Something went wrong. Please try again.');
                return data;
            });
        }).then(function (item) {
            var rendered = renderItem(item);
            pending.replaceWith(rendered);
            // keep the sidebar in step without a reload
            var list = $('#histList');
            if (!list) {   // first question ever: build the history list
                var hint = document.querySelector('.side-section:last-child .side-hint');
                if (hint) {
                    list = el('ul', 'hist-list'); list.id = 'histList';
                    hint.replaceWith(list);
                }
            }
            if (list) {
                var li = document.createElement('li'); li.className = 'hist'; li.setAttribute('data-text', text.toLowerCase());
                var a = document.createElement('a'); a.href = '#q-' + item.query_id;
                a.appendChild(icon('i-chat'));
                a.appendChild(el('span', null, text.length > 46 ? text.slice(0, 43) + '...' : text));
                li.appendChild(a); list.insertBefore(li, list.firstChild);
            }
            scrollDown(true);
        }).catch(function (err) {
            typing.replaceWith(errorRow(err.message || 'Network error. Is the server running?'));
            input.value = text; autosize();
        }).then(function () {
            busy = false; autosize(); input.focus();
        });
    });

    input.focus();
})();
