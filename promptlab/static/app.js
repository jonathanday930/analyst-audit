/* AnalystAudit prompt lab, client side.
   Prompt edits live in localStorage so a page reload (or an accidental close mid-run) never
   loses a draft; named versions saved to disk via /api/versions are the durable copies.

   The results pane never assumes a shape for what a pass returns. Raw mode prints the model's
   text verbatim; pipeline mode prints the parsed objects as JSON. Both survive a schema change
   in app/llm/schemas.py without needing an edit here. */

const STORAGE_KEY = 'promptlab.draft.v2';
const POLL_MS = 1500;

const MODE_NOTES = {
  raw: '<strong>Raw output.</strong> No output schema is sent, so what you see is exactly what '
     + 'Claude wrote. Use this while the prompt is asking for fields app/llm/schemas.py does not '
     + 'define yet: a structured call would silently refit the answer to the old fields.',
  pipeline: '<strong>Full pipeline.</strong> Answers are fitted to app/llm/schemas.py, then run '
     + 'through ticker resolution, price data, stance snapshots and the claim analyzer. Fields '
     + 'your prompt asks for that the schema does not define are dropped.',
};

const state = {
  passes: [],
  models: [],
  versions: [],
  runs: [],
  activePass: null,
  edits: {},          // passId -> { prompt, model, versionId }
  mode: 'raw',
  selected: {},       // passId -> bool, raw mode only
  run: null,
  pollTimer: null,
  view: 'output',
  pinnedClaimsRunId: null,   // run_id whose claim-finder output this run will reuse
  pinnedClaimsInfo: null,    // { title, url, claim_count } for the banner, set alongside the id
};

const $ = (id) => document.getElementById(id);
const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};
const passById = (id) => state.passes.find((pass) => pass.id === id);

/* --- persistence --------------------------------------------------------------------- */

function loadDraft() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; } catch { return {}; }
}

function saveDraft() {
  const payload = {
    edits: state.edits,
    activePass: state.activePass,
    mode: state.mode,
    selected: state.selected,
    url: $('url').value,
    analyst: $('analyst').value,
    skipAnalysis: state.skipAnalysis,
    useCache: state.useCache,
    pinnedClaimsRunId: state.pinnedClaimsRunId,
    pinnedClaimsInfo: state.pinnedClaimsInfo,
  };
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(payload)); } catch { /* quota; ignore */ }
}

/* --- bootstrap ----------------------------------------------------------------------- */

async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail || detail; } catch { /* non-JSON body */ }
    throw new Error(detail);
  }
  return response.json();
}

async function init() {
  const data = await api('/api/bootstrap');
  state.passes = data.passes;
  state.models = data.models;
  state.versions = data.versions;
  state.runs = data.runs;

  const draft = loadDraft();
  state.passes.forEach((pass) => {
    const saved = (draft.edits || {})[pass.id];
    state.edits[pass.id] = saved || { prompt: pass.default_prompt, model: pass.default_model, versionId: '' };
    state.selected[pass.id] = (draft.selected || {})[pass.id] ?? (pass.id === 'claim_finder');
  });
  state.activePass = draft.activePass && state.edits[draft.activePass] ? draft.activePass : state.passes[0].id;
  state.mode = draft.mode === 'pipeline' ? 'pipeline' : 'raw';
  state.skipAnalysis = draft.skipAnalysis ?? true;
  state.useCache = draft.useCache ?? true;
  state.pinnedClaimsRunId = draft.pinnedClaimsRunId || null;
  state.pinnedClaimsInfo = draft.pinnedClaimsInfo || null;
  if (draft.url) $('url').value = draft.url;
  if (draft.analyst) $('analyst').value = draft.analyst;
  $('mode').value = state.mode;

  renderModelOptions();
  renderModeControls();
  renderTabs();
  renderEditor();
  renderRuns();
  applyPinBanner();

  if (data.active_run_id) startPolling(data.active_run_id);
}

/* --- mode ---------------------------------------------------------------------------- */

function passRunsInThisMode(pass) {
  if (pass.id === 'claim_finder' && state.pinnedClaimsRunId) return false;
  return state.mode === 'pipeline' ? true : pass.supports_raw;
}

function renderModeControls() {
  $('mode-note').innerHTML = MODE_NOTES[state.mode];
  const toggles = $('mode-toggles');
  toggles.replaceChildren();

  if (state.mode === 'raw') {
    state.passes.filter((pass) => pass.supports_raw).forEach((pass) => {
      toggles.append(checkbox(`run-${pass.id}`, `Run ${pass.label.toLowerCase()}`, state.selected[pass.id],
        (checked) => { state.selected[pass.id] = checked; saveDraft(); }));
    });
  } else {
    toggles.append(checkbox('skip-analysis', 'Skip claim analyzer', state.skipAnalysis,
      (checked) => { state.skipAnalysis = checked; saveDraft(); }));
  }
  toggles.append(checkbox('use-cache', 'Use cached source', state.useCache,
    (checked) => { state.useCache = checked; saveDraft(); }));
}

function checkbox(id, labelText, checked, onChange) {
  const label = el('label', 'check');
  const input = document.createElement('input');
  input.type = 'checkbox';
  input.id = id;
  input.checked = checked;
  input.onchange = () => onChange(input.checked);
  label.append(input, document.createTextNode(' ' + labelText));
  return label;
}

/* --- editor -------------------------------------------------------------------------- */

function activePass() { return passById(state.activePass); }

function isModified(passId) {
  return state.edits[passId].prompt.trim() !== passById(passId).default_prompt.trim();
}

function renderTabs() {
  const tabs = $('pass-tabs');
  tabs.replaceChildren();
  state.passes.forEach((pass) => {
    const button = el('button', pass.id === state.activePass ? 'active' : '');
    if (!passRunsInThisMode(pass)) {
      button.classList.add('unavailable');
      button.title = (pass.id === 'claim_finder' && state.pinnedClaimsRunId)
        ? `Claims are pinned from run ${state.pinnedClaimsRunId} — claim finder will not run this pass.`
        : 'Pipeline mode only: this pass reads one already-extracted claim, which raw mode cannot produce.';
    }
    button.append(el('span', null, pass.label));
    if (isModified(pass.id)) button.append(el('span', 'dot'));
    button.onclick = () => { state.activePass = pass.id; renderTabs(); renderEditor(); saveDraft(); };
    tabs.append(button);
  });
}

function renderModelOptions() {
  const select = $('model');
  select.replaceChildren();
  state.models.forEach((model) => select.append(new Option(model, model)));
}

function renderVersionOptions() {
  const select = $('version');
  const pass = activePass();
  select.replaceChildren();
  select.append(new Option('(none)', ''));
  state.versions
    .filter((version) => version.pass_id === pass.id)
    .forEach((version) => select.append(new Option(version.name, version.id)));
  select.value = state.edits[pass.id].versionId || '';
}

function renderEditor() {
  const pass = activePass();
  const edit = state.edits[pass.id];

  $('pass-blurb').textContent = pass.blurb;
  $('pass-module').textContent = `Committed prompt lives in ${pass.module}. Edits here apply to this run only, they do not write back to the file.`;
  $('prompt').value = edit.prompt;

  if (!state.models.includes(edit.model)) {
    $('model').append(new Option(edit.model, edit.model));
    state.models.push(edit.model);
  }
  $('model').value = edit.model;

  renderVersionOptions();
  renderPromptStats();
}

function renderPromptStats() {
  const pass = activePass();
  const edit = state.edits[pass.id];
  const modified = isModified(pass.id);
  const stats = $('prompt-stats');
  stats.className = modified ? 'hint modified' : 'hint';
  const modelNote = edit.model === pass.default_model ? '' : ` · model overridden (code default ${pass.default_model})`;
  const skipNote = passRunsInThisMode(pass) ? '' : ' · not run in raw mode';
  stats.textContent = `${edit.prompt.length.toLocaleString()} chars · ${modified ? 'edited vs. code' : 'same as code'}${modelNote}${skipNote}`;
}

/* --- running ------------------------------------------------------------------------- */

async function startRun() {
  const url = $('url').value.trim();
  if (!url && !state.pinnedClaimsRunId) { toast('Paste a URL first.'); $('url').focus(); return; }

  const selected = state.mode === 'raw'
    ? state.passes.filter((pass) => pass.supports_raw && state.selected[pass.id]).map((pass) => pass.id)
    : state.passes.map((pass) => pass.id);
  if (!selected.length) { toast('Pick at least one pass to run.'); return; }

  const passes = {};
  state.passes.forEach((pass) => {
    const edit = state.edits[pass.id];
    const version = state.versions.find((v) => v.pass_id === pass.id && v.id === edit.versionId);
    passes[pass.id] = { prompt: edit.prompt, model: edit.model, version_name: version ? version.name : '' };
  });

  $('run').disabled = true;
  setStatus('running', 'Starting…');
  $('steps').replaceChildren();
  $('steps-wrap').hidden = false;
  $('steps-wrap').open = true;
  $('files').hidden = true;
  $('view-output').replaceChildren();
  $('open-report').hidden = true;
  showView('output');

  try {
    const { run_id: runId } = await api('/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url,
        analyst_name: $('analyst').value.trim(),
        mode: state.mode,
        selected_passes: selected,
        skip_analysis: state.skipAnalysis,
        use_cache: state.useCache,
        passes,
        pinned_claims_run_id: state.pinnedClaimsRunId || null,
      }),
    });
    saveDraft();
    startPolling(runId);
  } catch (error) {
    $('run').disabled = false;
    setStatus('error', error.message);
  }
}

function startPolling(runId) {
  $('run').disabled = true;
  clearInterval(state.pollTimer);
  const tick = async () => {
    try {
      const status = await api(`/api/runs/${runId}`);
      state.run = status;
      renderSteps(status.steps, { collapse: status.state !== 'running' });
      if (status.state === 'running') {
        const last = status.steps[status.steps.length - 1];
        setStatus('running', last ? last.message : 'Running…');
        return;
      }
      clearInterval(state.pollTimer);
      $('run').disabled = false;
      if (status.state === 'error') { setStatus('error', status.error || 'Run failed.'); return; }
      finishRun(status);
    } catch (error) {
      clearInterval(state.pollTimer);
      $('run').disabled = false;
      setStatus('error', error.message);
    }
  };
  tick();
  state.pollTimer = setInterval(tick, POLL_MS);
}

async function finishRun(status) {
  setStatus('done', `Done. ${summarise(status.record)} from "${status.record.source.title}".`);
  renderFiles(status);
  renderOutput(status.record);
  if (status.files.html) {
    $('open-report').href = `/api/runs/${status.run_id}/report`;
    $('open-report').hidden = false;
  }
  try {
    const { runs } = await api('/api/runs');
    state.runs = runs;
    renderRuns();
  } catch { /* the list is a convenience; a failure here shouldn't disturb the result */ }
}

function summarise(record) {
  if (record.mode === 'raw') {
    const chars = record.raw_results.reduce((sum, r) => sum + (r.text ? r.text.length : 0), 0);
    return `${record.raw_results.length} pass(es), ${chars.toLocaleString()} chars of output`;
  }
  return `${record.claims.length} claim(s), ${record.stances.length} stance(s)`;
}

function setStatus(kind, text) {
  $('status').className = `status ${kind}`;
  $('status-text').textContent = text;
}

function renderSteps(steps, { collapse = false } = {}) {
  const list = $('steps');
  $('steps-wrap').hidden = steps.length === 0;
  $('steps-summary').textContent = `Run log (${steps.length} step${steps.length === 1 ? '' : 's'})`;
  list.replaceChildren(...steps.map((step) => el('li', null, step.message)));
  if (collapse) $('steps-wrap').open = false;
  else list.scrollTop = list.scrollHeight;
}

/* --- results ------------------------------------------------------------------------- */

function renderFiles(status) {
  const files = status.files;
  $('files').hidden = false;
  const target = status.modified_passes.length ? status.modified_passes.join(' and ') : 'claim_finder';
  const ask = `Read ${files.markdown}. That's a prompt lab run of the AnalystAudit pipeline. Help me improve the ${target} prompt based on what it got wrong.`;
  $('claude-ask').textContent = ask;
  $('claude-ask').dataset.copy = ask;

  const rows = [fileRow('digest', files.markdown), fileRow('structured', files.json), fileRow('source text', files.source)];
  if (files.html) rows.push(fileRow('styled report', files.html));
  rows.push(fileRow('always-newest', files.latest));
  $('file-list').replaceChildren(...rows);
}

function fileRow(label, path) {
  const li = el('li');
  li.append(el('span', null, `${label}: `), document.createTextNode(path));
  return li;
}

function sourceSummary(record) {
  const row = el('div', 'summary-row');
  row.append(el('strong', null, record.source.title));
  row.append(el('span', 'badge badge--outline', record.source.type.toUpperCase()));
  row.append(el('span', 'badge badge--accent', record.mode === 'raw' ? 'RAW OUTPUT' : 'PIPELINE'));
  row.append(document.createTextNode(
    `published ${record.source.published_at || 'unknown'} · ${record.source.char_count.toLocaleString()} chars`
    + (record.used_cached_source ? ' · from cache' : '')));
  return row;
}

function promptSummary(record) {
  const modified = Object.entries(record.passes).filter(([, data]) => data.modified).map(([id]) => id);
  const row = el('div', 'summary-row');
  row.append(el('span', 'hint', modified.length
    ? `Edited prompts this run: ${modified.join(', ')}`
    : 'Every pass ran the prompt currently in code.'));
  return row;
}

function renderRawOutput(view, record) {
  record.raw_results.forEach((result) => {
    const node = $('tpl-raw-pass').content.cloneNode(true);
    const section = node.querySelector('.raw-pass');
    section.querySelector('h3').textContent = record.passes[result.pass_id].label;

    if (result.error) {
      section.querySelector('.raw-meta').textContent = result.model;
      section.querySelector('.raw-copy').remove();
      const pre = section.querySelector('.raw-text');
      pre.className = 'raw-error';
      pre.textContent = `The call failed. ${result.error}`;
      view.append(section);
      return;
    }

    const tokens = [];
    if (result.input_tokens !== null) tokens.push(`${result.input_tokens.toLocaleString()} in`);
    if (result.output_tokens !== null) tokens.push(`${result.output_tokens.toLocaleString()} out`);
    section.querySelector('.raw-meta').textContent =
      [result.model, tokens.join(' / '), result.stop_reason].filter(Boolean).join(' · ');

    if (result.thinking) {
      const details = section.querySelector('.raw-thinking');
      details.hidden = false;
      details.querySelector('pre').textContent = result.thinking;
    }
    const text = result.text || '(the model returned no text)';
    section.querySelector('.raw-text').textContent = text;
    section.querySelector('.raw-copy').onclick = () => copyText(text);
    view.append(section);
  });
}

function jsonBlock(label, value) {
  const wrap = document.createDocumentFragment();
  if (label) wrap.append(el('div', 'json-label', label));
  wrap.append(el('pre', 'json-block', JSON.stringify(value, null, 2)));
  return wrap;
}

function renderPipelineOutput(view, record) {
  view.append(el('div', 'section-title', `Claims (${record.claims.length})`));
  if (record.claims.length) {
    record.claims.forEach((entry, index) => {
      view.append(jsonBlock(`Claim ${index + 1}`, entry.claim));
      if (entry.resolution) view.append(jsonBlock('Analyzer result', entry.resolution));
      else if (entry.skip_reason) view.append(el('div', 'hint', `Analyzer: not run. ${entry.skip_reason}`));
    });
  } else {
    view.append(el('div', 'empty', 'Nothing extracted.'));
  }

  view.append(el('div', 'section-title', `Stances (${record.stances.length})`));
  if (record.stances.length) {
    record.stances.forEach((entry, index) => {
      view.append(jsonBlock(`Stance ${index + 1}`, entry.stance));
      if (entry.snapshot) view.append(jsonBlock('Market snapshot', entry.snapshot));
      else if (entry.skip_reason) view.append(el('div', 'hint', `Market snapshot: ${entry.skip_reason}`));
    });
  } else {
    view.append(el('div', 'empty', 'Nothing extracted.'));
  }
}

function renderOutput(record) {
  const view = $('view-output');
  view.replaceChildren(sourceSummary(record), promptSummary(record));
  if (record.mode === 'raw') renderRawOutput(view, record);
  else renderPipelineOutput(view, record);
}

function renderRuns() {
  const view = $('view-runs');
  view.replaceChildren();
  if (!state.runs.length) { view.append(el('div', 'empty', 'No runs yet.')); return; }
  state.runs.forEach((run) => {
    const row = el('div', 'run-row');
    const left = el('div');
    left.append(el('div', 'rr-title', run.title || run.url));
    left.append(el('div', 'rr-meta',
      `${run.run_id} · ${run.mode || 'pipeline'}${run.modified_passes.length ? ` · edited: ${run.modified_passes.join(', ')}` : ''}`));
    const right = el('div', 'rr-right');
    right.append(el('div', 'rr-counts', run.summary || ''));
    if (run.mode === 'pipeline' && run.claim_count > 0) {
      const pinBtn = el('button', 'ghost small pin-claims',
        run.run_id === state.pinnedClaimsRunId ? 'Pinned ✓' : 'Pin claims →');
      if (run.run_id === state.pinnedClaimsRunId) pinBtn.disabled = true;
      pinBtn.onclick = (event) => { event.stopPropagation(); pinClaims(run); };
      right.append(pinBtn);
    }
    row.append(left, right);
    row.onclick = () => loadPastRun(run.run_id);
    view.append(row);
  });
}

/* --- pinned claims --------------------------------------------------------------------
   Reuses a past pipeline run's already-extracted claims instead of re-running claim finder,
   so the claim set stays fixed while the claim analyzer prompt is edited and re-run — claim
   finder isn't deterministic, so re-extracting on every analyzer edit would let the claim set
   itself drift, confounding the comparison. See runlog.pinned_claims_from_run / the
   `prefetched_claims` seam in preview_pipeline.run_pipeline. */

function pinClaims(run) {
  state.pinnedClaimsRunId = run.run_id;
  state.pinnedClaimsInfo = { title: run.title || run.url, url: run.url, claim_count: run.claim_count };
  state.mode = 'pipeline';
  $('mode').value = 'pipeline';
  applyPinBanner();
  renderModeControls();
  renderTabs();
  renderRuns();
  renderPromptStats();
  saveDraft();
  toast(`Pinned ${run.claim_count} claim(s) from "${run.title || run.url}".`);
}

function unpinClaims() {
  state.pinnedClaimsRunId = null;
  state.pinnedClaimsInfo = null;
  applyPinBanner();
  renderTabs();
  renderRuns();
  renderPromptStats();
  saveDraft();
}

function applyPinBanner() {
  const banner = $('pin-banner');
  const urlInput = $('url');
  if (state.pinnedClaimsRunId && state.pinnedClaimsInfo) {
    banner.hidden = false;
    const count = state.pinnedClaimsInfo.claim_count;
    $('pin-banner-text').textContent =
      `Claims pinned from "${state.pinnedClaimsInfo.title}" (${count} claim${count === 1 ? '' : 's'})`;
    urlInput.value = state.pinnedClaimsInfo.url;
    urlInput.disabled = true;
  } else {
    banner.hidden = true;
    urlInput.disabled = false;
  }
}

async function loadPastRun(runId) {
  try {
    const status = await api(`/api/runs/${runId}`);
    state.run = status;
    renderSteps(status.steps, { collapse: true });
    setStatus('done', `Loaded ${runId}. ${summarise(status.record)}.`);
    renderFiles(status);
    renderOutput(status.record);
    $('open-report').hidden = !status.files.html;
    if (status.files.html) $('open-report').href = `/api/runs/${runId}/report`;
    showView('output');
  } catch (error) {
    toast(error.message);
  }
}

/* --- views / misc -------------------------------------------------------------------- */

function showView(view) {
  state.view = view;
  ['output', 'markdown', 'runs'].forEach((name) => { $(`view-${name}`).hidden = name !== view; });
  $('result-tabs').querySelectorAll('button').forEach((button) => {
    button.classList.toggle('active', button.dataset.view === view);
  });
  if (view === 'markdown') loadMarkdown();
}

async function loadMarkdown() {
  const body = $('markdown-body');
  if (!state.run || state.run.state !== 'done') { body.textContent = 'Run something first.'; return; }
  body.textContent = 'Loading…';
  try {
    const response = await fetch(`/api/runs/${state.run.run_id}/markdown`);
    body.textContent = response.ok ? await response.text() : 'No digest saved for this run.';
  } catch (error) {
    body.textContent = error.message;
  }
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); toast('Copied.'); }
  catch { toast('Clipboard blocked; select and copy manually.'); }
}

let toastTimer = null;
function toast(message) {
  const node = $('toast');
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, 2200);
}

/* --- wiring -------------------------------------------------------------------------- */

$('mode').addEventListener('change', (event) => {
  state.mode = event.target.value;
  if (state.mode !== 'pipeline' && state.pinnedClaimsRunId) {
    unpinClaims();
    toast("Unpinned claims — raw mode can't use them.");
  }
  renderModeControls();
  renderTabs();
  renderPromptStats();
  saveDraft();
});

$('unpin-claims').addEventListener('click', unpinClaims);

$('prompt').addEventListener('input', (event) => {
  state.edits[state.activePass].prompt = event.target.value;
  renderPromptStats();
  renderTabs();
  saveDraft();
});

$('model').addEventListener('change', (event) => {
  state.edits[state.activePass].model = event.target.value;
  renderPromptStats();
  saveDraft();
});

$('version').addEventListener('change', async (event) => {
  const versionId = event.target.value;
  state.edits[state.activePass].versionId = versionId;
  if (!versionId) { saveDraft(); return; }
  try {
    const version = await api(`/api/versions/${state.activePass}/${versionId}`);
    state.edits[state.activePass].prompt = version.prompt;
    if (version.model) state.edits[state.activePass].model = version.model;
    renderEditor();
    renderTabs();
    saveDraft();
    toast(`Loaded "${version.name}".`);
  } catch (error) { toast(error.message); }
});

$('reset-default').addEventListener('click', () => {
  const pass = activePass();
  state.edits[pass.id] = { prompt: pass.default_prompt, model: pass.default_model, versionId: '' };
  renderEditor();
  renderTabs();
  saveDraft();
  toast('Reset to the prompt in code.');
});

$('save-version').addEventListener('click', async () => {
  const nameInput = $('version-name');
  const name = nameInput.value.trim();
  if (!name) { toast('Name the version first.'); nameInput.focus(); return; }
  const edit = state.edits[state.activePass];
  try {
    const result = await api('/api/versions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pass_id: state.activePass, name, prompt: edit.prompt, model: edit.model }),
    });
    state.versions = result.versions;
    edit.versionId = result.saved.id;
    nameInput.value = '';
    renderVersionOptions();
    saveDraft();
    toast(`Saved "${result.saved.name}".`);
  } catch (error) { toast(error.message); }
});

$('delete-version').addEventListener('click', async () => {
  const versionId = state.edits[state.activePass].versionId;
  if (!versionId) { toast('Select a saved version first.'); return; }
  try {
    const result = await api(`/api/versions/${state.activePass}/${versionId}`, { method: 'DELETE' });
    state.versions = result.versions;
    state.edits[state.activePass].versionId = '';
    renderVersionOptions();
    saveDraft();
    toast('Deleted.');
  } catch (error) { toast(error.message); }
});

$('run').addEventListener('click', startRun);
$('clear-cache').addEventListener('click', async () => {
  const { cleared } = await api('/api/cache/clear', { method: 'POST' });
  toast(`Cleared ${cleared} cached source${cleared === 1 ? '' : 's'}.`);
});

$('copy-prompt').addEventListener('click', () => copyText($('claude-ask').dataset.copy || ''));
$('copy-markdown').addEventListener('click', () => copyText($('markdown-body').textContent));

$('result-tabs').addEventListener('click', (event) => {
  const button = event.target.closest('button');
  if (button) showView(button.dataset.view);
});

['url', 'analyst'].forEach((id) => $(id).addEventListener('change', saveDraft));

document.addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
    event.preventDefault();
    if (!$('run').disabled) startRun();
  }
});

init().catch((error) => setStatus('error', `Could not load the lab: ${error.message}`));
