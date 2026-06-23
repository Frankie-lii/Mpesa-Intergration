import os
import base64
import httpx
import asyncio
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="M-Pesa STK Push API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Config (loaded from .env) ────────────────────────────────────────────────
CONSUMER_KEY    = os.getenv("MPESA_CONSUMER_KEY", "your_consumer_key")
CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET", "your_consumer_secret")
SHORTCODE       = os.getenv("MPESA_SHORTCODE", "174379")         # sandbox default
PASSKEY         = os.getenv("MPESA_PASSKEY", "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919")  # sandbox default
CALLBACK_URL    = os.getenv("MPESA_CALLBACK_URL", "https://yourdomain.com/mpesa/callback")
SANDBOX         = os.getenv("MPESA_SANDBOX", "true").lower() == "true"

BASE_URL = "https://sandbox.safaricom.co.ke" if SANDBOX else "https://api.safaricom.co.ke"

# In-memory store for transaction results (use a DB in production)
transactions: dict = {}


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


def get_password(timestamp: str) -> str:
    raw = f"{SHORTCODE}{PASSKEY}{timestamp}"
    return base64.b64encode(raw.encode()).decode()


async def get_access_token() -> str:
    credentials = base64.b64encode(f"{CONSUMER_KEY}:{CONSUMER_SECRET}".encode()).decode()
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/oauth/v1/generate?grant_type=client_credentials",
            headers={"Authorization": f"Basic {credentials}"},
            timeout=15,
        )
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Token error: {response.text}")
    return response.json()["access_token"]


def format_phone(phone: str) -> str:
    """Convert 07XXXXXXXX or 7XXXXXXXX to 2547XXXXXXXX"""
    phone = phone.strip().replace(" ", "").replace("+", "")
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    elif phone.startswith("7") or phone.startswith("1"):
        phone = "254" + phone
    return phone


# ── Request / Response models ─────────────────────────────────────────────────

class STKRequest(BaseModel):
    phone: str
    amount: int
    reference: str = "Payment"
    description: str = "M-Pesa Payment"


class STKResponse(BaseModel):
    success: bool
    message: str
    checkout_request_id: str | None = None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/mpesa/stkpush", response_model=STKResponse)
async def stk_push(data: STKRequest):
    """Initiate an STK Push to the customer's phone."""
    phone     = format_phone(data.phone)
    timestamp = get_timestamp()
    password  = get_password(timestamp)
    token     = await get_access_token()

    payload = {
        "BusinessShortCode": SHORTCODE,
        "Password":          password,
        "Timestamp":         timestamp,
        "TransactionType":   "CustomerPayBillOnline",
        "Amount":            data.amount,
        "PartyA":            phone,
        "PartyB":            SHORTCODE,
        "PhoneNumber":       phone,
        "CallBackURL":       CALLBACK_URL,
        "AccountReference":  data.reference[:12],
        "TransactionDesc":   data.description[:13],
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )

    result = resp.json()

    if resp.status_code == 200 and result.get("ResponseCode") == "0":
        checkout_id = result["CheckoutRequestID"]
        transactions[checkout_id] = {"status": "pending", "phone": phone, "amount": data.amount}
        return STKResponse(
            success=True,
            message="STK Push sent. Ask customer to enter PIN.",
            checkout_request_id=checkout_id,
        )
    else:
        error_msg = result.get("errorMessage") or result.get("ResponseDescription") or "Unknown error"
        raise HTTPException(status_code=400, detail=error_msg)


@app.post("/mpesa/callback")
async def mpesa_callback(request: Request):
    """Safaricom posts payment result here after customer enters PIN."""
    body = await request.json()
    print("📲 M-Pesa Callback received:", body)

    try:
        stk = body["Body"]["stkCallback"]
        checkout_id = stk["CheckoutRequestID"]
        result_code = stk["ResultCode"]

        if result_code == 0:
            items = {i["Name"]: i.get("Value") for i in stk["CallbackMetadata"]["Item"]}
            transactions[checkout_id] = {
                "status":  "success",
                "code":    items.get("MpesaReceiptNumber"),
                "amount":  items.get("Amount"),
                "phone":   items.get("PhoneNumber"),
                "date":    items.get("TransactionDate"),
            }
        else:
            transactions[checkout_id] = {
                "status":  "failed",
                "reason":  stk.get("ResultDesc", "Payment cancelled or failed"),
            }
    except Exception as e:
        print("Callback parse error:", e)

    return {"ResultCode": 0, "ResultDesc": "Accepted"}


@app.get("/mpesa/status/{checkout_id}")
async def check_status(checkout_id: str):
    """Frontend polls this to know when payment completes."""
    result = transactions.get(checkout_id)
    if not result:
        return {"status": "pending"}
    return result


@app.get("/health")
async def health():
    return {"status": "ok", "sandbox": SANDBOX, "shortcode": SHORTCODE}


# ── Serve frontend ────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return FileResponse("static/index.html")
