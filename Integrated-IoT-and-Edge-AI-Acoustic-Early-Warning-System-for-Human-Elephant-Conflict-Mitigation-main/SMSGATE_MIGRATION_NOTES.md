# SMSGate Migration Analysis & Integration Notes

## 1. Executive Summary
This document analyzes the existing SMS architecture in `android_sms_gateway.py` and outlines the migration to SMS Gateway for Android (`smsgate`, Local Server mode). The goal is to route bilingual alerts through a local Android phone SIM card while preserving recipient groups, multilingual builders, deduplication/cooldown policies, and existing trigger endpoints in `server.py`.

---

## 2. Existing TextBee Implementation vs. SMSGate

| Dimension | Existing TextBee Gateway | Target SMSGate Transport |
| :--- | :--- | :--- |
| **Transport Model** | External Cloud Relay (`https://api.textbee.dev`) | Direct HTTP to Android Phone running SMSGate app (`http://<phone_ip>:8080`) |
| **Authentication** | `x-api-key` header | HTTP Basic Auth (`username`, `password`) |
| **Endpoint Path** | `POST /gateway/send-sms` | `POST /messages` (configurable via `SMSGATE_MESSAGES_PATH`) |
| **Status Polling** | Passive Webhook callbacks | Active status polling via `GET /messages/{id}` and health via `GET /health` |
| **Error Retries** | Ad-hoc in-loop retry (max 2) | Structured `call_with_retries` with exponential backoff on retryable errors only |
| **Configuration** | Stored partly in `android_sms_config.json` | Environment variables only for gateway host and credentials |

---

## 3. Key Integration Points in `android_sms_gateway.py`

1. **Provider Setting & Configuration Validation**:
   - Add `provider` field (`"smsgate"` by default, fallback `"textbee"`).
   - Read SMSGate parameters strictly from environment variables:
     - `SMSGATE_BASE_URL` (must be http/https pointing to private/loopback/CGNAT host or `.local`/`.lan` unless `SMSGATE_ALLOW_PUBLIC_HOST=true`)
     - `SMSGATE_USERNAME`, `SMSGATE_PASSWORD`
     - `SMSGATE_MESSAGES_PATH` (defaults to `/messages`)
     - `SMSGATE_TIMEOUT` (default `8.0`)
     - `SMSGATE_MAX_RETRIES` (default `3`)
     - `SMSGATE_BACKOFF` (default `2.0`)
     - `SMS_TTL_SECONDS` (default `900`)
     - `SMS_PRIORITY` (default `100`)
   - If environment variables are missing, mark status as `"not configured"` gracefully without server crash.

2. **Send Function (`send_sms`)**:
   - Check `self.config.get("provider", "smsgate")`.
   - When `"smsgate"`, instantiate/use `SMSGateClient` from `smsgate_client.py`.
   - Dispatch to one recipient at a time.
   - Use stable idempotency message ID: `f"evt{history_id}-{int(time.time())}"` or recipient-specific UUID across retry attempts.
   - Wrap in `call_with_retries` for transient errors (`GatewayTimeout`, `GatewayServerError`, `GatewayUnavailable`).
   - Abort immediately on `GatewayAuthError` or `GatewayRejected` without retrying.

3. **Status Mapping & History**:
   - Initial dispatch creation: `"submitted"`
   - Gateway returns HTTP 2xx: `"gateway_accepted"` (never record or display as `"delivered"`)
   - Background poller checks `get_status(message_id)`:
     - State `Sent` -> `"sent_to_carrier"`
     - State `Delivered` -> `"delivered"`
     - State `Failed` or `Cancelled` -> `"failed"` with sanitized reason
     - Stuck in `Processed` > 5 minutes -> `"unknown"`

4. **Background Status Poller**:
   - Lightweight daemon thread running every 15 seconds.
   - Inspects recent history records in `"gateway_accepted"` or `"sent_to_carrier"` state within the last 15 minutes.
   - Updates `android_sms_history.json` with carrier progress.

---

## 4. Detection Triggers in `server.py`

1. **Trigger Point 1: Acoustic / Sensor Route (`/api/alerts/process`, lines 2086–2098)**
   - Ingests confirmed elephant detection events from edge nodes.
   - Calls `android_sms_mgr.process_detection_async(...)`.
2. **Trigger Point 2: Camera CSV Watcher / Sync (`_persist_camera_detection_to_supabase`, lines 2281–2309)**
   - Triggered when computer vision logs a verified sighting to `elephant_detection_dataset.csv`.
   - Calls `circuitdigest_mgr.process_detection_async(...)` and `android_sms_mgr.process_detection_async(...)`.

*Note on Double SMS:* Today, both CircuitDigest and Android SMS managers fire for camera detections. This behavior is documented and preserved unchanged per instructions.

---

## 5. Security & Privacy Invariants

- Never write `SMSGATE_PASSWORD` or raw phone numbers into `android_sms_config.json`, history, or API logs.
- Mask all phone numbers in UI and JSON outputs using `mask_phone_number()`.
- Require explicit confirmation for manual test SMS dispatches.
