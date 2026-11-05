"""WhatsApp Management & User Onboarding API."""
from typing import Dict, Any, Optional
import httpx
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import HTMLResponse
from backend.app.config import settings
from backend.app.db.repository import repository
from backend.app.security.auth_deps import get_current_user, AuthenticatedUser

router = APIRouter(tags=["WhatsApp & Onboarding"])


class UserOnboardRequest(BaseModel):
    phone_number: str
    email: Optional[str] = None
    display_name: Optional[str] = None


@router.get("/api/whatsapp/status")
async def get_whatsapp_status():
    """Returns current WhatsApp connection state and instance metadata."""
    if settings.MESSAGING_CHANNEL == "mock":
        return {
            "status": "open",
            "instance": settings.EVOLUTION_INSTANCE_NAME,
            "mode": "mock",
            "connected": True
        }

    url = f"{settings.EVOLUTION_BASE_URL.rstrip('/')}/instance/connectionState/{settings.EVOLUTION_INSTANCE_NAME}"
    headers = {"apikey": settings.EVOLUTION_GLOBAL_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                state = data.get("instance", {}).get("state", "disconnected")
                return {
                    "status": state,
                    "instance": settings.EVOLUTION_INSTANCE_NAME,
                    "connected": state == "open",
                    "raw": data
                }
    except Exception as e:
        pass

    return {
        "status": "connecting",
        "instance": settings.EVOLUTION_INSTANCE_NAME,
        "connected": False,
        "detail": "Evolution Go instance reachable or pending QR scan"
    }


@router.get("/api/whatsapp/qr")
async def get_whatsapp_qr(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Returns the pairing QR code for scanning. Protected by admin authentication."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden: Admin privileges required to view WhatsApp pairing QR")

    if settings.MESSAGING_CHANNEL == "mock":
        return {
            "status": "ready",
            "instance": settings.EVOLUTION_INSTANCE_NAME,
            "pairing_code": "FASTAGENT-DEV-MOCK",
            "qr_code_base64": None,
            "message": "Mock channel active: WhatsApp pairing simulated."
        }

    url = f"{settings.EVOLUTION_BASE_URL.rstrip('/')}/instance/connect/{settings.EVOLUTION_INSTANCE_NAME}"
    headers = {"apikey": settings.EVOLUTION_GLOBAL_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                return res.json()
    except Exception as e:
        pass

    return {
        "status": "pending",
        "instance": settings.EVOLUTION_INSTANCE_NAME,
        "message": "Connect your phone via Evolution Go instance or Web Dashboard"
    }


@router.post("/api/users/onboard")
async def onboard_user(req: UserOnboardRequest):
    """Registers a phone number and maps it to a unique user UUID with initial policy settings."""
    phone = req.phone_number.strip().lstrip("+")
    if not phone or not phone.isdigit():
        raise HTTPException(status_code=400, detail="Invalid phone number format.")

    user = await repository.register_user(
        phone=phone,
        email=req.email,
        display_name=req.display_name
    )
    return {
        "status": "registered",
        "message": f"Phone number +{phone} onboarded successfully.",
        "user": user
    }


@router.get("/connect", response_class=HTMLResponse)
async def connect_portal(phone: Optional[str] = Query(default=None)):
    """Mobile-optimized 1-Click Google OAuth onboarding page for WhatsApp users."""
    from backend.app.channels.base import get_user_uuid_from_channel_id

    clean_phone = (phone or "").strip().lstrip("+")
    user_uuid = get_user_uuid_from_channel_id(clean_phone) if clean_phone else "anonymous_user"

    # Ensure user record exists in repository
    if clean_phone and clean_phone.isdigit():
        if not await repository.is_user_registered(clean_phone):
            await repository.register_user(phone=clean_phone)

    auth_url = f"/api/auth/google/url?user_id={user_uuid}&redirect=true"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Connect Google Account | FastAgent</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', -apple-system, sans-serif; }}
    body {{
      background: #090d16;
      color: #f1f5f9;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 24px 16px;
    }}
    .card {{
      background: rgba(15, 23, 42, 0.75);
      backdrop-filter: blur(16px);
      border: 1px solid rgba(51, 65, 85, 0.6);
      border-radius: 20px;
      padding: 36px 28px;
      max-width: 440px;
      width: 100%;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.6);
      text-align: center;
    }}
    .logo-badge {{
      width: 56px;
      height: 56px;
      border-radius: 16px;
      background: linear-gradient(135deg, #6366f1, #a855f7);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 20px;
      box-shadow: 0 10px 25px -5px rgba(99, 102, 241, 0.4);
    }}
    .logo-badge svg {{ width: 28px; height: 28px; fill: white; }}
    h1 {{ font-size: 24px; font-weight: 700; color: #ffffff; letter-spacing: -0.02em; margin-bottom: 8px; }}
    .subtitle {{ font-size: 14px; color: #94a3b8; line-height: 1.5; margin-bottom: 24px; }}
    .phone-tag {{
      display: inline-block;
      background: rgba(99, 102, 241, 0.12);
      border: 1px solid rgba(99, 102, 241, 0.3);
      color: #a5b4fc;
      padding: 4px 12px;
      border-radius: 9999px;
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 24px;
    }}
    .features {{
      text-align: left;
      background: rgba(15, 23, 42, 0.5);
      border: 1px solid rgba(51, 65, 85, 0.4);
      border-radius: 14px;
      padding: 16px;
      margin-bottom: 28px;
    }}
    .feature-item {{
      display: flex;
      align-items: flex-start;
      gap: 12px;
      margin-bottom: 12px;
      font-size: 13px;
      color: #cbd5e1;
      line-height: 1.4;
    }}
    .feature-item:last-child {{ margin-bottom: 0; }}
    .feature-icon {{ color: #10b981; flex-shrink: 0; font-size: 16px; margin-top: 1px; }}
    .google-btn {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      width: 100%;
      background: #ffffff;
      color: #1e293b;
      font-size: 15px;
      font-weight: 600;
      padding: 14px 20px;
      border-radius: 12px;
      text-decoration: none;
      transition: all 0.2s ease;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
    }}
    .google-btn:hover {{
      background: #f8fafc;
      transform: translateY(-1px);
      box-shadow: 0 6px 16px rgba(0, 0, 0, 0.35);
    }}
    .google-btn svg {{ width: 20px; height: 20px; }}
    .footer-note {{
      margin-top: 20px;
      font-size: 12px;
      color: #64748b;
      line-height: 1.5;
    }}
    .security-badge {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      font-size: 11px;
      color: #10b981;
      margin-top: 16px;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo-badge">
      <svg viewBox="0 0 24 24"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
    </div>
    <h1>Connect FastAgent</h1>
    <p class="subtitle">Link your Google Calendar and Gmail to manage your daily schedule directly over WhatsApp.</p>

    {f'<div class="phone-tag">📱 +{clean_phone}</div>' if clean_phone else ''}

    <div class="features">
      <div class="feature-item">
        <span class="feature-icon">✓</span>
        <div><strong>Google Calendar:</strong> Instant scheduling, conflict detection, and morning briefings.</div>
      </div>
      <div class="feature-item">
        <span class="feature-icon">✓</span>
        <div><strong>Gmail:</strong> Smart unread triage and VIP message summaries.</div>
      </div>
      <div class="feature-item">
        <span class="feature-icon">✓</span>
        <div><strong>Safe Confirmations:</strong> Destructive or sending actions always require your WhatsApp approval.</div>
      </div>
    </div>

    <a href="{auth_url}" class="google-btn">
      <svg viewBox="0 0 24 24">
        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
      </svg>
      Sign in with Google
    </a>

    <div class="security-badge">
      🔒 AES-256-GCM Encrypted & Isolated per user
    </div>

    <p class="footer-note">You can revoke FastAgent's access anytime in your Google Security settings.</p>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html_content)


@router.get("/connect/success", response_class=HTMLResponse)
async def connect_success(phone: Optional[str] = Query(default=None), user_id: Optional[str] = Query(default=None)):
    """Success landing page shown to user on mobile after completing Google OAuth."""
    clean_phone = (phone or "").strip().lstrip("+")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Connected Successfully | FastAgent</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', -apple-system, sans-serif; }}
    body {{
      background: #090d16;
      color: #f1f5f9;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 24px 16px;
    }}
    .card {{
      background: rgba(15, 23, 42, 0.8);
      backdrop-filter: blur(16px);
      border: 1px solid rgba(16, 185, 129, 0.4);
      border-radius: 20px;
      padding: 40px 28px;
      max-width: 440px;
      width: 100%;
      box-shadow: 0 25px 50px -12px rgba(16, 185, 129, 0.2);
      text-align: center;
    }}
    .check-circle {{
      width: 64px;
      height: 64px;
      border-radius: 50%;
      background: rgba(16, 185, 129, 0.15);
      border: 2px solid #10b981;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 24px;
    }}
    .check-circle svg {{ width: 32px; height: 32px; stroke: #10b981; fill: none; stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; }}
    h1 {{ font-size: 24px; font-weight: 700; color: #ffffff; letter-spacing: -0.02em; margin-bottom: 8px; }}
    .subtitle {{ font-size: 14px; color: #94a3b8; line-height: 1.6; margin-bottom: 28px; }}
    .wa-btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      width: 100%;
      background: #25D366;
      color: #ffffff;
      font-size: 15px;
      font-weight: 600;
      padding: 14px 20px;
      border-radius: 12px;
      text-decoration: none;
      transition: all 0.2s ease;
      box-shadow: 0 4px 14px rgba(37, 211, 102, 0.35);
    }}
    .wa-btn:hover {{
      background: #20bd5a;
      transform: translateY(-1px);
    }}
    .tip-box {{
      margin-top: 24px;
      background: rgba(30, 41, 59, 0.5);
      border: 1px dashed rgba(71, 85, 105, 0.6);
      border-radius: 12px;
      padding: 14px;
      font-size: 13px;
      color: #cbd5e1;
      text-align: left;
    }}
    .tip-title {{ font-weight: 600; color: #38bdf8; margin-bottom: 4px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="check-circle">
      <svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>
    </div>
    <h1>You're All Set!</h1>
    <p class="subtitle">Your Google Account is now securely linked with FastAgent. Tokens are encrypted with AES-256-GCM.</p>

    <a href="https://wa.me/" class="wa-btn">
      💬 Return to WhatsApp
    </a>

    <div class="tip-box">
      <div class="tip-title">⚡ Try your first message:</div>
      <div>"What meetings do I have tomorrow?" or "Schedule a 30m call with Priya on Monday at 10am"</div>
    </div>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html_content)

