# M-Pesa STK Push — Python FastAPI

A complete M-Pesa STK Push integration with a Python backend and HTML/CSS/JS frontend.

---

## Project structure

```
mpesa-integration/
├── main.py            ← FastAPI backend (all M-Pesa logic)
├── .env               ← Your Daraja credentials (never commit this)
├── requirements.txt   ← Python dependencies
├── README.md
└── static/
    └── index.html     ← Frontend UI
```

---

## Setup

### 1. Get Daraja credentials

1. Go to https://developer.safaricom.co.ke
2. Sign up / log in
3. Click **My Apps** → **Create App**
4. Select **Lipa na M-Pesa Sandbox**
5. Copy your **Consumer Key** and **Consumer Secret**

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure .env

Edit `.env` and fill in your credentials:

```env
MPESA_CONSUMER_KEY=your_key_here
MPESA_CONSUMER_SECRET=your_secret_here
MPESA_CALLBACK_URL=https://YOUR_NGROK_URL/mpesa/callback
```

The sandbox `SHORTCODE` and `PASSKEY` are already filled in — they work for testing.

### 4. Expose your server with ngrok (for the callback)

Safaricom needs to reach your server to confirm payment. Use ngrok:

```bash
# Terminal 1 — start ngrok
ngrok http 8000

# Copy the https URL, e.g.: https://abc123.ngrok-free.app
# Paste it into .env as:
# MPESA_CALLBACK_URL=https://abc123.ngrok-free.app/mpesa/callback
```

### 5. Run the server

```bash
# Terminal 2 — start FastAPI
uvicorn main:app --reload --port 8000
```

### 6. Open the app

Visit: http://localhost:8000

---

## How it works

```
Browser → POST /mpesa/stkpush
        → FastAPI gets access token from Safaricom
        → FastAPI sends STK Push request
        → Safaricom sends PIN prompt to customer's phone
        → Customer enters PIN
        → Safaricom POST to /mpesa/callback
        → FastAPI saves result
        → Browser polls GET /mpesa/status/{id}
        → Shows success/failure + receipt
```

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/mpesa/stkpush` | Initiate STK Push |
| `POST` | `/mpesa/callback` | Safaricom webhook (auto-called) |
| `GET`  | `/mpesa/status/{id}` | Poll payment status |
| `GET`  | `/health` | Server health check |
| `GET`  | `/` | Frontend UI |

---

## Test phone numbers (sandbox)

Use these Safaricom sandbox numbers to simulate payments:

| Phone | PIN | Result |
|-------|-----|--------|
| 254708374149 | any | Success |
| 254700000000 | any | Insufficient funds |

---

## Going live (production)

1. Set `MPESA_SANDBOX=false` in `.env`
2. Replace shortcode and passkey with your production values
3. Deploy to a server with a real HTTPS domain (Render, Railway, VPS, etc.)
4. Update `MPESA_CALLBACK_URL` to your production URL
