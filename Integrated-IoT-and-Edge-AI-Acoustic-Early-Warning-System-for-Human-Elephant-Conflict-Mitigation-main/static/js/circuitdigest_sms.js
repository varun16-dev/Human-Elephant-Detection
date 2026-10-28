/**
 * CircuitDigest Cloud SMS Gateway Controller
 * Department of AI & ML, Sri Sairam College of Engineering
 *
 * Manages CircuitDigest Cloud REST API:
 * - Status inspection & masked credential display
 * - Dual recipient group management (Forest Officers & Local Villagers)
 * - Template variable calculation (30-char limit) & bilingual message preview
 * - Confirmed Test SMS dispatch modal
 * - Dispatch audit log & history table
 */

const CircuitDigestSmsGateway = (() => {
  let simCount = 2;
  let isSending = false;
  let cachedStatus = {};

  async function init() {
    console.log("[CIRCUITDIGEST-SMS] Initializing CircuitDigest SMS Gateway UI controller...");
    await loadStatus();
    await loadRecipients();
    await loadHistory();
    updatePreview(0);

    // Periodic refresh every 15 seconds
    setInterval(loadStatus, 15000);
    setInterval(loadHistory, 15000);

    const testModal = document.getElementById("circuitdigest-test-modal");
    if (testModal) {
      testModal.addEventListener("click", (e) => {
        if (e.target === testModal) closeTestModal();
      });
    }

    const recipientModal = document.getElementById("circuitdigest-recipient-modal");
    if (recipientModal) {
      recipientModal.addEventListener("click", (e) => {
        if (e.target === recipientModal) closeRecipientModal();
      });
    }
  }

  // Toast notification helper
  function notify(msg, type = "info") {
    if (typeof window.showToast === "function") {
      window.showToast(msg, type);
    } else if (typeof showToast === "function") {
      showToast(msg, type);
    } else {
      console.log(`[CD-SMS] [${type.toUpperCase()}] ${msg}`);
      let container = document.getElementById("toast-container");
      if (!container) {
        container = document.createElement("div");
        container.id = "toast-container";
        container.className = "toast-container";
        document.body.appendChild(container);
      }
      const toast = document.createElement("div");
      toast.className = `toast-item ${type}`;
      toast.innerHTML = `<span>${msg}</span>`;
      container.appendChild(toast);
      setTimeout(() => toast.remove(), 4000);
    }
  }

  // Load Status & Quota
  async function loadStatus() {
    try {
      const res = await fetch("/api/circuitdigest/status");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      cachedStatus = data;

      // Status Badge
      const badge = document.getElementById("cd-status-badge");
      if (badge) {
        if (!data.is_configured) {
          badge.className = "badge";
          badge.style.background = "rgba(239, 68, 68, 0.15)";
          badge.style.color = "#ef4444";
          badge.style.border = "1px solid rgba(239, 68, 68, 0.3)";
          badge.innerHTML = '<i class="fa-solid fa-circle-exclamation"></i> API Key Needed';
        } else {
          badge.className = "badge";
          badge.style.background = "rgba(16, 185, 129, 0.15)";
          badge.style.color = "#10b981";
          badge.style.border = "1px solid rgba(16, 185, 129, 0.3)";
          badge.innerHTML = '<i class="fa-solid fa-cloud-bolt"></i> Cloud Active';
        }
      }

      // Incident state pill
      const statePill = document.getElementById("cd-incident-state");
      if (statePill) {
        if (data.incident_active) {
          statePill.style.color = "#ef4444";
          statePill.style.borderColor = "rgba(239, 68, 68, 0.4)";
          statePill.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> ACTIVE INCIDENT (${data.current_count} ELEPHANTS)`;
        } else {
          statePill.style.color = "#94a3b8";
          statePill.style.borderColor = "rgba(148, 163, 184, 0.2)";
          statePill.innerHTML = '<i class="fa-solid fa-shield"></i> NO ACTIVE INCIDENT';
        }
      }

      // Display masked API Key and settings
      const keyDisplay = document.getElementById("cd-key-display");
      if (keyDisplay) keyDisplay.textContent = data.api_key_masked || "Not configured";

      const templateDisplay = document.getElementById("cd-template-display");
      if (templateDisplay) templateDisplay.textContent = `Template ID: ${data.template_id || 103}`;

      const quotaDisplay = document.getElementById("cd-quota-display");
      if (quotaDisplay) {
        quotaDisplay.textContent = `${data.today_sms_sent || 0} / ${data.max_daily_limit || 50} Today`;
      }

      const totalRecipients = document.getElementById("cd-recipients-count-display");
      if (totalRecipients) {
        totalRecipients.textContent = `${data.active_officers_count || 0} Officers • ${data.active_villagers_count || 0} Villagers`;
      }

      // Sync inputs if not focused
      const locInput = document.getElementById("cd-location-input");
      if (locInput && document.activeElement !== locInput && data.location_name) {
        locInput.value = data.location_name;
      }

      const templateSelect = document.getElementById("cd-template-select");
      if (templateSelect && document.activeElement !== templateSelect && data.template_id) {
        templateSelect.value = String(data.template_id);
      }

      const stateSelect = document.getElementById("cd-state-select");
      if (stateSelect && document.activeElement !== stateSelect && data.state) {
        stateSelect.value = data.state;
      }

      const cooldownSelect = document.getElementById("cd-cooldown-input");
      if (cooldownSelect && document.activeElement !== cooldownSelect && data.cooldown_seconds) {
        cooldownSelect.value = String(data.cooldown_seconds);
      }

      const policySelect = document.getElementById("cd-policy-select");
      if (policySelect && document.activeElement !== policySelect && data.count_change_policy) {
        policySelect.value = data.count_change_policy;
      }

    } catch (e) {
      console.error("[CIRCUITDIGEST-SMS] Error loading status:", e);
    }
  }

  // Load Recipient Lists
  async function loadRecipients() {
    try {
      const res = await fetch("/api/circuitdigest/recipients");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      renderRecipientGroup("officers", data.officers || []);
      renderRecipientGroup("villagers", data.villagers || []);
    } catch (e) {
      console.error("[CIRCUITDIGEST-SMS] Error loading recipients:", e);
    }
  }

  function renderRecipientGroup(group, list) {
    const tbody = document.getElementById(`cd-${group}-table-body`);
    if (!tbody) return;

    if (!list || list.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="4" style="text-align: center; padding: 0.8rem; color: #64748b; font-size: 0.78rem;">
            No ${group} registered yet. Click "+ Add ${group === "officers" ? "Officer" : "Villager"}" to add verified numbers.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = list.map((item) => `
      <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.05); font-size: 0.78rem;">
        <td style="padding: 0.5rem 0.6rem; color: #fff; font-weight: 600;">
          ${escapeHtml(item.name || "Recipient")}
        </td>
        <td style="padding: 0.5rem 0.6rem; font-family: monospace; color: #38bdf8;">
          ${escapeHtml(item.phone_masked || item.phone)}
        </td>
        <td style="padding: 0.5rem 0.6rem;">
          <span style="font-size: 0.7rem; padding: 0.15rem 0.4rem; border-radius: 4px; font-weight: 700; ${
            item.enabled
              ? "background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3);"
              : "background: rgba(100, 116, 139, 0.15); color: #94a3b8; border: 1px solid rgba(100, 116, 139, 0.3);"
          }">
            ${item.enabled ? "Active" : "Muted"}
          </span>
        </td>
        <td style="padding: 0.5rem 0.6rem; text-align: right;">
          <button type="button" class="btn-free-secondary" style="padding: 0.2rem 0.45rem; font-size: 0.7rem; margin-right: 0.3rem;"
            onclick="CircuitDigestSmsGateway.toggleRecipientStatus('${group}', '${item.id}', ${!item.enabled})" title="Toggle Active/Muted">
            <i class="fa-solid fa-power-off"></i>
          </button>
          <button type="button" class="btn-free-secondary" style="padding: 0.2rem 0.45rem; font-size: 0.7rem; color: #ef4444;"
            onclick="CircuitDigestSmsGateway.deleteRecipient('${group}', '${item.id}')" title="Delete Recipient">
            <i class="fa-solid fa-trash"></i>
          </button>
        </td>
      </tr>
    `).join("");
  }

  // Add Recipient Modal
  function openAddRecipientModal(group) {
    const modal = document.getElementById("circuitdigest-recipient-modal");
    const groupInput = document.getElementById("cd-recipient-modal-group");
    const title = document.getElementById("cd-recipient-modal-title");

    if (groupInput) groupInput.value = group;
    if (title) title.textContent = group === "officers" ? "Add Forest Officer" : "Add Local Villager";

    const nameInput = document.getElementById("cd-recipient-name-input");
    const phoneInput = document.getElementById("cd-recipient-phone-input");
    if (nameInput) nameInput.value = "";
    if (phoneInput) phoneInput.value = "";

    if (modal) {
      modal.style.display = "flex";
      modal.style.opacity = "1";
    }
  }

  function closeRecipientModal() {
    const modal = document.getElementById("circuitdigest-recipient-modal");
    if (modal) modal.style.display = "none";
  }

  async function submitAddRecipient() {
    const groupInput = document.getElementById("cd-recipient-modal-group");
    const nameInput = document.getElementById("cd-recipient-name-input");
    const phoneInput = document.getElementById("cd-recipient-phone-input");

    const group = groupInput ? groupInput.value : "officers";
    const name = nameInput ? nameInput.value.trim() : "";
    const phone = phoneInput ? phoneInput.value.trim() : "";

    if (!phone) {
      notify("Please enter a destination phone number.", "warning");
      return;
    }

    try {
      const res = await fetch("/api/circuitdigest/recipients/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ group, name, phone })
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || "Failed to add recipient");
      }
      notify(data.message || "Recipient added successfully!", "success");
      closeRecipientModal();
      await loadRecipients();
      await loadStatus();
    } catch (e) {
      notify(`Error: ${e.message}`, "error");
    }
  }

  async function toggleRecipientStatus(group, recipientId, newStatus) {
    try {
      const res = await fetch("/api/circuitdigest/recipients/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ group, id: recipientId, enabled: newStatus })
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || "Update failed");
      }
      notify("Recipient status updated.", "info");
      await loadRecipients();
      await loadStatus();
    } catch (e) {
      notify(`Error: ${e.message}`, "error");
    }
  }

  async function deleteRecipient(group, recipientId) {
    if (!confirm(`Are you sure you want to remove this recipient from ${group}?`)) return;

    try {
      const res = await fetch("/api/circuitdigest/recipients/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ group, id: recipientId })
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || "Delete failed");
      }
      notify(data.message || "Recipient removed.", "success");
      await loadRecipients();
      await loadStatus();
    } catch (e) {
      notify(`Error: ${e.message}`, "error");
    }
  }

  // Update Dynamic Variable Preview
  async function updatePreview(delta = 0) {
    simCount = Math.max(1, simCount + delta);
    const countDisplay = document.getElementById("cd-sim-count");
    if (countDisplay) countDisplay.textContent = simCount;

    const locInput = document.getElementById("cd-location-input");
    const stateSelect = document.getElementById("cd-state-select");
    const templateSelect = document.getElementById("cd-template-select");

    const location = (locInput ? locInput.value : "") || "Monitoring Zone 1";
    const state = (stateSelect ? stateSelect.value : "") || "tamil_nadu";
    const templateId = parseInt(templateSelect ? templateSelect.value : "103") || 103;

    try {
      const res = await fetch("/api/circuitdigest/preview-message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          count: simCount,
          location: location,
          state: state,
          template_id: templateId,
          group: "officer"
        })
      });
      if (!res.ok) return;
      const data = await res.json();

      // Display CircuitDigest Cloud rendered SMS template
      const previewBox = document.getElementById("cd-message-preview");
      if (previewBox) {
        previewBox.textContent = data.rendered_sms;
      }

      // Display variables var1 and var2 metrics
      const metricsBox = document.getElementById("cd-preview-metrics");
      if (metricsBox) {
        metricsBox.innerHTML = `
          <span><strong>var1 (${data.var1_len}/30):</strong> "${escapeHtml(data.var1)}"</span> &bull; 
          <span><strong>var2 (${data.var2_len}/30):</strong> "${escapeHtml(data.var2)}"</span>
        `;
      }

      // Display full bilingual audit record preview
      const bilingualBox = document.getElementById("cd-bilingual-preview");
      if (bilingualBox) {
        bilingualBox.textContent = data.bilingual_message;
      }

    } catch (e) {
      console.error("[CIRCUITDIGEST-SMS] Preview error:", e);
    }
  }

  // Save Gateway Settings
  async function saveSettings() {
    const locInput = document.getElementById("cd-location-input");
    const templateSelect = document.getElementById("cd-template-select");
    const stateSelect = document.getElementById("cd-state-select");
    const cooldownSelect = document.getElementById("cd-cooldown-input");
    const policySelect = document.getElementById("cd-policy-select");
    const absenceInput = document.getElementById("cd-absence-input");

    const payload = {
      location_name: locInput ? locInput.value.trim() : "Monitoring Zone 1",
      template_id: parseInt(templateSelect ? templateSelect.value : "103") || 103,
      state: stateSelect ? stateSelect.value : "tamil_nadu",
      cooldown_seconds: parseInt(cooldownSelect ? cooldownSelect.value : "300") || 300,
      count_change_policy: policySelect ? policySelect.value : "increase_only",
      absence_reset_seconds: parseInt(absenceInput ? absenceInput.value : "120") || 120
    };

    try {
      const res = await fetch("/api/circuitdigest/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || "Failed to update configuration");
      }
      notify("CircuitDigest Cloud settings saved successfully!", "success");
      await loadStatus();
      updatePreview(0);
    } catch (e) {
      notify(`Error: ${e.message}`, "error");
    }
  }

  // Validate API Key
  async function validateConnection() {
    const btn = document.getElementById("btn-validate-cd");
    const originalText = btn ? btn.innerHTML : "";
    if (btn) {
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Checking...';
      btn.disabled = true;
    }

    try {
      const res = await fetch("/api/circuitdigest/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
      });
      const data = await res.json();

      const resultBox = document.getElementById("cd-validate-result");
      if (resultBox) {
        resultBox.style.display = "block";
        if (data.valid) {
          resultBox.style.background = "rgba(16, 185, 129, 0.15)";
          resultBox.style.borderColor = "rgba(16, 185, 129, 0.3)";
          resultBox.style.color = "#10b981";
          resultBox.innerHTML = `<i class="fa-solid fa-check-circle"></i> <strong>Key Syntax Verified:</strong> ${data.message} (Endpoint: ${data.details.endpoint})`;
        } else {
          resultBox.style.background = "rgba(239, 68, 68, 0.15)";
          resultBox.style.borderColor = "rgba(239, 68, 68, 0.3)";
          resultBox.style.color = "#ef4444";
          resultBox.innerHTML = `<i class="fa-solid fa-circle-exclamation"></i> <strong>Configuration Notice:</strong> ${data.message}`;
        }
      }
    } catch (e) {
      notify(`Connection error: ${e.message}`, "error");
    } finally {
      if (btn) {
        btn.innerHTML = originalText;
        btn.disabled = false;
      }
    }
  }

  // Explicit Test SMS Modal & Execution
  function promptTestModal() {
    const modal = document.getElementById("circuitdigest-test-modal");
    const previewBox = document.getElementById("cd-message-preview");
    const modalPreview = document.getElementById("cd-modal-preview");
    const phoneInput = document.getElementById("cd-modal-phone-input");

    if (modalPreview && previewBox) {
      modalPreview.textContent = previewBox.textContent;
    }

    // Default to first active officer phone if available
    if (phoneInput && !phoneInput.value) {
      phoneInput.placeholder = "e.g. 919876543210 (Must be verified on circuitdigest.cloud)";
    }

    if (modal) {
      modal.style.display = "flex";
      modal.style.opacity = "1";
    }
  }

  function closeTestModal() {
    const modal = document.getElementById("circuitdigest-test-modal");
    if (modal) modal.style.display = "none";
  }

  async function executeTestSms() {
    if (isSending) return;
    const phoneInput = document.getElementById("cd-modal-phone-input");
    const phone = phoneInput ? phoneInput.value.trim() : "";

    const btn = document.getElementById("btn-confirm-cd-send");
    isSending = true;
    if (btn) {
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Dispatched to Gateway...';
      btn.disabled = true;
    }

    try {
      const locInput = document.getElementById("cd-location-input");
      const templateSelect = document.getElementById("cd-template-select");

      const res = await fetch("/api/circuitdigest/send-test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          confirmed: true,
          phone: phone || undefined,
          count: simCount,
          location: locInput ? locInput.value : "Monitoring Zone 1",
          template_id: parseInt(templateSelect ? templateSelect.value : "103") || 103,
          group: "officer"
        })
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || data.message || "Failed to dispatch test SMS");
      }
      notify(data.message || "Test SMS submitted to CircuitDigest Cloud!", "success");
      closeTestModal();
      await loadHistory();
      await loadStatus();
    } catch (e) {
      notify(`Test SMS Error: ${e.message}`, "error");
    } finally {
      isSending = false;
      if (btn) {
        btn.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Authorize & Send';
        btn.disabled = false;
      }
    }
  }

  // Load Dispatch Audit History
  async function loadHistory() {
    try {
      const res = await fetch("/api/circuitdigest/history?limit=30");
      if (!res.ok) return;
      const history = await res.json();
      const tbody = document.getElementById("cd-history-body");
      if (!tbody) return;

      if (!history || history.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="6" style="text-align: center; padding: 1.2rem; color: #64748b;">
              No CircuitDigest SMS dispatches recorded yet.
            </td>
          </tr>
        `;
        return;
      }

      tbody.innerHTML = history.map((item) => {
        let badgeColor = "#10b981";
        let badgeBg = "rgba(16, 185, 129, 0.15)";
        let badgeBorder = "rgba(16, 185, 129, 0.3)";
        let statusText = "DISPATCHED";

        if (!item.success) {
          badgeColor = "#ef4444";
          badgeBg = "rgba(239, 68, 68, 0.15)";
          badgeBorder = "rgba(239, 68, 68, 0.3)";
          statusText = "FAILED";
        }

        const dateStr = item.timestamp ? new Date(item.timestamp).toLocaleTimeString() : "--";

        return `
          <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.05); font-size: 0.76rem;">
            <td style="padding: 0.5rem 0.6rem; color: #94a3b8; font-family: monospace;">
              ${escapeHtml(dateStr)}
            </td>
            <td style="padding: 0.5rem 0.6rem; color: #f59e0b; font-weight: 700;">
              ID: ${escapeHtml(String(item.template_id || 103))}
            </td>
            <td style="padding: 0.5rem 0.6rem; font-family: monospace; color: #38bdf8;">
              ${escapeHtml(item.recipient_masked || item.recipient_mobile || "N/A")}
            </td>
            <td style="padding: 0.5rem 0.6rem; color: #cbd5e1; max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(item.var1 || "")}">
              ${escapeHtml(item.var1 || "-")}
            </td>
            <td style="padding: 0.5rem 0.6rem; color: #cbd5e1; max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(item.var2 || "")}">
              ${escapeHtml(item.var2 || "-")}
            </td>
            <td style="padding: 0.5rem 0.6rem;">
              <span style="display: inline-block; font-size: 0.68rem; font-weight: 700; padding: 0.15rem 0.4rem; border-radius: 4px; background: ${badgeBg}; color: ${badgeColor}; border: 1px solid ${badgeBorder};">
                ${statusText}
              </span>
            </td>
          </tr>
        `;
      }).join("");
    } catch (e) {
      console.error("[CIRCUITDIGEST-SMS] Error loading history:", e);
    }
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  return {
    init,
    loadStatus,
    loadRecipients,
    loadHistory,
    updatePreview,
    saveSettings,
    validateConnection,
    promptTestModal,
    closeTestModal,
    executeTestSms,
    openAddRecipientModal,
    closeRecipientModal,
    submitAddRecipient,
    toggleRecipientStatus,
    deleteRecipient
  };
})();

// Auto-initialize when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  CircuitDigestSmsGateway.init();
});
