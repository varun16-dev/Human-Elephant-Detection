/**
 * Local Baileys WhatsApp Notification Service
 * Elephant Monitoring System
 * 
 * Provides local, free, standalone WhatsApp messaging over Baileys.
 * Restricts delivery ONLY to authorized recipient (+917094528671).
 */

require('dotenv').config();
const express = require('express');
const cors = require('cors');
const path = require('path');
const fs = require('fs');
const pino = require('pino');
const QRCode = require('qrcode');
const qrcodeTerminal = require('qrcode-terminal');

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  Browsers
} = require('@whiskeysockets/baileys');

const app = express();
app.use(cors());
app.use(express.json({ limit: '20mb' }));
app.use(express.urlencoded({ extended: true, limit: '20mb' }));

const PORT = parseInt(process.env.WHATSAPP_PORT || '3001', 10);
const AUTHORIZED_RECIPIENT = process.env.WHATSAPP_RECIPIENT || '+917094528671';

// Sessions directory for persistent authentication
const SESSIONS_DIR = path.join(__dirname, 'sessions');
if (!fs.existsSync(SESSIONS_DIR)) {
  fs.mkdirSync(SESSIONS_DIR, { recursive: true });
}

// Global state
let sock = null;
let isConnected = false;
let currentQRCode = null;
let currentQRDataUrl = null;
let currentPairingCode = null;
let connectedPhone = null;
let connectionAttempts = 0;
let isInitializing = false;

function cleanPhoneNumber(phone) {
  if (!phone) return '';
  return phone.toString().replace(/[^0-9]/g, '');
}

function isAuthorizedRecipient(targetPhone) {
  const cleanTarget = cleanPhoneNumber(targetPhone);
  const cleanAllowed = cleanPhoneNumber(AUTHORIZED_RECIPIENT);
  return cleanTarget === cleanAllowed;
}

// Initialize Baileys WhatsApp Socket
async function startWhatsAppService() {
  if (isInitializing) return;
  isInitializing = true;
  console.log('[WhatsApp] Starting service...');

  try {
    const { state, saveCreds } = await useMultiFileAuthState(SESSIONS_DIR);
    const { version, isLatest } = await fetchLatestBaileysVersion();
    console.log(`[WhatsApp] Using Baileys version ${version.join('.')} (isLatest: ${isLatest})`);

    sock = makeWASocket({
      version,
      auth: state,
      // Standard Ubuntu/Chrome browser tuple required by WhatsApp Web protocol
      browser: Browsers.ubuntu('Chrome'),
      printQRInTerminal: false,
      logger: pino({ level: 'silent' }),
      syncFullHistory: false,
      markOnlineOnConnect: true,
      connectTimeoutMs: 60000,
      defaultQueryTimeoutMs: 60000
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        currentQRCode = qr;
        try {
          currentQRDataUrl = await QRCode.toDataURL(qr, { margin: 2, scale: 7 });
        } catch (e) {
          console.error('[WhatsApp] Error generating QR data URL:', e.message);
        }

        console.log('\n[WhatsApp] ==========================================');
        console.log('[WhatsApp] WAITING FOR WHATSAPP PAIRING');
        console.log('[WhatsApp] Open http://localhost:' + PORT + '/qr to scan QR or use 8-digit code');
        console.log('[WhatsApp] ==========================================\n');
        
        try {
          qrcodeTerminal.generate(qr, { small: true });
        } catch (te) {}
      }

      if (connection === 'close') {
        isConnected = false;
        connectedPhone = null;
        currentPairingCode = null;
        isInitializing = false;
        const statusCode = lastDisconnect?.error?.output?.statusCode;
        const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
        
        console.log(`[WhatsApp] Connection closed (status: ${statusCode}). Reconnect: ${shouldReconnect}`);

        if (shouldReconnect) {
          connectionAttempts++;
          const delay = Math.min(3000 * connectionAttempts, 12000);
          console.log(`[WhatsApp] Reconnecting in ${delay / 1000}s...`);
          setTimeout(startWhatsAppService, delay);
        } else {
          console.log('[WhatsApp] Device logged out. Clearing sessions and generating fresh QR...');
          try {
            fs.rmSync(SESSIONS_DIR, { recursive: true, force: true });
            fs.mkdirSync(SESSIONS_DIR, { recursive: true });
          } catch (err) {
            console.error('[WhatsApp] Error clearing sessions:', err);
          }
          setTimeout(startWhatsAppService, 3000);
        }
      } else if (connection === 'open') {
        isConnected = true;
        currentQRCode = null;
        currentQRDataUrl = null;
        currentPairingCode = null;
        connectionAttempts = 0;
        isInitializing = false;
        
        const userJid = sock.user?.id || '';
        connectedPhone = userJid.split(':')[0] || userJid.split('@')[0] || 'Unknown';
        
        console.log('\n[WhatsApp] ==========================================');
        console.log('[WhatsApp] WhatsApp Status: CONNECTED');
        console.log(`[WhatsApp] Logged in account: +${connectedPhone}`);
        console.log(`[WhatsApp] Authorized recipient: ${AUTHORIZED_RECIPIENT}`);
        console.log('[WhatsApp] ==========================================\n');
      }
    });

  } catch (error) {
    console.error('[WhatsApp] Initialization error:', error);
    isInitializing = false;
    setTimeout(startWhatsAppService, 5000);
  }
}

// ==============================================================================
// HTTP ENDPOINTS
// ==============================================================================

// 1. Health Endpoint
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    service: 'whatsapp',
    provider: 'baileys'
  });
});

// 2. Status Endpoint
app.get('/status', (req, res) => {
  if (isConnected) {
    res.json({
      connected: true,
      phone: connectedPhone ? `+${connectedPhone}` : undefined,
      provider: 'baileys'
    });
  } else {
    res.json({
      connected: false,
      has_qr: Boolean(currentQRCode),
      provider: 'baileys'
    });
  }
});

// 3. Pairing Code Endpoint (Link with ANY phone number as the sender bot)
app.post('/pairing-code', async (req, res) => {
  try {
    if (isConnected) {
      return res.json({ connected: true, message: 'Already connected!' });
    }

    if (!sock) {
      return res.status(503).json({ error: 'WhatsApp socket is initializing, please retry in 3 seconds.' });
    }

    const targetPhone = req.body?.phone;
    if (!targetPhone) {
      return res.status(400).json({ error: 'Please enter a phone number with country code (e.g. +91XXXXXXXXXX)' });
    }

    let cleanNumber = cleanPhoneNumber(targetPhone);
    // Auto-prefix 91 for standard 10-digit Indian numbers
    if (cleanNumber.length === 10) {
      cleanNumber = '91' + cleanNumber;
    }

    if (cleanNumber.length < 11 || cleanNumber.length > 15) {
      return res.status(400).json({ error: 'Invalid phone number. Please include your country code (e.g. +91XXXXXXXXXX)' });
    }

    console.log(`[WhatsApp] Requesting 8-digit pairing code for sender +${cleanNumber}...`);
    const code = await sock.requestPairingCode(cleanNumber);
    
    // Format as XXXX-XXXX for ease of reading
    const formattedCode = code?.match(/.{1,4}/g)?.join('-') || code;
    currentPairingCode = formattedCode;
    console.log(`[WhatsApp] Pairing Code generated for sender +${cleanNumber}: ${formattedCode}`);

    return res.json({
      success: true,
      code: formattedCode,
      raw_code: code,
      phone: `+${cleanNumber}`
    });
  } catch (error) {
    console.error('[WhatsApp] Error requesting pairing code:', error);
    return res.status(500).json({ error: error.message || 'Failed to generate pairing code' });
  }
});

// 4. QR Code & Pairing Web Display Page
app.get('/qr', (req, res) => {
  if (isConnected) {
    return res.send(`
      <!DOCTYPE html>
      <html>
      <head>
        <title>WhatsApp Connected - Elephant Early Warning System</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
          body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0b132b; color: #fff; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
          .card { background: #1c2541; padding: 2.5rem; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); text-align: center; max-width: 480px; border: 1px solid #3a506b; }
          .badge { background: #10b981; color: #fff; padding: 8px 16px; border-radius: 9999px; font-weight: 700; font-size: 0.95rem; display: inline-block; margin-bottom: 1.5rem; }
          h2 { margin: 0 0 0.5rem 0; color: #e0e1dd; }
          p { color: #a0aec0; font-size: 0.95rem; line-height: 1.5; }
          .info { background: #0f172a; padding: 1.2rem; border-radius: 8px; margin-top: 1.5rem; font-family: monospace; color: #38bdf8; text-align: left; }
          .test-btn { background: #3b82f6; color: #fff; border: none; padding: 12px 24px; border-radius: 8px; font-weight: 600; cursor: pointer; margin-top: 1.5rem; font-size: 1rem; }
          .test-btn:hover { background: #2563eb; }
        </style>
      </head>
      <body>
        <div class="card">
          <div class="badge">WhatsApp Status: CONNECTED</div>
          <h2>System Linked &amp; Ready</h2>
          <p>Your WhatsApp account is active and will receive real-time elephant detection alerts.</p>
          <div class="info">
            <div>Phone: +${connectedPhone || 'Active'}</div>
            <div>Authorized Recipient: ${AUTHORIZED_RECIPIENT}</div>
            <div>Provider: Baileys Local</div>
          </div>
          <div style="background: rgba(59, 130, 246, 0.15); border: 1px solid #3b82f6; border-radius: 8px; padding: 12px; margin-top: 1.2rem; font-size: 0.88rem; text-align: left; color: #93c5fd; line-height: 1.5;">
            <strong>💡 Where to find your messages:</strong><br/>
            • If you linked your own number (+917094528671), open WhatsApp and look in your <strong>"Message yourself" / "You"</strong> chat.<br/>
            • WhatsApp does not ring for self-messages. To get ringing pop-up alerts, link with a secondary/different phone number!
          </div>
          <button class="test-btn" onclick="sendTest()">Send Test WhatsApp Message</button>
          <div id="testResult" style="margin-top: 1rem; font-size: 0.9rem; color: #cbd5e1;"></div>
        </div>
        <script>
          async function sendTest() {
            const el = document.getElementById('testResult');
            el.innerText = 'Sending test message...';
            try {
              const res = await fetch('/test-whatsapp', { method: 'POST' });
              const d = await res.json();
              if (d.success) {
                el.innerText = '✅ Test message sent to ' + d.recipient + '!';
                el.style.color = '#34d399';
              } else {
                el.innerText = '❌ ' + (d.error || 'Failed');
                el.style.color = '#f87171';
              }
            } catch(e) {
              el.innerText = 'Error: ' + e.message;
            }
          }
        </script>
      </body>
      </html>
    `);
  }

  res.send(`
    <!DOCTYPE html>
    <html>
    <head>
      <title>Link WhatsApp - Elephant Early Warning System</title>
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0b132b; color: #fff; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 1.5rem; }
        .card { background: #1c2541; padding: 2rem; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); text-align: center; max-width: 520px; width: 100%; border: 1px solid #3a506b; }
        h2 { margin: 0 0 0.5rem 0; color: #e0e1dd; }
        p.subtitle { color: #a0aec0; font-size: 0.95rem; margin-bottom: 1.5rem; }
        
        .tabs { display: flex; gap: 8px; margin-bottom: 1.5rem; background: #0f172a; padding: 6px; border-radius: 10px; }
        .tab-btn { flex: 1; padding: 10px; background: transparent; color: #94a3b8; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; transition: 0.2s; font-size: 0.95rem; }
        .tab-btn.active { background: #3b82f6; color: #fff; }

        .tab-content { display: none; }
        .tab-content.active { display: block; }

        .qr-box { background: #fff; padding: 1rem; border-radius: 12px; display: inline-block; margin-bottom: 1.2rem; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
        .qr-box img { display: block; width: 250px; height: 250px; }
        
        .code-display { background: #0f172a; border: 2px dashed #3b82f6; padding: 1.2rem; border-radius: 12px; margin: 1.2rem 0; }
        .code-val { font-size: 2.2rem; font-weight: 800; letter-spacing: 4px; color: #38bdf8; font-family: monospace; }
        
        .btn-action { background: #10b981; color: #fff; border: none; padding: 12px 20px; border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 1rem; width: 100%; margin-top: 0.5rem; }
        .btn-action:hover { background: #059669; }

        .steps { text-align: left; background: #0f172a; padding: 1rem 1.25rem; border-radius: 8px; font-size: 0.9rem; color: #cbd5e1; line-height: 1.6; margin-top: 1rem; }
        .steps ol { margin: 0; padding-left: 1.2rem; }
        .badge { background: #3b82f6; color: #fff; padding: 4px 12px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; display: inline-block; margin-bottom: 0.75rem; }
      </style>
      <script>
        // Check connection status every 2 seconds
        setInterval(async () => {
          try {
            const res = await fetch('/status');
            const data = await res.json();
            if (data.connected) {
              window.location.reload();
            }
          } catch(e) {}
        }, 2000);

        function showTab(tab) {
          document.getElementById('tab-qr').classList.toggle('active', tab === 'qr');
          document.getElementById('tab-code').classList.toggle('active', tab === 'code');
          document.getElementById('btn-tab-qr').classList.toggle('active', tab === 'qr');
          document.getElementById('btn-tab-code').classList.toggle('active', tab === 'code');
        }

        async function requestPairingCode() {
          const phoneInput = document.getElementById('senderPhoneInput');
          const phoneVal = phoneInput ? phoneInput.value.trim() : '';
          const disp = document.getElementById('pairingCodeBox');
          const btn = document.getElementById('getCodeBtn');

          if (!phoneVal) {
            disp.innerHTML = '<div style="color: #f87171;">⚠️ Please enter the phone number you want to link (e.g. +91XXXXXXXXXX)</div>';
            return;
          }

          btn.innerText = 'Generating code...';
          btn.disabled = true;
          try {
            const res = await fetch('/pairing-code', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ phone: phoneVal })
            });
            const data = await res.json();
            if (data.success && data.code) {
              disp.innerHTML = '<div class="code-val">' + data.code + '</div><div style="color: #34d399; font-size: 0.9rem; margin-top: 6px; font-weight: 600;">Code for ' + data.phone + '</div><div style="color: #94a3b8; font-size: 0.8rem; margin-top: 4px;">Enter this code on that phone within 2 minutes</div>';
              btn.innerText = 'Request New Code';
            } else {
              disp.innerHTML = '<div style="color: #f87171;">❌ ' + (data.error || 'Failed to generate code') + '</div>';
              btn.innerText = 'Try Again';
            }
          } catch (e) {
            disp.innerHTML = '<div style="color: #f87171;">Error: ' + e.message + '</div>';
            btn.innerText = 'Try Again';
          }
          btn.disabled = false;
        }
      </script>
    </head>
    <body>
      <div class="card">
        <div class="badge">LOCAL BAILEYS WHATSAPP</div>
        <h2>Link Elephant Alert Sender</h2>
        <p class="subtitle">Connect ANY WhatsApp number to act as the alert sender</p>

        <div class="tabs">
          <button id="btn-tab-qr" class="tab-btn active" onclick="showTab('qr')">Option 1: Scan QR Code</button>
          <button id="btn-tab-code" class="tab-btn" onclick="showTab('code')">Option 2: 8-Digit Code</button>
        </div>

        <!-- TAB 1: QR CODE -->
        <div id="tab-qr" class="tab-content active">
          <p style="color: #cbd5e1; font-size: 0.9rem; margin: 0 0 1rem 0;">
            Scan with <strong>ANY phone number</strong> (secondary SIM, friend, family phone).
          </p>
          ${
            currentQRDataUrl
              ? `
              <div class="qr-box">
                <img src="${currentQRDataUrl}" alt="WhatsApp QR Code" />
              </div>
              `
              : `
              <div style="padding: 2.5rem 1rem; color: #94a3b8;">
                Generating fresh QR code... page refreshes automatically.
              </div>
              `
          }
          <div class="steps">
            <ol>
              <li>Open <strong>WhatsApp</strong> on the sender phone</li>
              <li>Tap <strong>Settings</strong> &gt; <strong>Linked Devices</strong></li>
              <li>Tap <strong>Link a Device</strong></li>
              <li>Scan the QR code above</li>
            </ol>
          </div>
        </div>

        <!-- TAB 2: PAIRING CODE -->
        <div id="tab-code" class="tab-content">
          <p style="color: #cbd5e1; font-size: 0.9rem; text-align: left; margin: 0 0 1rem 0;">
            Enter the phone number you want to link as the alert sender (e.g. your second phone, family phone):
          </p>
          
          <div style="text-align: left; margin-bottom: 1rem;">
            <label style="display:block; font-size: 0.85rem; color: #94a3b8; margin-bottom: 6px; font-weight: 600;">Sender Phone Number (with Country Code):</label>
            <input id="senderPhoneInput" type="tel" placeholder="+91XXXXXXXXXX" style="width: 100%; padding: 12px 14px; border-radius: 8px; border: 1px solid #3b82f6; background: #0f172a; color: #fff; font-size: 1.05rem; font-family: monospace; outline: none;" />
          </div>

          <button id="getCodeBtn" class="btn-action" onclick="requestPairingCode()">Get 8-Digit Pairing Code</button>

          <div id="pairingCodeBox" class="code-display" style="margin-top: 1rem;">
            <div style="color: #94a3b8; font-size: 0.9rem;">The 8-digit code will appear here</div>
          </div>

          <div class="steps">
            <ol>
              <li>Open <strong>WhatsApp</strong> on that phone</li>
              <li>Tap <strong>Settings</strong> &gt; <strong>Linked Devices</strong> &gt; <strong>Link a Device</strong></li>
              <li>At the bottom, tap <strong>"Link with phone number instead"</strong></li>
              <li>Type the 8-digit code shown above</li>
            </ol>
          </div>
        </div>

        <div style="margin-top: 1.2rem; font-size: 0.8rem; color: #64748b;">
          Elephant alert notifications are delivered to: <strong style="color: #93c5fd;">${AUTHORIZED_RECIPIENT}</strong>
        </div>

      </div>
    </body>
    </html>
  `);
});

// 5. Send Message Endpoint
app.post('/send-message', async (req, res) => {
  try {
    const { to, message } = req.body;

    if (!to || !message) {
      return res.status(400).json({ error: 'Missing required parameters: to and message' });
    }

    // Recipient restriction check
    if (!isAuthorizedRecipient(to)) {
      console.warn(`[WhatsApp] Rejected unauthorized recipient: ${to} (Authorized: ${AUTHORIZED_RECIPIENT})`);
      return res.status(403).json({
        error: `Unauthorized recipient. Testing mode active: notifications are restricted to ${AUTHORIZED_RECIPIENT}.`
      });
    }

    if (!isConnected || !sock) {
      console.warn('[WhatsApp] Attempted to send message while disconnected');
      return res.status(503).json({
        error: 'WhatsApp is not connected. Scan QR or link code at http://localhost:' + PORT + '/qr'
      });
    }

    const cleanNumber = cleanPhoneNumber(to);
    const jid = `${cleanNumber}@s.whatsapp.net`;

    console.log(`[WhatsApp] Sending message to ${to}...`);
    const sentMsg = await sock.sendMessage(jid, { text: message });
    const messageId = sentMsg?.key?.id || 'sent';

    console.log(`[WhatsApp] Message successfully sent to ${to} (ID: ${messageId})`);
    return res.json({
      success: true,
      recipient: to,
      messageId
    });

  } catch (error) {
    console.error('[WhatsApp] Error sending message:', error);
    return res.status(500).json({ error: error.message || 'Failed to send WhatsApp message' });
  }
});

// 6. Send Image with Caption Endpoint
app.post('/send-image', async (req, res) => {
  try {
    const { to, image_path, caption, image_base64 } = req.body;

    if (!to) {
      return res.status(400).json({ error: 'Missing required parameter: to' });
    }

    // Recipient restriction check
    if (!isAuthorizedRecipient(to)) {
      console.warn(`[WhatsApp] Rejected unauthorized recipient: ${to}`);
      return res.status(403).json({
        error: `Unauthorized recipient. Testing mode active: notifications are restricted to ${AUTHORIZED_RECIPIENT}.`
      });
    }

    if (!isConnected || !sock) {
      return res.status(503).json({
        error: 'WhatsApp is not connected. Scan QR or link code at http://localhost:' + PORT + '/qr'
      });
    }

    const cleanNumber = cleanPhoneNumber(to);
    const jid = `${cleanNumber}@s.whatsapp.net`;

    let imageBuffer = null;

    if (image_base64) {
      const cleanB64 = image_base64.replace(/^data:image\/\w+;base64,/, '');
      imageBuffer = Buffer.from(cleanB64, 'base64');
    } else if (image_path) {
      let resolved = image_path;
      if (!fs.existsSync(resolved)) {
        const altPath = path.resolve(__dirname, '..', 'WelcomeScreen', 'fall_final', 'detected_elephants', path.basename(image_path));
        if (fs.existsSync(altPath)) resolved = altPath;
      }

      if (fs.existsSync(resolved)) {
        imageBuffer = fs.readFileSync(resolved);
      }
    }

    if (imageBuffer) {
      console.log(`[WhatsApp] Sending image with caption to ${to}...`);
      const sentMsg = await sock.sendMessage(jid, {
        image: imageBuffer,
        caption: caption || ''
      });
      const messageId = sentMsg?.key?.id || 'sent';
      console.log(`[WhatsApp] Image message sent to ${to} (ID: ${messageId})`);
      return res.json({
        success: true,
        recipient: to,
        messageId
      });
    } else {
      console.warn('[WhatsApp] Image file could not be read; falling back to text caption');
      const sentMsg = await sock.sendMessage(jid, { text: caption || 'Elephant detected' });
      return res.json({
        success: true,
        recipient: to,
        messageId: sentMsg?.key?.id || 'sent',
        fallback: 'text_only'
      });
    }

  } catch (error) {
    console.error('[WhatsApp] Error sending image:', error);
    return res.status(500).json({ error: error.message || 'Failed to send WhatsApp image' });
  }
});

// 7. Test WhatsApp Endpoint
app.post('/test-whatsapp', async (req, res) => {
  try {
    const testMessage = `🧪 TEST MESSAGE

Hello Varun,

This is a test message from the Elephant Monitoring System.

Your local WhatsApp notification service is working correctly.

— Elephant Monitoring System`;

    if (!isConnected || !sock) {
      return res.status(503).json({
        success: false,
        error: 'WhatsApp is not connected. Please scan QR or link code at http://localhost:' + PORT + '/qr',
        recipient: AUTHORIZED_RECIPIENT
      });
    }

    const cleanNumber = cleanPhoneNumber(AUTHORIZED_RECIPIENT);
    const jid = `${cleanNumber}@s.whatsapp.net`;

    console.log(`[WhatsApp] Sending test message to ${AUTHORIZED_RECIPIENT}...`);
    const sentMsg = await sock.sendMessage(jid, { text: testMessage });
    const messageId = sentMsg?.key?.id || 'sent';

    console.log(`[WhatsApp] Test message sent successfully (ID: ${messageId})`);
    return res.json({
      success: true,
      message: 'Test message sent successfully',
      recipient: AUTHORIZED_RECIPIENT,
      messageId
    });

  } catch (error) {
    console.error('[WhatsApp] Test message failed:', error);
    return res.status(500).json({
      success: false,
      error: error.message || 'Failed to send test message',
      recipient: AUTHORIZED_RECIPIENT
    });
  }
});

// Start Express Listener
app.listen(PORT, '0.0.0.0', () => {
  console.log(`\n==================================================`);
  console.log(`  Local Baileys WhatsApp Service (v2.0)`);
  console.log(`  Running on: http://localhost:${PORT}`);
  console.log(`  Health Check: http://localhost:${PORT}/health`);
  console.log(`  Status Check: http://localhost:${PORT}/status`);
  console.log(`  Pairing Page: http://localhost:${PORT}/qr`);
  console.log(`  Authorized Recipient: ${AUTHORIZED_RECIPIENT}`);
  console.log(`==================================================\n`);
  
  startWhatsAppService();
});
