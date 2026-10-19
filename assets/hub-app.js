'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const SVG = 'http://www.w3.org/2000/svg';
  const datasetEvidencePage = ['benchmark', 'leaderboard'].includes(document.body.dataset.page);
  const datasetFilterPage = datasetEvidencePage || document.body.dataset.page === 'datasets';
  const state = { scenario: 'all', history: 'all', product: 'all', context: 'R13_visuelle6', dataset: datasetEvidencePage ? 'VISUELLE-v1' : 'all', predecessors: false, query: '', news: 'all' };
  // Editorial defaults preserve one source-table context, never a pooled dataset ranking.
  const featuredComparisons = { 'VISUELLE-v1': 'R13_visuelle6', 'VISUELLE-2.0': 'visuelle2022_so2_10' };
  const MAX_VISIBLE_METHODS = 10;
  let catalog, hub, news, release, resources, orgLogos, survey, portal;
  const surveyState = { dataset: 'all' };
  const palette = ['#b79bff', '#ec78bd', '#9162db', '#f3a0c4', '#bb65b2', '#95a6ff', '#d3b5f5', '#f77e9c', '#b4bfff', '#d879de'];
  function methodColor(row, group) {
    return palette[Math.max(0, group.rows.findIndex(item => item.id === row.id)) % palette.length];
  }
  function paint(node, row, group) { node.style.setProperty('--method-color', methodColor(row, group)); return node; }
  function freshBadge(recordId) {
    if (release?.predecessor_verified !== true || release.reviewed !== true || release.badge_days !== 14 || !Array.isArray(release.changes)) return null;
    const change = release.changes.find(item => item.record_id === recordId);
    if (!change || !['new', 'updated'].includes(change.change_kind) || !['source_checked_provisional', 'reviewed'].includes(change.review_status)) return null;
    const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
    const evidenceUrl = value => { try { const parsed = new URL(value); return typeof value === 'string' && ['http:', 'https:'].includes(parsed.protocol) && !!parsed.hostname; } catch { return false; } };
    if (typeof change.review_id !== 'string' || !change.review_id.trim() || typeof change.change_reason !== 'string' || !change.change_reason.trim() || !Array.isArray(change.evidence_links) || !change.evidence_links.length || !change.evidence_links.every(evidenceUrl)) return null;
    if (!change.previous_release_id || change.previous_release_id !== release.previous_release_id || change.current_release_id !== release.release_id) return null;
    if (!hash(change.previous_snapshot_sha256) || !hash(change.current_snapshot_sha256) || !hash(change.current_record_sha256)) return null;
    if (change.previous_snapshot_sha256 !== release.previous_snapshot_sha256 || change.current_snapshot_sha256 !== release.current_snapshot_sha256) return null;
    if (change.change_kind === 'new' ? change.previous_record_sha256 !== null : !hash(change.previous_record_sha256) || change.previous_record_sha256 === change.current_record_sha256) return null;
    const at = Date.parse(change.first_published_at), expires = Date.parse(change.badge_expires_at), reviewed = Date.parse(change.reviewed_at), now = Date.now();
    if (![at, expires, reviewed].every(Number.isFinite) || reviewed > at || now < at || expires - at !== 14 * 86400000 || now >= expires) return null;
    const node = badge(change.change_kind === 'new' ? 'New' : 'Updated', 'new-badge');
    node.title = change.change_kind === 'new' ? 'Added in this reviewed release; not a new publication date.' : 'This catalog record changed in this reviewed release.';
    return node;
  }
  const families = {
    pop: 'POP signal pipeline',
    transformer: 'Transformer',
    rnn: 'Neural sequence / fusion',
    diffusion: 'Diffusion pipeline',
    baseline: 'Statistical / donor baseline'
  };

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }
  function svg(tag, attributes = {}, text) {
    const node = document.createElementNS(SVG, tag);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
    if (text !== undefined) node.textContent = String(text);
    return node;
  }
  function badge(text, kind = 'muted') { return el('span', `badge ${kind}`, text); }
  function link(text, url, cls = 'text-link') {
    const node = el('a', cls, text);
    try {
      const parsed = new URL(url, location.href);
      if (!['https:', 'http:'].includes(parsed.protocol)) return el('span', '', text);
      node.href = parsed.href;
      if (parsed.origin !== location.origin) { node.target = '_blank'; node.rel = 'noopener noreferrer'; }
    } catch { return el('span', '', text); }
    return node;
  }
  function paperAccess(paperId, fallbackUrl) {
    const resource = resources?.papers?.[paperId];
    const node = el('span', 'paper-access');
    node.append(link(resource?.label || 'Read paper ↗', resource?.pdf_url || fallbackUrl));
    if (resource?.access_note) { const note = el('span', 'access-note', resource.access_note); node.append(note); }
    return node;
  }
  function sources(items) {
    const node = el('div', 'source-list');
    for (const item of items || []) node.append(link(`${item.id || 'Primary'} source ↗`, item.url));
    return node;
  }
  function empty(title, copy) {
    const node = el('div', 'empty-state');
    node.append(el('h3', '', title));
    if (copy) node.append(el('p', '', copy));
    return node;
  }
  function text(id, value) { if ($(id)) $(id).textContent = value; }
  function historyFits(track) { return state.history === 'all' || track === state.history; }
  function scenarioFits(tags = {}) {
    if (state.scenario === 'existing' && tags.store_context !== 'existing') return false;
    if (state.scenario === 'new_store' && tags.store_context !== 'new') return false;
    if (state.scenario === 'new_pair' && tags.product_location_pair !== 'new') return false;
    return state.product === 'all' || tags.seasonal_or_replenishable === state.product;
  }
  function hasStratumFilter() { return state.scenario !== 'all' || state.product !== 'all'; }
  function historyLabel(group) { return group.context.track === 'N0' ? 'Zero history' : group.context.history_days === 14 ? '2 weeks of sales' : `${group.context.history_days} days of sales`; }
  function comparisonName(group) {
    return ({ R13_visuelle6: 'MuQAR', R14_visuelle6: 'Dif4FF', R15_visuelle6: 'MDiFF', visuelle2022_so2_10: 'VISUELLE 2.0', R09_release6: 'GTM · older paper' })[group.id] || group.title;
  }
  function score(value) { return value.toLocaleString(undefined, { maximumFractionDigits: 3 }); }
  function inputs(row) { return row.features.map(value => value.replaceAll('_', ' ')).join(' · '); }
  function family(row) {
    if (/\bPOP\b/i.test(row.method)) return 'pop';
    if (/diff|dif4ff/i.test(row.method)) return 'diffusion';
    if (/muqar|rnn|lstm|cnn/i.test(row.method)) return 'rnn';
    if (/transformer|\bGTM\b/i.test(row.method)) return 'transformer';
    return 'baseline';
  }
  function shortMethod(name) {
    return name.replace(/\s*\((?:paper|cited) comparator\)/g, '')
      .replace('GTM-Transformer + Google Trends', 'GTM + Trends')
      .replace('GTM-Transformer, no exogenous signal', 'GTM · no signal')
      .replace('GTM-Transformer + Fashion IQ tags', 'GTM + Fashion IQ')
      .replace('GTM-Transformer', 'GTM')
      .replace('Cross-Attention RNN', 'Cross-Attn RNN')
      .replace('Concat Multimodal RNN', 'Concat RNN')
      .replace('Simple exponential smoothing', 'SES')
      .replace('Last-observation naive', 'Last-value naive');
  }
  function filterParams() {
    const params = new URLSearchParams();
    if (datasetFilterPage) {
      if (state.dataset && state.dataset !== 'all') params.set('dataset', state.dataset);
      return params;
    }
    if (state.scenario !== 'all') params.set('scenario', state.scenario);
    if (state.history !== 'all') params.set('history', state.history);
    if (state.product !== 'all') params.set('product', state.product);
    if (state.context && state.context !== 'R13_visuelle6') params.set('context', state.context);
    if (state.dataset !== 'all') params.set('dataset', state.dataset);
    if (state.predecessors) params.set('predecessors', '1');
    return params;
  }
  function updateQuery() {
    const params = filterParams();
    history.replaceState(null, '', location.pathname + (params.size ? `?${params}` : '') + location.hash);
  }
  function currentPaper(sourceId, dates = surveyDates()) {
    const paper = portal?.papers?.[sourceId];
    return !!paper && paper.auxiliary_only !== true && surveyPeriod(paper, dates) === 'recent';
  }
  function currentDatasets() {
    const dates = surveyDates();
    return (catalog?.datasets || []).filter(dataset => portal?.datasets?.[dataset.id]?.source_ids?.some(id => currentPaper(id, dates)));
  }
  function currentComparison(group) {
    const meta = portal?.comparison_groups?.[group.id];
    return !!meta && meta.source_id === group.source.id && currentPaper(meta.source_id);
  }
  function renderWindow() {
    const dates = surveyDates();
    for (const node of document.querySelectorAll('.portal-window')) node.textContent = `Five-year view ${dates.start}–${dates.end}. Evidence as of 2026-10-11 (partial, bounded check). No completed five-year baseline search yet.`;
  }
  function chooseDatasetContext() {
    const picker = $('evidence-dataset-select'), available = currentDatasets();
    let dataset = available.find(item => item.id === state.dataset || datasetName(item) === state.dataset);
    if (!dataset) dataset = available.find(item => item.id === 'VISUELLE-v1') || available[0];
    state.dataset = dataset?.id || '';
    picker.replaceChildren();
    for (const item of available) picker.append(new Option(datasetName(item), item.id));
    if (!available.length) picker.append(new Option('No datasets available', ''));
    picker.disabled = !available.length; picker.value = state.dataset;
    const groups = dataset ? hub.paper_groups.filter(group => group.context.dataset === datasetName(dataset) && currentComparison(group)) : [];
    const selected = groups.find(group => group.id === featuredComparisons[state.dataset]) || groups[0];
    state.context = selected?.id || '';
    return selected;
  }

  function matchingRows(group) {
    if (!group) return [];
    return group.rows.filter(row => !state.query || `${row.method} ${inputs(row)}`.toLowerCase().includes(state.query))
      .slice().sort((a, b) => a.metrics.WAPE - b.metrics.WAPE || a.method.localeCompare(b.method));
  }
  function selectedRows(group) { return matchingRows(group).slice(0, MAX_VISIBLE_METHODS); }
  function announce(row) {
    text('chart-status', `${row.method} · WAPE ${score(row.metrics.WAPE)}% · ${inputs(row)}.`);
    for (const mark of document.querySelectorAll('[data-chart-row]')) mark.setAttribute('data-selected', String(mark.dataset.chartRow === row.id));
  }
  function interactive(mark, row) {
    mark.classList.add('chart-hit-target');
    mark.setAttribute('tabindex', '0');
    mark.setAttribute('role', 'button');
    mark.setAttribute('aria-label', `${row.method}, WAPE ${score(row.metrics.WAPE)} percent. Inputs: ${inputs(row)}.`);
    mark.setAttribute('data-chart-row', row.id);
    mark.append(svg('title', {}, `${row.method}\nWAPE ${score(row.metrics.WAPE)}%\n${inputs(row)}\nPaper-reported, not reproduced.`));
    mark.addEventListener('click', () => announce(row));
    mark.addEventListener('focus', () => announce(row));
    mark.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); announce(row); }
    });
    return mark;
  }
  function chartRoot(id, width, height, title, group) {
    const chart = svg('svg', { viewBox: `0 0 ${width} ${height}`, width, height, class: 'chart-svg', role: 'group', 'aria-labelledby': `${id}-title ${id}-description` });
    chart.style.minWidth = `${width}px`;
    chart.append(svg('title', { id: `${id}-title` }, title),
      svg('desc', { id: `${id}-description` }, `${group.title}. ${historyLabel(group)}; ${group.context.horizon_weeks}-week forecast horizon. One source table, WAPE lower is better. Focus or select a mark for the reported value and inputs. No lab runs or cross-paper ranking.`));
    return chart;
  }
  function scaleMaximum(rows) {
    const max = Math.max(...rows.map(row => row.metrics.WAPE), 1);
    const rough = max / 4, magnitude = 10 ** Math.floor(Math.log10(rough));
    const step = [1, 2, 2.5, 5, 10].find(value => value * magnitude >= rough) * magnitude;
    return { max: Math.ceil(max / step) * step, step };
  }
  function wrapLabel(label, maxLength = 17) {
    const lines = [''];
    for (const word of label.split(/\s+/)) {
      const index = lines.length - 1;
      if (lines[index] && lines[index].length + word.length + 1 > maxLength) lines.push(word);
      else lines[index] += `${lines[index] ? ' ' : ''}${word}`;
    }
    if (lines.length > 3) return [lines[0], lines[1], `${lines.slice(2).join(' ').slice(0, maxLength - 1)}…`];
    return lines;
  }
  function barChart(group, rows) {
    const width = Math.max(800, rows.length * 155 + 85), height = 430;
    const left = 64, right = width - 25, top = 30, bottom = 300;
    const chart = chartRoot('reported-bars', width, height, 'Paper-reported WAPE by method', group);
    const domain = scaleMaximum(rows), plotHeight = bottom - top;
    for (let tick = 0; tick <= domain.max + domain.step / 100; tick += domain.step) {
      const y = bottom - tick / domain.max * plotHeight;
      chart.append(svg('line', { x1: left, y1: y, x2: right, y2: y, class: tick === 0 ? 'chart-axis-line' : 'chart-grid-line' }),
        svg('text', { x: left - 12, y: y + 4, class: 'chart-tick', 'text-anchor': 'end' }, score(tick)));
    }
    chart.append(svg('text', { x: 17, y: (top + bottom) / 2, transform: `rotate(-90 17 ${(top + bottom) / 2})`, class: 'chart-axis-label', 'text-anchor': 'middle' }, 'WAPE (%)'));
    const slot = (right - left) / rows.length, barWidth = Math.min(58, slot * 0.58);
    rows.forEach((row, index) => {
      const x = left + slot * (index + 0.5), y = bottom - row.metrics.WAPE / domain.max * plotHeight;
      const mark = paint(svg('rect', { x: x - barWidth / 2, y, width: barWidth, height: Math.max(1, bottom - y), rx: 3, class: `chart-bar family-${family(row)}` }), row, group);
      chart.append(interactive(mark, row), svg('text', { x, y: Math.max(18, y - 10), class: 'chart-value', 'text-anchor': 'middle' }, score(row.metrics.WAPE)));
      const label = svg('text', { x, y: bottom + 25, class: 'chart-method-label', 'text-anchor': 'middle' });
      label.append(svg('title', {}, row.method));
      wrapLabel(shortMethod(row.method)).forEach((line, lineIndex) => label.append(svg('tspan', { x, dy: lineIndex ? 16 : 0 }, line)));
      chart.append(label);
    });
    chart.append(svg('text', { x: (left + right) / 2, y: height - 17, class: 'chart-axis-label', 'text-anchor': 'middle' }, 'Methods · WAPE (%) ↓'));
    return chart;
  }
  function dotChart(group, rows) {
    const width = 1000, height = Math.max(330, rows.length * 44 + 100);
    const left = 390, right = width - 70, top = 30, bottom = height - 60;
    const chart = chartRoot('reported-dots', width, height, 'Reported forecasting performance within one evaluation setting', group);
    const domain = scaleMaximum(rows);
    for (let tick = 0; tick <= domain.max + domain.step / 100; tick += domain.step) {
      const x = left + tick / domain.max * (right - left);
      chart.append(svg('line', { x1: x, y1: top - 8, x2: x, y2: bottom, class: tick === 0 ? 'chart-axis-line' : 'chart-grid-line' }),
        svg('text', { x, y: bottom + 24, class: 'chart-tick', 'text-anchor': 'middle' }, score(tick)));
    }
    const slot = (bottom - top) / rows.length;
    rows.forEach((row, index) => {
      const y = top + slot * (index + 0.5), x = left + row.metrics.WAPE / domain.max * (right - left);
      const label = svg('text', { x: left - 18, y: y + 4, class: 'chart-method-label', 'text-anchor': 'end' }, shortMethod(row.method));
      label.append(svg('title', {}, row.method));
      chart.append(label, interactive(paint(svg('circle', { cx: x, cy: y, r: 7, class: `chart-dot family-${family(row)}` }), row, group), row),
        svg('text', { x: x + 13, y: y + 4, class: 'chart-value' }, score(row.metrics.WAPE)));
    });
    chart.append(svg('text', { x: (left + right) / 2, y: height - 9, class: 'chart-axis-label', 'text-anchor': 'middle' }, 'WAPE (%) · lower is better'));
    return chart;
  }
  function renderLegend(rows) {
    const host = $('chart-legend');
    if (!host) return;
    host.replaceChildren();
    for (const key of [...new Set(rows.map(family))]) {
      const item = el('span', 'chart-legend-item');
      item.append(el('span', `legend-swatch family-${key}`), el('span', '', families[key]));
      host.append(item);
    }
  }
  function tableShell(caption, headers) {
    const table = el('table', 'result-table compact-table');
    table.append(el('caption', 'sr-only', caption));
    const head = el('thead'), row = el('tr');
    for (const heading of headers) { const cell = el('th', '', heading); cell.scope = 'col'; row.append(cell); }
    head.append(row); table.append(head);
    return { table, body: el('tbody') };
  }
  function mountTable(host, table) {
    if (host.tagName === 'TABLE') { host.classList.add('result-table', 'compact-table'); host.replaceChildren(...table.childNodes); }
    else { const scroll = el('div', 'table-scroll'); scroll.append(table); host.replaceChildren(scroll); }
  }
  function resultTable(group, rows) {
    const { table, body } = tableShell(`${group.title}. Paper-reported WAPE; lower is better. No shared benchmark ranking.`, ['Method', 'WAPE ↓', 'Inputs']);
    for (const row of rows) {
      const tr = el('tr'), name = el('td', 'method-cell'), icon = paint(el('span', `method-icon family-${family(row)}`, '●'), row, group);
      icon.setAttribute('aria-hidden', 'true'); const label = el('span', 'method-name', shortMethod(row.method)); label.title = row.method; name.append(icon, label); const fresh = freshBadge(row.id); if (fresh) name.append(fresh);
      tr.append(name, el('td', 'score-cell', `${score(row.metrics.WAPE)}%`), el('td', 'inputs-cell', inputs(row))); body.append(tr);
    }
    table.append(body); return table;
  }
  function renderEvidence() {
    if (!hub || !catalog || !$('evidence-dataset-select')) return;
    const group = chooseDatasetContext(), matches = matchingRows(group), rows = selectedRows(group);
    if ($('full-leaderboard-link')) {
      const params = filterParams();
      $('full-leaderboard-link').href = `/leaderboard/${params.size ? `?${params}` : ''}`;
    }
    $('context-source').replaceChildren();
    evidenceVisible(!!rows.length);
    if (!group) {
      text('context-summary', '');
      text('filter-status', '');
      showEvidenceEmpty('No comparison in this catalog yet.', 'Choose another dataset.');
      renderLegend([]); return;
    }
    text('context-summary', `${comparisonName(group)} · ${group.source.first_public_year} · ${historyLabel(group)} · ${group.context.horizon_weeks}-week forecast${group.group_label ? ` · ${group.group_label}; PDF page UNVERIFIED` : ""}`);
    const reported = badge('Paper results'); reported.title = 'Reported in the linked paper; not reproduced by XferAI. Inputs may differ by method.';
    reported.append(el('span', 'sr-only', ` · ${reported.title}`));
    $('context-source').append(reported, paperAccess(group.source.id, group.source.url));
    const count = matches.length > MAX_VISIBLE_METHODS ? `${rows.length} of ${matches.length}` : String(rows.length);
    text('filter-status', `${count} methods`);
    const fresh = freshBadge(group.id); if (fresh && $('filter-status')) $('filter-status').append(' ', fresh);
    text('chart-status', '');
    if (!rows.length) {
      showEvidenceEmpty('No matching method.', 'Choose another dataset.');
      renderLegend([]); return;
    }
    if ($('leaderboard-content')) mountTable($('leaderboard-content'), resultTable(group, rows));
    if ($('bar-chart')) $('bar-chart').replaceChildren(barChart(group, rows));
    if ($('dot-chart')) $('dot-chart').replaceChildren(dotChart(group, rows));
    renderLegend(rows);
  }
  function evidenceVisible(visible) {
    for (const node of document.querySelectorAll('body[data-page="benchmark"] .chart-section')) node.hidden = !visible;
    for (const id of ['leaderboard-content', 'chart-status']) if ($(id)) $(id).hidden = !visible;
    if ($('evidence-empty')) { $('evidence-empty').hidden = visible; $('evidence-empty').replaceChildren(); }
    if (!visible) for (const id of ['leaderboard-content', 'bar-chart', 'dot-chart']) if ($(id)) $(id).replaceChildren();
  }
  function showEvidenceEmpty(title, copy) {
    if ($('evidence-empty')) $('evidence-empty').replaceChildren(empty(title, copy));
  }
  function renderDatasets() {
    const host = $('dataset-table');
    if (!host || !catalog) return;
    const available = currentDatasets();
    if (!available.some(dataset => dataset.id === state.dataset)) state.dataset = 'all';
    const picker = $('dataset-select');
    if (picker) {
      picker.replaceChildren(new Option('All datasets', 'all'));
      for (const dataset of available) picker.append(new Option(datasetName(dataset), dataset.id));
      picker.disabled = available.length === 0; picker.value = state.dataset;
    }
    const rows = available.filter(dataset => state.dataset === 'all' || dataset.id === state.dataset);
    text('dataset-status', `${rows.length} ${rows.length === 1 ? 'dataset' : 'datasets'}`);
    if (!rows.length) { host.replaceChildren(empty('No dataset in this five-year view yet.')); return; }
    const { table, body } = tableShell('Data used by current-window papers. Available modalities are not all required by every method.', ['Dataset', 'Data inputs', 'Forecast target', 'Get data']);
    for (const dataset of rows) {
      const meta = portal.datasets[dataset.id];
      const access = resources?.datasets?.[dataset.name];
      const row = el('tr'), dataCell = el('td', 'source-cell');
      if (access?.access_url) { const action = link(access.button, access.access_url); action.title = access.note; dataCell.append(action); }
      else dataCell.append(el('span', 'access-unavailable', access ? 'Not public' : 'Access unverified'));
      const name = el('td', 'method-cell'); name.append(link(datasetName(dataset), `/survey/`, 'dataset-name-link'));
      name.append(el('span', 'dataset-history', datasetHistory(dataset))); name.title = dataset.name;
      const fresh = freshBadge(dataset.id || dataset.name); if (fresh) name.append(fresh);
      const modality = el('td', 'dataset-modality', meta.data_class_label); modality.title = [meta.time_series_role, meta.images_role, meta.metadata_role].join(' ');
      row.append(name, modality, el('td', 'inputs-cell', meta.forecast_target), dataCell); body.append(row);
    }
    table.append(body); mountTable(host, table);
  }
  function datasetHistory(dataset) {
    if (dataset.name === 'VISUELLE-2.0') return '2 weeks in featured comparison';
    if (dataset.name === 'Myntra-private-new-styles') return 'New / unseen items';
    if (dataset.tracks.includes('N0') && dataset.tracks.includes('K')) return 'Zero / early history';
    if (dataset.tracks.includes('K')) return 'Early history';
    return dataset.tracks.includes('N0') ? 'Zero history' : 'See source';
  }
  function datasetName(dataset) {
    return ({'VISUELLE-v1':'VISUELLE', 'VISUELLE-2.0':'VISUELLE 2.0', 'Myntra-private-new-styles':'Myntra', 'European-bags-censored-private':'European bags'})[dataset.name] || dataset.name;
  }

  function newsCategory(item) {
    const category = item.category.toLowerCase();
    if (category.includes('event') || category.includes('competition')) return 'event';
    if (category.includes('dataset') || category.includes('code')) return 'dataset';
    if (category.includes('paper')) return 'paper';
    if (category.includes('industry') || category.includes('guide')) return 'industry';
    if (category.includes('product')) return 'product';
    return category;
  }
  function displayDate(item) {
    const raw = item.event_start || item.published_at, precision = item.date_precision || '';
    if (!raw) return 'Date unverified';
    if (precision.includes('month') || precision.startsWith('journal_issue')) return raw.slice(0, 7);
    return raw;
  }
  function dateLabel(item) {
    const precision = item.date_precision || '';
    if (item.event_start) return 'Recorded event';
    if (precision.startsWith('journal_issue')) return 'Journal issue';
    if (precision.includes('not_code_release')) return 'Paper submission; code release date unverified';
    if (precision.includes('arxiv_submission')) return 'Paper submission';
    return 'Published';
  }
  function newsCard(item) {
    const card = el('article', 'news-card'), top = el('div', 'news-top'), body = el('div', 'news-body');
    top.append(el('span', '', item.category), el('span', '', displayDate(item)));
    const fresh = freshBadge(item.id); if (fresh) top.append(fresh);
    body.append(el('h3', '', item.short_title || item.title), el('p', '', item.short_summary || item.summary));
    if (item.short_status) body.append(el('p', 'fine-print', item.short_status));
    const paperId = resources?.news_papers?.[item.id];
    if (item.id === 'visuelle2-2022') body.append(link('Access data ↗', resources?.datasets?.['VISUELLE-2.0']?.access_url || item.url));
    if (paperId) body.append(paperAccess(paperId, item.url));
    else body.append(link('Source ↗', item.url));
    if (item.id === 'mdiff-2024' && item.source_urls?.[0]) body.append(link('Code ↗', item.source_urls[0]));
    if (paperId === 'censored2025') body.append(link('Article ↗', item.url));
    card.append(top, body); return card;
  }
  function renderIndustries() {
    const host = $('industry-cards'); if (!host || !orgLogos?.logos) return;
    const run = el('div', 'ticker-group');
    const visible = orgLogos.logos.filter(org => org.display_in_ticker !== false && ((org.ticker_scope === 'historical_lineage' && org.requested_display_on && org.source_url && org.paper_ids?.length) || (org.paper_ids || []).some(id => currentPaper(id)) || (org.industry_source_ids || []).some(id => portal?.industry_sources?.some(source => source.id === id && surveyPeriod(source, surveyDates()) === 'recent'))));
    for (const org of visible) {
      const chip = link('', org.source_url, 'industry-chip org-logo');
      chip.title = org.relationship;
      chip.setAttribute('aria-label', `${org.name}: ${org.ticker_scope === 'historical_lineage' ? 'historical research source' : 'research source'}`);
      const img = el('img'); img.src = org.image; img.alt = org.name;
      chip.append(img); const caption = org.caption || (org.id === 'ibm-research' ? 'Research' : ''); if (caption) chip.append(el('span', 'org-caption', caption)); run.append(chip);
    }
    const copy = run.cloneNode(true); copy.setAttribute('aria-hidden', 'true');
    for (const anchor of copy.querySelectorAll('a')) anchor.tabIndex = -1;
    host.replaceChildren(run, copy);
  }
  function renderVenueWatch() {
    const host = $('venue-watch'); if (!host || !news?.venue_watch) return;
    const list = el('div', 'venue-watch-list');
    for (const venue of news.venue_watch) {
      const item = el('div', 'venue-watch-item'); item.append(venue.official_url ? link(venue.name, venue.official_url) : el('span', '', venue.name), el('span', 'venue-status', venue.short_status)); list.append(item);
    }
    host.replaceChildren(list);
  }
  function renderNews() {
    if (!news) return;
    const industry = (portal?.industry_sources || []).filter(item => surveyPeriod(item, surveyDates()) === 'recent').map(item => ({
      id: item.id, title: item.title, short_title: item.title, category: item.source_type === 'industry_paper_pending' ? 'Paper' : 'Industry guide',
      published_at: item.first_public_date, date_precision: item.date_precision, summary: item.summary, short_summary: item.summary,
      short_status: item.show_in_survey ? 'Industry guidance · Not benchmarked' : item.scope_status === 'implementation_context' ? 'Industry deployment context · Cold-start results not isolated' : 'Launch-history limit unverified · Review queue',
      url: item.pdf?.url || item.full_text_url || item.paper_url
    }));
    const records = [...industry, ...news.items];
    if ($('home-news')) {
      const ordered = records.filter(item => {
        const first = item.event_start || item.published_at;
        return first && surveyPeriod({first_public_date: first.length === 10 ? first : null, first_public_year: Number(first.slice(0,4))}, surveyDates()) === 'recent';
      });
      $('home-news').replaceChildren(...ordered.slice(0, 6).map(newsCard));
    }
    if ($('news-grid')) {
      const rows = records.filter(item => state.news === 'all' || newsCategory(item) === state.news);
      text('news-status', `${rows.length} records · partial coverage · Industry checked ${portal?.metadata_checked_on || 'date unavailable'}`);
      $('news-grid').replaceChildren(...(rows.length ? rows.map(newsCard) : [empty('No verified update yet.')]));
    }
    renderVenueWatch();
  }
  function surveyDates(now = new Date()) {
    const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now).map(part => [part.type, part.value]));
    const year = Number(parts.year), month = Number(parts.month), day = Number(parts.day);
    const start = new Date(Date.UTC(year - 5, month - 1, day));
    if (start.getUTCMonth() !== month - 1) start.setUTCDate(0);
    return { start: start.toISOString().slice(0, 10), end: `${parts.year}-${parts.month}-${parts.day}`, startYear: year - 5, endYear: year };
  }
  function surveyPeriod(paper, dates) {
    if (paper.first_public_date) {
      if (paper.first_public_date > dates.end) return 'future';
      return paper.first_public_date >= dates.start ? 'recent' : 'older';
    }
    if (!Number.isInteger(paper.first_public_year)) return 'uncertain';
    const earliest = `${paper.first_public_year}-01-01`, latest = `${paper.first_public_year}-12-31`;
    if (latest < dates.start) return 'older';
    if (earliest > dates.end) return 'future';
    return earliest >= dates.start && latest <= dates.end ? 'recent' : 'uncertain';
  }
  function normalized(value) { return String(value || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase(); }
  function relevance(paper, query) {
    const terms = normalized(query).match(/[\p{L}\p{N}]+/gu) || [];
    if (!terms.length) return 1;
    const fields = [
      [paper.title, 8], [paper.recipe, 6], [(paper.method_ids || []).join(' '), 6], [(paper.datasets || []).join(' '), 5],
      [paper.summary, 4], [paper.history_label, 3], [(paper.strengths || []).join(' '), 2],
      [(paper.limitations || []).join(' '), 1], [paper.venue?.label, 2], [paper.horizon, 1],
      [Array.isArray(paper.authors) ? paper.authors.join(' ') : paper.authors, 2], [paper.organization, 6], [paper.modality_label, 2],
      ['coldstart cold start forecasting new product demand forecasting', 1]
    ].map(([value, weight]) => [normalized(value).match(/[\p{L}\p{N}]+/gu) || [], weight]);
    let total = 0;
    for (const term of terms) {
      const weights = fields.map(([words, weight]) => words.includes(term) ? weight * 3 : words.some(word => word.startsWith(term)) ? weight : 0);
      const best = Math.max(...weights);
      if (!best) return 0;
      total += best;
    }
    return total;
  }
  function surveyPaper(paper, period) {
    const card = el('article', 'survey-paper'), meta = el('div', 'survey-paper-meta');
    meta.append(el('span', '', paper.venue?.label || String(paper.year)));
    const industry = paper.source_type && paper.source_type !== 'paper';
    if (industry) meta.append(badge('Industry guidance'));
    if (paper.status === 'rejected_for_admission_leak_unresolvable') meta.append(badge('Rejected for admission'));
    if (period === 'older') meta.append(badge('Older lineage'));
    if (period === 'uncertain') meta.append(badge('Date needs checking'));
    const fresh = freshBadge(paper.id); if (fresh) meta.append(fresh);
    const readUrl = paper.full_text_url || paper.pdf?.url || paper.paper_url;
    const title = el('h2'); title.append(link(paper.title, readUrl, ''));
    const history = industry ? paper.history_label : paper.tracks.includes('N0') ? 'Zero history' : paper.history?.observed_weekly_points === 2 && paper.history?.launch_age_days === 14 ? '2 weeks of sales' : paper.history_label;
    const datasets = (paper.datasets || []).map(name => datasetName({name})).join(', ') || 'See source';
    card.append(meta, title, el('p', 'survey-fit', `${history} · ${industry ? paper.modality_label : datasets}`), el('p', '', paper.summary));
    if (paper.rejection_note) card.append(el('p', 'survey-fit', paper.rejection_note));
    const details = el('details'), summary = el('summary', '', 'Strengths & limits');
    details.append(summary);
    if (paper.strengths?.[0]) details.append(el('p', '', `Strength: ${paper.strengths[0]}`));
    for (const limitation of paper.limitations || []) details.append(el('p', '', limitation));
    details.append(el('p', '', `Forecast: ${paper.horizon}`), el('p', '', `First public: ${paper.first_public_date || `${paper.first_public_year} (exact date unverified)`}. Publication year: ${paper.year}.`), el('p', '', paper.date_note), el('p', '', `${paper.version} · ${paper.locator}`));
    details.append(link('Publication ↗', paper.paper_url));
    card.append(details);
    const actions = el('div', 'survey-links');
    actions.append(link(industry ? paper.action_label || 'Read source ↗' : paper.pdf?.label || 'Read paper ↗', readUrl));
    if (paper.pdf?.access_note) actions.append(el('span', 'access-note', paper.pdf.access_note));
    card.append(actions); return card;
  }
  function renderSurvey() {
    const host = $('survey-results'); if (!host || !survey || !portal) return;
    const dates = surveyDates();
    const papers = survey.papers.filter(paper => portal.papers[paper.id]).map(paper => ({...paper, ...portal.papers[paper.id], source_type: 'paper'}));
    const guidance = portal.industry_sources.filter(source => source.show_in_survey === true && source.scope_status === 'direct_new_item_provisional' && source.tracks.length && source.source_type !== 'industry_paper_pending');
    const all = [...papers, ...guidance].map(paper => ({ paper, period: surveyPeriod(paper, dates) })).filter(item => item.period !== 'future');
    const picker = $('survey-dataset-select');
    if (picker && picker.options.length <= 1) {
      const names = [...new Set(papers.flatMap(paper => paper.datasets || []))].sort();
      for (const name of names) picker.append(new Option(datasetName({name}), name));
      picker.value = surveyState.dataset;
    }
    const rows = all.filter(item => surveyState.dataset === 'all' || (item.paper.datasets || []).includes(surveyState.dataset));
    rows.sort((a, b) => (b.paper.first_public_year - a.paper.first_public_year) || a.paper.title.localeCompare(b.paper.title));
    text('survey-window', `Five-year view ${dates.start}–${dates.end}. Evidence as of 2026-10-11 (partial, bounded check). No completed five-year baseline search yet.`);
    const coverage = survey.coverage || {};
    const cadence = 'Weekly refresh planned; not yet scheduled';
    text('survey-cadence', `${cadence} · ${coverage.last_successful_weekly_refresh ? `Last completed: ${coverage.last_successful_weekly_refresh}` : 'First weekly refresh pending'}`);
    text('survey-status', `${rows.length} ${rows.length === 1 ? 'source' : 'sources'}`);
    host.replaceChildren(...(rows.length ? rows.map(item => surveyPaper(item.paper, item.period)) : [empty('No matching source in this catalog yet.', 'Choose another dataset.')]));
  }
  function render() { renderWindow(); renderEvidence(); renderDatasets(); }
  function loadingError(ids, message) {
    for (const id of ids) if ($(id)) $(id).replaceChildren(empty('The snapshot could not load.', message));
  }
  const menu = $('menu-toggle');
  if (menu && $('main-nav')) menu.addEventListener('click', () => {
    const open = menu.getAttribute('aria-expanded') !== 'true';
    menu.setAttribute('aria-expanded', String(open)); $('main-nav').classList.toggle('open', open);
  });
  const params = new URLSearchParams(location.search);
  if ($('survey-dataset-select')) {
    $('survey-dataset-select').addEventListener('change', event => { surveyState.dataset = event.target.value; renderSurvey(); });
  }

  if (!datasetFilterPage && params.get('context')) state.context = params.get('context');
  if ($('dataset-select') && params.get('dataset')) state.dataset = params.get('dataset');
  if ($('evidence-dataset-select')) {
    if (params.get('dataset')) state.dataset = params.get('dataset');
    $('evidence-dataset-select').addEventListener('change', event => { state.dataset = event.target.value; renderEvidence(); updateQuery(); });
  }
  if ($('predecessors')) {
    state.predecessors = params.get('predecessors') === '1'; $('predecessors').checked = state.predecessors;
    $('predecessors').addEventListener('change', event => { state.predecessors = event.target.checked; render(); updateQuery(); });
  }
  for (const [id, key] of [['scenario', 'scenario'], ['history', 'history'], ['product-type', 'product']]) {
    const node = $(id); if (!node) continue;
    const value = params.get(key) || 'all';
    if ([...node.options].some(option => option.value === value)) node.value = state[key] = value;
    node.addEventListener('change', () => { state[key] = node.value; render(); updateQuery(); });
  }
  if ($('scenario-filters')) $('scenario-filters').addEventListener('submit', event => event.preventDefault());
  if ($('reset-filters')) $('reset-filters').addEventListener('click', () => {
    state.scenario = state.history = state.product = state.dataset = 'all'; state.query = ''; state.context = 'R13_visuelle6'; state.predecessors = false;
    for (const id of ['scenario', 'history', 'product-type']) if ($(id)) $(id).value = 'all';
    if ($('search')) $('search').value = '';
    if ($('predecessors')) $('predecessors').checked = false;
    render(); updateQuery();
  });
  if ($('comparison-select')) $('comparison-select').addEventListener('change', event => { state.context = event.target.value; renderEvidence(); updateQuery(); });
  if ($('dataset-select')) $('dataset-select').addEventListener('change', event => { state.dataset = event.target.value; renderDatasets(); updateQuery(); });
  if ($('search')) $('search').addEventListener('input', event => { state.query = event.target.value.trim().toLowerCase(); renderEvidence(); });
  for (const button of document.querySelectorAll('[data-news]')) button.addEventListener('click', () => {
    state.news = button.dataset.news;
    for (const peer of document.querySelectorAll('[data-news]')) peer.setAttribute('aria-pressed', String(peer === button));
    renderNews();
  });
  async function json(path) {
    const response = await fetch(path, { cache: 'no-cache' });
    if (!response.ok) throw Error(`Unavailable snapshot: ${path}`);
    return response.json();
  }
  Promise.allSettled([json('/assets/catalog.json'), json('/assets/benchmark-hub.json'), json('/assets/news.json'), json('/assets/release.json'), json('/assets/resources.json'), json('/assets/logos/provenance.json'), $('survey-results') ? json('/assets/survey.json') : Promise.resolve(null), json('/assets/portal-view.json')]).then(results => {
    const [catalogResult, hubResult, newsResult, releaseResult, resourceResult, logoResult, surveyResult, portalResult] = results;
    if (resourceResult.status === 'fulfilled') resources = resourceResult.value;
    if (logoResult.status === 'fulfilled') orgLogos = logoResult.value;
    if (releaseResult.status === 'fulfilled') release = releaseResult.value;
    try {
      if (catalogResult.status !== 'fulfilled' || hubResult.status !== 'fulfilled' || portalResult.status !== 'fulfilled') throw Error('Evidence unavailable');
      const c = catalogResult.value, h = hubResult.value;
      const p = portalResult.value;
      if (p.schema_version !== 1 || p.window?.years !== 5 || p.window?.timezone !== 'America/Los_Angeles' || !p.papers || !p.datasets || !p.comparison_groups || !Array.isArray(p.industry_sources)) throw Error('Shared window contract unavailable');
      for (const source of [...Object.values(p.papers), ...p.industry_sources]) {
        if (!Number.isInteger(source.first_public_year) || source.first_public_year < 1 || source.first_public_year > 9999) throw Error('Invalid source year');
        if (source.first_public_date && (!/^\d{4}-\d{2}-\d{2}$/.test(source.first_public_date) || Number(source.first_public_date.slice(0,4)) !== source.first_public_year || !Number.isFinite(Date.parse(source.first_public_date)))) throw Error('Invalid source date');
      }
      for (const source of p.industry_sources) if (source.admission_ready !== false || source.reproduction_status !== 'not_run' || source.scores != null || source.benchmark_admitted !== false || !Array.isArray(source.tracks) || source.tracks.some(track => !['N0','K'].includes(track)) || (source.show_in_survey && (source.scope_status !== 'direct_new_item_provisional' || !source.tracks.length || source.source_type === 'industry_paper_pending'))) throw Error('Industry review required');
      if (c.mode !== 'literature_review' || h.mode !== 'literature_review' || h.lab_benchmark.executed_runs !== 0 || h.performance_over_time.points.length) throw Error('Reviewed run renderer required');
      for (const group of [...h.paper_groups, ...h.predecessor_groups]) {
        if (group.numeric_ranking_authorized !== false || group.benchmark_admitted !== false) throw Error('Provisional renderer only');
        for (const row of group.rows) if (typeof row.metrics.WAPE !== 'number' || !Number.isFinite(row.metrics.WAPE) || row.metrics.WAPE < 0 || !row.reported_not_reproduced) throw Error('Invalid reported WAPE');
      }
      portal = p; catalog = c; hub = h; render();
      if ($('scenario-filters') || $('evidence-dataset-select') || $('dataset-select')) updateQuery();
      text('method-count', c.summary.candidate_methods); text('paper-count', c.summary.direct_task_fit_papers);
      if ($('metric-source-links')) $('metric-source-links').replaceChildren(...h.metrics.map(metric => link(`${metric.id} definition ↗`, metric.source_url)));
    } catch {
      evidenceVisible(false);
      showEvidenceEmpty('The snapshot could not load.', 'Reload the page.');
      loadingError(['dataset-table'], 'Reload the hosted page or use a local web server. No forecast has run.');
      text('filter-status', 'Evidence unavailable'); text('dataset-status', 'Evidence unavailable'); text('context-summary', 'No results loaded.'); text('chart-status', 'No points shown.');
      for (const id of ['comparison-select', 'dataset-select', 'evidence-dataset-select']) if ($(id)) $(id).disabled = true;
      if ($('context-details')) $('context-details').hidden = true;
    }
    renderIndustries();
    if ($('survey-results')) {
      try {
        const value = surveyResult.status === 'fulfilled' ? surveyResult.value : null;
        if (!portal || value?.schema_version !== 1 || value.mode !== 'literature_review' || !Array.isArray(value.papers)) throw Error('Invalid survey');
        for (const paper of value.papers) if (paper.admission_ready !== false || paper.reproduction_status !== 'not_run' || !paper.tracks?.length || paper.tracks.some(track => !['N0', 'K'].includes(track)) || !Number.isInteger(paper.first_public_year)) throw Error('Unreviewed survey state');
        survey = value; renderSurvey();
      } catch { text('survey-status', 'Survey unavailable'); loadingError(['survey-results'], 'Reload the page.'); }
    }
    if (logoResult.status !== 'fulfilled') loadingError(['industry-cards'], 'Research-source logos are unavailable.');
    if (newsResult.status === 'fulfilled') { news = newsResult.value; renderNews(); }
    else loadingError(['news-grid', 'home-news'], 'The news snapshot is unavailable. Forecast comparisons are loaded separately.');
  });
})();
