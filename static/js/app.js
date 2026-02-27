// ═══════════════════════════════════════════════════════════════
//  FITTRACKER — Frontend (Plotly.js charts, JSON backend)
// ═══════════════════════════════════════════════════════════════

let allExercises = [];
let allPrograms  = [];
let currentProgramDetail  = null;
let currentSessionForExercise = null;
let workoutTimerInterval  = null;
let workoutStartTime      = null;
let currentWorkoutData    = {};

// ── INIT ──────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  document.getElementById('today-date').textContent =
    new Date().toLocaleDateString('fr-FR', {weekday:'long', year:'numeric', month:'long', day:'numeric'});
  document.getElementById('workout-date-display').textContent =
    new Date().toLocaleDateString('fr-FR', {weekday:'long', day:'numeric', month:'long'});
  document.getElementById('workout-date-input').value = new Date().toISOString().split('T')[0];

  document.querySelectorAll('.nav-link').forEach(link =>
    link.addEventListener('click', e => { e.preventDefault(); showPage(link.dataset.page); })
  );

  await Promise.all([loadExercises(), loadPrograms()]);
  await loadDashboard();
});

// ── NAVIGATION ─────────────────────────────────────────────────

function showPage(page) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
  document.querySelectorAll('.bnav-item').forEach(b => b.classList.remove('active'));

  document.getElementById('page-' + page).classList.add('active');

  const sideLink = document.querySelector(`.nav-link[data-page="${page}"]`);
  if (sideLink) sideLink.classList.add('active');

  const bnavBtn = document.querySelector(`.bnav-item[data-page="${page}"]`);
  if (bnavBtn) bnavBtn.classList.add('active');

  // Scroll to top on mobile page change
  document.querySelector('.main-content').scrollTo(0, 0);

  if (page === 'history') loadHistory();
  if (page === 'records') loadRecords();
}

// ── DATA ────────────────────────────────────────────────────────

async function loadExercises() {
  allExercises = await fetch('/api/exercises').then(r => r.json());
  renderExercisesPage(allExercises);
  populateProgressSelect();
}

async function loadPrograms() {
  allPrograms = await fetch('/api/programs').then(r => r.json());
  renderPrograms();
  populateWorkoutProgramSelect();
}

async function loadDashboard() {
  // KPIs
  const stats = await fetch('/api/stats/summary').then(r => r.json());
  document.getElementById('kpi-month').textContent  = stats.month_sessions;
  document.getElementById('kpi-week').textContent   = stats.week_sessions;
  document.getElementById('kpi-volume').textContent = fmtVol(stats.total_volume);
  document.getElementById('kpi-prs').textContent    = stats.pr_count;

  // Recent logs
  const logs = await fetch('/api/logs?limit=5').then(r => r.json());
  const el = document.getElementById('recent-logs');
  el.innerHTML = logs.length === 0
    ? `<div class="empty-state"><div class="empty-icon">🏋️</div><p>Aucune séance enregistrée. Commencez !</p></div>`
    : logs.map(l => renderLogCard(l)).join('');

  // Plotly charts (each loads independently)
  loadPlotlyChart('/api/charts/weekly_volume',      'chart-weekly');
  loadPlotlyChart('/api/charts/muscle_distribution','chart-muscle');
  loadPlotlyChart('/api/charts/heatmap',            'chart-heatmap');
  loadPlotlyChart('/api/charts/pr_bars',            'chart-pr-bars');
}

async function loadPlotlyChart(endpoint, divId) {
  try {
    const figData = await fetch(endpoint).then(r => r.json());
    if (!figData || !figData.data) {
      document.getElementById(divId).innerHTML =
        `<div class="empty-state"><div class="empty-icon">📊</div><p>Pas encore de données</p></div>`;
      return;
    }
    const config = { responsive: true, displayModeBar: false, locale: 'fr' };
    Plotly.newPlot(divId, figData.data, figData.layout, config);
  } catch(e) {
    console.warn('Chart error', endpoint, e);
  }
}

async function loadProgressChart() {
  const exId = document.getElementById('progress-ex-select').value;
  const div = document.getElementById('chart-progress');
  if (!exId) {
    div.innerHTML = `<div class="empty-state"><div class="empty-icon">📈</div><p>Choisissez un exercice ci-dessus</p></div>`;
    return;
  }
  try {
    const figData = await fetch(`/api/charts/exercise_progress/${exId}`).then(r => r.json());
    if (!figData || !figData.data) {
      div.innerHTML = `<div class="empty-state"><div class="empty-icon">📈</div><p>Pas encore de données pour cet exercice</p></div>`;
      return;
    }
    Plotly.newPlot('chart-progress', figData.data, figData.layout, {responsive:true, displayModeBar:false});
  } catch(e) { console.warn(e); }
}

// ── EXERCISES PAGE ──────────────────────────────────────────────

function renderExercisesPage(exs) {
  const grid = document.getElementById("exercises-grid");
  if (!exs.length) {
    grid.innerHTML = `<div class="empty-state"><div class="empty-icon">💪</div><p>Aucun exercice</p></div>`;
    return;
  }
  grid.innerHTML = exs.map(e => `
    <div class="exercise-card ex-tooltip-wrap" data-exid="${e.id}">
      <div class="ex-name">${e.name}</div>
      <div style="font-size:11px;color:var(--text-muted);margin:2px 0">${e.muscle_group||""}</div>
      <div class="ex-meta">
        <span class="ex-tag tag-${e.category}">${catLabel(e.category)}</span>
        ${e.is_custom?"<span class=\"ex-tag\" style=\"background:rgba(0,230,118,.1);color:#00e676\">Custom</span>":""}
      </div>
      <div style="font-size:10px;color:var(--text-muted);margin-top:8px;opacity:0.6">ℹ Survol pour détails</div>
    </div>`).join("");
  grid.querySelectorAll(".exercise-card").forEach(card => {
    const ex = exs.find(e => e.id === card.dataset.exid);
    if (ex) attachTooltip(card, ex);
  });
}

function filterExercises(btn, cat) {
  document.querySelectorAll('#page-exercises .filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderExercisesPage(cat ? allExercises.filter(e => e.category === cat) : allExercises);
}

async function saveExercise() {
  const data = { name: v('ex-name'), muscle_group: v('ex-muscle'), category: v('ex-cat'), description: v('ex-desc') };
  if (!data.name) return toast('Nom requis','error');
  await post('/api/exercises', data);
  closeModal('modal-exercise');
  toast('Exercice créé !');
  await loadExercises();
}

// ── PROGRAMS PAGE ───────────────────────────────────────────────

function renderPrograms() {
  const grid = document.getElementById('programs-grid');
  grid.innerHTML = allPrograms.map(p => `
    <div class="program-card">
      <span class="prog-badge ${p.is_custom?'':'preset'}">${p.is_custom?'Custom':'Intégré'}</span>
      <h3>${p.name}</h3>
      <div class="prog-desc">${p.description||''}</div>
      <div class="prog-spw">📅 ${p.sessions_per_week} séance${p.sessions_per_week>1?'s':''}/semaine</div>
      <div class="prog-sessions">${p.sessions.map(s=>`<span class="prog-session-chip">${s.name}</span>`).join('')}</div>
      <div class="prog-actions">
        <button class="btn-primary btn-sm" onclick="openProgramDetail('${p.id}')">✏️ Éditer</button>
        ${p.is_custom?`<button class="btn-secondary btn-sm" onclick="deleteProgram('${p.id}')">🗑️ Supprimer</button>`:''}
      </div>
    </div>`).join('');
}

async function saveProgram() {
  const data = { name: v('prog-name'), description: v('prog-desc'), sessions_per_week: parseInt(v('prog-spw'))||3 };
  if (!data.name) return toast('Nom requis','error');
  const prog = await post('/api/programs', data);
  closeModal('modal-program');
  toast('Programme créé !');
  await loadPrograms();
  openProgramDetail(prog.id);
}

async function deleteProgram(id) {
  if (!confirm('Supprimer ce programme ?')) return;
  await fetch(`/api/programs/${id}`, {method:'DELETE'});
  toast('Programme supprimé');
  await loadPrograms();
}

function openProgramDetail(progId) {
  currentProgramDetail = allPrograms.find(p => p.id === progId);
  if (!currentProgramDetail) return;
  document.getElementById('detail-prog-name').textContent = currentProgramDetail.name;
  renderDetailSessions();
  openModal('modal-program-detail');
}

function renderDetailSessions() {
  const container = document.getElementById('detail-sessions');
  const p = currentProgramDetail;
  if (!p.sessions?.length) {
    container.innerHTML = `<div class="empty-state" style="padding:20px"><p>Aucune séance. Ajoutez-en une ci-dessous.</p></div>`;
    return;
  }
  container.innerHTML = p.sessions.map(s => `
    <div class="detail-session-card">
      <div class="detail-session-header">
        <span>${s.name}</span>
        ${s.day_of_week?`<span class="day-badge">${s.day_of_week}</span>`:''}
        <div class="session-actions">
          <button class="btn-primary btn-sm" onclick="openAddExercise('${s.id}')">+ Exercice</button>
          <button class="btn-icon" onclick="deleteSession('${s.id}')">🗑</button>
        </div>
      </div>
      ${s.exercises.length===0
        ? `<div style="padding:12px 16px;font-size:12px;color:var(--text-muted)">Aucun exercice</div>`
        : s.exercises.map(e => `
          <div class="detail-exercise-row ex-tooltip-wrap" data-exid="${e.exercise_id}" style="cursor:default">
            <span class="det-ex-name">${e.exercise_name} <span style="font-size:10px;color:var(--text-muted)">ℹ</span></span>
            <span class="ex-tag tag-${e.category}" style="font-size:10px">${catLabel(e.category)}</span>
            <span class="det-ex-sets">${e.sets} sets</span>
            <span class="det-ex-reps">${e.target_reps||''}</span>
            <button class="btn-icon" onclick="deleteSessionExercise('${e.id}')">✕</button>
          </div>`).join('')
      }
    </div>`).join('');

  // Attach tooltips to exercise rows in program detail
  container.querySelectorAll('.detail-exercise-row').forEach(row => {
    const ex = allExercises.find(e => e.id === row.dataset.exid);
    if (ex) attachTooltip(row, ex);
  });
}

async function addSession() {
  const name = v('new-session-name').trim();
  const day  = v('new-session-day');
  if (!name) return toast('Nom requis','error');
  await post(`/api/programs/${currentProgramDetail.id}/sessions`, {name, day_of_week: day});
  toast('Séance ajoutée !');
  await loadPrograms();
  currentProgramDetail = allPrograms.find(p => p.id === currentProgramDetail.id);
  renderDetailSessions();
  document.getElementById('new-session-name').value = '';
}

async function deleteSession(sid) {
  if (!confirm('Supprimer cette séance ?')) return;
  await fetch(`/api/sessions/${sid}`, {method:'DELETE'});
  toast('Séance supprimée');
  await loadPrograms();
  currentProgramDetail = allPrograms.find(p => p.id === currentProgramDetail.id);
  renderDetailSessions();
}

function openAddExercise(sessionId) {
  currentSessionForExercise = sessionId;
  document.getElementById('filter-cat').value = '';
  filterExercisesModal();
  openModal('modal-add-exercise');
}

function filterExercisesModal() {
  const cat = v('filter-cat');
  const filtered = cat ? allExercises.filter(e => e.category === cat) : allExercises;
  const byMuscle = {};
  filtered.forEach(e => { if (!byMuscle[e.muscle_group]) byMuscle[e.muscle_group]=[]; byMuscle[e.muscle_group].push(e); });
  let html = '';
  for (const [mg, exs] of Object.entries(byMuscle)) {
    html += `<optgroup label="${mg}">`;
    exs.forEach(e => html += `<option value="${e.id}">${e.name}</option>`);
    html += '</optgroup>';
  }
  document.getElementById('add-ex-select').innerHTML = html;
}

async function saveExerciseToSession() {
  const data = { exercise_id: v('add-ex-select'), sets: parseInt(v('add-ex-sets'))||3, target_reps: v('add-ex-reps') };
  await post(`/api/sessions/${currentSessionForExercise}/exercises`, data);
  closeModal('modal-add-exercise');
  toast('Exercice ajouté !');
  await loadPrograms();
  currentProgramDetail = allPrograms.find(p => p.id === currentProgramDetail.id);
  renderDetailSessions();
}

async function deleteSessionExercise(id) {
  await fetch(`/api/session_exercises/${id}`, {method:'DELETE'});
  toast('Exercice retiré');
  await loadPrograms();
  currentProgramDetail = allPrograms.find(p => p.id === currentProgramDetail.id);
  renderDetailSessions();
}

// ── WORKOUT ─────────────────────────────────────────────────────

function populateWorkoutProgramSelect() {
  const sel = document.getElementById('workout-program-select');
  sel.innerHTML = '<option value="">-- Programme --</option>' +
    allPrograms.map(p => `<option value="${p.id}">${p.name}</option>`).join('');
}

function loadWorkoutSessions() {
  const pid  = v('workout-program-select');
  const prog = allPrograms.find(p => p.id === pid);
  const sel  = document.getElementById('workout-session-select');
  sel.innerHTML = '<option value="">-- Séance --</option>';
  if (prog) prog.sessions.forEach(s =>
    sel.innerHTML += `<option value="${s.id}">${s.name}${s.day_of_week?' — '+s.day_of_week:''}</option>`
  );
}

function startWorkout() {
  const pid = v('workout-program-select');
  const sid = v('workout-session-select');
  if (!sid) return toast('Choisissez une séance','error');

  const prog    = allPrograms.find(p => p.id === pid);
  const session = prog?.sessions.find(s => s.id === sid);
  if (!session) return toast('Séance introuvable','error');

  currentWorkoutData = { session_id: sid, program_id: pid, log_date: v('workout-date-input') };
  document.getElementById('workout-session-name').textContent = `${prog?.name} — ${session.name}`;
  document.getElementById('workout-setup').classList.add('hidden');
  document.getElementById('workout-active').classList.remove('hidden');

  renderWorkoutExercises(session);

  workoutStartTime = Date.now();
  workoutTimerInterval = setInterval(() => {
    const e = Math.floor((Date.now()-workoutStartTime)/1000);
    document.getElementById('workout-timer').textContent =
      `⏱ ${String(Math.floor(e/60)).padStart(2,'0')}:${String(e%60).padStart(2,'0')}`;
  }, 1000);
}

function renderWorkoutExercises(session) {
  const list = document.getElementById('workout-exercises-list');
  list.innerHTML = session.exercises.map(ex => {
    const isCali = ex.category === 'calisthenics';
    const rows = Array.from({length: ex.sets}, (_,i) => `
      <tr data-set="${i+1}" data-exid="${ex.exercise_id}">
        <td style="color:var(--text-muted);font-weight:600">${i+1}</td>
        ${isCali ? `
          <td colspan="2"><input class="figure-input" type="text" placeholder="Ex: Muscle Up, L-Sit 20s, Front Lever 5s..."></td>
          <td><input class="set-input reps-input" type="number" placeholder="Reps" min="0"></td>
        ` : `
          <td><input class="set-input weight-input" type="number" placeholder="kg" min="0" step="0.5"></td>
          <td><input class="set-input reps-input" type="number" placeholder="Reps" min="0"></td>
        `}
        <td><button class="set-done-btn" onclick="this.classList.toggle('done')">✓</button></td>
      </tr>`).join('');

    return `
      <div class="exercise-workout-card">
        <div class="exercise-workout-header ex-tooltip-wrap" data-exid="${ex.exercise_id}" style="cursor:default">
          <h4>${ex.exercise_name}${isCali?'<span class="callisthenics-badge">🌟 Calisthenics</span>':''} <span style="font-size:11px;color:var(--text-muted);font-weight:400">ℹ</span></h4>
          <span class="target-reps">${ex.sets} × ${ex.target_reps||'?'}</span>
        </div>
        <table class="sets-table">
          <thead><tr>
            <th>Set</th>
            ${isCali?'<th colspan="2">Figure / Description</th>':'<th>Poids (kg)</th>'}
            <th>Reps</th>
            <th>✓</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }).join('');

  // Attach tooltips to exercise headers
  list.querySelectorAll('.exercise-workout-header').forEach(header => {
    const ex = allExercises.find(e => e.id === header.dataset.exid);
    if (ex) attachTooltip(header, ex);
  });
}

async function finishWorkout() {
  clearInterval(workoutTimerInterval);
  const sets = [];
  document.querySelectorAll('#workout-exercises-list tbody tr').forEach(row => {
    const exId   = row.dataset.exid;
    const setNum = parseInt(row.dataset.set);
    const weight = row.querySelector('.weight-input')?.value;
    const reps   = row.querySelector('.reps-input')?.value;
    const figure = row.querySelector('.figure-input')?.value?.trim();
    if (reps || weight || figure) {
      sets.push({ exercise_id: exId, set_number: setNum,
                  reps: parseInt(reps)||null, weight: parseFloat(weight)||null, figure: figure||'' });
    }
  });

  if (!sets.length && !confirm('Aucun set rempli. Sauvegarder quand même ?')) return;

  await post('/api/logs', {...currentWorkoutData, sets});
  toast('✅ Séance sauvegardée & Excel mis à jour !');

  document.getElementById('workout-active').classList.add('hidden');
  document.getElementById('workout-setup').classList.remove('hidden');
  document.getElementById('workout-timer').textContent = '⏱ 00:00';
  document.getElementById('workout-exercises-list').innerHTML = '';

  await loadDashboard();
}

// ── HISTORY ─────────────────────────────────────────────────────

async function loadHistory() {
  const logs = await fetch('/api/logs?limit=200').then(r=>r.json());
  const el = document.getElementById('history-list');
  el.innerHTML = logs.length===0
    ? `<div class="empty-state"><div class="empty-icon">📅</div><p>Aucun historique disponible.</p></div>`
    : logs.map(l => renderLogCard(l, true)).join('');
}

function renderLogCard(log, showDelete=false) {
  const vol  = log.sets.reduce((acc,s)=>acc+(s.weight||0)*(s.reps||0),0);
  const d    = new Date(log.log_date);
  const dateStr = d.toLocaleDateString('fr-FR',{day:'2-digit',month:'short'}).toUpperCase();
  return `
    <div class="log-card">
      <div class="log-date">${dateStr}</div>
      <div class="log-info">
        <strong>${log.session_name||'Séance libre'}</strong>
        <span>${log.program_name||''}</span>
      </div>
      <div class="log-stats">
        <div class="log-stat"><div class="log-stat-val">${log.sets.length}</div><div class="log-stat-lbl">Sets</div></div>
        <div class="log-stat"><div class="log-stat-val">${fmtVol(vol)}</div><div class="log-stat-lbl">Volume</div></div>
      </div>
      ${showDelete?`<button class="btn-icon" onclick="deleteLog('${log.id}')">🗑</button>`:''}
    </div>`;
}

async function deleteLog(id) {
  if (!confirm('Supprimer cette séance ?')) return;
  await fetch(`/api/logs/${id}`, {method:'DELETE'});
  toast('Séance supprimée');
  loadHistory();
  loadDashboard();
}

// ── RECORDS ─────────────────────────────────────────────────────

let allRecords = [];

async function loadRecords() {
  allRecords = await fetch('/api/stats/personal_records').then(r=>r.json());
  renderRecordsGrid(allRecords);
}

function filterRecords(btn, cat) {
  document.querySelectorAll('#page-records .filter-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  renderRecordsGrid(cat ? allRecords.filter(r=>r.category===cat) : allRecords);
}

function renderRecordsGrid(prs) {
  const grid = document.getElementById('records-grid');
  if (!prs.length) {
    grid.innerHTML=`<div class="empty-state"><div class="empty-icon">🏆</div><p>Aucun record encore. Entraînez-vous !</p></div>`;
    return;
  }
  grid.innerHTML = prs.map(r=>`
    <div class="record-card">
      <div class="rec-name">${r.exercise_name}</div>
      <div class="rec-muscle">${catLabel(r.category)}</div>
      ${r.max_weight?`
        <div class="rec-weight">${r.max_weight}</div>
        <div class="rec-unit">kg${r.reps_at_max?` × ${r.reps_at_max} reps`:''}</div>`
      :`<div class="rec-weight" style="font-size:22px;color:var(--accent-green)">—</div>`}
      <div class="rec-date">Dernier : ${r.last_performed||'—'}</div>
    </div>`).join('');
}

// ── PROGRESS SELECT ──────────────────────────────────────────────

function populateProgressSelect() {
  const sel = document.getElementById('progress-ex-select');
  const byMuscle = {};
  allExercises.forEach(e => { if (!byMuscle[e.muscle_group]) byMuscle[e.muscle_group]=[]; byMuscle[e.muscle_group].push(e); });
  let html = '<option value="">-- Choisir un exercice --</option>';
  for (const [mg, exs] of Object.entries(byMuscle)) {
    html += `<optgroup label="${mg}">`;
    exs.forEach(e => html += `<option value="${e.id}">${e.name}</option>`);
    html += '</optgroup>';
  }
  sel.innerHTML = html;
}

// ── UTILS ────────────────────────────────────────────────────────

function v(id)    { const el=document.getElementById(id); return el?.value||''; }
function post(url,data) { return fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}).then(r=>r.json()); }
function openModal(id)  { document.getElementById(id).classList.remove('hidden'); }
function closeModal(id) { document.getElementById(id).classList.add('hidden'); }

function catLabel(cat) {
  return {machine:'⚙️ Machine',free_weight:'🏋️ Haltères',bodyweight:'🤸 Corps',calisthenics:'🌟 Calisthenics'}[cat] || cat;
}

function fmtVol(v) {
  if (!v) return '0 kg';
  if (v >= 1000000) return Math.round(v/1000)/1000 + 't';
  if (v >= 1000)    return Math.round(v/100)/10 + 't';
  return Math.round(v) + ' kg';
}

function toast(msg, type='success') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `toast${type==='error'?' error':''}`;
  t.classList.remove('hidden');
  setTimeout(()=>t.classList.add('hidden'), 3200);
}

function exportExcel() {
  toast('Export en cours...');
  window.location.href = '/api/export/excel';
}

// ═══════════════════════════════════════════════════════════════
//  EXERCISE TOOLTIP SYSTEM
// ═══════════════════════════════════════════════════════════════

// Wger exercise image API — free, no key needed
// https://wger.de/api/v2/exerciseimage/?exercise={wger_id}&format=json&language=2
const WGER_IMG_CACHE = {};   // ex.id → image URL or null
let tooltipHideTimer = null;

// ── Attach tooltip to any element ─────────────────────────────

function attachTooltip(el, exercise) {
  el.addEventListener('mouseenter', (e) => showTooltip(e, exercise));
  el.addEventListener('mousemove',  (e) => positionTooltip(e));
  el.addEventListener('mouseleave', ()  => hideTooltip());
}

// ── Show ───────────────────────────────────────────────────────

async function showTooltip(e, ex) {
  clearTimeout(tooltipHideTimer);
  const tip = document.getElementById('ex-tooltip');

  // Fill text content immediately
  document.getElementById('tooltip-name').textContent = ex.name;

  // Tags
  const tags = document.getElementById('tooltip-tags');
  tags.innerHTML = `
    <span class="ex-tag tag-${ex.category}">${catLabel(ex.category)}</span>
    ${ex.muscle_group ? `<span class="ex-tag" style="background:rgba(0,212,255,.1);color:#00d4ff;font-size:10px">${ex.muscle_group}</span>` : ''}
    ${ex.is_custom ? `<span class="ex-tag" style="background:rgba(0,230,118,.1);color:#00e676;font-size:10px">Custom</span>` : ''}
  `;

  document.getElementById('tooltip-desc').textContent     = ex.description  || 'Aucune description disponible.';
  document.getElementById('tooltip-tips-text').textContent = ex.tips || '';
  document.getElementById('tooltip-secondary').innerHTML  = ex.muscles_secondary
    ? `<strong>Muscles secondaires :</strong> ${ex.muscles_secondary}` : '';

  // Show/hide tips block
  const tipsEl = document.getElementById('tooltip-tips');
  tipsEl.style.display = ex.tips ? 'block' : 'none';

  // Image zone
  const imgEl      = document.getElementById('tooltip-img');
  const loadingEl  = document.getElementById('tooltip-img-loading');
  const placeholEl = document.getElementById('tooltip-img-placeholder');

  imgEl.style.display = 'none';
  loadingEl.classList.remove('hidden');
  placeholEl.classList.add('hidden');

  tip.classList.add('visible');
  positionTooltip(e);

  // Load image (cached)
  const imgUrl = await getExerciseImage(ex);
  if (imgUrl) {
    imgEl.src = imgUrl;
    imgEl.style.display = 'block';
  } else {
    loadingEl.classList.add('hidden');
    placeholEl.classList.remove('hidden');
  }
}

function tooltipImgLoaded() {
  document.getElementById('tooltip-img-loading').classList.add('hidden');
}
function tooltipImgError() {
  document.getElementById('tooltip-img').style.display = 'none';
  document.getElementById('tooltip-img-loading').classList.add('hidden');
  document.getElementById('tooltip-img-placeholder').classList.remove('hidden');
}

// ── Position ───────────────────────────────────────────────────

function positionTooltip(e) {
  const tip = document.getElementById('ex-tooltip');
  const TW = 320, TH = 420;
  const margin = 16;
  let x = e.clientX + 14;
  let y = e.clientY - 60;

  if (x + TW > window.innerWidth - margin)  x = e.clientX - TW - 14;
  if (y + TH > window.innerHeight - margin) y = window.innerHeight - TH - margin;
  if (y < margin) y = margin;

  tip.style.left = x + 'px';
  tip.style.top  = y + 'px';
}

// ── Hide ───────────────────────────────────────────────────────

function hideTooltip() {
  tooltipHideTimer = setTimeout(() => {
    document.getElementById('ex-tooltip').classList.remove('visible');
  }, 120);
}

// ── Fetch image from Wger API ─────────────────────────────────

async function getExerciseImage(ex) {
  const cacheKey = ex.id;
  if (WGER_IMG_CACHE[cacheKey] !== undefined) return WGER_IMG_CACHE[cacheKey];

  // Try Wger API if we have a wger_id > 0
  if (ex.wger_id && ex.wger_id > 0) {
    try {
      const res = await fetch(
        `https://wger.de/api/v2/exerciseimage/?exercise=${ex.wger_id}&format=json&language=2`,
        { signal: AbortSignal.timeout(4000) }
      );
      const data = await res.json();
      if (data.results && data.results.length > 0) {
        // Prefer animated GIF first, then any image
        const gif = data.results.find(r => r.image && r.image.endsWith('.gif'));
        const url = gif ? gif.image : data.results[0].image;
        WGER_IMG_CACHE[cacheKey] = url;
        return url;
      }
    } catch (_) { /* API unavailable */ }
  }

  // Fallback : try Wger search by exercise name
  try {
    const nameQuery = encodeURIComponent(ex.name.split(' ').slice(0,3).join(' '));
    const res = await fetch(
      `https://wger.de/api/v2/exercise/search/?term=${nameQuery}&language=fr&format=json`,
      { signal: AbortSignal.timeout(3000) }
    );
    const data = await res.json();
    const suggestions = data.suggestions || [];
    if (suggestions.length > 0 && suggestions[0].data?.id) {
      const exId = suggestions[0].data.id;
      const imgRes = await fetch(
        `https://wger.de/api/v2/exerciseimage/?exercise=${exId}&format=json`,
        { signal: AbortSignal.timeout(3000) }
      );
      const imgData = await imgRes.json();
      if (imgData.results && imgData.results.length > 0) {
        const gif = imgData.results.find(r => r.image && r.image.endsWith('.gif'));
        const url = gif ? gif.image : imgData.results[0].image;
        WGER_IMG_CACHE[cacheKey] = url;
        return url;
      }
    }
  } catch (_) { /* search unavailable */ }

  WGER_IMG_CACHE[cacheKey] = null;
  return null;
}