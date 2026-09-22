/**
 * Module 2 & 3: Edge-AI Acoustic DSP Engine & ANN Classifier Simulator
 * Integrated IoT and Edge-AI Acoustic Early Warning System
 */

let audioCtx = null;
let animationId = null;

function initAudioDSP() {
  renderMFCCMatrix([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
  startWaveformAnimation('standby');
  updateGauge(0.0, false);
}

function renderMFCCMatrix(coefficients) {
  const container = document.getElementById('mfcc-matrix');
  if (!container) return;
  
  container.innerHTML = '';
  for (let i = 0; i < 12; i++) {
    const val = coefficients[i] !== undefined ? coefficients[i] : 0;
    const intensity = Math.min(Math.max((val + 15) / 30, 0.05), 1);
    
    const cell = document.createElement('div');
    cell.className = 'mfcc-cell';
    cell.style.background = val === 0 ? 'rgba(16, 185, 129, 0.12)' : `rgba(${Math.floor(255 * intensity)}, ${Math.floor(185 * (1 - intensity))}, 128, 0.85)`;
    cell.title = `MFCC-${i+1}: ${val.toFixed(2)}`;
    container.appendChild(cell);
  }
}

function startWaveformAnimation(sampleType) {
  const canvas = document.getElementById('waveform-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  
  // Set resolution
  canvas.width = canvas.offsetWidth || 500;
  canvas.height = canvas.offsetHeight || 180;
  
  let phase = 0;
  
  if (animationId) cancelAnimationFrame(animationId);
  
  function draw() {
    if (canvas.offsetWidth > 0 && canvas.width !== canvas.offsetWidth) {
      canvas.width = canvas.offsetWidth;
    }
    if (canvas.offsetHeight > 0 && canvas.height !== canvas.offsetHeight) {
      canvas.height = canvas.offsetHeight;
    }

    ctx.fillStyle = '#040810';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // Draw Grid Lines
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    ctx.lineWidth = 1;
    for (let x = 0; x < canvas.width; x += 40) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, canvas.height);
      ctx.stroke();
    }
    for (let y = 0; y < canvas.height; y += 30) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(canvas.width, y);
      ctx.stroke();
    }
    
    // Draw Audio Signal Waveform
    ctx.beginPath();
    ctx.lineWidth = 2.5;
    ctx.strokeStyle = (sampleType === 'trumpet' || sampleType === 'rumble') ? '#ef4444' : '#10b981';
    
    const centerY = canvas.height / 2;
    
    for (let x = 0; x < canvas.width; x += 2) {
      let amp = 0;
      if (sampleType === 'trumpet') {
        // High energy trumpet harmonics
        amp = Math.sin((x * 0.04) + phase) * 45 + Math.sin((x * 0.12) + phase * 2) * 20 + (Math.random() - 0.5) * 8;
      } else if (sampleType === 'rumble') {
        // Low frequency infrasonic rumble < 30Hz
        amp = Math.sin((x * 0.015) + phase) * 55 + (Math.random() - 0.5) * 4;
      } else if (sampleType === 'wind') {
        // Broad noise wind
        amp = (Math.random() - 0.5) * 12 + Math.sin((x * 0.005) + phase) * 6;
      } else {
        // Standby quiet single flat line signal
        amp = (Math.random() - 0.5) * 1.2;
      }
      
      const y = centerY + amp;
      if (x === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    
    ctx.stroke();
    phase += 0.15;
    animationId = requestAnimationFrame(draw);
  }
  
  draw();
}

let lastAlertedNodeId = null;

function updateEdgeAIDisplayFromNodes(nodes) {
  const alertNode = nodes.find(n => n.status === 'ALERT');
  const classEl = document.getElementById('ai-detected-class');
  const decisionEl = document.getElementById('ai-decision-text');
  const telemetryStatusEl = document.getElementById('edge-telemetry-status');
  const telemetryBadgeEl = document.getElementById('edge-telemetry-badge');

  if (alertNode) {
    // 1. Threat Detected via Telemetry: Waveform changes to Red Wave Signature
    startWaveformAnimation('trumpet');
    renderMFCCMatrix([14.2, -8.5, 6.2, 12.1, -4.3, 8.7, -2.1, 5.4, -1.8, 4.2, 2.1, -0.9]);
    updateGauge(alertNode.confidence || 96.4, true);

    if (classEl) {
      classEl.textContent = `ELEPHANT DETECTED AT ${alertNode.location.toUpperCase()}: ${alertNode.sound_class || 'Elephant Trumpet'}`;
      classEl.style.color = 'var(--status-danger)';
    }

    if (decisionEl) {
      decisionEl.textContent = `Analysis: Fused Decision = CONFIRMED ELEPHANT DETECTED | Freq Peak = 1450Hz | Target: ${alertNode.name}`;
    }

    if (telemetryStatusEl) {
      telemetryStatusEl.textContent = `CRITICAL THREAT AT ${alertNode.location.toUpperCase()}`;
      telemetryStatusEl.style.color = 'var(--status-danger)';
    }

    if (telemetryBadgeEl) {
      telemetryBadgeEl.textContent = `AUTOMATIC SMS DISPATCHED`;
      telemetryBadgeEl.style.background = 'rgba(239, 68, 68, 0.2)';
      telemetryBadgeEl.style.color = '#ef4444';
    }

    // 2. AUTOMATIC VILLAGE GEOTARGETED SMS DISPATCH (Zero manual click needed)
    if (lastAlertedNodeId !== alertNode.id) {
      lastAlertedNodeId = alertNode.id;
      playSyntheticAudioEffect('trumpet');

      setTimeout(() => {
        alert(`🚨 AUTONOMOUS FIELD ALERT DETECTED!\n\nSensor Node: ${alertNode.name}\nTarget Village: ${alertNode.location}\nAcoustic Signature: ${alertNode.sound_class} (${alertNode.confidence}% Confidence)\n\n📱 AUTOMATIC GEOTARGETED VILLAGE SMS DISPATCHED!\nAlert Message: "CRITICAL WARNING: Elephant acoustic frequency (1450Hz) detected at ${alertNode.location} boundary. Stay indoors & secure farm livestock."\n\nStatus: Sent AUTOMATICALLY to registered residents of ${alertNode.location}.`);
      }, 300);
    }
  } else {
    // Zero Threat: System Standby (Flat Green Line)
    lastAlertedNodeId = null;
    startWaveformAnimation('standby');
    renderMFCCMatrix([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
    updateGauge(0.0, false);

    if (classEl) {
      classEl.textContent = "System Standby - Hardware Interface Ready (No Intrusions)";
      classEl.style.color = "#10b981";
    }

    if (decisionEl) {
      decisionEl.textContent = "Status: Sensor mesh online • Standing by for field acoustic telemetry.";
    }

    if (telemetryStatusEl) {
      telemetryStatusEl.textContent = "Active Monitoring";
      telemetryStatusEl.style.color = "var(--accent-emerald)";
    }

    if (telemetryBadgeEl) {
      telemetryBadgeEl.textContent = "Real-time Field Mesh";
      telemetryBadgeEl.style.background = "rgba(16, 185, 129, 0.15)";
      telemetryBadgeEl.style.color = "var(--accent-emerald)";
    }
  }
}

function testAudioSample(sampleType) {
  fetch('/api/edge-ai/predict', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sample_type: sampleType })
  })
  .then(res => res.json())
  .then(data => {
    // Update ANN Gauge
    updateGauge(data.confidence, data.threat_score > 70);
    
    // Update Class Text
    const classEl = document.getElementById('ai-detected-class');
    const decisionEl = document.getElementById('ai-decision-text');
    
    if (classEl) {
      classEl.textContent = data.class;
      classEl.style.color = data.threat_score > 70 ? 'var(--status-danger)' : 'var(--status-safe)';
    }
    
    if (decisionEl) {
      decisionEl.textContent = `Decision: ${data.fused_decision} | Freq Peak: ${data.frequency_peak_hz}Hz | Energy: ${data.energy_db}`;
    }
    
    // Update Waveform & MFCC
    startWaveformAnimation(sampleType);
    if (data.mfcc) renderMFCCMatrix(data.mfcc);
    
    // Synthesize audio sound effect using Web Audio API
    playSyntheticAudioEffect(sampleType);
  })
  .catch(err => console.error("Edge AI prediction error:", err));
}

function updateGauge(confidence, isThreat) {
  const valEl = document.getElementById('gauge-val');
  const bgEl = document.getElementById('gauge-bg');
  
  if (valEl) valEl.textContent = `${confidence.toFixed(1)}%`;
  
  if (bgEl) {
    const color = isThreat ? 'var(--status-danger)' : 'var(--status-safe)';
    bgEl.style.background = `conic-gradient(${color} 0% ${confidence}%, rgba(255,255,255,0.08) ${confidence}% 100%)`;
    bgEl.style.boxShadow = isThreat ? '0 0 25px rgba(239, 68, 68, 0.4)' : '0 0 20px rgba(16, 185, 129, 0.3)';
  }
}

function playSyntheticAudioEffect(type) {
  try {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    
    const now = audioCtx.currentTime;
    
    if (type === 'trumpet') {
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(320, now);
      osc.frequency.exponentialRampToValueAtTime(840, now + 0.3);
      osc.frequency.exponentialRampToValueAtTime(450, now + 0.6);
      gain.gain.setValueAtTime(0.3, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.7);
      osc.start(now);
      osc.stop(now + 0.7);
    } else if (type === 'rumble') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(28, now);
      gain.gain.setValueAtTime(0.5, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 1.2);
      osc.start(now);
      osc.stop(now + 1.2);
    }
  } catch(e) {
    console.log("Audio play blocked or unavailable", e);
  }
}
