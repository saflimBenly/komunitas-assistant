from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os

app = FastAPI()

# Serve static files
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ewccarqqiqfpnlnjuhzb.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_Vx9ioiVeW9WxvYkzKgCWxA_pmb5arka")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
if not OPENROUTER_KEY:
    raise RuntimeError("OPENROUTER_KEY environment variable not set")

@app.get("/")
async def index():
    return FileResponse("index.html")

@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    message = body.get("message", "")
    
    # Get events from Supabase
    async with httpx.AsyncClient() as client:
        events_resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/event?select=*&limit=5",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        )
        events = events_resp.json()
        event_list = "\n".join([f"- {e['nama']} ({e.get('tanggal', 'TBA')})" for e in events]) or "Belum ada event"
    
    # Call OpenRouter
    async with httpx.AsyncClient() as client:
        ai_resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://komunitas-app.onrender.com",
                "X-Title": "Komunitas Assistant"
            },
            json={
                "model": "nex-agi/nex-n2.5-mini:free",
                "messages": [
                    {
                        "role": "system",
                        "content": f"Kamu adalah asisten komunitas yang ramah. Gunakan bahasa Indonesia.\nEvent tersedia: {event_list}\nFungi: info event, daftar event, cek status.\nJika user mau daftar, minta nama & email lalu simpan via API /api/daftar."
                    },
                    {"role": "user", "content": message}
                ],
                "max_tokens": 500
            }
        )
        ai_data = ai_resp.json()
        reply = ai_data["choices"][0]["message"]["content"]
    
    return JSONResponse({"reply": reply})

@app.get("/api/events")
async def get_events():
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/event?select=*&limit=10",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        )
    return JSONResponse(resp.json())

@app.post("/api/daftar")
async def daftar(request: Request):
    body = await request.json()
    nama = body.get("nama", "")
    email = body.get("email", "")
    event_id = body.get("event_id", "")
    
    async with httpx.AsyncClient() as client:
        # Insert anggota
        anggota_resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/anggota",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"},
            json={"nama": nama, "email": email}
        )
        anggota_data = anggota_resp.json()
        anggota_id = anggota_data[0]["id"] if isinstance(anggota_data, list) else None
        
        # Insert pendaftaran
        if anggota_id and event_id:
            await client.post(
                f"{SUPABASE_URL}/rest/v1/pendaftaran",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"},
                json={"anggota_id": anggota_id, "event_id": event_id}
            )
    
    return JSONResponse({"status": "ok", "message": f"Terima kasih {nama}, pendaftaran berhasil!"})
