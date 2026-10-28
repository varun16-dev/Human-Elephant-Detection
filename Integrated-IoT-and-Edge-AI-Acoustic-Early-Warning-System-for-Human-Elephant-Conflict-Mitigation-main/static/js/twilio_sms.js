/**
 * Twilio Programmable Messaging Integration Controller
 * Department of AI & ML, Sri Sairam College of Engineering
 */

const TwilioSmsGateway = (() => {
  let simCount = 2;
  let isSending = false;

  async function init() {
    console.log("[TWILIO-SMS] Initializing Twilio SMS Gateway UI controller...");
    await loadStatus();
    await loadHistory();
    updatePreview(0);

    // Periodic refresh of status & history
    setInterval(loadStatus, 15000);
    setInterval(loadHistory, 15000);

    const modal = document.getElementById("twilio-test-modal");
    if (modal) {
      modal.addEventListener("click", (e) => {
        if (e.target === modal) closeTestModal();
      });
    }
  }

  async function loadStatus() {
    try {
      const res = await fetch("/api/twilio/status");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      // Badges & status pills
      const badge = document.getElementById("twilio-status-badge");
      if (badge) {
        if (!data.is_configured) {
          badge.className = "badge";
          badge.style.background = "rgba(239, 68, 68, 0.15)";
          badge.style.color = "#ef4444";
          badge.style.border = "1px solid rgba(239, 68, 68, 0.3)";
          badge.innerHTML = '<i class="fa-solid fa-circle-exclamation"></i> Credentials Needed';
        } else {
          badge.className = "badge";
          badge.style.background = "rgba(16, 185, 129, 0.15)";
          badge.style.color = "#10b981";
          badge.style.border = "1px solid rgba(16, 185, 129, 0.3)";
          badge.innerHTML = '<i class="fa-solid fa-check-circle"></i> Configured';
        }
      }

      // Display masked credentials
      const sidDisplay = document.getElementById("twilio-sid-display");
      if (sidDisplay) sidDisplay.textContent = data.account_sid_masked || "Not configured";

      const fromDisplay = document.getElementById("twilio-from-display");
      if (fromDisplay) fromDisplay.textContent = data.from_number_masked || "Not configured";

      const toDisplay = document.getElementById("twilio-to-display");
      if (toDisplay) toDisplay.textContent = data.to_number_masked || "Not configured";

      // Form fields
      const stateSelect = document.getElementById("twilio-state-select");
      if (stateSelect && !stateSelect.dataset.userEdited) {
        stateSelect.value = data.state || "tamil_nadu";
      }

      const locInput = document.getElementById("twilio-location-input");
      if (locInput && !locInput.dataset.userEdited) {
        locInput.value = data.location_name || "Monitoring Zone 1";
      }

      const cooldownInput = document.getElementById("twilio-cooldown-input");
      if (cooldownInput && !cooldownInput.dataset.userEdited) {
        cooldownInput.value = data.cooldown_seconds || 300;
      }

      const policySelect = document.getElementById("twilio-policy-select");
      if (policySelect && !policySelect.dataset.userEdited) {
        policySelect.value = data.count_change_policy || "increase_only";
      }

      const absenceInput = document.getElementById("twilio-absence-input");
      if (absenceInput && !absenceInput.dataset.userEdited) {
        absenceInput.value = data.absence_reset_seconds || 120;
      }

      // Incident state pill
      const incidentPill = document.getElementById("twilio-incident-state");
      if (incidentPill) {
        if (data.incident_active) {
          incidentPill.style.background = "rgba(245, 158, 11, 0.2)";
          incidentPill.style.color = "#f59e0b";
          incidentPill.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> ACTIVE INCIDENT (${data.current_count} Elephants)`;
        } else {
          incidentPill.style.background = "rgba(100, 116, 139, 0.2)";
          incidentPill.style.color = "#94a3b8";
          incidentPill.innerHTML = '<i class="fa-solid fa-shield-check"></i> IDLE / SAFE';
        }
      }

      // Last delivery status
      const lastStatusPill = document.getElementById("twilio-last-status");
      if (lastStatusPill) {
        lastStatusPill.textContent = data.last_message_status || "IDLE";
        if (data.last_message_status === "DELIVERED") {
          lastStatusPill.style.color = "#10b981";
        } else if (data.last_message_status === "QUEUED" || data.last_message_status === "SENT") {
          lastStatusPill.style.color = "#38bdf8";
        } else if (data.last_message_status === "FAILED" || data.last_message_status === "UNDELIVERED") {
          lastStatusPill.style.color = "#ef4444";
        } else {
          lastStatusPill.style.color = "#94a3b8";
        }
      }
    } catch (e) {
      console.warn("[TWILIO-SMS] Status update notice:", e);
    }
  }

  async function updatePreview(delta = 0) {
    simCount = Math.max(1, simCount + delta);
    const countEl = document.getElementById("twilio-sim-count");
    if (countEl) countEl.textContent = simCount;

    const stateSelect = document.getElementById("twilio-state-select");
    const locInput = document.getElementById("twilio-location-input");

    const state = stateSelect ? stateSelect.value : "tamil_nadu";
    const location = locInput && locInput.value.trim() ? locInput.value.trim() : "Monitoring Zone 1";

    try {
      const res = await fetch("/api/twilio/preview-message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ count: simCount, state: state, location: location })
      });
      if (!res.ok) return;
      const data = await res.json();

      const previewBox = document.getElementById("twilio-message-preview");
      if (previewBox) {
        previewBox.textContent = data.message;
      }

      const metricsEl = document.getElementById("twilio-preview-metrics");
      if (metricsEl) {
        metricsEl.innerHTML = `
          <span><i class="fa-solid fa-font"></i> ${data.char_count} chars</span> • 
          <span><i class="fa-solid fa-layer-group"></i> ${data.segment_count} segment${data.segment_count > 1 ? 's' : ''} (${data.encoding})</span> •
          <span><i class="fa-solid fa-language"></i> ${data.is_unicode ? 'Unicode Regional SMS' : 'GSM-7 Standard'}</span>
        `;
      }
    } catch (e) {
      console.warn("[TWILIO-SMS] Preview notice:", e);
    }
  }

  async function validateConnection() {
    const btn = document.getElementById("btn-validate-twilio");
    const resultBox = document.getElementById("twilio-validate-result");
    if (!resultBox) return;

    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Validating Credentials...';
    }

    resultBox.style.display = "block";
    resultBox.style.background = "rgba(15, 23, 42, 0.7)";
    resultBox.style.borderColor = "rgba(56, 189, 248, 0.3)";
    resultBox.style.color = "#cbd5e1";
    resultBox.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Checking Twilio API credentials...';

    try {
      const res = await fetch("/api/twilio/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
      });
      const data = await res.json();

      if (data.valid) {
        resultBox.style.background = "rgba(16, 185, 129, 0.12)";
        resultBox.style.borderColor = "rgba(16, 185, 129, 0.4)";
        resultBox.style.color = "#a7f3d0";
        resultBox.innerHTML = `
          <div style="font-weight: 700; margin-bottom: 0.3rem;"><i class="fa-solid fa-circle-check" style="color: #10b981;"></i> ${data.message}</div>
          <div style="font-size: 0.75rem; color: #cbd5e1;">Account: ${data.details.friendly_name || 'Active'} | Type: ${data.details.type || 'Standard'} | From: ${data.details.from_number_masked || 'Configured'}</div>
        `;
      } else {
        resultBox.style.background = "rgba(239, 68, 68, 0.12)";
        resultBox.style.borderColor = "rgba(239, 68, 68, 0.4)";
        resultBox.style.color = "#fca5a5";
        resultBox.innerHTML = `
          <div style="font-weight: 700; margin-bottom: 0.3rem;"><i class="fa-solid fa-circle-xmark" style="color: #ef4444;"></i> Twilio Validation Failed</div>
          <div style="font-size: 0.75rem; color: #fecaca;">${data.message}</div>
          <div style="font-size: 0.7rem; color: #94a3b8; margin-top: 0.25rem;">Ensure TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in .env or settings are accurate.</div>
        `;
      }
    } catch (e) {
      resultBox.style.background = "rgba(239, 68, 68, 0.12)";
      resultBox.style.borderColor = "rgba(239, 68, 68, 0.4)";
      resultBox.style.color = "#fca5a5";
      resultBox.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Server connection error: ${e.message}`;
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-stethoscope"></i> Test Connection';
      }
      await loadStatus();
    }
  }

  async function saveSettings() {
    const btn = document.getElementById("btn-save-twilio-config");
    const state = document.getElementById("twilio-state-select")?.value;
    const location = document.getElementById("twilio-location-input")?.value;
    const cooldown = document.getElementById("twilio-cooldown-input")?.value;
    const policy = document.getElementById("twilio-policy-select")?.value;
    const absence = document.getElementById("twilio-absence-input")?.value;

    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';
    }

    try {
      const res = await fetch("/api/twilio/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          state: state,
          location_name: location,
          cooldown_seconds: cooldown,
          count_change_policy: policy,
          absence_reset_seconds: absence
        })
      });
      const data = await res.json();
      if (data.success) {
        alert("Twilio alert settings saved successfully!");
      } else {
        alert("Failed to save settings: " + (data.error || "Unknown error"));
      }
    } catch (e) {
      alert("Error saving settings: " + e.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Settings';
      }
      await loadStatus();
    }
  }

  function promptTestModal() {
    const modal = document.getElementById("twilio-test-modal");
    const previewText = document.getElementById("twilio-message-preview")?.textContent || "";
    const modalRecipient = document.getElementById("twilio-modal-recipient");
    const modalPreview = document.getElementById("twilio-modal-preview");

    if (modalRecipient) {
      const toDisplay = document.getElementById("twilio-to-display")?.textContent || "Configured recipient";
      modalRecipient.textContent = toDisplay;
    }

    if (modalPreview) {
      modalPreview.textContent = previewText;
    }

    if (modal) {
      modal.style.display = "flex";
      modal.classList.add("show");
    }
  }

  function closeTestModal() {
    const modal = document.getElementById("twilio-test-modal");
    if (modal) {
      modal.style.display = "none";
      modal.classList.remove("show");
    }
  }

  async function executeTestSms() {
    if (isSending) return;
    isSending = true;

    const btn = document.getElementById("btn-confirm-twilio-send");
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Submitting to Twilio...';
    }

    const state = document.getElementById("twilio-state-select")?.value;
    const location = document.getElementById("twilio-location-input")?.value;

    try {
      const res = await fetch("/api/twilio/send-test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          confirmed: true,
          count: simCount,
          state: state,
          location: location
        })
      });
      const data = await res.json();

      closeTestModal();

      if (data.success) {
        alert(`Twilio Test SMS successfully submitted!\n\nMessage SID: ${data.record.message_sid}\nInitial Status: ${data.record.status}\n\nNotice: Check your authorized phone handset.`);
      } else {
        alert(`Twilio Test SMS Failed:\n\n${data.error || data.message || 'Unknown provider rejection'}`);
      }
    } catch (e) {
      alert("Error contacting server: " + e.message);
    } finally {
      isSending = false;
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-check"></i> Authorize & Send SMS';
      }
      await loadStatus();
      await loadHistory();
    }
  }

  async function loadHistory() {
    const tbody = document.getElementById("twilio-history-body");
    if (!tbody) return;

    try {
      const res = await fetch("/api/twilio/history?limit=15");
      if (!res.ok) return;
      const history = await res.json();

      if (!history || history.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="5" style="text-align: center; padding: 1.2rem; color: #64748b;">
              <i class="fa-solid fa-inbox" style="margin-right: 0.4rem;"></i> No Twilio SMS messages dispatched yet.
            </td>
          </tr>
        `;
        return;
      }

      tbody.innerHTML = "";
      history.forEach(item => {
        const row = document.createElement("tr");

        let statusColor = "#94a3b8";
        if (item.status === "DELIVERED") statusColor = "#10b981";
        else if (item.status === "QUEUED" || item.status === "SENT") statusColor = "#38bdf8";
        else if (item.status === "FAILED" || item.status === "UNDELIVERED") statusColor = "#ef4444";

        let timeStr = item.timestamp ? item.timestamp.replace("T", " ").substring(0, 19) : "N/A";

        row.innerHTML = `
          <td style="font-family: monospace; font-size: 0.72rem; white-space: nowrap;">${timeStr}</td>
          <td style="font-family: monospace; font-size: 0.74rem;">${item.to || 'N/A'}</td>
          <td style="font-size: 0.72rem; color: #cbd5e1; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${item.body_snippet || ''}">
            ${item.body_snippet || 'Elephant Alert'}
          </td>
          <td style="font-size: 0.7rem; color: #94a3b8;">
            ${item.segment_count || 1} seg (${item.encoding || 'UCS-2'})
          </td>
          <td>
            <span style="font-size: 0.7rem; font-weight: 700; color: ${statusColor}; padding: 0.15rem 0.45rem; border-radius: 4px; background: rgba(0,0,0,0.25);">
              ${item.status || 'QUEUED'}
            </span>
            ${item.error_message ? `<div style="font-size: 0.65rem; color: #fca5a5; margin-top: 0.2rem;">${item.error_message}</div>` : ''}
          </td>
        `;
        tbody.appendChild(row);
      });
    } catch (e) {
      console.warn("[TWILIO-SMS] History update notice:", e);
    }
  }

  return {
    init,
    loadStatus,
    updatePreview,
    validateConnection,
    saveSettings,
    promptTestModal,
    closeTestModal,
    executeTestSms,
    loadHistory
  };
})();

// Auto-initialize when document is ready
document.addEventListener("DOMContentLoaded", () => {
  TwilioSmsGateway.init();
});
