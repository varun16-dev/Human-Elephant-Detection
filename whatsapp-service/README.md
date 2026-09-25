# Local WhatsApp Notification Service (Baileys)

Local, free WhatsApp notification service for the Elephant Monitoring & Early Warning System.

## Features
- **Node.js + Baileys + Express** running locally on `http://localhost:3001`
- **Zero Paid APIs**: No Twilio, No Evolution API, No subscriptions
- **Single Recipient Lockdown**: Restricted strictly to authorized recipient (`+917094528671`)
- **Web QR Code Pairing**: Scan via `http://localhost:3001/qr` or terminal
- **Persistent Sessions**: Authenticated state is saved in `whatsapp-service/sessions/`
- **Auto-Reconnect**: Automatically reconnects with exponential backoff on network hiccups

## Endpoints
- `GET /health`: Service health check
- `GET /status`: Connection status (`connected: true/false`, linked phone number)
- `GET /qr`: Browser-accessible QR pairing page with instructions
- `POST /send-message`: Dispatch text alert (`{"to": "+917094528671", "message": "..."}`)
- `POST /send-image`: Dispatch detection photo with caption
- `POST /test-whatsapp`: Safe self-test message

## Starting the Service
```bash
cd whatsapp-service
npm install
npm start
```
Then visit `http://localhost:3001/qr` in your browser and link your WhatsApp device.
