/* Offline gallery: compact metadata is eager; complete entry text is read on demand. */
(function (host) {
  'use strict';
  const PAGE_SIZE = 40;

  function filtered(cards, state) {
    const rows = cards.filter(function (card) {
      return (!state.state || [card.status, card.disposition, card.availability].includes(state.state)) &&
        (!state.from || (card.day && card.day >= state.from)) &&
        (!state.to || (card.day && card.day <= state.to));
    });
    return state.order === 'oldest' ? rows.reverse() : rows;
  }

  function pageOf(cards, requested) {
    const pages = Math.ceil(cards.length / PAGE_SIZE);
    const page = Math.max(0, Math.min(Number(requested) || 0, Math.max(0, pages - 1)));
    return {cards: cards.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE), page: page, pages: pages, total: cards.length};
  }

  function createSearch(load) {
    let serial = 0;
    let active = null;
    function cancel() {
      serial += 1;
      if (active) active.abort();
      active = null;
    }
    return {
      cancel: cancel,
      get busy() { return active !== null; },
      run: async function (cards, query, progress) {
        cancel();
        const ticket = serial;
        const controller = new AbortController();
        active = controller;
        const needle = query.trim().toLowerCase();
        const matches = new Set();
        let next = 0, completed = 0, failed = 0;
        async function scan() {
          while (!controller.signal.aborted && next < cards.length) {
            const card = cards[next++];
            try {
              const text = await load(card, controller.signal);
              if (controller.signal.aborted || ticket !== serial) return;
              if (text.toLowerCase().includes(needle)) matches.add(card.key);
            } catch (error) {
              if (controller.signal.aborted || ticket !== serial) return;
              failed += 1;
            }
            completed += 1;
            if (progress && ticket === serial) progress({completed: completed, total: cards.length, failed: failed});
          }
        }
        // Local script reads remain bounded while all recorded entries are searched.
        await Promise.all(Array.from({length: Math.min(4, cards.length)}, scan));
        if (controller.signal.aborted || ticket !== serial) return null;
        active = null;
        return {cards: cards.filter(function (card) { return matches.has(card.key); }), failed: failed};
      }
    };
  }

  function createScriptLoader(document) {
    let sequence = 0;
    const pending = new Map();
    function receive(key, revision, text) {
      const script = document.currentScript;
      const token = script && script.dataset.cpbRequest;
      const request = token && pending.get(token);
      if (!request) return;
      if (key !== request.card.key || revision !== request.card.revision || typeof text !== 'string') {
        request.finish(new Error('Entry changed or search document is invalid; refresh the gallery.'));
      } else {
        request.finish(null, text);
      }
    }
    function load(card, signal) {
      return new Promise(function (resolve, reject) {
        const token = String(++sequence);
        const script = document.createElement('script');
        let settled = false;
        function abort() {
          const error = new Error('Search replaced.');
          error.name = 'AbortError';
          finish(error);
        }
        function finish(error, text) {
          if (settled) return;
          settled = true;
          pending.delete(token);
          signal.removeEventListener('abort', abort);
          script.remove();
          script.onload = null;
          script.onerror = null;
          if (error) reject(error); else resolve(text);
        }
        pending.set(token, {card: card, finish: finish});
        signal.addEventListener('abort', abort, {once: true});
        if (signal.aborted) { abort(); return; }
        script.dataset.cpbRequest = token;
        script.async = true;
        script.src = card.search + '?revision=' + encodeURIComponent(card.revision);
        script.onload = function () { finish(new Error('Search document did not provide the recorded entry.')); };
        script.onerror = function () { finish(new Error('A local search document could not be read.')); };
        document.head.appendChild(script);
      });
    }
    return {load: load, receive: receive};
  }

  function element(document, tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  }

  function renderCard(document, card) {
    const section = element(document, 'section', null, 'iteration ' + (card.status || ''));
    section.dataset.entry = card.entry_id;
    section.dataset.state = card.status || '';
    section.dataset.availability = card.availability || '';
    const image = element(document, 'div', null, 'image');
    if (card.result) {
      const link = element(document, 'a');
      link.href = card.result;
      const img = element(document, 'img');
      img.src = card.result;
      img.alt = card.iteration_id || card.entry_id;
      img.loading = 'lazy';
      img.decoding = 'async';
      link.appendChild(img);
      image.appendChild(link);
    } else {
      image.appendChild(element(document, 'p', 'No local result file', 'none'));
    }
    const facts = element(document, 'div', null, 'facts');
    const title = element(document, 'h2', [card.character, card.slot, card.iteration_id].filter(Boolean).join(' / ') + ' ');
    title.appendChild(element(document, 'span', card.status || 'not recorded', 'status'));
    facts.appendChild(title);
    facts.appendChild(element(document, 'p', 'Received / published ' + (card.at || 'not recorded'), 'when'));
    facts.appendChild(element(document, 'p', 'Model: ' + (card.model || 'not recorded') + '; seed: ' + (card.seed === null || card.seed === undefined ? 'not recorded' : card.seed)));
    const judgment = [card.evaluation && 'Evaluation: ' + card.evaluation, card.disposition && 'Disposition: ' + card.disposition, card.selection_basis && 'Selection basis: ' + card.selection_basis].filter(Boolean).join('; ');
    if (judgment) facts.appendChild(element(document, 'p', judgment));
    if (card.availability === 'unavailable' || card.diagnostic_count) {
      facts.appendChild(element(document, 'p', 'Recorded diagnostic: open the complete details.', 'diagnostic'));
    }
    const detail = element(document, 'a', 'Full details and recorded evidence', 'detail-link');
    detail.href = card.detail;
    facts.appendChild(detail);
    section.appendChild(image);
    section.appendChild(facts);
    return section;
  }

  let loader = null;

  function start(index) {
    const document = host.document;
    const target = document.getElementById('gallery-entries');
    const progress = document.getElementById('gallery-progress');
    if (document.body.dataset.revision !== index.revision) {
      progress.textContent = 'The gallery files changed during loading. Refresh, or run studio.py sync if the warning remains.';
      progress.className = 'diagnostic';
      return;
    }
    loader = createScriptLoader(document);
    const search = createSearch(loader.load);
    const controls = {};
    ['order', 'query', 'state', 'from', 'to', 'auto', 'prev', 'next', 'count'].forEach(function (name) {
      controls[name] = document.getElementById('gallery-' + name);
    });
    const storageKey = 'cpb-gallery:' + document.body.dataset.studio + ':' + host.location.pathname;
    const state = {order: 'newest', query: '', state: '', from: '', to: '', auto: true, page: 0};
    try { Object.assign(state, JSON.parse(host.sessionStorage.getItem(storageKey) || '{}')); } catch (error) { /* optional browser storage */ }
    ['order', 'query', 'state', 'from', 'to'].forEach(function (name) { controls[name].value = state[name]; });
    controls.auto.checked = state.auto;
    let rows = index.cards, debounce = null, failed = 0, completedQuery = null;
    document.getElementById('gallery-summary').textContent = index.cards.length + ' recorded images. Open an entry for complete prompts, settings, history and source files.';
    function save() {
      try { host.sessionStorage.setItem(storageKey, JSON.stringify(state)); } catch (error) { /* browsing does not require storage */ }
    }
    function render() {
      const result = pageOf(filtered(rows, state), state.page);
      state.page = result.page;
      target.replaceChildren.apply(target, result.cards.map(function (card) { return renderCard(document, card); }));
      controls.count.textContent = result.total + ' matches; page ' + (result.pages ? result.page + 1 : 0) + ' / ' + result.pages;
      controls.prev.disabled = result.page === 0;
      controls.next.disabled = result.page + 1 >= result.pages;
      save();
    }
    function completedMessage() {
      progress.className = failed ? 'diagnostic' : '';
      progress.textContent = failed ? 'Search incomplete: ' + failed + ' entry files could not be read or changed. Refresh, or run studio.py sync; displayed matches cover only the readable entries.' :
        (state.query.trim() ? 'Searched the complete recorded details of all ' + index.cards.length + ' entries.' : '');
    }
    async function applyQuery() {
      debounce = null;
      const query = state.query.trim().toLowerCase();
      if (!query) {
        search.cancel();
        rows = index.cards;
        failed = 0;
        completedQuery = null;
        completedMessage();
        render();
        return;
      }
      if (completedQuery === query) { completedMessage(); render(); return; }
      rows = [];
      render();
      progress.className = '';
      progress.textContent = 'Searching complete recorded details: 0 / ' + index.cards.length;
      const result = await search.run(index.cards, query, function (update) {
        progress.textContent = 'Searching complete recorded details: ' + update.completed + ' / ' + update.total +
          (update.failed ? '; ' + update.failed + ' unreadable' : '');
      });
      if (!result) return;
      completedQuery = query;
      rows = result.cards;
      failed = result.failed;
      completedMessage();
      render();
    }
    controls.query.addEventListener('input', function () {
      state.query = controls.query.value;
      state.page = 0;
      completedQuery = null;
      search.cancel();
      if (debounce !== null) host.clearTimeout(debounce);
      rows = [];
      render();
      progress.textContent = state.query.trim() ? 'Waiting to search complete recorded details...' : '';
      debounce = host.setTimeout(applyQuery, 180);
    });
    ['order', 'state', 'from', 'to'].forEach(function (name) {
      controls[name].addEventListener('change', function () {
        state[name] = controls[name].value;
        state.page = 0;
        render();
      });
    });
    controls.auto.addEventListener('change', function () { state.auto = controls.auto.checked; save(); });
    controls.prev.addEventListener('click', function () { state.page -= 1; render(); });
    controls.next.addEventListener('click', function () { state.page += 1; render(); });
    host.setInterval(function () {
      if (state.auto && !document.hidden && !search.busy && debounce === null) host.location.reload();
    }, 30000);
    applyQuery();
  }

  const api = {start: start, filtered: filtered, pageOf: pageOf, createSearch: createSearch,
    createScriptLoader: createScriptLoader, renderCard: renderCard,
    searchDocument: function (key, revision, text) { if (loader) loader.receive(key, revision, text); }};
  host.CPBGallery = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
