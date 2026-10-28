/**
 * Android SIM SMS Gateway (TextBee) Controller
 * Department of AI & ML, Sri Sairam College of Engineering
 *
 * Manages client-side operations for Android-based SIM SMS alerts:
 * - Gateway health & device connection validation
 * - Dynamic bilingual message preview (English + Tamil / English + Kannada)
 * - State selection (Tamil Nadu / Karnataka) & monitoring location
 * - Cooldown & count change policy configuration
 * - Explicitly confirmed Real Test SMS dispatch
 * - History and delivery status inspection
 */

const AndroidSmsGateway = (function () {
  let isInitialized = false;
  let currentConfig = {};
  let previewSimCount = 3;

  // Masking helpers
  function maskPhone(phone) {
    if (!phone) return 'Not configured';
    const s = String(phone).replace(/[^\d+]/g, '');
    if (s.length >= 10) {
      const last4 = s.slice(-4);
      const first4 = s.slice(0, 4);
      return `${first4} ***-***-${last4}`;
    }
    return '••••••••';
  }

  // Toast notification fallback
  function notify(msg, type = 'info') {
    if (typeof window.showToast === 'function') {
      window.showToast(msg, type);
    } else if (typeof showToast === 'function') {
      showToast(msg, type);
    } else {
      console.log(`[SMS-TOAST] [${type.toUpperCase()}] ${msg}`);
      let container = document.getElementById('toast-container');
      if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
      }
      const toast = document.createElement('div');
      toast.className = `toast-item ${type}`;
      toast.innerHTML = `<span>${msg}</span>`;
      container.appendChild(toast);
      setTimeout(() => toast.remove(), 4000);
    }
  }

  // Fetch current config & device status
  async function loadStatus() {
    try {
      const resp = await fetch('/api/sms/status');
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      currentConfig = data;
      renderConfig(data);
      updatePreview();
      loadRecipients();
      loadHistory();
    } catch (e) {
      console.error('[ANDROID-SMS] Error loading status:', e);
      renderDisconnected('Failed to fetch gateway status');
    }
  }

  // Populate UI elements from loaded config
  function renderConfig(data) {
    // Status Badge
    const badge = document.getElementById('sms-gateway-status-badge');
    const deviceBadge = document.getElementById('sms-device-info-badge');
    
    if (badge) {
      if (data.provider === 'smsgate') {
        if (data.smsgate_configured) {
          badge.innerHTML = `<i class="fa-solid fa-circle-check"></i> SMSGate: Ready (${escapeHtml(data.smsgate_base_url || 'Local Server')})`;
          badge.style.background = 'rgba(16, 185, 129, 0.15)';
          badge.style.color = '#10b981';
          badge.style.borderColor = 'rgba(16, 185, 129, 0.4)';
        } else {
          badge.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> SMSGate: Not Configured (Set .env)';
          badge.style.background = 'rgba(245, 158, 11, 0.15)';
          badge.style.color = '#f59e0b';
          badge.style.borderColor = 'rgba(245, 158, 11, 0.4)';
        }
      } else {
        if (data.has_api_key) {
          badge.innerHTML = '<i class="fa-solid fa-circle-check"></i> TextBee Configured (Ready)';
          badge.style.background = 'rgba(16, 185, 129, 0.15)';
          badge.style.color = '#10b981';
          badge.style.borderColor = 'rgba(16, 185, 129, 0.4)';
        } else {
          badge.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> API Key Required';
          badge.style.background = 'rgba(245, 158, 11, 0.15)';
          badge.style.color = '#f59e0b';
          badge.style.borderColor = 'rgba(245, 158, 11, 0.4)';
        }
      }
    }

    // Daily quota / provider display
    const quotaEl = document.getElementById('sms-daily-quota-display');
    if (quotaEl && data.free_tier_limits) {
      const used = data.free_tier_limits.daily_sent_today || 0;
      const limit = data.free_tier_limits.daily_limit || 'Plan Quota';
      const provName = data.free_tier_limits.provider || (data.provider === 'smsgate' ? 'SMSGate' : 'TextBee');
      quotaEl.textContent = `${used} / ${limit} (${provName})`;
    }

    // Populate input fields
    const stateSel = document.getElementById('sms-state-select');
    if (stateSel && data.state) stateSel.value = data.state;

    const locInp = document.getElementById('sms-location-input');
    if (locInp && data.location_name) locInp.value = data.location_name;

    const recipInp = document.getElementById('sms-recipient-input');
    if (recipInp && data.recipient_phone) recipInp.value = data.recipient_phone;

    const recipMasked = document.getElementById('sms-recipient-masked-display');
    if (recipMasked) {
      recipMasked.textContent = data.recipient_masked || 'Not configured';
    }

    const keyInp = document.getElementById('sms-api-key-input');
    if (keyInp) {
      if (data.has_api_key) {
        keyInp.placeholder = data.api_key_masked || '••••••••••••••••';
      } else {
        keyInp.placeholder = 'Paste TextBee API Key (x-api-key)';
      }
    }

    const devInp = document.getElementById('sms-device-id-input');
    if (devInp && data.device_id) devInp.value = data.device_id;

    const cdInp = document.getElementById('sms-cooldown-input');
    if (cdInp && data.cooldown_seconds) cdInp.value = data.cooldown_seconds;

    const polSel = document.getElementById('sms-policy-select');
    if (polSel && data.count_change_policy) polSel.value = data.count_change_policy;

    const absInp = document.getElementById('sms-absence-input');
    if (absInp && data.absence_reset_seconds) absInp.value = data.absence_reset_seconds;

    // Render Last Alert Outcome
    renderLastAlert(data.last_alert);
  }

  function renderLastAlert(last) {
    const card = document.getElementById('sms-last-alert-card');
    if (!card) return;

    if (!last) {
      card.style.display = 'none';
      return;
    }

    card.style.display = 'block';
    const statusEl = document.getElementById('sms-last-status');
    const timeEl = document.getElementById('sms-last-time');
    const countEl = document.getElementById('sms-last-count');
    const recipEl = document.getElementById('sms-last-recipient');
    const textEl = document.getElementById('sms-last-message-text');

    if (statusEl) {
      const ok = last.success;
      statusEl.textContent = last.status || (ok ? 'ACCEPTED' : 'FAILED');
      statusEl.style.color = ok ? '#10b981' : '#ef4444';
      statusEl.style.borderColor = ok ? 'rgba(16, 185, 129, 0.4)' : 'rgba(239, 68, 68, 0.4)';
    }

    if (timeEl) timeEl.textContent = last.timestamp || '--';
    if (countEl) countEl.textContent = `${last.elephant_count || 0} Elephant(s)`;
    if (recipEl) recipEl.textContent = last.recipient_masked || '--';
    if (textEl) textEl.textContent = last.message || last.details || '--';
  }

  // Live dynamic message preview generator
  async function updatePreview() {
    const state = document.getElementById('sms-state-select')?.value || 'karnataka';
    const loc = document.getElementById('sms-location-input')?.value || 'Monitoring Zone 1';
    const count = parseInt(previewSimCount) || 3;

    const countDisplay = document.getElementById('sms-preview-count-label');
    if (countDisplay) countDisplay.textContent = `${count} elephant${count > 1 ? 's' : ''}`;

    const charEl = document.getElementById('sms-char-count-display');
    const encEl = document.getElementById('sms-encoding-display');
    const segEl = document.getElementById('sms-segment-count-display');
    const previewBox = document.getElementById('sms-preview-message-box');

    try {
      const resp = await fetch('/api/sms/preview-message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          state: state,
          location: loc,
          count: count,
          confidence: 94.5,
          full: true
        })
      });
      if (resp.ok) {
        const data = await resp.json();
        if (previewBox) previewBox.textContent = data.message || '';
        if (charEl) charEl.textContent = `Chars: ${data.char_count || 0}`;
        if (encEl) encEl.textContent = data.encoding || 'UCS-2 (Unicode)';
        if (segEl) segEl.textContent = `Segments: ${data.segments || 1} (${data.chars_per_segment || 67} chars/seg)`;
        return;
      }
    } catch (e) {
      console.warn('[ANDROID-SMS] Preview fetch failed, falling back to local:', e);
    }

    // Local fallback if offline or request failed
    const now = new Date();
    const day = String(now.getDate()).padStart(2, '0') + '-' + String(now.getMonth() + 1).padStart(2, '0') + '-' + now.getFullYear();
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true });
    const fullTime = `${day}, ${timeStr}`;

    let preview = '';
    const enNoun = count === 1 ? 'elephant' : 'elephants';

    if (state === 'tamil_nadu') {
      const taNoun = count === 1 ? 'யானை' : 'யானைகள்';
      preview = `🚨 ELEPHANT ALERT!
English: ${count} ${enNoun} detected near ${loc}. Confidence: 94.5%. Time: ${fullTime}. Avoid approaching the elephant. Follow forest department instructions. View details: http://127.0.0.1:5000/
தமிழ்: ${loc} அருகே ${count} ${taNoun} கண்டறியப்பட்டுள்ளன. கண்டறிதல் நம்பகத்தன்மை: 94.5%. நேரம்: ${fullTime}. யானையை நெருங்க வேண்டாம். வனத்துறையின் அறிவுறுத்தல்களைப் பின்பற்றவும். மேலும் விவரங்கள்: http://127.0.0.1:5000/`;
    } else {
      const knNoun = count === 1 ? 'ಆನೆ' : 'ಆನೆಗಳು';
      preview = `🚨 ELEPHANT ALERT!
English: ${count} ${enNoun} detected near ${loc}. Confidence: 94.5%. Time: ${fullTime}. Avoid approaching the elephant. Follow forest department instructions. View details: http://127.0.0.1:5000/
ಕನ್ನಡ: ${loc} ಸಮೀಪ ${count} ${knNoun} ಪತ್ತೆಯಾಗಿವೆ. ಪತ್ತೆಹಚ್ಚುವಿಕೆಯ ವಿಶ್ವಾಸಾರ್ಹತೆ: 94.5%. ಸಮಯ: ${fullTime}. ಆನೆಯ ಹತ್ತಿರ ಹೋಗಬೇಡಿ. ಅರಣ್ಯ ಇಲಾಖೆಯ ಸೂಚನೆಗಳನ್ನು ಪಾಲಿಸಿ. ಹೆಚ್ಚಿನ ವಿವರಗಳು: http://127.0.0.1:5000/`;
    }

    if (previewBox) previewBox.textContent = preview;
    const len = preview.length;
    if (charEl) charEl.textContent = `Chars: ${len}`;
    if (encEl) encEl.textContent = 'UCS-2 (Unicode)';
    const segs = len <= 70 ? 1 : Math.ceil(len / 67);
    if (segEl) segEl.textContent = `Segments: ${segs} (67 chars/seg)`;
  }

  // Adjust preview count simulator (+ or -)
  function adjustPreviewCount(delta) {
    let next = (parseInt(previewSimCount) || 1) + delta;
    if (next < 1) next = 1;
    if (next > 25) next = 25;
    previewSimCount = next;
    updatePreview();
  }

  // Dual Recipient Management: Load & Render
  async function loadRecipients() {
    try {
      const resp = await fetch('/api/sms/recipients');
      if (!resp.ok) return;
      const data = await resp.json();
      renderRecipients(data);
    } catch (e) {
      console.error('[ANDROID-SMS] Error loading recipients:', e);
    }
  }

  function renderRecipients(data) {
    const officers = data.officers || [];
    const villagers = data.villagers || [];

    // Badges
    const offBadge = document.getElementById('sms-officers-count-badge');
    if (offBadge) {
      const activeCount = officers.filter(o => o.enabled).length;
      offBadge.textContent = `${activeCount} / ${officers.length} active`;
    }

    const vilBadge = document.getElementById('sms-villagers-count-badge');
    if (vilBadge) {
      const activeCount = villagers.filter(v => v.enabled).length;
      vilBadge.textContent = `${activeCount} / ${villagers.length} active`;
    }

    // Render Officers Table
    const offTbody = document.getElementById('sms-officers-table-body');
    if (offTbody) {
      if (!officers.length) {
        offTbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 0.75rem; color: #64748b;">No forest officers configured. Click "Add Recipient" to add one.</td></tr>';
      } else {
        offTbody.innerHTML = officers.map(o => {
          const langDisplay = o.language === 'tamil_nadu' ? 'தமிழ்' : (o.language === 'karnataka' ? 'ಕನ್ನಡ' : 'Default');
          const statusBtn = o.enabled
            ? `<button type="button" onclick="AndroidSmsGateway.toggleRecipient('${o.id}', 'officers')" class="btn" style="padding: 0.15rem 0.45rem; font-size: 0.68rem; background: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.4); border-radius: 4px; cursor: pointer;">Active</button>`
            : `<button type="button" onclick="AndroidSmsGateway.toggleRecipient('${o.id}', 'officers')" class="btn" style="padding: 0.15rem 0.45rem; font-size: 0.68rem; background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 4px; cursor: pointer;">Disabled</button>`;
          return `
            <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
              <td style="padding: 0.4rem 0.5rem; font-weight: 600; color: #fff;">${escapeHtml(o.name || '--')}</td>
              <td style="padding: 0.4rem 0.5rem; font-family: monospace; color: #a7f3d0;">${escapeHtml(o.phone || '--')}</td>
              <td style="padding: 0.4rem 0.5rem; color: #38bdf8;">${langDisplay}</td>
              <td style="padding: 0.4rem 0.5rem;">${statusBtn}</td>
              <td style="padding: 0.4rem 0.5rem;">
                <button type="button" onclick="AndroidSmsGateway.deleteRecipient('${o.id}', 'officers', '${escapeJsStr(o.name)}')" title="Remove" style="background: none; border: none; color: #f87171; cursor: pointer; padding: 0.2rem;">
                  <i class="fa-solid fa-trash-can"></i>
                </button>
              </td>
            </tr>
          `;
        }).join('');
      }
    }

    // Render Villagers Table
    const vilTbody = document.getElementById('sms-villagers-table-body');
    if (vilTbody) {
      if (!villagers.length) {
        vilTbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 0.75rem; color: #64748b;">No villagers configured. Click "Add Recipient" to add one.</td></tr>';
      } else {
        vilTbody.innerHTML = villagers.map(v => {
          const langDisplay = v.language === 'tamil_nadu' ? 'தமிழ்' : (v.language === 'karnataka' ? 'ಕನ್ನಡ' : 'Default');
          const locDisplay = v.location ? ` <span style="color: #94a3b8; font-size: 0.7rem;">(${escapeHtml(v.location)})</span>` : '';
          const statusBtn = v.enabled
            ? `<button type="button" onclick="AndroidSmsGateway.toggleRecipient('${v.id}', 'villagers')" class="btn" style="padding: 0.15rem 0.45rem; font-size: 0.68rem; background: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.4); border-radius: 4px; cursor: pointer;">Active</button>`
            : `<button type="button" onclick="AndroidSmsGateway.toggleRecipient('${v.id}', 'villagers')" class="btn" style="padding: 0.15rem 0.45rem; font-size: 0.68rem; background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 4px; cursor: pointer;">Disabled</button>`;
          return `
            <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
              <td style="padding: 0.4rem 0.5rem; font-weight: 600; color: #fff;">${escapeHtml(v.name || '--')}${locDisplay}</td>
              <td style="padding: 0.4rem 0.5rem; font-family: monospace; color: #fde68a;">${escapeHtml(v.phone || '--')}</td>
              <td style="padding: 0.4rem 0.5rem; color: #38bdf8;">${langDisplay}</td>
              <td style="padding: 0.4rem 0.5rem;">${statusBtn}</td>
              <td style="padding: 0.4rem 0.5rem;">
                <button type="button" onclick="AndroidSmsGateway.deleteRecipient('${v.id}', 'villagers', '${escapeJsStr(v.name)}')" title="Remove" style="background: none; border: none; color: #f87171; cursor: pointer; padding: 0.2rem;">
                  <i class="fa-solid fa-trash-can"></i>
                </button>
              </td>
            </tr>
          `;
        }).join('');
      }
    }
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function escapeJsStr(str) {
    if (!str) return '';
    return String(str).replace(/'/g, "\\'").replace(/"/g, '\\"');
  }

  // Recipient Modal controls
  function openAddRecipientModal(group = 'officer') {
    const modal = document.getElementById('sms-add-recipient-modal');
    const groupSel = document.getElementById('sms-new-recip-group');
    if (groupSel) groupSel.value = group === 'villagers' || group === 'villager' ? 'villager' : 'officer';

    // Clear inputs
    const nameInp = document.getElementById('sms-new-recip-name');
    const phoneInp = document.getElementById('sms-new-recip-phone');
    const locInp = document.getElementById('sms-new-recip-location');
    if (nameInp) nameInp.value = '';
    if (phoneInp) phoneInp.value = '';
    if (locInp) locInp.value = '';

    if (modal) {
      modal.style.display = 'flex';
      modal.classList.add('show');
    }
  }

  function closeAddRecipientModal() {
    const modal = document.getElementById('sms-add-recipient-modal');
    if (modal) {
      modal.style.display = 'none';
      modal.classList.remove('show');
    }
  }

  async function submitNewRecipient(event) {
    if (event && event.preventDefault) event.preventDefault();
    const groupRaw = document.getElementById('sms-new-recip-group')?.value || 'officer';
    const group = (groupRaw === 'villager' || groupRaw === 'villagers') ? 'villagers' : 'officers';
    const name = document.getElementById('sms-new-recip-name')?.value?.trim();
    const phone = document.getElementById('sms-new-recip-phone')?.value?.trim();
    const location = document.getElementById('sms-new-recip-location')?.value?.trim();
    const language = document.getElementById('sms-new-recip-language')?.value || 'karnataka';

    if (!name || !phone) {
      notify('⚠️ Please provide both name and phone number', 'warning');
      return;
    }

    try {
      const resp = await fetch('/api/sms/recipients/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          group: group,
          name: name,
          phone: phone,
          location: location,
          language: language
        })
      });
      const data = await resp.json();
      if (data.success) {
        notify(`✅ Added ${name} to ${group === 'officers' ? 'Forest Officers' : 'Local Villagers'}`, 'success');
        closeAddRecipientModal();
        loadRecipients();
      } else {
        notify(`⚠️ Could not add recipient: ${data.error || data.message}`, 'warning');
      }
    } catch (e) {
      notify(`Error adding recipient: ${e.message}`, 'error');
    }
  }

  async function toggleRecipient(id, group) {
    try {
      const resp = await fetch('/api/sms/recipients/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, group })
      });
      const data = await resp.json();
      if (data.success) {
        notify('Recipient status updated', 'info');
        loadRecipients();
      } else {
        notify(`Failed to update status: ${data.error || data.message}`, 'warning');
      }
    } catch (e) {
      notify(`Error: ${e.message}`, 'error');
    }
  }

  async function deleteRecipient(id, group, name) {
    if (!confirm(`Are you sure you want to remove ${name || 'this recipient'} from SMS alerts?`)) {
      return;
    }
    try {
      const resp = await fetch('/api/sms/recipients/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, group })
      });
      const data = await resp.json();
      if (data.success) {
        notify(`Removed ${name || 'recipient'} successfully`, 'success');
        loadRecipients();
      } else {
        notify(`Failed to delete: ${data.error || data.message}`, 'warning');
      }
    } catch (e) {
      notify(`Error: ${e.message}`, 'error');
    }
  }

  // Save Settings
  async function saveSettings() {
    const btn = document.getElementById('btn-save-sms-config');
    if (btn) btn.disabled = true;

    const payload = {
      state: document.getElementById('sms-state-select')?.value,
      location_name: document.getElementById('sms-location-input')?.value,
      recipient_phone: document.getElementById('sms-recipient-input')?.value,
      cooldown_seconds: parseInt(document.getElementById('sms-cooldown-input')?.value) || 300,
      count_change_policy: document.getElementById('sms-policy-select')?.value || 'always',
      absence_reset_seconds: parseInt(document.getElementById('sms-absence-input')?.value) || 120
    };

    const apiKeyVal = document.getElementById('sms-api-key-input')?.value?.trim();
    if (apiKeyVal && !apiKeyVal.startsWith('••••')) {
      payload.api_key = apiKeyVal;
    }

    const devIdVal = document.getElementById('sms-device-id-input')?.value?.trim();
    if (devIdVal) {
      payload.device_id = devIdVal;
    }

    try {
      const resp = await fetch('/api/sms/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await resp.json();
      if (data.success) {
        notify('✅ SMS Gateway configuration saved successfully!', 'success');
        renderConfig(data.config);
      } else {
        notify(`⚠️ Save warning: ${data.error || data.message}`, 'warning');
      }
    } catch (e) {
      notify(`❌ Save error: ${e.message}`, 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  // Validate TextBee Connection & Detect Android Devices
  async function validateGateway() {
    const btn = document.getElementById('btn-validate-sms-gateway');
    const spinner = document.getElementById('sms-validate-spinner');
    const resultBox = document.getElementById('sms-validate-result');

    if (btn) btn.disabled = true;
    if (spinner) spinner.style.display = 'inline-flex';
    if (resultBox) resultBox.style.display = 'none';

    try {
      const resp = await fetch('/api/sms/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await resp.json();

      if (resultBox) {
        resultBox.style.display = 'block';
        if (data.valid) {
          resultBox.className = 'sms-result-valid';
          resultBox.style.background = 'rgba(16, 185, 129, 0.12)';
          resultBox.style.borderColor = 'rgba(16, 185, 129, 0.35)';
          resultBox.style.color = '#10b981';

          let devInfo = '';
          if (data.provider && data.provider.includes('SMSGate')) {
            const bat = data.battery_pct !== undefined && data.battery_pct !== null ? `🔋 Battery: ${data.battery_pct}%` : '';
            const inet = `🌐 Phone Internet: ${data.phone_internet ? 'Connected' : 'Offline'}`;
            const fail = `⚠️ Failed Last Hour: ${data.failed_last_hour || 0}`;
            const appSt = `App: ${data.app_status || 'OK'}`;
            devInfo = `📱 SMSGate Phone: [${appSt}] • ${bat} • ${inet} • ${fail}`;
          } else if (data.active_device) {
            const d = data.active_device;
            const model = d.model || d.name || 'Android Device';
            const bat = d.battery ? `• Battery: ${d.battery}%` : '';
            devInfo = `📱 Paired Device: <strong>${model}</strong> (ID: ${d.id || d.deviceId || 'active'}) ${bat}`;
          } else {
            devInfo = data.message || 'Connected';
          }

          resultBox.innerHTML = `
            <div style="font-weight: 700; margin-bottom: 0.3rem;">
              <i class="fa-solid fa-circle-check"></i> ${escapeHtml(data.message)}
            </div>
            <div style="font-size: 0.78rem; color: #cbd5e1;">${devInfo}</div>
          `;
          notify(`✅ ${data.provider || 'Gateway'} connection verified!`, 'success');
        } else {
          resultBox.className = 'sms-result-error';
          resultBox.style.background = 'rgba(239, 68, 68, 0.12)';
          resultBox.style.borderColor = 'rgba(239, 68, 68, 0.35)';
          resultBox.style.color = '#ef4444';
          resultBox.innerHTML = `
            <div style="font-weight: 700; margin-bottom: 0.3rem;">
              <i class="fa-solid fa-circle-xmark"></i> ${escapeHtml(data.status)}: ${escapeHtml(data.message)}
            </div>
            <div style="font-size: 0.75rem; color: #94a3b8;">
              ${data.provider && data.provider.includes('SMSGate') ? 'Ensure SMS Gateway for Android Local Server is active on phone and environment variables are set in .env.' : 'Check that your TextBee Android app is active and your API key is correct.'}
            </div>
          `;
          notify(`⚠️ Gateway validation failed: ${data.message}`, 'warning');
        }
      }
    } catch (e) {
      notify(`Connection error: ${e.message}`, 'error');
    } finally {
      if (btn) btn.disabled = false;
      if (spinner) spinner.style.display = 'none';
    }
  }

  // Prompt Explicit Confirmation Modal for Real Test SMS
  function promptTestModal() {
    const modal = document.getElementById('sms-test-confirm-modal');
    const recipient = document.getElementById('sms-recipient-input')?.value || currentConfig.recipient_phone;
    const state = document.getElementById('sms-state-select')?.value || currentConfig.state || 'karnataka';

    if (!recipient) {
      notify('⚠️ Please configure recipient mobile number first.', 'warning');
      alert('Please configure recipient mobile number first before sending a test SMS.');
      return;
    }

    const stateDisplay = state === 'tamil_nadu' ? 'Tamil Nadu (English + தமிழ்)' : 'Karnataka (English + ಕನ್ನಡ)';
    const modalRecip = document.getElementById('sms-modal-recipient-display');
    const modalState = document.getElementById('sms-modal-state-display');
    const keyWarn = document.getElementById('sms-modal-key-warning');

    if (modalRecip) modalRecip.textContent = recipient;
    if (modalState) modalState.textContent = stateDisplay;
    if (keyWarn) {
      const isPlaceholder = !currentConfig.has_api_key || currentConfig.api_key === 'test_key_123';
      keyWarn.style.display = isPlaceholder ? 'block' : 'none';
    }

    if (modal) {
      modal.style.display = 'flex';
      modal.classList.add('show');
    }
  }

  function closeTestModal() {
    const modal = document.getElementById('sms-test-confirm-modal');
    if (modal) {
      modal.style.display = 'none';
      modal.classList.remove('show');
    }
  }

  // Execute Confirmed Real Test SMS
  async function executeConfirmedTest() {
    closeTestModal();
    const btn = document.getElementById('btn-send-real-test-sms');
    const spinner = document.getElementById('sms-test-spinner');

    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Dispatching via SIM...';
    }
    if (spinner) spinner.style.display = 'inline-flex';

    notify('🚀 Authorizing and dispatching real test SMS via Android SIM card...', 'info');

    const recipient = document.getElementById('sms-recipient-input')?.value || currentConfig.recipient_phone;

    try {
      const resp = await fetch('/api/sms/send-test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          recipient: recipient,
          confirmed: true
        })
      });

      const data = await resp.json();
      if (data.success) {
        notify('✅ Real Test SMS accepted by Gateway! Check your recipient phone.', 'success', 6000);
        renderLastAlert(data.record);
        loadHistory();
      } else {
        const errorDetail = data.message || data.error || 'Gateway dispatch rejected';
        notify(`❌ SMS Dispatch failed: ${errorDetail}`, 'error', 8000);
        if (data.record) renderLastAlert(data.record);

        // Clear user-facing alert with guidance
        alert(`Android SIM SMS Notice:\n\n${errorDetail}\n\n• For SMSGate: Ensure your Android phone has SMS Gateway for Android running in Local Server mode and credentials match .env.\n• For TextBee: Ensure your Android phone is linked with the TextBee app and your API key is pasted in the dashboard.`);
      }
    } catch (e) {
      notify(`Dispatch error: ${e.message}`, 'error');
      alert(`Dispatch connection error: ${e.message}`);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Send Real Test SMS to Friend';
      }
      if (spinner) spinner.style.display = 'none';
    }
  }

  // Load and render history table
  async function loadHistory() {
    const tbody = document.getElementById('sms-history-table-body');
    if (!tbody) return;

    try {
      const resp = await fetch('/api/sms/history');
      if (!resp.ok) return;
      const data = await resp.json();
      const items = data.history || [];

      if (!items.length) {
        tbody.innerHTML = `
          <tr>
            <td colspan="6" style="text-align: center; padding: 1.2rem; color: #64748b;">
              No SMS alerts sent yet. Alerts will appear here when elephants are detected.
            </td>
          </tr>
        `;
        return;
      }

      tbody.innerHTML = items.slice(0, 15).map(item => {
        const ok = item.success;
        const statusBadge = ok
          ? `<span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); font-size: 0.68rem; padding: 0.15rem 0.45rem; border-radius: 4px;">
              <i class="fa-solid fa-check"></i> ${item.status || 'ACCEPTED'}
            </span>`
          : `<span class="badge" style="background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); font-size: 0.68rem; padding: 0.15rem 0.45rem; border-radius: 4px;">
              <i class="fa-solid fa-xmark"></i> ${item.status || 'FAILED'}
            </span>`;

        const langBadge = item.state === 'tamil_nadu' ? 'தமிழ்' : 'ಕನ್ನಡ';
        const countBadge = item.elephant_count > 0
          ? `<strong style="color: #f59e0b;">${item.elephant_count}</strong>`
          : `<span style="color: #94a3b8;">Test</span>`;

        return `
          <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.05); font-size: 0.78rem;">
            <td style="padding: 0.6rem 0.8rem; font-family: monospace; color: #94a3b8;">${item.timestamp || '--'}</td>
            <td style="padding: 0.6rem 0.8rem;">${countBadge}</td>
            <td style="padding: 0.6rem 0.8rem; color: #cbd5e1;">${item.location || '--'}</td>
            <td style="padding: 0.6rem 0.8rem;"><span style="color: #38bdf8; font-weight: 600;">EN + ${langBadge}</span></td>
            <td style="padding: 0.6rem 0.8rem; font-family: monospace; color: #a7f3d0;">${item.recipient_masked || '--'}</td>
            <td style="padding: 0.6rem 0.8rem;">${statusBadge}</td>
          </tr>
        `;
      }).join('');

    } catch (e) {
      console.error('[ANDROID-SMS] Error loading history:', e);
    }
  }

  // Toggle API key visibility
  function toggleApiKeyVisibility() {
    const inp = document.getElementById('sms-api-key-input');
    const icon = document.getElementById('sms-api-key-eye');
    if (!inp) return;
    if (inp.type === 'password') {
      inp.type = 'text';
      if (icon) icon.className = 'fa-solid fa-eye-slash';
    } else {
      inp.type = 'password';
      if (icon) icon.className = 'fa-solid fa-eye';
    }
  }

  // Initialize
  function init() {
    if (isInitialized) return;
    isInitialized = true;
    loadStatus();

    // Event listeners for preview updates
    document.getElementById('sms-state-select')?.addEventListener('change', updatePreview);
    document.getElementById('sms-location-input')?.addEventListener('input', updatePreview);

    const modal = document.getElementById('sms-test-confirm-modal');
    if (modal) {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) closeTestModal();
      });
    }

    // Refresh every 30 seconds if on alert tab
    setInterval(() => {
      const pane = document.getElementById('alerts-tab');
      if (pane && pane.classList.contains('active')) {
        loadHistory();
      }
    }, 30000);
  }

  // Auto-init on DOMContentLoaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return {
    init,
    loadStatus,
    loadRecipients,
    openAddRecipientModal,
    closeAddRecipientModal,
    submitNewRecipient,
    toggleRecipient,
    deleteRecipient,
    saveSettings,
    validateGateway,
    promptTestModal,
    closeTestModal,
    executeConfirmedTest,
    updatePreview,
    adjustPreviewCount,
    toggleApiKeyVisibility
  };
})();
