/**
 * 100% Free Instant Alert Hub Module
 * Department of AI & ML, Sri Sairam College of Engineering
 * 
 * Handles Option A (Telegram Bot API) and Option B (Carrier Email-to-SMS via Free SMTP)
 * Zero third-party fees, zero subscriptions, forever free.
 */

(function () {
  'use strict';

  // State Management
  const state = {
    activeChannel: 'telegram', // 'telegram', 'email_sms', 'both'
    supportedCarriers: {},
    isSending: false,
    pollInterval: null
  };

  // Toast Notification System
  function showToast(message, type = 'success', duration = 4000) {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast-item ${type}`;

    let icon = '<i class="fa-solid fa-circle-check" style="color: #10b981;"></i>';
    if (type === 'error') icon = '<i class="fa-solid fa-triangle-exclamation" style="color: #ef4444;"></i>';
    if (type === 'warning') icon = '<i class="fa-solid fa-circle-info" style="color: #f59e0b;"></i>';

    toast.innerHTML = `${icon}<span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }
  window.showToast = showToast;

  // Load Configuration from Backend
  async function loadFreeAlertConfig() {
    try {
      const response = await fetch('/api/alerts/free/config');
      if (!response.ok) throw new Error('Failed to fetch alert configuration');
      const data = await response.json();

      // Populate carrier dropdown
      state.supportedCarriers = data.supported_carriers || {};
      const carrierSelect = document.getElementById('free-carrier-select');
      if (carrierSelect && Object.keys(state.supportedCarriers).length > 0) {
        carrierSelect.innerHTML = '';
        for (const [key, info] of Object.entries(state.supportedCarriers)) {
          const opt = document.createElement('option');
          opt.value = key;
          opt.textContent = `${info.name} (${info.region})`;
          if (key === (data.default_carrier || 'verizon')) {
            opt.selected = true;
          }
          carrierSelect.appendChild(opt);
        }
      }

      // Populate fields
      const telegramTokenInput = document.getElementById('free-telegram-token');
      const telegramChatInput = document.getElementById('free-telegram-chat');
      const smtpEmailInput = document.getElementById('free-smtp-email');
      const phoneInput = document.getElementById('free-target-phone');

      if (telegramTokenInput && data.telegram_bot_token) telegramTokenInput.value = data.telegram_bot_token;
      if (telegramChatInput && data.telegram_chat_id) telegramChatInput.value = data.telegram_chat_id;
      if (smtpEmailInput && data.smtp_email) smtpEmailInput.value = data.smtp_email;
      if (phoneInput && data.default_phone) phoneInput.value = data.default_phone;

      // Set initial channel tab
      if (data.broadcast_channel) {
        setChannel(data.broadcast_channel);
      }
    } catch (err) {
      console.warn('[FREE_ALERT] Could not load alert config:', err);
    }
  }

  // Switch between Telegram / Carrier SMS / Dual Broadcast
  function setChannel(channel) {
    state.activeChannel = channel;
    
    // Update pill buttons
    document.querySelectorAll('.route-pill-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.channel === channel);
    });

    // Show/hide relevant fields
    const telegramGroup = document.getElementById('telegram-fields-group');
    const smsGroup = document.getElementById('sms-fields-group');

    if (telegramGroup) {
      telegramGroup.style.display = (channel === 'telegram' || channel === 'both') ? 'grid' : 'none';
    }
    if (smsGroup) {
      smsGroup.style.display = (channel === 'email_sms' || channel === 'both') ? 'grid' : 'none';
    }

    // Update primary button text
    const sendBtnText = document.getElementById('btn-free-send-text');
    if (sendBtnText) {
      if (channel === 'telegram') sendBtnText.textContent = 'Dispatch Free Telegram Alert';
      else if (channel === 'email_sms') sendBtnText.textContent = 'Dispatch Free Carrier SMS';
      else sendBtnText.textContent = 'Dual Broadcast (Telegram + SMS)';
    }
  }

  // Preset Template Applicator
  function applyPreset(type) {
    const msgField = document.getElementById('free-alert-message');
    const sevField = document.getElementById('free-alert-severity');
    if (!msgField) return;

    const time = new Date().toLocaleTimeString();
    if (type === 'elephant') {
      msgField.value = `🚨 CRITICAL: Elephant confirmed entering Sector 4 corridor near settlement at ${time}. Non-invasive bio-acoustic deterrents activated. Villagers remain indoors.`;
      if (sevField) sevField.value = 'CRITICAL';
    } else if (type === 'acoustic') {
      msgField.value = `⚠️ EARLY WARNING: Low-frequency acoustic elephant rumble detected by Field Node 01 (${time}). Ranging 18-25Hz, confidence 89%. Monitoring team dispatched.`;
      if (sevField) sevField.value = 'WARNING';
    } else if (type === 'ranger') {
      msgField.value = `📢 PATROL UPDATE: Forest perimeter check complete at ${time}. All LoRa mesh nodes functional. Corridor clear.`;
      if (sevField) sevField.value = 'INFO';
    } else if (type === 'test') {
      msgField.value = `🧪 FREE ALERT SYSTEM PING: Diagnostic test initiated from central command dashboard at ${time}. $0 API verified.`;
      if (sevField) sevField.value = 'TEST';
    }

    updateCharCount();
  }

  // Update Character Counter
  function updateCharCount() {
    const msgField = document.getElementById('free-alert-message');
    const countDisplay = document.getElementById('free-char-count');
    if (!msgField || !countDisplay) return;

    const len = msgField.value.length;
    countDisplay.textContent = `${len} characters`;

    if (state.activeChannel === 'email_sms' || state.activeChannel === 'both') {
      if (len > 155) {
        countDisplay.textContent = `${len} / 155 chars (Exceeds single SMS length)`;
        countDisplay.className = 'char-counter warning';
      } else {
        countDisplay.textContent = `${len} / 155 chars (Single SMS)`;
        countDisplay.className = 'char-counter';
      }
    } else {
      countDisplay.className = 'char-counter';
    }
  }

  // Dispatch Free Alert
  async function sendFreeAlert() {
    if (state.isSending) return;

    const msgField = document.getElementById('free-alert-message');
    const sevField = document.getElementById('free-alert-severity');
    const chatField = document.getElementById('free-telegram-chat');
    const phoneField = document.getElementById('free-target-phone');
    const carrierField = document.getElementById('free-carrier-select');
    const customCarrierField = document.getElementById('free-custom-carrier-domain');

    const message = (msgField ? msgField.value : '').trim();
    if (!message) {
      showToast('Please type an alert message or choose a preset template.', 'warning');
      if (msgField) msgField.focus();
      return;
    }

    const payload = {
      channel: state.activeChannel,
      message: message,
      severity: sevField ? sevField.value : 'CRITICAL',
      telegram_chat_id: chatField ? chatField.value.trim() : null,
      phone_number: phoneField ? phoneField.value.trim() : null,
      carrier_key: carrierField ? carrierField.value : 'verizon',
      custom_carrier_domain: customCarrierField ? customCarrierField.value.trim() : null
    };

    // Client-side quick validation
    if (state.activeChannel === 'telegram' || state.activeChannel === 'both') {
      if (!payload.telegram_chat_id) {
        showToast('Please provide a Telegram Chat ID (or your @userinfobot ID).', 'warning');
        if (chatField) chatField.focus();
        return;
      }
    }
    if (state.activeChannel === 'email_sms' || state.activeChannel === 'both') {
      if (!payload.phone_number) {
        showToast('Please provide a 10-digit mobile number for Carrier SMS.', 'warning');
        if (phoneField) phoneField.focus();
        return;
      }
    }

    const sendBtn = document.getElementById('btn-free-send');
    const spinner = document.getElementById('free-send-spinner');
    const btnIcon = document.getElementById('free-send-icon');

    try {
      state.isSending = true;
      if (sendBtn) sendBtn.disabled = true;
      if (spinner) spinner.style.display = 'inline-block';
      if (btnIcon) btnIcon.style.display = 'none';

      const resp = await fetch('/api/alerts/free/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await resp.json();

      if (!resp.ok) {
        throw new Error(data.message || 'Alert dispatch failed');
      }

      if (data.overall_status === 'SUCCESS') {
        showToast(`🎉 Alert Dispatched Successfully via ${state.activeChannel.toUpperCase()}! (${data.duration_ms}ms)`, 'success');
      } else if (data.overall_status === 'PARTIAL') {
        showToast(`⚠️ Partial Delivery: One channel succeeded while another had errors. (${data.duration_ms}ms)`, 'warning');
      } else {
        const errDetail = data.telegram?.details || data.email_sms?.details || data.message || 'Dispatch failed';
        showToast(`❌ Dispatch Error: ${errDetail}`, 'error', 6000);
      }

      // Refresh history log table
      loadAlertTransmissionLog();

    } catch (err) {
      console.error('[FREE_ALERT] Error sending alert:', err);
      showToast(`Error: ${err.message}`, 'error', 6000);
    } finally {
      state.isSending = false;
      if (sendBtn) sendBtn.disabled = false;
      if (spinner) spinner.style.display = 'none';
      if (btnIcon) btnIcon.style.display = 'inline-block';
    }
  }

  // Test Option A: Telegram Bot Handshake & Ping
  async function testTelegramPing() {
    const tokenField = document.getElementById('free-telegram-token');
    const chatField = document.getElementById('free-telegram-chat');
    const testBtn = document.getElementById('btn-test-telegram');

    const botToken = tokenField ? tokenField.value.trim() : '';
    const chatId = chatField ? chatField.value.trim() : '';

    if (!botToken && !chatId) {
      showToast('Enter your Bot Token and Chat ID to run verification.', 'warning');
      return;
    }

    try {
      if (testBtn) {
        testBtn.disabled = true;
        testBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Testing Bot...';
      }

      const resp = await fetch('/api/alerts/free/test-telegram', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bot_token: botToken, chat_id: chatId })
      });

      const data = await resp.json();
      if (data.success) {
        showToast(`✅ ${data.details.message || 'Telegram Bot verified successfully!'}`, 'success', 5000);
      } else {
        const errorMsg = data.details?.error || 'Verification failed';
        showToast(`❌ Telegram Test Failed: ${errorMsg}`, 'error', 7000);
      }
    } catch (err) {
      showToast(`Network error testing Telegram: ${err.message}`, 'error');
    } finally {
      if (testBtn) {
        testBtn.disabled = false;
        testBtn.innerHTML = '<i class="fa-brands fa-telegram"></i> Test Telegram Ping';
      }
    }
  }

  // Test Option B: Carrier Email-to-SMS Gateway
  async function testCarrierSmsPing() {
    const emailField = document.getElementById('free-smtp-email');
    const passField = document.getElementById('free-smtp-password');
    const phoneField = document.getElementById('free-target-phone');
    const carrierField = document.getElementById('free-carrier-select');
    const testBtn = document.getElementById('btn-test-carrier-sms');

    const smtpEmail = emailField ? emailField.value.trim() : '';
    const smtpPass = passField ? passField.value.trim() : '';
    const phone = phoneField ? phoneField.value.trim() : '';
    const carrier = carrierField ? carrierField.value : 'verizon';

    if (!smtpEmail) {
      showToast('Enter your Gmail/SMTP email address.', 'warning');
      return;
    }

    try {
      if (testBtn) {
        testBtn.disabled = true;
        testBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Testing SMTP...';
      }

      const resp = await fetch('/api/alerts/free/test-email-sms', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          smtp_email: smtpEmail,
          smtp_password: smtpPass,
          test_phone: phone,
          test_carrier: carrier
        })
      });

      const data = await resp.json();
      if (data.success) {
        showToast(`✅ ${data.details.message}. Relay verified!`, 'success', 5000);
      } else {
        const errorMsg = data.details?.error || 'SMTP Test Failed';
        showToast(`❌ Carrier SMS Test Failed: ${errorMsg}`, 'error', 8000);
      }
    } catch (err) {
      showToast(`Network error testing SMTP: ${err.message}`, 'error');
    } finally {
      if (testBtn) {
        testBtn.disabled = false;
        testBtn.innerHTML = '<i class="fa-solid fa-envelope-circle-check"></i> Test Carrier SMS';
      }
    }
  }

  // Save Settings to Backend
  async function saveSettings() {
    const telegramTokenInput = document.getElementById('free-telegram-token');
    const telegramChatInput = document.getElementById('free-telegram-chat');
    const smtpEmailInput = document.getElementById('free-smtp-email');
    const smtpPassInput = document.getElementById('free-smtp-password');
    const phoneInput = document.getElementById('free-target-phone');
    const carrierSelect = document.getElementById('free-carrier-select');
    const saveBtn = document.getElementById('btn-save-free-config');

    const newConfig = {
      telegram_bot_token: telegramTokenInput ? telegramTokenInput.value.trim() : '',
      telegram_chat_id: telegramChatInput ? telegramChatInput.value.trim() : '',
      smtp_email: smtpEmailInput ? smtpEmailInput.value.trim() : '',
      smtp_password: smtpPassInput ? smtpPassInput.value.trim() : '',
      default_phone: phoneInput ? phoneInput.value.trim() : '',
      default_carrier: carrierSelect ? carrierSelect.value : 'verizon',
      broadcast_channel: state.activeChannel
    };

    try {
      if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';
      }

      const resp = await fetch('/api/alerts/free/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newConfig)
      });
      const data = await resp.json();
      if (data.status === 'success') {
        showToast('Settings saved successfully to free_alert_config.json!', 'success');
      } else {
        showToast(`Could not save settings: ${data.message}`, 'error');
      }
    } catch (err) {
      showToast(`Error saving settings: ${err.message}`, 'error');
    } finally {
      if (saveBtn) {
        saveBtn.disabled = false;
        saveBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Settings';
      }
    }
  }

  // Render Alert Transmission Log
  async function loadAlertTransmissionLog() {
    const tbody = document.getElementById('free-alert-history-body');
    if (!tbody) return;

    try {
      const resp = await fetch('/api/alerts/free/history');
      if (!resp.ok) return;
      const history = await resp.json();

      if (!history || history.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="5" style="text-align: center; padding: 1.5rem; color: #64748b;">
              <i class="fa-solid fa-clock-rotate-left" style="margin-right: 0.4rem;"></i> No alerts dispatched yet. Send a test alert above to verify transmission.
            </td>
          </tr>
        `;
        return;
      }

      tbody.innerHTML = '';
      history.slice(0, 15).forEach(item => {
        const time = item.timestamp ? item.timestamp.split(' ')[1] : 'N/A';
        const channelLabel = item.channel_requested === 'both' ? 'Dual (TG + SMS)' : (item.channel_requested === 'telegram' ? 'Telegram' : 'Carrier SMS');
        
        let statusBadge = '<span class="status-badge-delivered"><i class="fa-solid fa-check"></i> Delivered</span>';
        if (item.overall_status === 'FAILED') {
          statusBadge = '<span class="status-badge-failed"><i class="fa-solid fa-xmark"></i> Failed</span>';
        } else if (item.overall_status === 'PARTIAL') {
          statusBadge = '<span class="status-badge-delivered" style="background: rgba(245, 158, 11, 0.15); color: #f59e0b; border-color: rgba(245, 158, 11, 0.3);"><i class="fa-solid fa-triangle-exclamation"></i> Partial</span>';
        }

        const sevClass = (item.severity || 'CRITICAL').toLowerCase();
        let sevBadge = `<span class="badge-det ${sevClass}">${item.severity || 'ALERT'}</span>`;

        // Tooltip detail
        const details = item.telegram?.details || item.email_sms?.details || item.message || '';

        const row = document.createElement('tr');
        row.innerHTML = `
          <td style="font-family: monospace; color: #94a3b8;">${time}</td>
          <td><strong style="color: #38bdf8;">${channelLabel}</strong></td>
          <td>${sevBadge}</td>
          <td>${statusBadge}</td>
          <td style="font-size: 0.75rem; color: #94a3b8; max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${details}">
            ${details}
          </td>
        `;
        tbody.appendChild(row);
      });
    } catch (err) {
      console.warn('[FREE_ALERT] Error loading history:', err);
    }
  }

  // Quick Global SMS Trigger for Map Tab / Deterrent Card
  window.broadcastSMSAlert = async function () {
    const card = document.getElementById('card-sms');
    if (card) {
      card.style.transform = 'scale(0.96)';
      setTimeout(() => card.style.transform = '', 200);
    }

    showToast('🚨 Triggering Free Emergency Broadcast across Telegram & Carrier SMS...', 'warning', 3000);

    try {
      const resp = await fetch('/api/alerts/free/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          channel: 'both',
          message: '🚨 CRITICAL ELEPHANT DETECTED: Automated field warning triggered by Command Dashboard! Villagers remain indoors; elephant mitigation teams en route.',
          severity: 'CRITICAL'
        })
      });
      const data = await resp.json();
      if (data.overall_status === 'SUCCESS' || data.overall_status === 'PARTIAL') {
        showToast('✅ Emergency Alert Dispatched to Telegram & Carrier SMS ($0 API Cost)!', 'success', 5000);
      } else {
        showToast('⚠️ Alert triggered. Check Alert Management tab for channel status details.', 'warning', 5000);
      }
    } catch (e) {
      showToast(`Emergency alert error: ${e.message}`, 'error');
    }
  };

  // ==============================================================================
  // REAL TEST MESSAGE DELIVERY VERIFICATION ENGINE (CONTROLLER)
  // ==============================================================================
  const RealDeliveryVerification = (function () {
    let currentMethod = 'telegram';
    let lastEventId = null;

    function setMethod(method) {
      currentMethod = method;

      // Update toggle buttons
      document.getElementById('btn-method-telegram')?.classList.toggle('active', method === 'telegram');
      document.getElementById('btn-method-email-sms')?.classList.toggle('active', method === 'email_sms');
      document.getElementById('btn-method-gsm')?.classList.toggle('active', method === 'gsm_sim');

      const recipientLabel = document.getElementById('verify-recipient-label');
      const recipientInput = document.getElementById('verify-recipient-input');
      const recipientHint = document.getElementById('verify-recipient-hint');
      const carrierCol = document.getElementById('verify-carrier-col');
      const customDomainRow = document.getElementById('verify-custom-domain-row');

      if (method === 'telegram') {
        if (recipientLabel) recipientLabel.innerHTML = '<i class="fa-brands fa-telegram" style="color: #38bdf8;"></i> Telegram Chat ID / Username:';
        if (recipientInput) recipientInput.placeholder = 'e.g. 123456789 or @username';
        if (recipientHint) recipientHint.textContent = 'Enter your numeric Telegram Chat ID (get from @userinfobot) or channel handle.';
        if (carrierCol) carrierCol.style.display = 'none';
        if (customDomainRow) customDomainRow.style.display = 'none';
      } else if (method === 'email_sms') {
        if (recipientLabel) recipientLabel.innerHTML = '<i class="fa-solid fa-mobile-screen" style="color: #10b981;"></i> 10-Digit Mobile Number (US/CA):';
        if (recipientInput) recipientInput.placeholder = 'e.g. 5551234567';
        if (recipientHint) recipientHint.textContent = 'North American 10-digit phone number. Note: Indian (+91) carriers do not support email gateways.';
        if (carrierCol) carrierCol.style.display = 'block';
      } else if (method === 'gsm_sim') {
        if (recipientLabel) recipientLabel.innerHTML = '<i class="fa-solid fa-sim-card" style="color: #f59e0b;"></i> SIM Destination Phone:';
        if (recipientInput) recipientInput.placeholder = 'e.g. +91 9876543210';
        if (recipientHint) recipientHint.textContent = 'Requires physical GSM modem shield (SIM800L). Note: Hardware is currently unsupported.';
        if (carrierCol) carrierCol.style.display = 'none';
        if (customDomainRow) customDomainRow.style.display = 'none';
      }

      refreshSenderInfo();
    }

    async function refreshSenderInfo() {
      const senderDisplay = document.getElementById('verify-sender-display');
      const senderPill = document.getElementById('verify-sender-auth-pill');
      if (!senderDisplay) return;

      try {
        const resp = await fetch('/api/alerts/free/config');
        if (!resp.ok) return;
        const cfg = await resp.json();

        if (currentMethod === 'telegram') {
          if (cfg.telegram_bot_token && !cfg.telegram_bot_token.includes('••••')) {
            senderDisplay.textContent = `Configured Token: ${cfg.telegram_bot_token.slice(0, 4)}••••••••`;
          } else if (cfg.telegram_bot_token) {
            senderDisplay.textContent = `Configured Token: ${cfg.telegram_bot_token}`;
          } else {
            senderDisplay.textContent = 'Not Configured (Missing TELEGRAM_BOT_TOKEN)';
          }

          if (cfg.telegram_bot_token) {
            if (senderPill) {
              senderPill.style.background = 'rgba(56, 189, 248, 0.15)';
              senderPill.style.color = '#38bdf8';
              senderPill.textContent = 'Credentials Present';
            }
          } else {
            if (senderPill) {
              senderPill.style.background = 'rgba(239, 68, 68, 0.15)';
              senderPill.style.color = '#ef4444';
              senderPill.textContent = 'Missing Token';
            }
          }
        } else if (currentMethod === 'email_sms') {
          if (cfg.smtp_email) {
            senderDisplay.textContent = `SMTP Account: ${cfg.smtp_email} (Relay: ${cfg.smtp_server}:${cfg.smtp_port})`;
            if (senderPill) {
              senderPill.style.background = 'rgba(16, 185, 129, 0.15)';
              senderPill.style.color = '#10b981';
              senderPill.textContent = 'SMTP Configured';
            }
          } else {
            senderDisplay.textContent = 'Not Configured (Missing SMTP Email / Password)';
            if (senderPill) {
              senderPill.style.background = 'rgba(239, 68, 68, 0.15)';
              senderPill.style.color = '#ef4444';
              senderPill.textContent = 'Missing SMTP';
            }
          }
        } else if (currentMethod === 'gsm_sim') {
          senderDisplay.textContent = 'None (GSM/SIM Hardware Not Detected)';
          if (senderPill) {
            senderPill.style.background = 'rgba(239, 68, 68, 0.2)';
            senderPill.style.color = '#ef4444';
            senderPill.textContent = 'Unsupported';
          }
        }
      } catch (e) {
        console.warn('[VERIFY] Error refreshing sender info:', e);
      }
    }

    function onRecipientChange() {
      // Optional live cleanup
    }

    function maskRecipientPreview(recipient) {
      if (!recipient) return 'Not Provided';
      const s = recipient.trim();
      if (currentMethod === 'telegram') {
        if (s.startsWith('@')) return s.length > 4 ? s.slice(0, 4) + '****' : '@***';
        if (s.length > 5) return s.slice(0, 3) + '••••' + s.slice(-2);
        return '••••';
      }
      const digits = s.replace(/\D/g, '');
      if (digits.length >= 10) return '***-***-' + digits.slice(-4);
      return '***';
    }

    async function validateOnly() {
      const recipient = (document.getElementById('verify-recipient-input')?.value || '').trim();
      const carrier = document.getElementById('verify-carrier-select')?.value || 'verizon';
      const customDomain = document.getElementById('verify-custom-domain-input')?.value || '';
      const spinner = document.getElementById('verify-spinner');

      try {
        if (spinner) spinner.style.display = 'inline-block';
        const resp = await fetch('/api/alerts/verify/validate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            method: currentMethod,
            recipient: recipient,
            carrier_key: carrier,
            custom_domain: customDomain
          })
        });

        const data = await resp.json();
        renderOutcome(data);
      } catch (err) {
        renderOutcome({
          status: 'CONFIGURATION_INVALID',
          error: `Validation error: ${err.message}`
        });
      } finally {
        if (spinner) spinner.style.display = 'none';
      }
    }

    function promptConfirmationModal() {
      const recipient = (document.getElementById('verify-recipient-input')?.value || '').trim();
      if (!recipient && currentMethod !== 'gsm_sim') {
        showToast('Please enter the recipient chat ID or mobile number.', 'warning');
        document.getElementById('verify-recipient-input')?.focus();
        return;
      }

      const modal = document.getElementById('verify-confirm-modal');
      const methodDisplay = document.getElementById('modal-confirm-method');
      const recipientDisplay = document.getElementById('modal-confirm-recipient');

      const methodNames = {
        telegram: 'Option A: Telegram Bot API',
        email_sms: 'Option B: Carrier Email-to-SMS',
        gsm_sim: 'Option C: GSM/SIM Hardware Device'
      };

      if (methodDisplay) methodDisplay.textContent = methodNames[currentMethod] || currentMethod;
      if (recipientDisplay) recipientDisplay.textContent = maskRecipientPreview(recipient);
      if (modal) {
        modal.style.display = 'flex';
        modal.classList.add('show');
      }
    }

    function closeConfirmationModal() {
      const modal = document.getElementById('verify-confirm-modal');
      if (modal) {
        modal.style.display = 'none';
        modal.classList.remove('show');
      }
    }

    async function executeConfirmedSend() {
      closeConfirmationModal();

      const recipient = (document.getElementById('verify-recipient-input')?.value || '').trim();
      const carrier = document.getElementById('verify-carrier-select')?.value || 'verizon';
      const customDomain = document.getElementById('verify-custom-domain-input')?.value || '';
      const sendBtn = document.getElementById('btn-send-real-test');
      const spinner = document.getElementById('verify-spinner');

      try {
        if (sendBtn) sendBtn.disabled = true;
        if (spinner) spinner.style.display = 'inline-block';

        const resp = await fetch('/api/alerts/verify/send-test', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            method: currentMethod,
            recipient: recipient,
            carrier_key: carrier,
            custom_domain: customDomain,
            confirmed: true
          })
        });

        const data = await resp.json();
        lastEventId = data.event_id || null;
        renderOutcome(data);

        if (data.status === 'AWAITING_RECIPIENT_CONFIRMATION' || data.status === 'ACCEPTED_BY_PROVIDER') {
          showToast(`Provider Accepted Test Message! (${data.status})`, 'success', 5000);
        } else if (data.status === 'CONFIGURATION_INVALID') {
          showToast(`Configuration Invalid: ${data.details || data.error}`, 'warning', 6000);
        } else if (data.status === 'SEND_FAILED') {
          showToast(`Send Failed: ${data.details || data.error}`, 'error', 6000);
        }

        // Refresh alert logs
        loadAlertTransmissionLog();

      } catch (err) {
        renderOutcome({
          status: 'SEND_FAILED',
          error: `Network dispatch error: ${err.message}`
        });
      } finally {
        if (sendBtn) sendBtn.disabled = false;
        if (spinner) spinner.style.display = 'none';
      }
    }

    function renderOutcome(result) {
      const panel = document.getElementById('verify-outcome-panel');
      const badgeContainer = document.getElementById('verify-status-badge');
      const detailsText = document.getElementById('verify-details-text');
      const metadataBox = document.getElementById('verify-metadata-box');
      const receiptAction = document.getElementById('verify-receipt-action');

      if (!panel) return;
      panel.style.display = 'block';

      const status = result.status || 'CONFIGURATION_INVALID';
      let badgeHtml = '';

      if (status === 'CONFIGURATION_INVALID') {
        badgeHtml = '<span class="badge" style="background: rgba(245, 158, 11, 0.2); color: #f59e0b; border: 1px solid #f59e0b; font-weight: 700; padding: 0.35rem 0.75rem; border-radius: 6px;"><i class="fa-solid fa-triangle-exclamation"></i> CONFIGURATION_INVALID</span>';
      } else if (status === 'SEND_FAILED') {
        badgeHtml = '<span class="badge" style="background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid #ef4444; font-weight: 700; padding: 0.35rem 0.75rem; border-radius: 6px;"><i class="fa-solid fa-circle-xmark"></i> SEND_FAILED</span>';
      } else if (status === 'ACCEPTED_BY_PROVIDER') {
        badgeHtml = '<span class="badge" style="background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid #38bdf8; font-weight: 700; padding: 0.35rem 0.75rem; border-radius: 6px;"><i class="fa-solid fa-paper-plane"></i> ACCEPTED_BY_PROVIDER</span>';
      } else if (status === 'AWAITING_RECIPIENT_CONFIRMATION') {
        badgeHtml = '<span class="badge" style="background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid #c084fc; font-weight: 700; padding: 0.35rem 0.75rem; border-radius: 6px;"><i class="fa-solid fa-clock"></i> AWAITING_RECIPIENT_CONFIRMATION</span>';
      } else if (status === 'DELIVERY_CONFIRMED') {
        badgeHtml = '<span class="badge" style="background: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid #10b981; font-weight: 700; padding: 0.35rem 0.75rem; border-radius: 6px;"><i class="fa-solid fa-circle-check"></i> DELIVERY_CONFIRMED</span>';
      } else if (status === 'READY') {
        badgeHtml = '<span class="badge" style="background: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid #10b981; font-weight: 700; padding: 0.35rem 0.75rem; border-radius: 6px;"><i class="fa-solid fa-circle-check"></i> READY_TO_SEND</span>';
      }

      if (badgeContainer) badgeContainer.innerHTML = badgeHtml;

      const desc = result.details || result.error || 'Verification check completed.';
      if (detailsText) detailsText.innerHTML = `<strong>Diagnostic Status:</strong> ${desc}`;

      if (metadataBox) {
        const time = result.timestamp || new Date().toLocaleString();
        const maskedRcpt = result.masked_recipient || 'N/A';
        const maskedSender = result.masked_sender || 'N/A';
        const raw = result.raw_response ? JSON.stringify(result.raw_response) : 'None';
        metadataBox.innerHTML = `
          <div><strong>Timestamp:</strong> ${time} | <strong>Method:</strong> ${(result.method || currentMethod).toUpperCase()}</div>
          <div><strong>Sender:</strong> ${maskedSender} | <strong>Recipient:</strong> ${maskedRcpt}</div>
          <div style="margin-top: 0.25rem; word-break: break-all;"><strong>Provider Response:</strong> ${raw}</div>
        `;
      }

      // Show manual confirmation button if provider accepted but handset confirmation unverified
      if (receiptAction) {
        if (status === 'AWAITING_RECIPIENT_CONFIRMATION' || status === 'ACCEPTED_BY_PROVIDER') {
          receiptAction.style.display = 'flex';
        } else {
          receiptAction.style.display = 'none';
        }
      }
    }

    async function confirmManualReceipt() {
      if (!lastEventId) {
        showToast('No active in-flight verification event to confirm.', 'warning');
        return;
      }

      const btn = document.getElementById('btn-confirm-receipt');
      try {
        if (btn) {
          btn.disabled = true;
          btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Confirming...';
        }

        const resp = await fetch('/api/alerts/verify/confirm-receipt', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ event_id: lastEventId })
        });

        const data = await resp.json();
        if (data.status === 'success') {
          showToast('🎉 Delivery Receipt Confirmed! Status: DELIVERY_CONFIRMED', 'success', 5000);
          renderOutcome(data.event);
        } else {
          showToast(`Error confirming receipt: ${data.error}`, 'error');
        }
      } catch (err) {
        showToast(`Confirmation error: ${err.message}`, 'error');
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<i class="fa-solid fa-check-double"></i> I Received It! (Confirm Delivery)';
        }
      }
    }

    function init() {
      setMethod('telegram');
      const carrierSelect = document.getElementById('verify-carrier-select');
      const customDomainRow = document.getElementById('verify-custom-domain-row');
      if (carrierSelect && customDomainRow) {
        carrierSelect.addEventListener('change', () => {
          customDomainRow.style.display = carrierSelect.value === 'custom' ? 'block' : 'none';
        });
      }
    }

    return {
      setMethod,
      onRecipientChange,
      validateOnly,
      promptConfirmationModal,
      closeConfirmationModal,
      executeConfirmedSend,
      confirmManualReceipt,
      init
    };
  })();

  // Expose methods to global scope
  window.FreeAlertHub = {
    setChannel,
    applyPreset,
    updateCharCount,
    sendFreeAlert,
    testTelegramPing,
    testCarrierSmsPing,
    saveSettings,
    loadAlertTransmissionLog
  };

  window.RealDeliveryVerification = RealDeliveryVerification;

  // Initialize on DOM Ready
  document.addEventListener('DOMContentLoaded', () => {
    loadFreeAlertConfig();
    loadAlertTransmissionLog();
    RealDeliveryVerification.init();

    // Listen to textarea changes for character counting
    const msgField = document.getElementById('free-alert-message');
    if (msgField) {
      msgField.addEventListener('input', updateCharCount);
    }

    // Custom carrier toggle
    const carrierSelect = document.getElementById('free-carrier-select');
    const customCarrierGroup = document.getElementById('custom-carrier-group');
    if (carrierSelect && customCarrierGroup) {
      carrierSelect.addEventListener('change', () => {
        customCarrierGroup.style.display = carrierSelect.value === 'custom' ? 'block' : 'none';
        updateCharCount();
      });
    }

    // Refresh history periodically when on alerts tab
    setInterval(() => {
      if (document.getElementById('alerts-tab')?.classList.contains('active')) {
        loadAlertTransmissionLog();
      }
    }, 5000);
  });

})();

