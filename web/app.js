'use strict';
// BANLAG UI. All data comes from the local API; every string is inserted with textContent (no innerHTML).
const $ = id => document.getElementById(id);
const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined && text !== null) n.textContent = String(text); return n; };
const clear = n => { n.replaceChildren(); return n; };
const S = { overview: null, cases: {}, current: null, pass: 'A' };
const SUBJECT_BINDINGS = ['EXPLICIT_EXACT', 'SUBJECT_ANAPHORA', 'SUBJECT_IMPLICIT'];
const fmtTime = iso => iso ? iso.replace('T', ' ').replace('+05:30', ' IST') : '—';
const utcToIst = s => { // provider format 'YYYY-MM-DD HH:MM:SS UTC'
  const m = /^(\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d) UTC$/.exec(s || ''); if (!m) return s || '—';
  const d = new Date(Date.UTC(+m[1], m[2] - 1, +m[3], +m[4], +m[5], +m[6]) + 330 * 60000);
  return d.toISOString().slice(0, 19).replace('T', ' ') + ' IST';
};
const short = h => h ? h.slice(0, 12) + '…' : '—';
// Public contract: machine readings of prose arrive only under `experimental` (unverified hypotheses), never as headline facts.
const xp = o => (o && o.experimental) || {};
const claimsOf = b => b.claims || xp(b).claims || [];   // parser claim spans: experimental
const subj = r => (r && (r.subject || xp(r).subject)) || { ingredients: [] };  // parser subject: experimental

// Static demo mode (GitHub Pages): the same UI replays responses pre-rendered by scripts/build_static_demo.py.
// Locally (python -m banlag) BANLAG_STATIC is undefined and every call goes to the local API exactly as before.
const STATIC = window.BANLAG_STATIC === true;
const staticFile = path => 'api/' + path.replace(/^\/api\//, '').replace(/\//g, '_') + '.json';
const normName = s => (String(s).toLowerCase().match(/[a-z0-9]+/g) || []).join(' ');
let STATIC_INDEX = null;
async function staticPost(path, body) {
  STATIC_INDEX = STATIC_INDEX || await (await fetch('api/_post_index.json')).json();
  const key = path === '/api/match'
    ? 'match:' + (Array.isArray(body.ingredients) ? body.ingredients.map(normName).sort().join('|') : '')
    : 'evaluate:' + JSON.stringify(body);
  const file = STATIC_INDEX[key];
  if (!file) throw Error(path === '/api/match'
    ? 'This read-only demo has pre-computed answers for all sixteen notified sets and close variants. Run BANLAG locally (python -m banlag) to check any ingredient list.'
    : 'Imports need the local app: this read-only demo can only replay the built-in samples. Run python -m banlag.');
  const d = await (await fetch('api/' + file)).json();
  if (d && d.__status && d.__status !== 200) throw Error(d.error || 'Request failed');
  return d;
}
async function api(path) { const r = await fetch(STATIC ? staticFile(path) : path); const d = await r.json(); if (!r.ok) throw Error(d.error || r.status); return d; }
async function post(path, body) {
  if (STATIC) return staticPost(path, body);
  const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const d = await r.json(); if (!r.ok) throw Error(d.error || 'Request failed'); return d;
}
function lab(x, big) { const s = el('span', 'lab ' + (x || 'A') + (big ? ' big' : ''), x === 'NOT_FLAGGED' ? 'NOT FLAGGED' : (x || '–')); s.title = labelName(x); return s; }
function labelName(x) {
  return { A: 'A · no AI answer', B: 'B · not the exact FDC', C: 'C · historical / general only', D: 'D · India restriction mentioned',
    E: 'E · present current use without India status', F: 'F · uncertain (scope, hedge, truncation)', NOT_FLAGGED: 'Not one of the sixteen notified sets' }[x] || x;
}

const QUALIFIERS = ['negated', 'denied', 'reported', 'conditional', 'proposed', 'historical', 'revoked'];
function claimClass(c) {
  const r = xp(c).restriction, types = c.types || xp(c).types || [], ub = c.use_binding || xp(c).use_binding;
  // No proof-like class exists: every highlight is an experimental parser reading (see the public contract).
  const qualified = r && QUALIFIERS.some(k => r[k]);
  if (r && ['EXPLICIT_EXACT', 'SUBJECT_ANAPHORA'].includes(r.binding)) return 'c-qualified';
  if (r && (r.binding === 'COMPONENT_ONLY' || r.binding === 'GENERIC' || r.hedged) && !qualified) return 'c-partial';
  if (types.includes('CURRENT_USE_STRONG') && SUBJECT_BINDINGS.includes(ub)) return 'c-strong';
  if (types.includes('CURRENT_USE_WEAK') && SUBJECT_BINDINGS.includes(ub)) return 'c-weak';
  if (types.includes('HISTORICAL')) return 'c-hist';
  if (['COMPONENT_ONLY', 'OTHER_ENTITY'].includes(ub) || (r && r.binding === 'OTHER_ENTITY')) return 'c-other';
  return '';
}
function claimTitle(c) {
  const x = xp(c), types = c.types || x.types || [], ub = c.use_binding || x.use_binding, cues = c.cues || x.cues || [];
  const parts = ['EXPERIMENTAL parser reading — not verified', types.join(', ') || 'no claim type'];
  if (ub) parts.push('bound to: ' + ub);
  if (cues.length) parts.push('cue: “' + cues.join('”, “') + '”');
  const r = xp(c).restriction;
  if (r) {
    const q = QUALIFIERS.filter(k => r[k]).concat(r.hedged && !r.reported ? ['hedged'] : []);
    parts.push(`restriction: ${r.binding}, ${r.jurisdiction}${q.length ? ', ' + q.join(', ') : ''}` +
      ' — experimental reading only; not a regulatory conclusion');
    for (const e of r.events || []) {
      if (e.kind !== 'RESTRICTION') continue;
      parts.push(`  ${e.id} “${e.term}” → ${e.entity}${e.why_not && e.why_not.length ? ': ' + e.why_not.join('; ') : ''}`);
    }
  }
  return parts.join('\n');
}
function renderAnswer(rec, target, opts = {}) {
  clear(target);
  const blocks = opts.limit ? rec.blocks.slice(0, opts.limit) : rec.blocks;
  for (const b of blocks) {
    if (b.type === 'heading') { target.append(el('h4', '', b.text)); continue; }
    const div = el('div', 'blk');
    const cl = claimsOf(b);
    if (b.label && cl.length) div.append(el('span', 'lbl', b.label + ': '));
    if (!cl.length) div.append(el('span', '', b.text));
    cl.forEach((c, i) => { const s = el('span', 'hl ' + claimClass(c), (i ? ' ' : '') + c.text); s.title = claimTitle(c); div.append(s); });
    for (const ch of b.chips || []) div.append(el('span', 'chip', ch.source + (ch.more ? ' +' + ch.more : '')));
    target.append(div);
  }
  if (opts.limit && rec.blocks.length > opts.limit) target.append(el('div', 'muted', `… ${rec.blocks.length - opts.limit} more blocks`));
  if (!opts.noCards && rec.source_cards && rec.source_cards.length) {
    const cards = el('div', 'cards', 'Source cards Google displayed (titles, not AI text; links were opaque redirects and were not opened): ');
    cards.append(el('span', '', rec.source_cards.map(c => c.source + ' — ' + c.title).join(' · ')));
    target.append(cards);
  }
}
function setVis(target, have, want) {
  clear(target);
  const hs = new Set(have), ws = new Set(want);
  for (const w of want) target.append(el('span', 'ing' + (hs.has(w) ? '' : ' missing'), (hs.has(w) ? '✓ ' : '✗ ') + w));
  for (const h of have) if (!ws.has(h)) target.append(el('span', 'ing extra', '+ ' + h));
}
function kv(target, rows) { const g = el('div', 'kv'); for (const [k, v] of rows) g.append(el('span', '', k), el('span', '', v)); target.append(g); return g; }

/* ---------- sidebar ---------- */
function renderSidebar() {
  const list = clear($('caseList'));
  for (const c of S.overview.cases) {
    const b = el('button', 'registry-item'); b.type = 'button'; b.dataset.id = c.id;
    const labels = el('span', 'labels'); labels.append(lab(c.g1_locked.A), lab(c.g1_locked.B));
    b.append(el('span', 'number', c.id), el('span', 'name', c.composition), labels);
    b.title = `${c.notice} · ${c.composition}\nPass A ${labelName(c.g1_locked.A)}\nPass B ${labelName(c.g1_locked.B)}`;
    b.addEventListener('click', () => { selectCase(c.id); showView('case'); });
    list.append(b);
  }
  const cl = clear($('controlList'));
  for (const n of S.overview.controls) {
    const row = el('div', 'registry-item'); row.append(el('span', 'number', n.record_id), el('span', 'name', n.query), lab('NOT_FLAGGED'));
    row.title = 'Preregistered negative control: ' + subj(xp(n).subject ? xp(n) : n).ingredients.join(' + ');
    cl.append(row);
  }
}

/* ---------- case file ---------- */
async function selectCase(id) {
  S.current = id;
  document.querySelectorAll('.registry-item[data-id]').forEach(n => n.classList.toggle('active', n.dataset.id === id));
  const c = S.cases[id] || (S.cases[id] = await api('/api/case/' + id));
  renderCase(c);
}
function renderCase(c) {
  const e = c.entry, src = S.overview.legal_source, ls = S.overview.legal_status;
  $('caseEyebrow').textContent = `${e.notice} · SECTION 26A · DATED 11 JUN 2026 · PIB ITEM ${e.pib_item}`;
  $('caseTitle').textContent = e.composition;
  const ua = c.uses.A;
  $('caseSub').textContent = `Preregistered query ${e.query_id} · ${c.in_family ? 'serratiopeptidase family' : 'outside the serratiopeptidase family'} · ` +
    `AI text names the set ${ua && subj(ua).match_strength === 'SPELLING_VARIANT' ? 'via a spelling variant (' + subj(ua).variant_terms.join(', ') + ') — reviewer must confirm' : 'literally (experimental reading)'}` +
    (c.headline ? ' · headline case (legal-audit choice)' : '');
  const pair = clear($('caseLabels')); pair.append(el('span', 'muted', 'Pass A'), lab(c.g1_locked.A, true), el('span', 'muted', 'Pass B'), lab(c.g1_locked.B, true));
  $('caseVerdictText').textContent = c.g1_positive
    ? 'Positive in both passes: current-use wording about this exact FDC, no India status. Asked directly, the same surface stated the prohibition.'
    : c.g1_locked.A === 'D' ? 'The AI Overview disclosed the India restriction in both passes. Not a finding — shown for completeness.'
      : c.g1_locked.A === 'F' ? 'Uncertain in both passes: the answer mixes this FDC with other compositions. Not counted.' : 'Not a positive.';
  $('caseVerdict').style.borderColor = c.g1_positive ? '#a07a2c' : '#3d5260';
  const sb = $('safetyBanner'); sb.hidden = !c.safety_banner; sb.textContent = c.safety_banner ? '⚠ ' + c.safety_banner : '';

  $('noticeName').textContent = e.notice;
  $('noticeMeta').textContent = src.gazette_issue;
  $('formulaText').textContent = e.composition;
  $('operative').textContent = '“…hereby prohibits the manufacture, sale or distribution of the fixed dose combination of ' + e.composition + ' for human use, with immediate effect.”';
  $('basis').textContent = '“' + e.stated_basis + '”';
  const g = clear($('legalStatus'));
  for (const [k, v] of [['Status', ls.status_label + ' (as of ' + ls.as_of + ')'], ['Amendments', 'none found in e-Gazette text search'],
    ['Courts', 'no order located; search not exhaustive'], ['Scope', 'exact combination only; not import, possession, use or prescribing'],
    ['Re-check', 'required if older than ' + ls.recheck_max_age_days + ' days at publication']]) g.append(el('b', '', k), el('span', '', v));
  renderUses(c);
  renderStatus(c);
  renderControls(c);
  renderTrace(c);
  renderCaseLive(c);
}
function renderUses(c) {
  const rec = c.uses[S.pass];
  document.querySelectorAll('.segbtn').forEach(b => b.classList.toggle('active', b.dataset.pass === S.pass));
  if (!rec) { $('usesAnswer').textContent = 'No capture.'; return; }
  const pill = $('usesPill'); pill.textContent = 'Locked coder (historical): ' + labelName(rec.gold_label) + ' · experimental parser: ' + (xp(rec).engine_label || '—');
  pill.className = 'pill';
  $('usesTime').textContent = fmtTime(rec.captured_at);
  $('usesQuery').textContent = rec.query;
  const sj = clear($('usesSubject'));
  const su = subj(rec); sj.append(el('span', '', 'Lead-sentence subject (experimental parser reading): '), el('b', '', su.ingredients.join(' + ') || '—'),
    el('span', '', ' → ' + (su.entity_vs_target || xp(su).entity_vs_target || '—') + (su.match_strength ? ' (' + su.match_strength.toLowerCase() + ')' : '')));
  renderAnswer(rec, $('usesAnswer'));
  const meta = clear($('usesMeta'));
  meta.append(el('div', '', `${rec.record_id} · ${rec.source_file} · SHA-256 ${short(rec.source_sha256)} · ${rec.locked_in}`));
  const fl = rec.flags || xp(rec).flags || []; if (fl.length) meta.append(el('div', '', 'parser caveats (experimental): ' + fl.join(', ')));
  const shots = el('div', 'shots');
  for (const s of rec.screenshots) { const a = el('a'); a.href = (STATIC ? '' : '/') + 'evidence/screenshots/' + s.file; a.target = '_blank'; a.rel = 'noopener'; a.title = s.file + ' · SHA-256 ' + s.sha256;
    const img = el('img'); img.src = a.href; img.alt = 'Archived screenshot ' + s.file; img.loading = 'lazy'; a.append(img); shots.append(a); }
  if (rec.screenshots.length) meta.append(shots);
}
function renderStatus(c) {
  const s = c.status, pc = xp(c).paired_prompt_contrast, nc = $('statusNotice');
  if (!s) {
    $('statusPill').textContent = 'NOT RUN'; $('statusPill').className = 'pill'; $('statusTime').textContent = '';
    $('statusQuery').textContent = '—';
    clear($('statusAnswer')).append(el('p', 'muted', 'Status prompts were preregistered only for cases positive in both passes.'));
    nc.className = 'notice-check none'; nc.textContent = ''; $('contrastText').textContent = ''; return;
  }
  $('statusPill').textContent = 'Locked coder (historical): ' + labelName(s.gold_label); $('statusPill').className = 'pill';
  $('statusTime').textContent = fmtTime(s.captured_at) + (pc && pc.minutes_after_pass_b ? ` · +${pc.minutes_after_pass_b} min after Pass B` : '');
  $('statusQuery').textContent = s.query;
  renderAnswer(s, $('statusAnswer'), { noCards: true });
  const chk = s.notice_checks[0];
  if (!chk) { nc.className = 'notice-check none'; nc.textContent = 'The AI status answer quotes no notice number. Gazette: ' + c.entry.notice + '.'; }
  else if (chk.status === 'MATCH') { nc.className = 'notice-check match'; nc.textContent = `String match: the answer contains “${chk.cited}”, the Gazette notice number for this composition (a string match, not proof of what the answer says about it).`; }
  else { nc.className = 'notice-check mismatch'; nc.textContent = `String check: the answer contains “${chk.cited}”; the Gazette notice for this composition is ${chk.expected}. In the registry, ${chk.cited} is the notice for ${chk.cited_notice_composition || 'an item outside this registry'}.`; }
  if (!s.capture_complete) nc.textContent += ' (Capture of this status answer is incomplete: collapsed view.)';
  $('contrastText').textContent = pc ? 'Experimental reading (unverified): ' + pc.statement : '';
}
function renderControls(c) {
  const p = clear($('controlPanel'));
  if (!c.controls.length) { p.append(el('p', 'muted', 'No preregistered look-alike query targets this notice. Use “Verify an import” → matcher to test any ingredient set.')); return; }
  for (const n of c.controls) {
    const head = el('div', 'ctrl-head'); head.append(lab('NOT_FLAGGED', true), el('b', '', '“' + n.query + '”'), el('span', 'muted', fmtTime(n.captured_at)));
    p.append(head);
    p.append(el('p', '', `Same register of current-use language, but the parser reads the AI subject as ${subj(n).ingredients.join(' + ')} (experimental) — not the notified set.`));
    const sv = el('div', 'setviz'); setVis(sv, subj(n).ingredients, c.entry.ingredients); p.append(sv);
    const box = el('div', 'answer'); renderAnswer(n, box, { limit: 9, noCards: true }); p.append(box);
  }
}
function renderTrace(c) {
  const p = clear($('tracePanel'));
  for (const pass of ['A', 'B']) {
    const r = c.uses[pass]; if (!r) continue;
    p.append(el('div', 'smallcap', `PASS ${pass} · LOCKED CODER (HISTORICAL, SINGLE CODER) ${r.gold_label} · EXPERIMENTAL PARSER ${xp(r).engine_label || '—'}`));
    const ol = el('ol', 'trace'); for (const t of xp(r).decision_trace || []) ol.append(el('li', '', t)); p.append(ol);
  }
  p.append(el('div', 'smallcap', 'EVIDENCE TIER AND PROVENANCE'));
  const gate = xp(c).publication_gate || { decision: '—', withhold_reasons: [], conditions: [] };
  kv(p, [['Historical result', c.g1_positive ? 'Locked single coder: E in both passes (preregistered G1 positive); not provenance-verified' : 'Not a G1 positive'],
    ['Origin', (S.overview.corpus.origin || 'SUPPRESSED') + ' — not a SerpApi capture; origin not cryptographically authenticated'],
    ['Citations', 'browser shows source names only (CHIP_LABEL_ONLY); Tier 2/3 need a SerpApi capture with reference_indexes'],
    ['Publication', 'Not determined by software; no human review recorded (experimental gate: ' + gate.decision + ')'],
    ['Never claimed', 'that any seller acts illegally, that the medicine is dangerous, or why the model answered as it did']]);
}

/* ---------- G1 ---------- */
function renderG1() {
  const o = S.overview, g = o.g1;
  const stats = clear($('g1Stats'));
  for (const [v, k] of [[g.locked.verdict, 'TERMINAL VERDICT (LOCKED RULE)'], [`${g.locked.n_positive} / ${g.locked.denominator}`, 'E IN BOTH PASSES (THRESHOLD ≥ 3)'],
    [`${g.locked.outside_family.length}`, 'OUTSIDE SERRATIOPEPTIDASE FAMILY (NEED ≥ 1)'], [xp(o).agreement ? xp(o).agreement.G1_PRIMARY : '—', 'EXPERIMENTAL PARSER = LOCKED LABEL (DEV SET)']]) {
    const s = el('div', 'stat'); s.append(el('div', 'v', v), el('div', 'k', k)); stats.append(s);
  }
  const t = clear($('g1Table'));
  const hr = el('tr'); for (const h of ['Q', 'Notice', 'Exact composition', 'Family', 'Pass A', 'Pass B', 'Experimental parser A/B', 'Positive', 'Status prompt', 'AI Mode (exploratory)']) hr.append(el('th', '', h));
  t.append(hr);
  for (const c of o.cases) {
    const tr = el('tr', c.g1_positive ? 'pos' : '');
    const ge = xp(c).g1_engine || {}; const eng = el('td'); eng.append(lab(ge.A), document.createTextNode(' '), lab(ge.B));
    const a = el('td'); a.append(lab(c.g1_locked.A)); const b = el('td'); b.append(lab(c.g1_locked.B));
    const st = el('td'); if (c.status) st.append(lab(c.status.gold_label)); else st.textContent = '—';
    const am = el('td'); if (c.ai_mode) am.append(lab(c.ai_mode.gold_label), el('span', 'muted', ' coder'));
    const comp = el('td'); const link = el('a', '', c.composition); link.href = '#'; link.addEventListener('click', ev => { ev.preventDefault(); selectCase(c.id); showView('case'); }); comp.append(link);
    tr.append(el('td', 'mono', c.query_id), el('td', 'mono', c.notice), comp, el('td', '', c.in_family ? 'yes' : '—'), a, b, eng, el('td', '', c.g1_positive ? 'YES' : 'no'), st, am);
    t.append(tr);
  }
  const s = clear($('sensTable'));
  const h2 = el('tr'); for (const h of ['Reading', 'Positives', 'Outside family', 'Verdict']) h2.append(el('th', '', h)); s.append(h2);
  for (const r of g.sensitivity) { const tr = el('tr'); tr.append(el('td', '', r.reading), el('td', '', r.positives.n_positive), el('td', '', r.positives.outside_family.join(', ')), el('td', '', r.positives.verdict)); s.append(tr); }
  const ic = clear($('integrityChain')), cp = o.corpus;
  kv(ic, [['Preregistration SHA-256', cp.prereg_sha256], ['Archive manifest SHA-256', cp.archive_manifest_sha256],
    ...Object.entries(cp.lock_records).map(([k, v]) => [k, v]), ['Replay corpus SHA-256', cp.sha256], ['Corpus = manifest', cp.manifest_match ? 'yes' : 'NO — rebuild'],
    ['Records', cp.n_records + ' (20 primary, 4 controls, 10 AI Mode, 7 status)'], ['Locked summary table re-parsed', g.summary_table_consistent ? 'consistent' : 'INCONSISTENT']]);
  ic.append(el('p', 'fineprint', cp.origin_statement));
}

/* ---------- integrity & benchmark ---------- */
function renderIntegrity() {
  const o = S.overview, t = clear($('noticeTable'));
  const hr = el('tr'); for (const h of ['Capture', 'AI status answer for', 'Notice cited by AI', 'Gazette notice for this composition', 'Check', 'Cited notice actually covers']) hr.append(el('th', '', h)); t.append(hr);
  for (const n of o.notice_integrity) {
    const tr = el('tr', n.status === 'MISMATCH' ? 'bad' : '');
    tr.append(el('td', 'mono', n.record_id), el('td', '', n.query), el('td', 'mono', n.cited), el('td', 'mono', n.expected), el('td', '', n.status), el('td', '', n.cited_notice_composition || '—'));
    t.append(tr);
  }
  const X = xp(o), b = clear($('benchTable'));
  const cols = ['system', 'primary_label_agreement', 'E_flag_precision', 'E_flag_recall', 'false_E_flags', 'status_answers_labelled_D', 'ai_mode_agreement', 'g1_verdict_from_system_labels'];
  const heads = ['System', 'Primary labels (20)', 'E precision', 'E recall', 'False E flags', 'Status → D', 'AI Mode (10)', 'G1 from its labels'];
  const hr2 = el('tr'); heads.forEach(h => hr2.append(el('th', '', h))); b.append(hr2);
  for (const s of X.benchmark.systems) { const tr = el('tr'); cols.forEach(k => tr.append(el('td', k === 'system' ? '' : 'mono', s[k]))); b.append(tr); }
  $('benchNote').textContent = 'EXPERIMENTAL research metrics on the development set, not verified accuracy. ' + X.benchmark.note + ' Keyword matching does well on this easy corpus; the hostile suite (adjacent bans, other-entity bans, cross-surface citations, forged provenance) is where it fails — see Verify an import.';
  const adv = X.adversarial, at = clear($('advTable'));
  const systems = Object.keys(adv.scores);
  const ah = el('tr'); ['Case', 'Rule label', ...systems.map(s => s.split(' (')[0])].forEach(h => ah.append(el('th', '', h))); at.append(ah);
  for (const r of adv.rows) {
    const tr = el('tr'); tr.append(el('td', '', r.case)); const g = el('td'); g.append(lab(r.gold)); tr.append(g);
    for (const s of systems) { const td = el('td'); td.append(lab(r[s])); if (r[s] !== r.gold) td.append(el('span', 'muted', ' ✗')); tr.append(td); }
    at.append(tr);
  }
  const st = el('tr'); st.append(el('td', '', 'Score (false E flags)'), el('td'));
  for (const s of systems) st.append(el('td', 'mono', `${adv.scores[s]} (${adv.false_E_flags[s]})`));
  at.append(st);
  $('advNote').textContent = adv.note;
  const d = clear($('disagree'));
  for (const x of X.disagreements) { d.append(el('p', '', `${x.record_id}: locked coder ${x.gold}, engine ${x.engine}.`)); const ol = el('ol', 'trace'); x.trace.forEach(s => ol.append(el('li', '', s))); d.append(ol); }
  d.append(el('p', 'fineprint', 'AI Mode never names the ingredients in its lead sentence for this answer, so the engine abstains (B) rather than inferring the exact set — the preregistration requires the AI text itself to establish it.'));
}

/* ---------- verify ---------- */
function renderVerify(r, note) {
  const p = clear($('verifyResult'));
  if (note) p.append(el('p', 'fineprint', note));
  const pv = r.provenance, rx = xp(r);
  const pill = el('div', 'pill ' + (r.origin === 'TRUSTED_LOCAL_SERPAPI_CAPTURE' ? 'ok' : 'bad'), r.origin.replaceAll('_', ' ')); p.append(pill);
  kv(p, [['Declared as', pv.declared_source_kind || '—'], ['Live-verified', pv.live_verified ? 'yes' : 'NO'], ['Metadata consistency', pv.metadata_consistency + ' (never upgrades trust)'],
    ['Experimental tier (unverified)', 'T' + rx.evidence_tier + ' · ' + rx.tier_status],
    ['Organic binding (experimental)', (r.organic_binding || rx.organic_binding || {}).status], ['Publication', 'Not determined by software (experimental gate: ' + (rx.publication_gate || {}).decision + ')']]);
  p.append(el('p', 'fineprint', pv.statement));
  if (pv.checks && pv.checks.length) {
    p.append(el('div', 'smallcap', 'PROVIDER-METADATA CHECKS'));
    const ul = el('ul', 'checks'); for (const c of pv.checks) { const li = el('li'); li.append(el('span', 'st ' + c.status, c.status + (c.advisory ? '*' : '')), el('span', '', c.check + (c.detail ? ' — ' + c.detail : ''))); ul.append(li); } p.append(ul);
  }
  p.append(el('div', 'smallcap', 'PER-SURFACE RESULT — MECHANICAL OBSERVATIONS, THEN EXPERIMENTAL READING'));
  for (const a of r.answers) {
    if (a.status === 'ABSENT') continue;
    if (a.observations) renderObservations(p, a.observations);
    const ax = xp(a), tr = (ax.analysis || {}).decision_trace || [];
    kv(p, [[a.surface + ' · experimental', `${labelName(ax.prereg_label)} · tier T${ax.tier} — unverified parser reading`], ['Citation binding', a.citation_binding], ['Why (experimental)', ((ax.tier_basis || []).join(' ') || tr.slice(-1)[0] || '—')]]);
  }
  const cp = r.cited_pages || rx.cited_pages || [];
  if (cp.length) {
    p.append(el('div', 'smallcap', 'CITED-PAGE TEXT SUPPLIED WITH THE IMPORT'));
    for (const c of cp) kv(p, [[c.url || '—', `${c.verification}; claim-bound: ${c.bound_to_current_use_claim ? 'yes' : 'no'} (support for the claim is an experimental reading)`]]);
  }
  for (const n of r.notice_integrity || []) p.append(el('div', 'notice-check ' + (n.status === 'MATCH' ? 'match' : 'mismatch'), `Notice-number string: “${n.cited}”, registry notice for the target ${n.expected} → ${n.status} (string match)`));
}
function renderSamples() {
  const box = $('sampleButtons');
  for (const s of window.BANLAG_SAMPLES || []) {
    const b = el('button', 'button hostile', '⚑ ' + s.name); b.type = 'button'; b.title = s.note;
    b.addEventListener('click', async () => { try { renderVerify(await post('/api/evaluate', s.payload), 'SYNTHETIC hostile sample — ' + s.note); } catch (e) { clear($('verifyResult')).append(el('p', '', 'Rejected: ' + e.message)); } });
    box.append(b);
  }
  $('fileInput').addEventListener('change', async ev => {
    const f = ev.target.files && ev.target.files[0]; if (!f) return;
    try { if (f.size > 2 * 1024 * 1024) throw Error('Maximum import is 2 MB'); renderVerify(await post('/api/evaluate', JSON.parse(await f.text())), 'Imported file: ' + f.name); }
    catch (e) { clear($('verifyResult')).append(el('p', '', 'Rejected: ' + e.message)); } finally { ev.target.value = ''; }
  });
  $('checkMatch').addEventListener('click', async () => {
    const names = $('ingredients').value.split(',').map(x => x.trim()).filter(Boolean);
    try { const x = await post('/api/match', { ingredients: names });
      $('matchResult').textContent = x.status === 'EXACT_NOTIFICATION_MATCH' ? `EXACT MATCH · ${x.entry.notice} · ${x.match_strength}` : `${x.status} · ${x.reason}` + (x.relations && x.relations.length ? ' (' + x.relations.map(r => r.relation.toLowerCase() + ' of ' + r.id).join(', ') + ')' : '');
      $('matchResult').style.color = x.status === 'EXACT_NOTIFICATION_MATCH' ? '#c8fb75' : '#ffc77d';
    } catch (e) { $('matchResult').textContent = 'Error: ' + e.message; }
  });
}

/* ---------- live capture rendering (shared by the case file and the SerpApi tab) ---------- */
const REL = { EXACT: 'all of this set’s names appear (mentions; not proof of an exhaustive ingredient list)', EXACT_LOWER_BOUND: 'names this set, then cut off “…” (could be a larger combination)', SUBSET: 'fewer ingredients',
  LOWER_BOUND_SUBSET: 'fewer ingredients, cut off', SUPERSET: 'more ingredients', SINGLE_COMPONENT: 'one ingredient only', OTHER_FORMULATION: 'a different set', NO_FORMULATION_NAMED: 'no formulation named',
  UNRECOGNISED_COMPONENT: 'lists a component BANLAG cannot identify (unresolved)',
  CONFLICTING_VIEWS: 'title, snippet and URL name different formulations (unresolved)', MULTIPLE_FORMULATIONS: 'names more than one combination (unresolved)' };
function relChip(r) { const s = el('span', 'rel ' + r, r.replaceAll('_', ' ')); s.title = REL[r] || r; return s; }
function cell(k, v) { const c = el('div', 'cell'); c.append(el('div', 'k', k)); const vv = el('div', 'v'); if (v instanceof Node) vv.append(v); else vv.textContent = v; c.append(vv); return c; }
function labCell(k, label, note) { const f = document.createDocumentFragment(); f.append(lab(label), el('span', '', note)); return cell(k, f); }
function renderFindings(target, coh) {
  for (const f of coh.findings) {
    const box = el('div', 'finding amber');
    if (f.type === 'RESTRICTION_CITATIONS_DO_NOT_NAME_THIS_NOTICE') {
      box.append(el('b', '', 'Candidate finding (experimental, needs human verification): the “prohibited” sentence’s citations may not concern this notice. '), el('span', '', f.statement + ' '));
      for (const s of f.other_notice_sources) box.append(el('span', '', `Reference [${s.index}]’s captured metadata names the ingredients of ${S.registry[s.entry] || s.entry} (${s.notice}) — candidate mapping to a different notified combination. `));
      for (const s of f.unresolved_sources) box.append(el('span', '', `Reference [${s.index}] is cut off or names no formulation, so it stays unresolved and could still concern this notice. `));
    } else { box.append(el('b', '', 'Candidate finding (experimental): a current-use claim may cite other formulations. '), el('span', '', f.statement)); }
    target.append(box);
  }
  const cov = coh.coverage || {};
  const unresolved = (cov.unresolved_references || []).map(i => '[' + i + ']').join(', ');
  target.append(el('div', 'finding grey', `Coherence status: ${(coh.status || '').replaceAll('_', ' ').toLowerCase()}. ` +
    `${cov.cited_references || 0} cited references read from captured titles, snippets and URLs` + (unresolved ? `; unresolved: ${unresolved}` : '') +
    '. No detected mismatch is not proof that a citation is coherent.'));
}
function renderCoherenceTable(target, coh) {
  const t = el('table', 'grid'); const h = el('tr'); ['Ref', 'Source', 'Formulation it names', 'vs this notice', 'Mentions a ban', 'Cited by'].forEach(x => h.append(el('th', '', x))); t.append(h);
  const citedBy = {}; for (const r of coh.claims) for (const c of r.cited) (citedBy[c.index] = citedBy[c.index] || []).push(r.kind === 'OTHER' ? r.claim_id : r.claim_id + ' (' + r.kind.toLowerCase().replace('_', '-') + ')');
  for (const r of coh.references) {
    const tr = el('tr'); const rel = el('td'); rel.append(relChip(r.relation));
    tr.append(el('td', 'mono', '[' + r.index + ']'), el('td', '', r.source || '—'), el('td', '', (r.ingredients.join(' + ') || '—') + (r.truncated ? ' …' : '') + (r.registry_entry ? ` = ${r.registry_entry}` : '') + (r.basis ? ` (from ${r.basis.replace('_', ' ')})` : '')),
      rel, el('td', '', r.mentions_restriction ? 'yes' : '—'), el('td', 'mono', (citedBy[r.index] || []).join(', ')));
    t.append(tr);
  }
  const w = el('div', 'tablewrap'); w.append(t); target.append(w);
  target.append(el('p', 'fineprint', coh.note + ' Listing a source is not an allegation about any publisher or product.'));
}
function renderLiveRun(run, target, archiveCase) {
  const a = run.answers && run.answers[0];
  const strip = el('div', 'strip');
  if (archiveCase) {
    strip.append(labCell('BROWSER ARCHIVE · PASS A', archiveCase.g1_locked.A, fmtTime(archiveCase.uses.A && archiveCase.uses.A.captured_at).slice(11)),
      labCell('BROWSER ARCHIVE · PASS B', archiveCase.g1_locked.B, fmtTime(archiveCase.uses.B && archiveCase.uses.B.captured_at).slice(11)));
  }
  const created = run.calls[0] && run.calls[0].provider_created_at;
  const liveCell = labCell('SERPAPI · AI OVERVIEW · EXPERIMENTAL READING', a ? xp(a).prereg_label : 'A', utcToIst(created).slice(11)); liveCell.title = 'SerpApi created_at ' + (created || '—') + ' · the label is an unverified historical/experimental reading';
  strip.append(liveCell,
    cell('EXPERIMENTAL TIER', `T${xp(run).evidence_tier} · ${xp(run).tier_status}`), cell('ORIGIN', run.origin === 'TRUSTED_LOCAL_SERPAPI_CAPTURE' ? 'SerpApi capture · seal verified with this machine’s key' : run.origin.replaceAll('_', ' ') + ' — origin not authenticated here'));
  target.append(strip);
  if (archiveCase) target.append(el('p', 'fineprint', 'Different client, location (Mumbai vs Jabalpur) and time: a separate observation, not a replication. Disclosure for the same query varied.'));
  if (!a) { target.append(el('p', 'muted', 'No AI Overview text in this run.')); return; }
  const g = el('div', 'livegrid'); const left = el('div'), right = el('div');
  left.append(el('div', 'smallcap', 'AI OVERVIEW TEXT AS CAPTURED · CHIPS = CITED REFERENCES (reference_indexes) · HIGHLIGHTS = EXPERIMENTAL'));
  const box = el('div', 'answer'); renderAnswer(a, box, { noCards: true }); left.append(box);
  left.append(el('div', 'smallcap', 'EXPERIMENTAL PARSER TRACE (UNVERIFIED)'));
  const ol = el('ol', 'trace'); (xp(a).decision_trace || []).forEach(t => ol.append(el('li', '', t))); left.append(ol);
  if (a.observations) renderObservations(right, a.observations);
  right.append(el('div', 'smallcap', 'CANDIDATE CITATION ↔ FORMULATION READING (EXPERIMENTAL)'));
  const coh = a.citation_coherence || xp(a).citation_coherence;
  if (coh) { renderFindings(right, coh); renderCoherenceTable(right, coh); }
  g.append(left, right); target.append(g);
  const o = el('div', 'finding grey');
  const t2 = xp(a).tier2_hits || [];
  o.append(el('b', '', 'Same search, organic results: '), el('span', '', `${run.organic.length} results captured; experimental reading: ${t2.length} candidate(s) stating the exact restriction (unverified). `));
  const sc = run.status_capture || xp(run).status_capture;
  if (sc) { const hits = sc.organic_exact_restriction_hits || xp(sc).organic_exact_restriction_hits || [];
    o.append(el('b', '', 'Separately asked status search: '), el('span', '', `AI Overview ${sc.ai_overview_status.replaceAll('_', ' ').toLowerCase()}; experimental reading: ${hits.length} organic candidate(s) (position ${hits.map(h => h.position).join(', ') || '—'}).`)); }
  target.append(o);
  const ck = run.provenance.clock_check;
  if (ck && ck.status === 'LOCAL_CLOCK_BEHIND_PROVIDER') target.append(el('p', 'fineprint', `Clock check: this machine's receipt times are ${ck.calls.map(c => c.received_minus_provider_created_s + ' s').join(', ')} relative to SerpApi's creation times — the local clock is behind; provider times are used for chronology.`));
}
function renderObservations(target, obs) {
  target.append(el('div', 'smallcap', 'MECHANICAL OBSERVATIONS · reference_indexes → CAPTURED REFERENCE · TYPED GAZETTE SETS'));
  if (obs.target) target.append(el('p', 'fineprint', `Target (Gazette registry): ${obs.target.notice} · ${obs.target.ingredients.join(' + ')}. Ingredient names below are literal string matches; a mention list is not an exhaustive ingredient list.`));
  const t = el('table', 'grid'); const h = el('tr'); ['Block', 'Ref', 'Captured source / title', 'Registry names present', 'Notice strings', 'Candidate entry · typed difference vs target', 'Open questions'].forEach(x => h.append(el('th', '', x))); t.append(h);
  for (const b of obs.blocks) {
    if (!b.linked_references.length && !b.unlinked_indexes.length) continue;
    const rows = b.linked_references.length ? b.linked_references : [null];
    rows.forEach((r, i) => {
      const tr = el('tr');
      const bt = el('td', '', i ? '' : b.block_id + ' · “' + b.text.slice(0, 90) + (b.text.length > 90 ? '…' : '') + '”'); bt.title = b.text;
      if (!r) { tr.append(bt, el('td', 'mono', '—'), el('td', '', 'no linkable reference'), el('td'), el('td'), el('td'), el('td', '', b.unlinked_indexes.map(u => u.value + ' ' + u.reason).join('; '))); t.append(tr); return; }
      const diffs = (r.candidate_differences_from_target || []).map(d => `${d.to_entry} ${d.to_notice}: +${d.added.join(', +') || '∅'}${d.removed.length ? ' −' + d.removed.join(', −') : ''} (candidate)`);
      const cands = r.candidate_entries.map(c => c.entry + ' ' + c.notice).join(', ');
      tr.append(bt, el('td', 'mono', '[' + r.index + ']'), el('td', '', (r.source || '—') + ' — ' + (r.title || '—')), el('td', '', r.registry_names_present.join(' + ') || '—'),
        el('td', 'mono', r.notice_strings_present.map(n => n.string).join(', ') || '—'), el('td', '', diffs.join('; ') || (cands ? cands + ' (candidate)' : '—')),
        el('td', '', [r.unresolved, ...(i ? [] : b.unlinked_indexes.map(u => u.value + ' ' + u.reason))].filter(Boolean).join('; ') || '—'));
      if (r.link) tr.title = r.link;
      t.append(tr);
    });
  }
  const w = el('div', 'tablewrap'); w.append(t); target.append(w);
  target.append(el('p', 'fineprint', obs.basis));
}
function renderCaseLive(c) {
  const p = clear($('caseLive'));
  if (!c.live_runs || !c.live_runs.length) {
    p.append(el('p', 'muted', 'No sealed SerpApi capture for this notice yet. Live captures run only from the approval-gated CLI; see the SerpApi tab for prepared plans.'));
    return;
  }
  for (const run of c.live_runs) renderLiveRun(run, p, c);
}

/* ---------- live tab ---------- */
async function renderLive() {
  const body = clear($('liveBody'));
  let d; try { d = await api('/api/live'); } catch (e) { body.append(el('p', '', 'Live status unavailable: ' + e.message)); return; }
  const top = el('div', 'lowergrid');
  const left = el('section', 'panel'), right = el('section', 'panel');
  const lt = el('div', 'paneltop'); lt.append(el('span', '', 'WHY SERPAPI IS THE INSTRUMENT, NOT A DECORATION')); left.append(lt);
  const li = el('div', 'panelinner'); left.append(li);
  li.append(el('p', '', 'Browser captures prove the phenomenon but cannot carry it further: Google shows source names, not URLs, so no claim can be bound to its cited page. SerpApi returns the same India AI Overview as structured text_blocks with reference_indexes, its references, and the same search\'s organic results — which is what Tier 2 (same-search discoverability) and Tier 3 (claim-bound cited page) need, and what makes the audit repeatable for every notice.'));
  kv(li, [['Engines', 'google (AI Overview + organic) · google_ai_overview (page_token follow-up, < 1 min) · google_ai_mode'], ['Trust', 'collector seals raw bytes + params + provider IDs with a machine-local HMAC; imports never reach this tier'], ['Server', 'never calls SerpApi; only reads the sealed store']]);
  const rt = el('div', 'paneltop'); rt.append(el('span', '', 'PLANS · EACH RUNS ONLY AFTER APPROVAL OF ITS EXACT HASH')); right.append(rt);
  const ri = el('div', 'panelinner'); right.append(ri);
  for (const p of d.plans) {
    const status = p.executed_runs.length ? 'EXECUTED · ' + p.executed_runs.join(', ') : 'PREPARED · AWAITING EXPLICIT APPROVAL';
    ri.append(el('div', 'smallcap', `${p.file} · ${p.plan.case} · max ${p.plan.max_calls} calls · ${status}`));
    ri.append(el('div', 'bottommeta', 'SHA-256 ' + p.sha256));
    for (const c of p.plan.calls) ri.append(el('pre', 'code', `${c.call_id} ${c.engine}${c.page_token_from ? ' (page_token from ' + c.page_token_from + ', only if needed)' : ''}  ` + JSON.stringify(c.params)));
  }
  ri.append(el('p', 'fineprint', 'CLI only: python -m banlag.collector <plan> --approve <sha256>, with BANLAG_SERPAPI_APPROVAL set to the same hash. No retries; any non-Success provider status stops the run; the sealing key must sit outside the project and any synced folder.'));
  top.append(left, right); body.append(top);
  if (!d.runs.length) body.append(el('p', 'finding grey', 'No sealed SerpApi capture on this machine. (Sealed captures are machine-local and not published by default.)'));
  for (const r of d.runs) {
    const sec = el('section', 'panel spaced'); const rh = el('div', 'paneltop');
    rh.append(el('span', '', `SEALED RUN ${r.run_id} · ${r.case || ''} ${r.notice || ''} · “${r.query || ''}”`)); sec.append(rh);
    const rb = el('div', 'panelinner'); sec.append(rb);
    if (r.error) { rb.append(el('p', '', 'Cannot evaluate: ' + r.error)); body.append(sec); continue; }
    renderLiveRun(r, rb, null);
    rb.append(el('div', 'smallcap', 'CALLS (EACH SEALED: RAW BYTES + PARAMS + PROVIDER IDS, HMAC)'));
    const t = el('table', 'grid'); const h = el('tr'); ['Call', 'Engine', 'HTTP', 'SerpApi search ID', 'Provider created', 'Seal', 'Raw SHA-256'].forEach(x => h.append(el('th', '', x))); t.append(h);
    for (const c of r.calls) { const tr = el('tr'); tr.append(el('td', 'mono', c.call_id), el('td', 'mono', c.engine), el('td', 'mono', c.http_status), el('td', 'mono', c.search_id || '—'),
      el('td', 'mono', utcToIst(c.provider_created_at)), el('td', '', c.origin + (c.reasons.length ? ' — ' + c.reasons.join('; ') : '')), el('td', 'mono', short(c.raw_sha256))); t.append(tr); }
    const w = el('div', 'tablewrap'); w.append(t); rb.append(w);
    body.append(sec);
  }
  $('netStatus').textContent = STATIC ? `◌ Read-only static demo · ${d.runs.length} archived SerpApi run(s)` : `◌ Local server · 0 outbound requests · ${d.runs.length} sealed SerpApi run(s) on this machine`;
}

/* ---------- shell ---------- */
function showView(v) {
  document.querySelectorAll('.tab').forEach(t => { const on = t.dataset.view === v; t.classList.toggle('active', on); t.setAttribute('aria-selected', on); });
  document.querySelectorAll('.view').forEach(s => { s.hidden = s.id !== 'view-' + v; });
  if (v === 'live') renderLive();
  window.scrollTo({ top: 0 });
}
async function init() {
  try { S.overview = await api('/api/overview'); }
  catch (e) { document.body.prepend(el('p', 'banner warn', (STATIC ? 'Demo data failed to load (' : 'Local server unavailable — run: python -m banlag (') + e.message + ')')); return; }
  const o = S.overview;
  S.registry = Object.fromEntries(o.cases.map(c => [c.id, c.composition]));
  const integ = o.corpus.integrity || { status: 'FAILED', reasons: ['integrity status missing'] };
  if (integ.status !== 'VERIFIED') {
    const b = el('div', 'banner warn', '⛔ Replay corpus failed its integrity check — archive labels, G1 verdict and findings are suppressed and every publication gate is WITHHOLD. ' + integ.reasons.join('; '));
    document.querySelector('.content').prepend(b);
  }
  if (STATIC) $('netStatus').textContent = '◌ Read-only static demo · replayed responses';
  $('provBadge').textContent = `Archive: preregistered browser test, G1 ${o.g1.locked.verdict} · Live: ${o.live.sealed_runs} sealed SerpApi run(s)`;
  $('footCorpus').textContent = `REPLAY CORPUS ${short(o.corpus.sha256)} · PREREG ${short(o.corpus.prereg_sha256)} · LEGAL STATUS AS OF ${o.legal_status.as_of}`;
  renderSidebar(); renderG1(); renderIntegrity(); renderSamples();
  document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => showView(t.dataset.view)));
  document.querySelectorAll('.segbtn').forEach(b => b.addEventListener('click', () => { S.pass = b.dataset.pass; renderUses(S.cases[S.current]); }));
  const head = o.cases.find(c => c.headline) || o.cases[0];
  await selectCase(head.id);
}
init();
