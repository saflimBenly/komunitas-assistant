from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import httpx
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ewccarqqiqfpnlnjuhzb.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_Vx9ioiVeW9WxvYkzKgCWxA_pmb5arka")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
WA_NUMBER = os.getenv("WA_NUMBER", "85220808253627")

@app.get("/")
async def index():
    return FileResponse("static/index.html")

@app.get("/admin")
async def admin():
    return FileResponse("static/admin.html")

@app.get("/daftar")
async def daftar_page():
    return FileResponse("static/daftar.html")

# === API CHAT ===
@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    message = body.get("message", "")
    
    async with httpx.AsyncClient() as client:
        events_resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/event?select=*&limit=5",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        )
        events = events_resp.json()
        event_list = "\n".join([f"📌 {e['nama']}\n   {e.get('tanggal', 'TBA')} | {e.get('lokasi', 'TBA')}" for e in events]) or "Belum ada event"
    
    async with httpx.AsyncClient() as client:
        ai_resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://komunitas-assistant.onrender.com",
                "X-Title": "Komunitas Assistant"
            },
            json={
                "model": "nex-agi/nex-n2.5-mini:free",
                "messages": [
                    {
                        "role": "system",
                        "content": f"Asisten komunitas ramah. Bahasa Indonesia.\n\nData event tersedia:\n{event_list}\n\nAturan format:\n- Jika menampilkan daftar event, gunakan format singkat per baris:\n  📌 Nama Event\n     Tanggal | Lokasi\n- Jangan tampilkan JSON mentah atau format teknis.\n- Jika user mau daftar, minta nama & email.\n- Jika user tanya jadwal, tampilkan format rapi seperti di atas."
                    },
                    {"role": "user", "content": message}
                ],
                "max_tokens": 500
            }
        )
        ai_data = ai_resp.json()
        reply = ai_data["choices"][0]["message"]["content"]
    
    return JSONResponse({"reply": reply})

# === API EVENTS ===
@app.get("/api/events")
async def get_events():
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/event?select=*&order=created_at.desc",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        )
    return JSONResponse(resp.json())

# === API DAFTAR ===
@app.post("/api/daftar")
async def daftar(request: Request):
    body = await request.json()
    nama = body.get("nama", "")
    email = body.get("email", "")
    no_telepon = body.get("no_telepon", "")
    event_id = body.get("event_id", "")
    
    if not nama or not email or not event_id:
        raise HTTPException(status_code=400, detail="Nama, email, dan event wajib diisi")
    
    async with httpx.AsyncClient() as client:
        # Cek apakah sudah terdaftar
        existing = await client.get(
            f"{SUPABASE_URL}/rest/v1/anggota?email=eq.{email}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        )
        existing_data = existing.json()
        
        if existing_data:
            anggota_id = existing_data[0]["id"]
        else:
            # Insert anggota baru
            anggota_resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/anggota",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"},
                json={"nama": nama, "email": email, "no_telepon": no_telepon}
            )
            anggota_data = anggota_resp.json()
            anggota_id = anggota_data[0]["id"] if isinstance(anggota_data, list) else None
        
        # Insert pendaftaran
        daftar_resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/pendaftaran",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"},
            json={"anggota_id": anggota_id, "event_id": event_id}
        )
        
        # Kirim notifikasi WhatsApp
        await send_wa_notification(nama, email, event_id)
    
    return JSONResponse({"status": "ok", "message": f"Terima kasih {nama}, pendaftaran berhasil!"})

async def send_wa_notification(nama, email, event_id):
    """Kirim notifikasi WhatsApp ke admin"""
    try:
        async with httpx.AsyncClient() as client:
            # Get event name
            event_resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/event?id=eq.{event_id}&select=nama",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
            )
            event_data = event_resp.json()
            event_name = event_data[0]["nama"] if event_data else "Event"
        
        message = f"🔔 Pendaftar Baru!\n\nNama: {nama}\nEmail: {email}\nEvent: {event_name}\n\nCek dashboard admin untuk detail."
        
        # Send via Hermes gateway (local)
        async with httpx.AsyncClient() as client:
            await client.post(
                "http://localhost:9119/api/send",
                json={
                    "platform": "whatsapp",
                    "to": WA_NUMBER,
                    "message": message
                },
                timeout=10
            )
    except Exception as e:
        print(f"WA notification failed: {e}")

# === ADMIN API ===
@app.post("/api/admin/login")
async def admin_login(request: Request):
    body = await request.json()
    password = body.get("password", "")
    
    if password == ADMIN_PASSWORD:
        return JSONResponse({"status": "ok", "token": "admin-session"})
    raise HTTPException(status_code=401, detail="Password salah")

@app.get("/api/admin/stats")
async def admin_stats(request: Request):
    async with httpx.AsyncClient() as client:
        # Total anggota
        anggota_resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/anggota?select=count",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Prefer": "count=exact"}
        )
        total_anggota = int(anggota_resp.headers.get("content-range", "0").split("/")[-1])
        
        # Total pendaftaran
        daftar_resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/pendaftaran?select=count",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Prefer": "count=exact"}
        )
        total_daftar = int(daftar_resp.headers.get("content-range", "0").split("/")[-1])
        
        # Pendaftaran per event
        events_resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/event?select=id,nama",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        )
        events = events_resp.json()
        
        event_stats = []
        for event in events:
            count_resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/pendaftaran?event_id=eq.{event['id']}&select=count",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Prefer": "count=exact"}
            )
            count = int(count_resp.headers.get("content-range", "0").split("/")[-1])
            event_stats.append({"nama": event["nama"], "pendaftar": count})
    
    return JSONResponse({
        "total_anggota": total_anggota,
        "total_pendaftaran": total_daftar,
        "event_stats": event_stats
    })

@app.get("/api/admin/pendaftar")
async def admin_pendaftar(request: Request):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/pendaftaran?select=*,anggota(nama,email,no_telepon),event(nama)&order=created_at.desc",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        )
    return JSONResponse(resp.json())

@app.post("/api/admin/event")
async def add_event(request: Request):
    body = await request.json()
    nama = body.get("nama", "")
    deskripsi = body.get("deskripsi", "")
    tanggal = body.get("tanggal", "")
    lokasi = body.get("lokasi", "")
    kuota = body.get("kuota", 0)
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/event",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"},
            json={"nama": nama, "deskripsi": deskripsi, "tanggal": tanggal, "lokasi": lokasi, "kuota": kuota}
        )
    return JSONResponse(resp.json())

@app.delete("/api/admin/event/{event_id}")
async def delete_event(event_id: str):
    async with httpx.AsyncClient() as client:
        await client.delete(
            f"{SUPABASE_URL}/rest/v1/event?id=eq.{event_id}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        )
    return JSONResponse({"status": "ok"})

@app.put("/api/admin/event/{event_id}")
async def update_event(event_id: str, request: Request):
    body = await request.json()
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{SUPABASE_URL}/rest/v1/event?id=eq.{event_id}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"},
            json=body
        )
    return JSONResponse({"status": "ok"})

app.mount("/static", StaticFiles(directory="static"), name="static")
