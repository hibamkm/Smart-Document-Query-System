/* Shared behaviour: theme, sidebar, upload modal, toasts, confirmations,
   document selection. Everything here is plain DOM code with no dependencies. */
(function () {
    'use strict';

    var $ = function (s, r) { return (r || document).querySelector(s); };
    var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

    window.SDQ = window.SDQ || {};

    /* ── CSRF helper for fetch() ─────────────────────── */
    var meta = $('meta[name="csrf-token"]');
    SDQ.csrf = meta ? meta.content : '';

    /* ── Theme ───────────────────────────────────────── */
    var themeBtn = $('#themeBtn');
    if (themeBtn) {
        themeBtn.addEventListener('click', function () {
            var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            try { localStorage.setItem('theme', next); } catch (e) {}
        });
    }

    /* ── Toasts ──────────────────────────────────────── */
    SDQ.toast = function (message, kind) {
        var host = $('#toasts');
        if (!host) return;
        var t = document.createElement('div');
        t.className = 'toast toast-' + (kind || 'info');
        var span = document.createElement('span');
        span.textContent = message;
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'icon-btn sm';
        btn.setAttribute('aria-label', 'Dismiss');
        btn.innerHTML = '<svg class="ico"><use href="#i-x"/></svg>';
        t.appendChild(span); t.appendChild(btn);
        host.appendChild(t);
        autoDismiss(t);
    };
    function autoDismiss(t) {
        var kill = function () { t.classList.add('out'); setTimeout(function () { t.remove(); }, 250); };
        $('button', t).addEventListener('click', kill);
        setTimeout(kill, t.classList.contains('toast-danger') ? 9000 : 5000);
    }
    $$('.toast').forEach(autoDismiss);

    /* ── Confirm dialogs on destructive forms ────────── */
    document.addEventListener('submit', function (e) {
        var msg = e.target.getAttribute && e.target.getAttribute('data-confirm');
        if (msg && !window.confirm(msg)) e.preventDefault();
    });

    /* ── Password show/hide + strength meter ─────────── */
    $$('[data-toggle-pw]').forEach(function (b) {
        b.addEventListener('click', function () {
            var input = b.parentElement.querySelector('input');
            var show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            b.textContent = show ? 'Hide' : 'Show';
        });
    });
    var pw1 = $('#pw1'), meter = $('#strength'), pw2 = $('#pw2');
    if (pw1 && meter) {
        pw1.addEventListener('input', function () {
            var v = pw1.value, s = 0;
            if (v.length >= 6) s++;
            if (v.length >= 10) s++;
            if (/[A-Z]/.test(v) && /[a-z]/.test(v)) s++;
            if (/\d/.test(v) && /[^A-Za-z0-9]/.test(v)) s++;
            meter.setAttribute('data-level', v ? Math.max(1, s) : 0);
        });
        pw2.addEventListener('input', function () {
            pw2.setCustomValidity(pw2.value && pw2.value !== pw1.value ? 'Passwords do not match' : '');
        });
    }

    /* The rest only applies to the signed-in app shell. */
    var app = $('#app');
    if (!app) return;

    /* ── Sidebar (mobile) ────────────────────────────── */
    var closeSide = function () { app.classList.remove('side-open'); };
    var menuBtn = $('#menuBtn');
    if (menuBtn) menuBtn.addEventListener('click', function () { app.classList.toggle('side-open'); });
    $('#scrim').addEventListener('click', closeSide);

    /* ── History filter ──────────────────────────────── */
    var hf = $('#historyFilter');
    if (hf) {
        hf.addEventListener('input', function () {
            var q = hf.value.toLowerCase().trim();
            $$('#histList .hist').forEach(function (li) {
                li.style.display = !q || li.getAttribute('data-text').indexOf(q) !== -1 ? '' : 'none';
            });
        });
    }
    $$('#histList a').forEach(function (a) {
        a.addEventListener('click', function () {
            closeSide();
            // Same page: let the hash change scroll, then highlight it.
            setTimeout(function () { SDQ.focusHash && SDQ.focusHash(); }, 30);
        });
    });


    /* ── Document viewer: a side panel, so the chat page stays put ── */
    var viewer = $('#viewer'), appEl = $('.app'), vBody = $('#viewerBody');
    function closeViewer() {
        if (!viewer.classList.contains('open')) return;
        viewer.classList.remove('open'); appEl.classList.remove('viewing');
        viewer.setAttribute('aria-hidden', 'true'); vBody.textContent = '';
    }
    SDQ.openViewer = function (id, name, type, page, quote) {
        var url = '/document/' + id + '/file';
        $('#viewerName').textContent = name;
        var badge = $('#viewerBadge'); badge.textContent = type.toUpperCase(); badge.className = 'doc-badge sm t-' + type;
        $('#viewerNewTab').href = url + (type === 'pdf' && page ? '#page=' + page : '');
        $('#viewerDownload').href = url + '?download=1';
        vBody.textContent = '';
        if (type === 'pdf') {
            var f = document.createElement('iframe');
            f.title = name; f.src = url + (page ? '#page=' + page : '');
            vBody.appendChild(f);
        } else if (type === 'txt' || type === 'md') {
            var pre = document.createElement('pre'); pre.className = 'viewer-text'; pre.textContent = 'Loading...';
            vBody.appendChild(pre);
            fetch(url).then(function (r) { return r.text(); }).then(function (t) { pre.textContent = t; })
                .catch(function () { pre.textContent = 'Could not load this file.'; });
        } else {
            var box = document.createElement('div'); box.className = 'viewer-note';
            var p = document.createElement('p'); p.textContent = 'Word documents can\u2019t be previewed in the browser.';
            var a = document.createElement('a'); a.className = 'btn btn-primary'; a.href = url + '?download=1'; a.textContent = 'Download ' + name;
            box.appendChild(p); box.appendChild(a); vBody.appendChild(box);
        }
        if (quote) {
            var q = document.createElement('div'); q.className = 'viewer-quote';
            q.textContent = 'Matched passage: ' + quote + (quote.length >= 160 ? '\u2026' : '');
            vBody.insertBefore(q, vBody.firstChild);
        }
        viewer.classList.add('open'); appEl.classList.add('viewing'); viewer.setAttribute('aria-hidden', 'false');
        closeSide();
    };
    document.addEventListener('click', function (e) {
        var a = e.target.closest && e.target.closest('a[data-view]');
        if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.button) return;   // modified clicks keep new-tab behaviour
        e.preventDefault(); e.stopPropagation();   // also keeps the sidebar row from toggling
        SDQ.openViewer(a.getAttribute('data-doc-id'), a.getAttribute('data-name'), a.getAttribute('data-type'),
                       a.getAttribute('data-page'), a.getAttribute('data-quote'));
    }, true);
    $('#viewerClose').addEventListener('click', closeViewer);
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeViewer(); });

    /* ── Upload modal ────────────────────────────────── */
    var modal = $('#uploadModal'), fileInput = $('#fileInput'), fileList = $('#fileList'),
        uploadBtn = $('#uploadBtn'), dropzone = $('#dropzone'), uploadForm = $('#uploadForm');
    var MAX_MB = 25, EXT = ['pdf', 'docx', 'txt', 'md'];
    var chosen = [];

    function openModal() { modal.classList.add('open'); modal.setAttribute('aria-hidden', 'false'); }
    function closeModal() { modal.classList.remove('open'); modal.setAttribute('aria-hidden', 'true'); }
    $$('[data-open-upload]').forEach(function (b) { b.addEventListener('click', function () { closeSide(); openModal(); }); });
    $$('[data-close-upload]').forEach(function (b) { b.addEventListener('click', closeModal); });
    modal.addEventListener('mousedown', function (e) { if (e.target === modal) closeModal(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeModal(); });

    function fmtSize(n) { return n < 1048576 ? Math.max(1, Math.round(n / 1024)) + ' KB' : (n / 1048576).toFixed(1) + ' MB'; }

    function syncInput() {
        var dt = new DataTransfer();
        chosen.forEach(function (f) { dt.items.add(f); });
        fileInput.files = dt.files;
        uploadBtn.disabled = chosen.length === 0;
        uploadBtn.textContent = chosen.length > 1 ? 'Upload ' + chosen.length + ' files' : 'Upload & index';
    }
    function renderFiles() {
        fileList.innerHTML = '';
        chosen.forEach(function (f, i) {
            var li = document.createElement('li');
            var ext = f.name.split('.').pop().toLowerCase();
            var badge = document.createElement('span');
            badge.className = 'doc-badge t-' + ext; badge.textContent = ext.toUpperCase();
            var name = document.createElement('span');
            name.className = 'fl-name'; name.textContent = f.name;
            var size = document.createElement('span');
            size.className = 'fl-size'; size.textContent = fmtSize(f.size);
            var rm = document.createElement('button');
            rm.type = 'button'; rm.className = 'icon-btn sm'; rm.setAttribute('aria-label', 'Remove');
            rm.innerHTML = '<svg class="ico"><use href="#i-x"/></svg>';
            rm.addEventListener('click', function () { chosen.splice(i, 1); renderFiles(); syncInput(); });
            li.appendChild(badge); li.appendChild(name); li.appendChild(size); li.appendChild(rm);
            fileList.appendChild(li);
        });
    }
    function addFiles(files) {
        Array.prototype.forEach.call(files, function (f) {
            var ext = f.name.split('.').pop().toLowerCase();
            if (EXT.indexOf(ext) === -1) { SDQ.toast('"' + f.name + '" is not a supported type.', 'danger'); return; }
            if (f.size > MAX_MB * 1048576) { SDQ.toast('"' + f.name + '" is over ' + MAX_MB + ' MB.', 'danger'); return; }
            if (chosen.some(function (c) { return c.name === f.name && c.size === f.size; })) return;
            chosen.push(f);
        });
        renderFiles(); syncInput();
    }
    fileInput.addEventListener('change', function () {
        var picked = Array.prototype.slice.call(fileInput.files);
        chosen = chosen.slice();
        addFiles(picked);
    });
    ['dragenter', 'dragover'].forEach(function (ev) {
        dropzone.addEventListener(ev, function (e) { e.preventDefault(); dropzone.classList.add('over'); });
    });
    ['dragleave', 'drop'].forEach(function (ev) {
        dropzone.addEventListener(ev, function (e) { e.preventDefault(); dropzone.classList.remove('over'); });
    });
    dropzone.addEventListener('drop', function (e) { addFiles(e.dataTransfer.files); });

    uploadForm.addEventListener('submit', function () {
        uploadBtn.disabled = true;
        uploadBtn.innerHTML = '<span class="spinner"></span> Indexing… this can take a moment';
    });

    // Drag a file anywhere on the page to start an upload.
    var overlay = $('#dropOverlay'), dragDepth = 0;
    function hasFiles(e) { return e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types || [], 'Files') !== -1; }
    window.addEventListener('dragenter', function (e) { if (hasFiles(e)) { dragDepth++; overlay.classList.add('show'); } });
    window.addEventListener('dragleave', function (e) { if (hasFiles(e) && --dragDepth <= 0) { dragDepth = 0; overlay.classList.remove('show'); } });
    window.addEventListener('dragover', function (e) { if (hasFiles(e)) e.preventDefault(); });
    window.addEventListener('drop', function (e) {
        overlay.classList.remove('show'); dragDepth = 0;
        if (!hasFiles(e) || modal.classList.contains('open')) return;
        e.preventDefault();
        openModal(); addFiles(e.dataTransfer.files);
    });

    /* ── Document scope (which files a question searches) ── */
    var KEY = 'sdq.selectedDocs';
    var allIds = $$('#docList .doc').map(function (li) { return parseInt(li.getAttribute('data-doc-id'), 10); });
    var selected = [];
    try { selected = JSON.parse(sessionStorage.getItem(KEY) || '[]'); } catch (e) {}
    selected = selected.filter(function (id) { return allIds.indexOf(id) !== -1; });

    // Drop the ?just_uploaded=<id> marker from the address bar; new documents
    // are searched along with the rest unless the user narrows the scope.
    var url = new URL(window.location.href);
    if (url.searchParams.has('just_uploaded')) {
        url.searchParams.delete('just_uploaded');
        history.replaceState({}, '', url.pathname + url.search + url.hash);
    }

    function persist() { try { sessionStorage.setItem(KEY, JSON.stringify(selected)); } catch (e) {} }
    function docName(id) {
        var li = $('#docList .doc[data-doc-id="' + id + '"] .doc-name');
        return li ? li.textContent : 'Document';
    }
    SDQ.getSelectedDocs = function () { return selected.slice(); };

    function renderScope() {
        $$('#docList .doc').forEach(function (li) {
            var on = selected.indexOf(parseInt(li.getAttribute('data-doc-id'), 10)) !== -1;
            li.classList.toggle('selected', on);
            li.setAttribute('aria-checked', on ? 'true' : 'false');
        });
        var hint = $('#scopeHint');
        if (hint) hint.textContent = selected.length
            ? 'Searching ' + selected.length + ' of ' + allIds.length + ' documents.'
            : 'Searching all documents.';
        var all = $('#selectAllBtn');
        if (all) all.textContent = selected.length ? 'Clear' : 'All';

        var scope = $('#scope');
        if (!scope) return;
        scope.innerHTML = '';
        if (!selected.length) { scope.hidden = true; return; }
        scope.hidden = false;
        var lbl = document.createElement('span'); lbl.className = 'scope-label'; lbl.textContent = 'Searching in';
        scope.appendChild(lbl);
        selected.forEach(function (id) {
            var c = document.createElement('span'); c.className = 'scope-chip';
            var t = document.createElement('span'); t.textContent = docName(id);
            var x = document.createElement('button'); x.type = 'button'; x.setAttribute('aria-label', 'Remove');
            x.innerHTML = '<svg class="ico"><use href="#i-x"/></svg>';
            x.addEventListener('click', function () { toggle(id); });
            c.appendChild(t); c.appendChild(x); scope.appendChild(c);
        });
    }
    function toggle(id) {
        var i = selected.indexOf(id);
        if (i === -1) selected.push(id); else selected.splice(i, 1);
        persist(); renderScope();
    }
    $$('#docList .doc').forEach(function (li) {
        var id = parseInt(li.getAttribute('data-doc-id'), 10);
        li.addEventListener('click', function () { toggle(id); });
        li.addEventListener('keydown', function (e) {
            if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); toggle(id); }
        });
    });
    var allBtn = $('#selectAllBtn');
    if (allBtn) allBtn.addEventListener('click', function () {
        selected = selected.length ? [] : allIds.slice();
        persist(); renderScope();
    });
    persist(); renderScope();
})();
