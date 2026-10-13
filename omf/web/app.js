'use strict';
// All page text goes in through text nodes / textContent only. No HTML parsing of data, no dynamic code, no remote resources.

const S = {
  ev: null, block: null, corrupt: '', scope: null, showAll: false,
  facts: { present: [], absent: [] }, solved: null, bound: null, shown: null, tampered: null, history: [],
};
const $ = (id) => document.getElementById(id);

function el(tag, attrs, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') n.className = v;
    else if (k === 'on') for (const [ev, fn] of Object.entries(v)) n.addEventListener(ev, fn);
    else if (k === 'data') for (const [dk, dv] of Object.entries(v)) n.dataset[dk] = dv;
    else n.setAttribute(k, v);
  }
  for (const c of kids.flat()) {
    if (c === null || c === undefined || c === false) continue;
    n.append(typeof c === 'string' || typeof c === 'number' ? document.createTextNode(String(c)) : c);
  }
  return n;
}
const clear = (n) => { while (n.firstChild) n.removeChild(n.firstChild); return n; };
const short = (h) => (typeof h === 'string' ? h.slice(0, 12) + '…' : '');
const cases = () => Object.fromEntries(S.ev.register.cases.map((c) => [c.id, c]));
const tag = (cls, text) => el('span', { class: 'tag ' + cls }, text);
const notice = (id) => { const c = cases()[id]; return c ? `${id} · ${c.notice}` : id; };

async function api(path, body) {
  const opt = body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  };
  const r = await fetch(path, opt);
  const j = await r.json();
  return { ok: r.ok, status: r.status, body: j };
}

// ---------------- Region 1 + 2: evidence and scope ----------------
function renderCapture() {
  const d = S.ev.derivative;
  const c = d.capture || {};
  const real = d.origin === 'ARCHIVED_SERPAPI_CAPTURE';
  const tr = d.trust || {};
  const projectionOnly = tr.state === 'PROJECTION_PINNED';
  const t = $('r1tag');
  t.className = 'tag ' + (real && tr.authentic === true ? 'real' : 'bad');
  t.textContent = projectionOnly ? 'CODE-PINNED PROJECTION · RAW NOT RE-VERIFIED' :
    (real && tr.authentic === true ? `REAL ARCHIVED · ${tr.state}` : `${tr.state || 'UNVERIFIED'} · NOT AUTHENTIC`);
  const meta = clear($('capmeta'));
  if (tr.withheld === true || tr.authentic !== true) {
    // G4 v2: the server released only a fixed diagnostic; there is no archive/derivative text to show.
    meta.append(el('div', { class: 'badbox' }, el('b', {}, `${tr.state || 'UNVERIFIED'}: `),
      `the evidence did not match the code-pinned archive (${tr.mismatch_count || 0} difference(s)). `,
      'All archived text, links, capture metadata and citation comparisons are withheld by the server. ',
      'Region 3 still works on hypothetical facts only; nothing there is taken from this evidence.'));
    return;
  }
  meta.append(el('div', {}, tr.authentic === true ? tag('real', projectionOnly ? 'CODE-PINNED ARCHIVE PROJECTION' : 'ARCHIVED SOURCE METADATA') : tag('bad', 'SOURCE METADATA · UNVERIFIED'), ' ',
    `SerpApi engine=${c.engine} (parent ${c.parent_engine}, gl=${c.gl}) · query “${c.parent_query}” · raw sha256 ${short(d.raw_sha256)} · trust ${tr.state}`));
  if (projectionOnly) meta.append(el('div', { class: 'warnbox' },
    'The raw capture is not included in this release. This projection matches a digest pinned in the application code; that is not an independent re-verification of the raw capture or provider authentication.'));
  const skew = /unresolved/.test(c.clock_note || '') ? ' · clock skew UNRESOLVED' : '';
  meta.append(el('details', {},
    el('summary', {}, `collector received ${c.collector_received_at_utc} · provider created ${c.provider_created_at_utc}${skew}`),
    el('div', { class: 'warnbox' }, c.clock_note || 'timestamps unavailable')));
}

function renderBlocks() {
  const list = clear($('blocks'));
  const derivative = S.ev.derivative || {};
  if (!Array.isArray(derivative.blocks) || derivative.blocks.length === 0) {
    list.append(el('li', { class: 'note' }, 'Historical Google/SerpApi captures are omitted from this public package. No captured answer blocks or citations are available or verified.'));
    $('showall').hidden = true;
    return;
  }
  $('showall').hidden = false;
  const blocks = derivative.blocks.filter((b) => !b.pointer.includes('/list/') && b.snippet);
  const shown = S.showAll ? blocks : blocks.filter((b) => b.pointer === S.block);
  for (const b of shown) {
    const live = b.pointer === S.block && S.scope && S.scope.block ? S.scope.block : b;
    const idx = (live.reference_indexes || []).map((i) => el('span', { class: 'chip idx' }, `[${i}]`));
    list.append(el('li', {}, el('button', {
      type: 'button', class: 'blk' + (b.pointer === S.block ? ' sel' : ''),
      on: { click: () => selectBlock(b.pointer) },
    }, el('span', { class: 'bt' }, b.snippet), idx, el('span', { class: 'status ' + live.link_status }, live.link_status))));
  }
  $('showall').textContent = S.showAll ? 'Show the selected paragraph only' : `Show all ${blocks.length} answer paragraphs (click one to inspect its citations)`;
}

function kindLabel(k, rows, names) {
  const ids = rows.map(notice).join(', ');
  switch (k) {
    case 'EXACT_MODELED_COMPOSITION': return ['tag official', `names exactly ${ids}`];
    case 'TRUNCATED_CONSISTENT_WITH': return ['tag warn', `TRUNCATED · consistent with ${rows.join(' or ')} · UNRESOLVED`];
    case 'OUTSIDE_MODELED_REGISTER': return ['tag bad', 'names a formulation outside the modeled register'];
    case 'NO_MODELED_COMPOSITION_MATCH': return ['tag warn', 'names no modeled composition'];
    case 'UNPARSED_INGREDIENT_LIST': return ['tag warn', `names ingredients in a list that is not parsed (${(names || []).join(', ')}) · UNRESOLVED`];
    case 'UNRESOLVED_TERMS': return ['tag warn', 'ingredient chain with unrecognised terms · UNRESOLVED'];
    default: return ['tag warn', 'no “A + B” ingredient chain found; text not parsed further · UNRESOLVED'];
  }
}

function renderScope() {
  const sc = S.scope.scope;
  const cited = clear($('cited'));
  const attrib = clear($('attrib'));
  const diff = clear($('diff'));
  const d = S.ev.derivative;
  if (S.scope.corruption) attrib.append(el('div', { class: 'badbox' }, `Adversarial copy: ${S.scope.corruption}.`));
  if (sc.attribution !== 'LINKED') {
    attrib.append(el('div', { class: 'badbox' },
      el('b', {}, `Source-to-sentence attribution: ${sc.attribution}. `),
      (S.scope.block && S.scope.block.link_reason) ? `${S.scope.block.link_reason}. ` : '',
      S.scope.evidence_state && !['RAW_REVERIFIED', 'PROJECTION_PINNED'].includes(S.scope.evidence_state)
        ? `Evidence state ${S.scope.evidence_state}: it does not match the code-pinned archive. ` : '',
      'The paragraph can no longer be tied to any cited source, so no cited-scope comparison is shown. Region 3 still runs on hypothetical facts, but nothing links it to this paragraph.'));
    cited.append(el('p', { class: 'note' }, 'No verified citations for this paragraph.'));
    return;
  }
  attrib.append(el('div', { class: 'row' }, tag('real', 'LINKED'),
    el('span', { class: 'note' }, `paragraph → references [${sc.links.map((l) => l.index).join(', ')}] (SerpApi reference_indexes; every paragraph and reference field matched the code-pinned archive: ${sc.evidence_state})`)));
  for (const l of sc.links) {
    const ref = d.references[l.index];
    const kinds = l.scope_kinds.map((k) => { const [cls, txt] = kindLabel(k, l.rows, l.names_seen); return el('span', { class: cls }, txt); });
    cited.append(el('div', { class: 'ref' },
      el('div', {}, el('span', { class: 'chip idx' }, `[${l.index}]`), el('span', { class: 'src' }, l.source || ''), ' — ', l.title || ''),
      el('div', { class: 'snip' }, `“${l.snippet || ''}”`),
      el('div', { class: 'url' }, `${ref.link_display || '(link withheld)'} · captured snippet${ref.snippet_truncated_in_capture ? ' (truncated by the search result)' : ''} · not page content`),
      el('div', { class: 'row' }, kinds)));
  }
  const target = sc.query_target_rows[0];
  if (!sc.diffs.length) {
    diff.append(el('p', { class: 'note' }, 'None of this paragraph\'s sources names a modeled composition different from the query target.'));
    return;
  }
  const C = cases();
  for (const x of sc.diffs) {
    const tgt = C[x.target_row], cit = C[x.cited_row];
    const chips = (c, extra) => c.ingredients.map((i) => el('span', { class: 'ingr' + (extra.includes(i) ? ' extra' : '') }, i));
    diff.append(el('div', { class: 'diffgrid' },
      el('span', { class: 'lab' }, `Query target`), el('span', {}, el('b', {}, notice(target)), ' ', chips(tgt, [])),
      el('span', { class: 'lab' }, `Cited [${x.reference_index}]`), el('span', {}, el('b', {}, notice(x.cited_row)), ' ', chips(cit, x.cited_has_extra))),
    el('div', { class: 'big' }, x.cited_has_extra.map((i) => `+ ${i}`).join('  '), x.cited_lacks.map((i) => `  − ${i}`).join('')),
    el('p', { class: 'note' }, `Source [${x.reference_index}] describes ${x.cited_row}, not the three-ingredient ${x.target_row} the query named.`));
  }
}

function renderOfficial() {
  const o = S.ev.register.official_source;
  clear($('officialnote')).append(
    `Notices: Gazette ${o.gazette_id}, PDF sha256 ${short(o.gazette_pdf_sha256)}; current status ${o.current_status_label}. `,
    'Both formulations have prohibitory notices. The paragraph is a qualified, class-level statement and is NOT shown false: this is a difference in scope, not an error verdict. ',
    'Search snippets are observations about web pages. They are never treated as a product\'s ingredients.',
  );
}

async function selectBlock(ptr) {
  S.block = ptr;
  const r = await api('/api/scope', { pointer: ptr, corrupt: S.corrupt || null });
  S.scope = r.body;
  renderBlocks();
  renderScope();
  renderResult();
}

// ---------------- Region 3: one missing fact ----------------
const hyp = (t) => ({ term: t, provenance: 'HYPOTHETICAL' });
function preset(name) {
  // Release-only fallback: seed a clearly hypothetical exercise from the public factual register.
  // It is not a replay of any captured search query or product label.
  const f08 = cases().F08;
  const observed = S.ev.derivative && S.ev.derivative.query_terms_observed;
  const q = Array.isArray(observed) && observed.length > 0 ? observed : f08.ingredients;
  const P = {
    query: [q, []], amox: [['amoxicillin', 'serratiopeptidase'], []], serr: [['serratiopeptidase'], []],
    none: [[], []], outside: [[...q, 'dimethicone'], []], conflict: [['chlordiazepoxide'], ['chlordiazepoxide']],
  }[name];
  S.facts = { present: P[0].map(hyp), absent: P[1].map(hyp) };
  S.history = [];
  S.lastNo = false;
  return solve();
}

async function solve() {
  const r = await api('/api/solve', { present: S.facts.present, absent: S.facts.absent });
  S.tampered = null;
  if (!r.ok) {
    S.solved = { error: r.body };
    S.shown = null;
    S.bound = null;
  } else {
    S.solved = r.body;
    S.shown = r.body.witness;
    // The page's own record of what the reviewer asserted, captured now, independent of any later witness edits.
    const a = r.body.accepted;
    const prov = {};
    for (const side of ['present', 'absent']) for (const f of a[side]) prov[`${side}:${f.term}`] = f.provenance;
    S.bound = {
      present: a.present.map((f) => f.term), absent: a.absent.map((f) => f.term), label_completeness: a.label_completeness,
      provenance: prov, unresolved_inputs: a.unresolved.map((u) => ({ input: u.input, side: u.side, reason: u.reason })),
    };
  }
  renderFacts();
  renderResult();
  renderWitness(null);
}

function renderFacts() {
  const box = clear($('facts'));
  const chip = (f, side) => el('span', { class: 'ingr ' + (side === 'present' ? 'p' : 'n') },
    side === 'present' ? '✓ ' : '✗ ', f.term, ' ', tag(f.provenance === 'USER_ASSERTED' ? 'user' : 'hypo', f.provenance),
    el('button', { class: 'x', type: 'button', title: 'remove', on: { click: () => { S.facts[side] = S.facts[side].filter((x) => x !== f); solve(); } } }, '×'));
  if (!S.facts.present.length && !S.facts.absent.length) box.append(el('span', { class: 'note' }, 'No accepted facts. Every modeled notice remains a candidate.'));
  box.append(...S.facts.present.map((f) => chip(f, 'present')), ...S.facts.absent.map((f) => chip(f, 'absent')));
}

function answer(kind) {
  const q = S.solved.result.question;
  if (kind === 'UNKNOWN') {
    S.history.push(`UNKNOWN for “${q}”: neither branch taken, candidates unchanged, question stays open.`);
    return renderResult();
  }
  S.history.push(`${kind} for “${q}” (hypothetical answer)`);
  S.facts[kind === 'YES' ? 'present' : 'absent'].push(hyp(q));
  S.lastNo = kind === 'NO';
  return solve();
}

function bridgeNote(q) {
  if (!S.scope || !S.scope.scope || S.scope.scope.attribution !== 'LINKED') return null;
  const d = S.scope.scope.diffs.find((x) => x.cited_has_extra.includes(q) || x.cited_lacks.includes(q));
  if (!d) return null;
  return el('div', { class: 'goodbox' },
    `Computed from the register, not looked up: “${q}” is the ingredient that separates cited source [${d.reference_index}]’s formulation (${d.cited_row}) from the query target (${d.target_row}).`);
}

function renderResult() {
  const box = clear($('result'));
  if (!S.solved || !S.ev) return;
  if (S.solved.error) {
    box.append(el('div', { class: 'badbox' }, el('b', {}, S.solved.error.error), ': ', S.solved.error.detail || ''));
    box.append(el('p', { class: 'note' }, S.ev.caveat));
    return;
  }
  const res = S.solved.result, acc = S.solved.accepted;
  const unc = res.unconfirmed_by_candidate || {};
  const candList = (ids) => ids.length ? ids.map(notice).join(', ') : 'none';
  for (const c of res.naming_caveats || []) box.append(el('div', { class: 'warnbox' }, c));
  if (acc.unresolved.length) {
    box.append(el('div', { class: 'warnbox' }, 'Not accepted as facts: ',
      acc.unresolved.map((u) => `${u.input} (${u.reason})`).join('; '), '. They narrow nothing.'));
  }
  if (res.status === 'NEXT_QUESTION') {
    box.append(el('div', { class: 'note' }, `Modeled candidates (${res.candidate_ids.length}): ${candList(res.candidate_ids)}`));
    box.append(el('div', { class: 'big' }, 'Does the complete product label list ', el('span', { class: 'q' }, res.question), '?'));
    box.append(el('div', { class: 'note' }, `Worst case: ${res.worst_case_depth} more yes/no answer${res.worst_case_depth === 1 ? '' : 's'} to leave one modeled candidate (proven optimal over this register).`));
    box.append(el('div', { class: 'parts' },
      el('div', {}, el('div', { class: 'h' }, 'YES →'), candList(res.partition.yes)),
      el('div', {}, el('div', { class: 'h' }, 'NO →'), candList(res.partition.no)),
      el('div', {}, el('div', { class: 'h' }, 'UNKNOWN →'), `stays ${candList(res.unknown_answer_keeps)}`)));
    box.append(el('div', { class: 'row' },
      el('button', { type: 'button', class: 'ans primary', on: { click: () => answer('YES') } }, 'YES'),
      el('button', { type: 'button', class: 'ans', on: { click: () => answer('NO') } }, 'NO'),
      el('button', { type: 'button', class: 'ans ghost', on: { click: () => answer('UNKNOWN') } }, 'UNKNOWN')));
    const b = bridgeNote(res.question);
    if (b) box.append(b);
  } else if (res.status === 'SINGLE_MODELED_CANDIDATE') {
    const id = res.candidate_ids[0];
    box.append(el('div', { class: 'big' }, `One modeled notice remains consistent: ${notice(id)}`));
    box.append(el('div', { class: 'note' }, 'FORMULATION-NOTICE SCOPE only.'));
    if (unc[id] && unc[id].length) box.append(el('div', { class: 'warnbox' }, `Still unconfirmed for ${id}: ${unc[id].join(', ')}.`));
    box.append(el('div', { class: 'warnbox' }, 'Not a product identification. Label completeness is NOT established, so an ingredient outside the ten modeled rows could still be present.',
      S.lastNo ? ' A NO answer cannot prove the label is complete.' : ''));
  } else if (res.status === 'OUTSIDE_MODELED_REGISTER_OR_CONFLICT') {
    box.append(el('div', { class: 'badbox' }, el('b', {}, 'No modeled notice matches these facts. '),
      'That does NOT mean the formulation is unrestricted: 6 of the 16 notices are not modeled, and other instruments may apply. Nothing is cleared.'));
  } else if (res.status === 'CONFLICT') {
    box.append(el('div', { class: 'badbox' }, el('b', {}, 'CONFLICT: '), `${res.conflict_terms.join(', ')} asserted both present and absent. A reviewer must resolve this before any question is computed.`));
  } else if (res.status === 'INDISTINGUISHABLE') {
    box.append(el('div', { class: 'badbox' }, `INDISTINGUISHABLE: ${res.indistinguishable_groups.map((g) => g.join('=')).join('; ')} have identical ingredient sets.`));
  } else {
    box.append(el('div', { class: 'badbox' }, `${res.status}: ${res.detail || ''}`));
  }
  if (S.history.length) box.append(el('div', { class: 'history' }, S.history.map((h) => el('div', {}, '• ' + h))));
  box.append(el('p', { class: 'note' }, S.ev.caveat));
}

// ---------------- Region 4: proof ----------------
function renderWitness(note) {
  const box = clear($('witness'));
  const w = S.shown;
  clear($('verdict'));
  $('wjson').textContent = w ? JSON.stringify(w, null, 1) : '';
  for (const b of document.querySelectorAll('#r4 button')) b.disabled = !w;
  if (!w) { box.append(el('p', { class: 'note' }, 'No witness for this input.')); return; }
  if (S.tampered) box.append(el('div', { class: 'badbox' }, tag('bad', 'TAMPERED'), ' ', note || S.tampered));
  const kv = el('div', { class: 'kv' });
  const row = (k, v) => kv.append(el('span', { class: 'k' }, k), el('span', { class: 'v' }, v));
  row('status', w.status);
  row('candidates', (w.candidate_ids || []).join(', ') || '—');
  row('question', w.question || '—');
  row('YES | NO', w.partition ? `${w.partition.yes.join(', ')} | ${w.partition.no.join(', ')}` : '—');
  row('optimal depth', w.worst_case_depth === null ? '—' : String(w.worst_case_depth));
  row('facts', [...w.facts.present.map((f) => `+${f.term} [${f.provenance}]`), ...w.facts.absent.map((f) => `−${f.term} [${f.provenance}]`)].join(' ') || '—');
  row('register', `${w.register_id} ${short(w.register_digest)}`);
  row('solver · tie rule', `${w.solver_version} · ${w.tie_rule}`);
  row('witness sha256', short(w.witness_digest));
  box.append(kv);
}

async function verify() {
  const out = clear($('verdict'));
  out.append(el('p', { class: 'note' }, 'Running the separate verifier process…'));
  const r = await api('/api/verify', { witness: S.shown, expected_facts: S.bound, mode: 'strict' });
  const v = r.body;
  clear(out);
  const pass = typeof v.verdict === 'string' && v.verdict.startsWith('PASS');
  out.append(el('div', { class: pass ? 'goodbox' : 'badbox' },
    el('b', {}, pass ? `${v.verdict}: ` : 'FAIL: '),
    pass ? `independently recomputed ${(v.checks || []).join(' · ')}` : (v.reason || 'rejected'),
    el('div', { class: 'note' }, `${v.verifier_version || ''} · isolated subprocess · ${v.process ? v.process.elapsed_ms : '?'} ms · shares no code with the solver`)));
}

async function doTamper(kind) {
  if (!S.solved || !S.solved.witness) return;
  const r = await api('/api/tamper', { witness: S.solved.witness, kind });
  if (!r.body.witness) { clear($('verdict')).append(el('div', { class: 'warnbox' }, r.body.note)); return; }
  S.shown = r.body.witness;
  S.tampered = r.body.note;
  renderWitness(r.body.note);
  await verify();
}

// ---------------- boot ----------------
async function boot() {
  const r = await api('/api/evidence');
  S.ev = r.body;
  if (!S.ev.derivative || !Array.isArray(S.ev.derivative.blocks) || !S.ev.derivative.blocks.length) {
    const banner = el('div', { class: 'warnbox' }, 'PUBLIC RELEASE: historical Google screenshots, search corpus, and captured F08 AI Overview text are omitted. Evidence is UNAVAILABLE and not verified. The One Missing Fact exercise below uses hypothetical facts only.');
    document.querySelector('main').prepend(banner);
    $('r1tag').textContent = 'EVIDENCE UNAVAILABLE';
    $('r1tag').className = 'tag bad';
  }
  S.block = S.ev.default_block;
  renderCapture();
  renderOfficial();
  clear($('foot')).append(
    `Register ${S.ev.register.register_id} sha256 ${short(S.ev.register.digest)} (derived from banlag/registry.json @ a84c345). `,
    S.ev.derivative_sha256 ? `Display derivative sha256 ${short(S.ev.derivative_sha256)}. ` : 'Historical display evidence omitted; no derivative verification is claimed. ',
    'Offline: served from 127.0.0.1, no external requests.');
  $('showall').addEventListener('click', () => { S.showAll = !S.showAll; renderBlocks(); });
  for (const b of document.querySelectorAll('[data-corrupt]')) {
    b.addEventListener('click', () => { S.corrupt = b.dataset.corrupt; selectBlock(S.block); });
  }
  for (const b of document.querySelectorAll('[data-preset]')) b.addEventListener('click', () => preset(b.dataset.preset));
  for (const b of document.querySelectorAll('[data-tamper]')) b.addEventListener('click', () => doTamper(b.dataset.tamper));
  $('verify').addEventListener('click', () => { if (S.tampered) { S.shown = S.solved.witness; S.tampered = null; renderWitness(null); } verify(); });
  $('addfact').addEventListener('submit', (e) => {
    e.preventDefault();
    const side = (e.submitter && e.submitter.dataset.side) || 'present';
    const t = $('term').value.trim();
    if (!t) return;
    S.facts[side].push(hyp(t));
    $('term').value = '';
    solve();
  });
  await selectBlock(S.block);
  await preset('query');
}

boot().catch((e) => { document.body.append(el('pre', {}, 'Startup failed: ' + String(e))); });
