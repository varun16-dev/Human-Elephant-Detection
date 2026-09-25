/**
 * Forest Officer User Management Module
 * Integrated IoT and Edge-AI Acoustic Early Warning System
 * Department of AI & ML, Sri Sairam College of Engineering
 */

let adminUsersList = [];

// Initialize when tab is opened
function initUserManagement() {
  console.log("[USER MGMT] Initializing Forest Officer User Management...");
  loadAdminUsers();
}

// Load users list from secured backend
async function loadAdminUsers() {
  const tbody = document.getElementById('user-mgmt-table-body');
  if (tbody) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" style="text-align: center; padding: 2.5rem; color: var(--text-muted);">
          <i class="fa-solid fa-spinner fa-spin" style="font-size: 1.5rem; margin-bottom: 0.5rem; color: var(--accent-emerald);"></i>
          <p>Loading registered users from Supabase Cloud...</p>
        </td>
      </tr>
    `;
  }

  try {
    const response = await fetch('/api/admin/users');
    if (!response.ok) {
      if (response.status === 403 || response.status === 401) {
        if (tbody) {
          tbody.innerHTML = `
            <tr>
              <td colspan="8" style="text-align: center; padding: 2.5rem; color: var(--status-danger);">
                <i class="fa-solid fa-lock" style="font-size: 1.5rem; margin-bottom: 0.5rem;"></i>
                <p style="font-weight: 700;">Unauthorized: Forest Officer privileges required.</p>
              </td>
            </tr>
          `;
        }
        return;
      }
      throw new Error(`Server returned ${response.status}`);
    }

    const data = await response.json();
    adminUsersList = data.users || [];
    renderUserManagementTable(adminUsersList);
    updateUserCountKPIs(adminUsersList);

  } catch (error) {
    console.error("[USER MGMT] Error loading users:", error);
    if (tbody) {
      tbody.innerHTML = `
        <tr>
          <td colspan="8" style="text-align: center; padding: 2.5rem; color: var(--status-danger);">
            <i class="fa-solid fa-triangle-exclamation" style="font-size: 1.5rem; margin-bottom: 0.5rem;"></i>
            <p style="font-weight: 600;">Failed to load user directory.</p>
            <p style="font-size: 0.8rem; margin-top: 0.25rem;">${error.message}</p>
          </td>
        </tr>
      `;
    }
  }
}

// Update KPI counters
function updateUserCountKPIs(users) {
  let total = users.length;
  let active = users.filter(u => u.status === 'Active').length;
  let villagers = users.filter(u => u.role === 'villager').length;
  let police = users.filter(u => u.role === 'police').length;
  let officers = users.filter(u => u.role === 'forest_officer').length;

  const totalEl = document.getElementById('kpi-total-users');
  const activeEl = document.getElementById('kpi-active-users');
  const villagersEl = document.getElementById('kpi-villagers-count');
  const policeEl = document.getElementById('kpi-police-count');
  const officersEl = document.getElementById('kpi-officers-count');

  if (totalEl) totalEl.textContent = total;
  if (activeEl) activeEl.textContent = active;
  if (villagersEl) villagersEl.textContent = villagers;
  if (policeEl) policeEl.textContent = police;
  if (officersEl) officersEl.textContent = officers;
}

// Render user table
function renderUserManagementTable(users) {
  const tbody = document.getElementById('user-mgmt-table-body');
  if (!tbody) return;

  if (!users || users.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" style="text-align: center; padding: 2.5rem; color: var(--text-muted);">
          <i class="fa-solid fa-user-slash" style="font-size: 1.5rem; margin-bottom: 0.5rem; color: var(--text-dim);"></i>
          <p style="font-weight: 600;">No users found matching current filters.</p>
        </td>
      </tr>
    `;
    return;
  }

  let html = '';
  users.forEach(u => {
    const role = u.role || 'villager';
    let roleBadge = '';
    if (role === 'forest_officer') {
      roleBadge = `<span class="user-role-badge officer"><i class="fa-solid fa-tree"></i> Forest Officer</span>`;
    } else if (role === 'villager') {
      roleBadge = `<span class="user-role-badge villager"><i class="fa-solid fa-house"></i> Villager</span>`;
    } else if (role === 'police') {
      roleBadge = `<span class="user-role-badge police"><i class="fa-solid fa-shield"></i> Police</span>`;
    } else {
      roleBadge = `<span class="user-role-badge">${role}</span>`;
    }

    const isActive = u.status === 'Active';
    const statusBadge = isActive
      ? `<span class="user-status-pill active"><span class="dot-indicator" style="background:#10b981; width:6px; height:6px; border-radius:50%;"></span> Active</span>`
      : `<span class="user-status-pill inactive"><span class="dot-indicator" style="background:#ef4444; width:6px; height:6px; border-radius:50%;"></span> Inactive</span>`;

    const toggleBtnText = isActive ? 'Disable' : 'Activate';
    const toggleBtnIcon = isActive ? 'fa-user-xmark' : 'fa-user-check';
    const toggleBtnClass = isActive ? 'btn-action-disable' : 'btn-action-activate';

    html += `
      <tr id="user-row-${u.id}">
        <td>
          <div style="font-weight: 700; color: #fff; font-size: 0.95rem;">${u.full_name || u.name || 'Unnamed User'}</div>
          <div style="font-size: 0.76rem; color: var(--text-dim); font-family: var(--font-mono);">ID: ${String(u.id).slice(0, 8)}...</div>
        </td>
        <td>
          <div style="color: var(--text-muted); font-size: 0.88rem;"><i class="fa-solid fa-envelope" style="color: #64748b; margin-right: 4px;"></i>${u.email || '—'}</div>
        </td>
        <td>
          <div style="color: var(--text-muted); font-size: 0.88rem;"><i class="fa-solid fa-phone" style="color: #64748b; margin-right: 4px;"></i>${u.phone || '—'}</div>
        </td>
        <td>${roleBadge}</td>
        <td>
          <div style="color: var(--text-main); font-size: 0.88rem;"><i class="fa-solid fa-location-dot" style="color: #ef4444; margin-right: 4px;"></i>${u.location || u.zone || 'Bannerghatta Corridor'}</div>
        </td>
        <td>${statusBadge}</td>
        <td>
          <div style="color: var(--text-dim); font-size: 0.82rem;">${formatDateString(u.created_at)}</div>
        </td>
        <td>
          <div style="display: flex; gap: 0.5rem; align-items: center;">
            <button class="btn-action-view" onclick="viewUserDetailsModal('${u.id}')" title="View Profile Details">
              <i class="fa-solid fa-eye"></i> View
            </button>
            <button class="${toggleBtnClass}" onclick="toggleUserStatus('${u.id}', '${u.status}')" title="${toggleBtnText} User Access">
              <i class="fa-solid ${toggleBtnIcon}"></i> ${toggleBtnText}
            </button>
          </div>
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
}

function formatDateString(str) {
  if (!str) return 'Recent';
  try {
    const d = new Date(str);
    if (isNaN(d.getTime())) return str.split('T')[0];
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch (e) {
    return str.split('T')[0];
  }
}

// Filter users by search and role
function filterUsers() {
  const searchTerm = (document.getElementById('user-search-input')?.value || '').toLowerCase();
  const roleFilter = document.getElementById('user-role-filter')?.value || 'all';

  const filtered = adminUsersList.filter(u => {
    const matchesSearch = (
      (u.full_name || u.name || '').toLowerCase().includes(searchTerm) ||
      (u.email || '').toLowerCase().includes(searchTerm) ||
      (u.phone || '').toLowerCase().includes(searchTerm) ||
      (u.location || u.zone || '').toLowerCase().includes(searchTerm)
    );
    const matchesRole = roleFilter === 'all' || u.role === roleFilter;
    return matchesSearch && matchesRole;
  });

  renderUserManagementTable(filtered);
}

// Create new user form submission
async function handleCreateUser(event) {
  event.preventDefault();

  const feedback = document.getElementById('create-user-feedback');
  const btn = document.getElementById('btn-create-user-submit');

  const fullName = document.getElementById('new-user-fullname').value.trim();
  const email = document.getElementById('new-user-email').value.trim();
  const phone = document.getElementById('new-user-phone').value.trim();
  const role = document.getElementById('new-user-role').value;
  const location = document.getElementById('new-user-location').value.trim();
  const password = document.getElementById('new-user-password').value;

  if (!fullName || !email || !role || !password) {
    showCreateUserFeedback('Please fill out all required fields.', false);
    return;
  }

  if (password.length < 6) {
    showCreateUserFeedback('Password must be at least 6 characters.', false);
    return;
  }

  const originalBtnText = btn.innerHTML;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Provisioning in Supabase Auth...';
  btn.disabled = true;

  try {
    const response = await fetch('/api/admin/users/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        full_name: fullName,
        email: email,
        phone: phone,
        role: role,
        location: location,
        password: password
      })
    });

    const data = await response.json();

    if (response.ok && data.success) {
      showCreateUserFeedback('User created successfully', true);
      // Reset form
      document.getElementById('create-user-form').reset();
      // Reload users list
      loadAdminUsers();
    } else {
      showCreateUserFeedback(data.error || 'Failed to create user.', false);
    }
  } catch (err) {
    console.error("[USER MGMT] Create user error:", err);
    showCreateUserFeedback('Network error provisioning user.', false);
  } finally {
    btn.innerHTML = originalBtnText;
    btn.disabled = false;
  }
}

function showCreateUserFeedback(msg, isSuccess) {
  const fb = document.getElementById('create-user-feedback');
  if (!fb) return;
  fb.textContent = msg;
  fb.className = isSuccess ? 'user-feedback-banner success' : 'user-feedback-banner error';
  fb.style.display = 'block';

  if (isSuccess) {
    setTimeout(() => {
      fb.style.display = 'none';
    }, 5000);
  }
}

// Toggle user Active / Inactive status
async function toggleUserStatus(userId, currentStatus) {
  const newStatus = currentStatus === 'Active' ? 'Inactive' : 'Active';
  const confirmMsg = newStatus === 'Inactive'
    ? 'Are you sure you want to DISABLE this user? They will not be able to log in to the dashboard.'
    : 'Are you sure you want to ACTIVATE this user? They will regain access to the dashboard.';

  if (!confirm(confirmMsg)) return;

  try {
    const response = await fetch('/api/admin/users/toggle-status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        status: newStatus
      })
    });

    const data = await response.json();
    if (response.ok && data.success) {
      loadAdminUsers();
    } else {
      alert(`Error updating status: ${data.error || 'Server error'}`);
    }
  } catch (err) {
    console.error("[USER MGMT] Toggle status error:", err);
    alert('Network error updating user status.');
  }
}

// Generate random strong temporary password
function generateTemporaryPassword() {
  const chars = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%';
  let pass = '';
  for (let i = 0; i < 10; i++) {
    pass += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  const input = document.getElementById('new-user-password');
  if (input) {
    input.value = pass;
    input.type = 'text'; // keep visible so officer can note it down
  }
}

// View User Modal
function viewUserDetailsModal(userId) {
  const user = adminUsersList.find(u => String(u.id) === String(userId));
  if (!user) return;

  const modal = document.getElementById('user-details-modal');
  const body = document.getElementById('user-modal-body');

  if (modal && body) {
    const role = user.role || 'villager';
    const roleName = role === 'forest_officer' ? 'Forest Officer (Administrator)' : (role === 'police' ? 'Police Department' : 'Villager (Community Safety)');
    
    body.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 1rem;">
        <div style="display: flex; align-items: center; gap: 1rem; border-bottom: 1px solid var(--border-color); padding-bottom: 1rem;">
          <div style="width: 50px; height: 50px; border-radius: 50%; background: rgba(16, 185, 129, 0.2); display: flex; align-items: center; justify-content: center; font-size: 1.5rem; color: #10b981;">
            <i class="fa-solid fa-user-shield"></i>
          </div>
          <div>
            <h3 style="font-family: var(--font-title); font-size: 1.3rem; color: #fff;">${user.full_name || user.name}</h3>
            <span style="font-size: 0.85rem; color: var(--text-muted);">${roleName}</span>
          </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; font-size: 0.9rem;">
          <div>
            <span style="color: var(--text-dim); display: block; font-size: 0.78rem; text-transform: uppercase;">Email Address</span>
            <span style="color: #fff; font-weight: 600;">${user.email || '—'}</span>
          </div>
          <div>
            <span style="color: var(--text-dim); display: block; font-size: 0.78rem; text-transform: uppercase;">Phone Number</span>
            <span style="color: #fff; font-weight: 600;">${user.phone || '—'}</span>
          </div>
          <div>
            <span style="color: var(--text-dim); display: block; font-size: 0.78rem; text-transform: uppercase;">Assigned Sector / Zone</span>
            <span style="color: #fff; font-weight: 600;">${user.location || user.zone || 'Bannerghatta Range'}</span>
          </div>
          <div>
            <span style="color: var(--text-dim); display: block; font-size: 0.78rem; text-transform: uppercase;">Account Status</span>
            <span style="color: ${user.status === 'Active' ? '#10b981' : '#ef4444'}; font-weight: 700;">${user.status || 'Active'}</span>
          </div>
          <div style="grid-column: span 2;">
            <span style="color: var(--text-dim); display: block; font-size: 0.78rem; text-transform: uppercase;">Supabase User ID</span>
            <span style="color: var(--accent-cyan); font-family: var(--font-mono); font-size: 0.82rem;">${user.id}</span>
          </div>
          <div style="grid-column: span 2;">
            <span style="color: var(--text-dim); display: block; font-size: 0.78rem; text-transform: uppercase;">Registration Date</span>
            <span style="color: #fff;">${user.created_at || 'Registered'}</span>
          </div>
        </div>
      </div>
    `;
    modal.style.display = 'flex';
  }
}

function closeUserDetailsModal() {
  const modal = document.getElementById('user-details-modal');
  if (modal) modal.style.display = 'none';
}
