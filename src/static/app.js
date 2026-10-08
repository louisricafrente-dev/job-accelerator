// State management
let currentStatus = 'new';
let currentLevel = 'All';
let currentRole = 'All';
let currentDateFilter = 'all';
let hasSalaryOnly = false;
let remoteOnly = false;
let hideSenior = false;
let searchQuery = '';
let jobsList = [];
let selectedIndex = 0;
let searchDebounceTimer = null;
let currentStats = {};
let mySkills = localStorage.getItem('job_accel_my_skills') || 'React, Python, TypeScript, Node.js, SQL';

const PIPELINE_STAGES = [
  { key: 'applied', label: '📝 Applied', short: 'Applied' },
  { key: 'hr_screening', label: '📞 HR Screening', short: 'HR Screen' },
  { key: 'tech_exam', label: '💻 Tech Exam', short: 'Tech Exam' },
  { key: 'final_interview', label: '🤝 Final Interview', short: 'Final' },
  { key: 'offer', label: '🎉 Job Offer', short: 'Offer' },
  { key: 'rejected', label: '✕ Rejected', short: 'Rejected' }
];

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  const skillsInput = document.getElementById('my-skills-input');
  if (skillsInput) skillsInput.value = mySkills;

  loadStats();
  loadJobs();
  setupKeyboardNavigation();
});

// Load stats from server
async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();
    currentStats = data;
    document.getElementById('stat-new').textContent = data.new || 0;
    document.getElementById('stat-saved').textContent = data.saved || 0;
    document.getElementById('stat-applied').textContent = data.applied || 0;
    renderPipelineSummary(data.by_stage || {});
  } catch (err) {
    console.error('Failed to load stats:', err);
  }
}

// Render pipeline summary badges in the Applications hub header
function renderPipelineSummary(byStage) {
  const container = document.getElementById('pipeline-stages-summary');
  if (!container) return;
  container.innerHTML = PIPELINE_STAGES.map(s => {
    const count = byStage[s.key] || 0;
    return `
      <div class="stage-stat-pill stage-${s.key}">
        <span class="stage-stat-label">${s.label}</span>
        <span class="stage-stat-num">${count}</span>
      </div>
    `;
  }).join('');
}

// Load jobs with current filters
async function loadJobs() {
  const feed = document.getElementById('job-feed');
  feed.innerHTML = '<div class="loading-state">Loading job postings...</div>';

  const pipelineHeader = document.getElementById('pipeline-hub-header');
  if (pipelineHeader) {
    pipelineHeader.style.display = currentStatus === 'applied' ? 'block' : 'none';
  }

  try {
    const params = new URLSearchParams({
      status: currentStatus,
      role: currentRole,
      experience_level: currentLevel,
      search: searchQuery,
      date_filter: currentDateFilter
    });
    if (hasSalaryOnly) params.set('has_salary', '1');
    if (remoteOnly) params.set('remote_only', '1');

    const res = await fetch(`/api/jobs?${params.toString()}`);
    const data = await res.json();
    let jobs = data.jobs || [];

    // Client-side Senior suppression if checkbox active and not explicitly viewing senior
    if (hideSenior && currentLevel !== 'Senior / Lead') {
      jobs = jobs.filter(j => j.experience_level !== 'Senior / Lead');
    }

    jobsList = jobs;
    selectedIndex = 0;
    renderJobs();
    updateSearchCount(jobs.length);
  } catch (err) {
    feed.innerHTML = `<div class="empty-state">Error loading jobs: ${err.message}</div>`;
  }
}

// Skills matching calculator
function getSkillsMatch(job) {
  if (!mySkills.trim()) return { count: 0, matched: [] };
  const tokens = mySkills.split(',').map(s => s.trim()).filter(Boolean);
  const targetText = `${job.title} ${job.role_category} ${job.notes || ''}`.toLowerCase();

  const matched = [];
  for (const token of tokens) {
    const escaped = token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(^|\\W)${escaped}(\\W|$)`, 'i');
    if (regex.test(targetText)) {
      matched.push(token);
    }
  }
  return { count: matched.length, matched };
}

// Handle changes to user's skills
function handleSkillsChange() {
  const input = document.getElementById('my-skills-input');
  if (input) {
    mySkills = input.value;
    localStorage.setItem('job_accel_my_skills', mySkills);
    renderJobs();
  }
}

// Calculate days since a given date string
function getDaysSince(dateStr) {
  if (!dateStr) return 0;
  try {
    const target = new Date(dateStr.slice(0, 10));
    const now = new Date();
    const diff = Math.max(0, Math.floor((now - target) / (1000 * 60 * 60 * 24)));
    return isNaN(diff) ? 0 : diff;
  } catch {
    return 0;
  }
}

// 1-Click Tailored Pitch Generator
function generateTailoredPitch(job) {
  const match = getSkillsMatch(job);
  let techSummary = 'modern full-stack web development and reliable backend architectures';
  if (match.matched.length > 0) {
    techSummary = match.matched.slice(0, 3).join(', ');
  } else if (job.role_category === 'Data/AI/ML') {
    techSummary = 'Python, data analytics, and machine learning pipelines';
  }

  return `Hi ${job.company} Hiring Team,\n\nI am writing to express my keen interest in the ${job.title} role. With hands-on experience in ${techSummary}, I build clean, reliable solutions and adapt quickly to team requirements. I would welcome the chance to discuss how my skill set aligns with ${job.company}'s goals.\n\nThank you and best regards!`;
}

// Copy pitch to clipboard
function copyTailoredPitch(jobId, event) {
  if (event) event.stopPropagation();
  const job = jobsList.find(j => j.id === jobId);
  if (!job) return;

  const pitch = generateTailoredPitch(job);
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(pitch).then(() => {
      showToast(`📋 Tailored pitch copied for ${job.company}!`);
    }).catch(() => {
      fallbackCopy(pitch, job.company);
    });
  } else {
    fallbackCopy(pitch, job.company);
  }
}

// Fallback clipboard copy
function fallbackCopy(text, company) {
  const ta = document.createElement('textarea');
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  document.execCommand('copy');
  document.body.removeChild(ta);
  showToast(`📋 Tailored pitch copied for ${company}!`);
}

// Show toast notification
function showToast(message) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = 'toast-message';
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('fade-out');
    setTimeout(() => toast.remove(), 400);
  }, 2600);
}

// Render cards
function renderJobs() {
  const feed = document.getElementById('job-feed');
  if (jobsList.length === 0) {
    feed.innerHTML = `
      <div class="empty-state">
        <p>No job postings found for the current filters.</p>
        <p style="margin-top: 8px; font-size: 0.88rem; color: #64748b;">Try changing the level filter or click "Sync 12 Boards".</p>
      </div>`;
    return;
  }

  feed.innerHTML = jobsList.map((job, idx) => {
    const isSelected = idx === selectedIndex ? 'selected' : '';

    // Level badge class
    let levelClass = 'badge-level-mid';
    if (job.experience_level.includes('Junior') || job.experience_level.includes('Entry')) {
      levelClass = 'badge-level-junior';
    } else if (job.experience_level.includes('Senior') || job.experience_level.includes('Lead')) {
      levelClass = 'badge-level-senior';
    }

    const tierClass = `badge-tier${job.tier || 1}`;
    const skillsMatch = getSkillsMatch(job);

    // Follow-up indicator logic
    const currentStage = job.pipeline_stage || 'applied';
    const appliedDays = getDaysSince(job.applied_at || job.date_posted || job.created_at);
    let followUpBadge = '';
    if (job.status === 'applied') {
      if (currentStage === 'applied' && appliedDays >= 5) {
        followUpBadge = `<span class="badge badge-followup-due" title="Applied ${appliedDays} days ago without status update">🔔 Follow-up Due (${appliedDays}d ago)</span>`;
      } else if (currentStage === 'offer') {
        followUpBadge = `<span class="badge badge-offer">🎉 Offer Received!</span>`;
      } else if (currentStage !== 'rejected') {
        followUpBadge = `<span class="badge badge-in-progress">⏳ ${appliedDays}d in pipeline</span>`;
      }
    }

    const isAppliedView = currentStatus === 'applied';

    return `
      <div class="job-card ${isSelected} ${isAppliedView ? 'applied-pipeline-card' : ''}" id="job-card-${idx}" onclick="selectCard(${idx})">
        <div class="job-main">
          <div class="job-header-row">
            <span class="job-title">${escapeHtml(job.title)}</span>
            <span class="company-name">@ ${escapeHtml(job.company)}</span>
            ${followUpBadge}
          </div>

          <div class="meta-row">
            <span class="badge badge-platform">${escapeHtml(job.platform)}</span>
            <span class="badge ${tierClass}">Tier ${job.tier}</span>
            <span class="badge ${levelClass}">${escapeHtml(job.experience_level)}</span>
            <span class="job-location">📍 ${escapeHtml(job.location || 'Remote')}</span>
            ${job.salary ? `<span class="job-salary">💰 ${escapeHtml(job.salary)}</span>` : ''}
            ${skillsMatch.count > 0 ? `<span class="badge badge-match">🎯 ${skillsMatch.matched.join(', ')}</span>` : ''}
            ${formatPostingDate(job.date_posted)}
          </div>

          ${isAppliedView ? `
            <div class="pipeline-card-controls">
              <div class="stage-select-group">
                <label class="stage-label">Pipeline Stage:</label>
                <select class="stage-select" onchange="changeJobStage(${job.id}, this.value)" onclick="event.stopPropagation()">
                  ${PIPELINE_STAGES.map(s => `
                    <option value="${s.key}" ${currentStage === s.key ? 'selected' : ''}>${s.label}</option>
                  `).join('')}
                </select>
              </div>
              <div class="inline-notes-wrapper" onclick="event.stopPropagation()">
                <input type="text" class="notes-input" placeholder="Recruiter name, interview notes, or follow-up deadline..." 
                       value="${escapeHtml(job.notes || '')}" onblur="saveJobNotes(${job.id}, this.value)" 
                       onkeydown="if(event.key==='Enter')this.blur()">
                <button class="btn-save-note" title="Save Note" onclick="this.previousElementSibling.blur()">💾</button>
              </div>
            </div>
          ` : ''}
        </div>

        <div class="job-actions">
          <a href="${escapeHtml(job.job_url)}" target="_blank" rel="noopener noreferrer" 
             class="btn-apply" onclick="handleApplyClick(event, ${job.id}, '${escapeHtml(job.job_url)}')">
            🚀 ${isAppliedView ? 'Open Link' : 'Apply Now'}
          </a>
          <button class="btn-pitch" title="Copy Tailored 3-Sentence Pitch" onclick="copyTailoredPitch(${job.id}, event)">
            📋 Pitch
          </button>
          <button class="btn-action-icon ${job.status === 'applied' ? 'btn-applied' : ''}" 
                  title="Mark Applied" onclick="event.stopPropagation(); updateJobStatus(${job.id}, 'applied')">
            ✅
          </button>
          <button class="btn-action-icon ${job.status === 'saved' ? 'btn-saved' : ''}" 
                  title="Save Job" onclick="event.stopPropagation(); updateJobStatus(${job.id}, 'saved')">
            ⭐
          </button>
          <button class="btn-action-icon" title="Ignore Job" onclick="event.stopPropagation(); updateJobStatus(${job.id}, 'ignored')">
            ✕
          </button>
        </div>
      </div>
    `;
  }).join('');
}

// Select card by index
function selectCard(idx) {
  if (idx < 0 || idx >= jobsList.length) return;
  const oldCard = document.getElementById(`job-card-${selectedIndex}`);
  if (oldCard) oldCard.classList.remove('selected');

  selectedIndex = idx;
  const newCard = document.getElementById(`job-card-${selectedIndex}`);
  if (newCard) {
    newCard.classList.add('selected');
    newCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

// 1-Click Apply click handler
function handleApplyClick(e, jobId, url) {
  setTimeout(() => {
    if (confirm('Mark this job as "Applied" in your tracking system?')) {
      updateJobStatus(jobId, 'applied');
    }
  }, 400);
}

// Stage change handler
function changeJobStage(jobId, stage) {
  updateJobStatus(jobId, 'applied', null, stage);
}

// Save inline notes
function saveJobNotes(jobId, newNotes) {
  const job = jobsList.find(j => j.id === jobId);
  if (job && (job.notes || '') !== newNotes) {
    updateJobStatus(jobId, null, newNotes).then(() => {
      showToast('💾 Application notes saved!');
    });
  }
}

// Update status via API
async function updateJobStatus(jobId, status = null, notes = null, stage = null, followUp = null) {
  try {
    const payload = {};
    if (status !== null) payload.status = status;
    if (notes !== null) payload.notes = notes;
    if (stage !== null) payload.stage = stage;
    if (followUp !== null) payload.follow_up_date = followUp;

    const res = await fetch(`/api/jobs/${jobId}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      loadStats();
      loadJobs();
    }
  } catch (err) {
    alert(`Failed to update status: ${err.message}`);
  }
}

// Trigger Sync
async function triggerSync() {
  const btn = document.getElementById('sync-btn');
  const spinner = document.getElementById('sync-spinner');
  const txt = document.getElementById('sync-text');
  const kwInput = document.getElementById('sync-keywords-input');
  const rawKws = kwInput ? kwInput.value.trim() : '';
  const keywords = rawKws ? rawKws.split(',').map(s => s.trim()).filter(Boolean) : null;

  btn.disabled = true;
  spinner.style.animation = 'spin 1s linear infinite';
  txt.textContent = 'Syncing...';

  try {
    const res = await fetch('/api/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keywords })
    });
    const data = await res.json();
    alert(`Sync completed across 12 boards! Added: ${data.added} new jobs (Skipped ${data.skipped} duplicates).`);
    loadStats();
    loadJobs();
  } catch (err) {
    alert(`Sync failed: ${err.message}`);
  } finally {
    btn.disabled = false;
    spinner.style.animation = '';
    txt.textContent = 'Sync 12 Boards';
  }
}

// Keyboard navigation
function setupKeyboardNavigation() {
  document.addEventListener('keydown', (e) => {
    // If typing in any input field or select, ignore navigation keys
    const tag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
    if (tag === 'input' || tag === 'textarea' || tag === 'select') {
      if (e.key === 'Escape') {
        document.activeElement.blur();
      }
      return;
    }

    if (e.key === '/') {
      e.preventDefault();
      const s = document.getElementById('search-input');
      if (s) s.focus();
      return;
    }

    if (jobsList.length === 0) return;
    const selectedJob = jobsList[selectedIndex];

    if (e.key === 'j' || e.key === 'ArrowDown') {
      e.preventDefault();
      selectCard(Math.min(selectedIndex + 1, jobsList.length - 1));
    } else if (e.key === 'k' || e.key === 'ArrowUp') {
      e.preventDefault();
      selectCard(Math.max(selectedIndex - 1, 0));
    } else if (e.key === 'a' || e.key === 'Enter') {
      if (selectedJob) {
        e.preventDefault();
        window.open(selectedJob.job_url, '_blank');
        if (confirm(`Mark "${selectedJob.title}" as Applied?`)) {
          updateJobStatus(selectedJob.id, 'applied');
        }
      }
    } else if (e.key === 'p') {
      if (selectedJob) {
        e.preventDefault();
        copyTailoredPitch(selectedJob.id);
      }
    } else if (e.key === 's') {
      if (selectedJob) {
        e.preventDefault();
        updateJobStatus(selectedJob.id, 'saved');
      }
    } else if (e.key === 'x') {
      if (selectedJob) {
        e.preventDefault();
        updateJobStatus(selectedJob.id, 'ignored');
      }
    }
  });
}

// Filter button handlers
function setStatus(status, elem) {
  currentStatus = status;
  updatePillActive('status-group', elem);
  loadJobs();
}

function setLevel(level, elem) {
  currentLevel = level;
  updatePillActive('level-group', elem);
  loadJobs();
}

function setRole(role, elem) {
  currentRole = role;
  updatePillActive('role-group', elem);
  loadJobs();
}

function setDateFilter(filter, elem) {
  currentDateFilter = filter;
  updatePillActive('date-group', elem);
  loadJobs();
}

function formatPostingDate(dateStr) {
  if (!dateStr) return '<span class="badge badge-date-older">📅 Recently</span>';
  const todayStr = new Date().toISOString().slice(0, 10);
  const d = new Date();
  d.setDate(d.getDate() - 1);
  const yesterdayStr = d.toISOString().slice(0, 10);

  if (dateStr.startsWith(todayStr)) {
    return `<span class="badge badge-date-today">🔥 Today (${escapeHtml(dateStr.slice(0, 10))})</span>`;
  } else if (dateStr.startsWith(yesterdayStr)) {
    return `<span class="badge badge-date-recent">🕒 Yesterday (${escapeHtml(dateStr.slice(0, 10))})</span>`;
  }
  return `<span class="badge badge-date-older">📅 ${escapeHtml(dateStr.slice(0, 10))}</span>`;
}

function toggleHideSenior(checkbox) {
  hideSenior = checkbox.checked;
  loadJobs();
}

function toggleSalaryOnly(checkbox) {
  hasSalaryOnly = checkbox.checked;
  loadJobs();
}

function toggleRemoteOnly(checkbox) {
  remoteOnly = checkbox.checked;
  loadJobs();
}

function handleSearchInput() {
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(() => {
    searchQuery = document.getElementById('search-input').value.trim();
    loadJobs();
  }, 250);
}

function updatePillActive(groupId, elem) {
  document.querySelectorAll(`#${groupId} .pill`).forEach(p => p.classList.remove('active'));
  elem.classList.add('active');
}

function updateSearchCount(count) {
  document.getElementById('search-count').textContent = `${count} jobs`;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
