import os
import sys
import io
import struct
import zlib
import subprocess
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse, Response, FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
import uvicorn

# --- OTOMATİK VERİTABANI SEÇİMİ & KÜTÜPHANE KONTROLÜ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.getenv("DATABASE_URL")
IS_POSTGRES = DATABASE_URL is not None and DATABASE_URL.startswith("postgres")

if IS_POSTGRES:
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "psycopg2-binary"])
        import psycopg2
        from psycopg2.extras import RealDictCursor

    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    import sqlite3

# --- AYARLAR & GÜVENLİK ---
SECRET_KEY = os.getenv("SECRET_KEY", "klinikmatrix-super-secret-jwt-key-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 720
DB_FILE = os.path.join(BASE_DIR, "crm_database.db")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/token")
app = FastAPI(title="Klinik Matrix | Dental CRM & Konfigüratör")


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hash_password(plain_password) == hashed_password


def get_db():
    if IS_POSTGRES:
        return psycopg2.connect(DATABASE_URL)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def execute_query(query: str, params=(), fetch_one=False, fetch_all=False, commit=False):
    conn = get_db()
    try:
        if IS_POSTGRES:
            formatted_query = query.replace("?", "%s")
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            formatted_query = query
            cursor = conn.cursor()

        cursor.execute(formatted_query, params)
        result = None
        if fetch_one:
            row = cursor.fetchone()
            result = dict(row) if row else None
        elif fetch_all:
            rows = cursor.fetchall()
            result = [dict(r) for r in rows]

        if commit:
            conn.commit()
        cursor.close()
        return result
    finally:
        conn.close()


def init_db():
    auto_id = "SERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"

    # Kullanıcılar
    execute_query(f'''CREATE TABLE IF NOT EXISTS users (
        id {auto_id},
        username TEXT UNIQUE,
        password_hash TEXT,
        full_name TEXT,
        role TEXT
    )''', commit=True)

    # Personel
    execute_query(f'''CREATE TABLE IF NOT EXISTS staff (
        id {auto_id},
        name TEXT UNIQUE,
        department TEXT,
        title TEXT
    )''', commit=True)

    # Ürünler
    execute_query(f'''CREATE TABLE IF NOT EXISTS products (
        id {auto_id},
        brand TEXT,
        model TEXT UNIQUE,
        price REAL,
        stock INTEGER
    )''', commit=True)

    # Satışlar
    execute_query(f'''CREATE TABLE IF NOT EXISTS sales (
        id {auto_id},
        date TEXT,
        staff_name TEXT,
        customer_name TEXT,
        customer_location TEXT,
        brand TEXT,
        model TEXT,
        price REAL,
        quantity INTEGER,
        total REAL
    )''', commit=True)

    # Müşteri Görüşmeleri
    execute_query(f'''CREATE TABLE IF NOT EXISTS interactions (
        id {auto_id},
        date TEXT,
        customer_name TEXT,
        devices TEXT,
        notes TEXT,
        "YETKİLİ PERSONEL" TEXT,
        "TEKLİF URL'si" TEXT
    )''', commit=True)

    # Mevcut tablolarda yeni kolonlar eksikse güvenli şekilde ekle
    for col_sql in [
        'ALTER TABLE interactions ADD COLUMN "YETKİLİ PERSONEL" TEXT',
        'ALTER TABLE interactions ADD COLUMN "TEKLİF URL\'si" TEXT',
    ]:
        try:
            execute_query(col_sql, commit=True)
        except Exception:
            pass

    # Güvenlik: Yalnızca hakan / 7659 kullanıcısı aktif olsun
    execute_query("DELETE FROM users WHERE username != ?", ("hakan",), commit=True)
    user = execute_query("SELECT id FROM users WHERE username = ?", ("hakan",), fetch_one=True)
    if not user:
        execute_query(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
            ("hakan", hash_password("7659"), "Hakan Behramoğlu", "Admin"),
            commit=True,
        )
    else:
        execute_query(
            "UPDATE users SET password_hash = ?, full_name = ?, role = ? WHERE username = ?",
            (hash_password("7659"), "Hakan Behramoğlu", "Admin", "hakan"),
            commit=True,
        )

    # Tohum veriler: Personel
    staff_count = execute_query("SELECT COUNT(*) as count FROM staff", fetch_one=True)
    if staff_count and staff_count["count"] == 0:
        seed_staff = [
            ("NEVZAT KİRTİŞ", "KURUMSAL SATIŞ", "KURUMSAL İLİŞKİLER DİREKTÖRÜ"),
            ("SAMET ŞEN", "GENEL SATIŞ", "SATIŞ MÜDÜRÜ"),
            ("HAKAN BEHRAMOĞLU", "SATIŞ VE PAZARLAMA", "İŞ GELİŞTİRME UZMANI"),
            ("SEDAT TUTKA", "SATIŞ", "SATIŞ TEMSİLCİSİ"),
            ("ALİ CAN ÇIPA", "KURUMSAL SATIŞ", "KURUMSAL SATIŞ TEMSİLCİSİ"),
        ]
        for item in seed_staff:
            execute_query(
                "INSERT INTO staff (name, department, title) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                item,
                commit=True,
            )

    # Tohum veriler: Ürünler
    prod_count = execute_query("SELECT COUNT(*) as count FROM products", fetch_one=True)
    if prod_count and prod_count["count"] == 0:
        seed_products = [
            ("STERN WEBER", "S200 ORTHO", 9500.0, 1),
            ("STERN WEBER", "S200 +", 12000.0, 40),
            ("STERN WEBER", "TR 220", 13500.0, 0),
            ("STERN WEBER", "S200 GOLD", 14500.0, 5),
            ("STERN WEBER", "S300", 15500.0, 27),
            ("STERN WEBER", "S 280 TRC", 17500.0, 1),
            ("STERN WEBER", "S 380 TRC", 25000.0, 59),
            ("STERN WEBER", "S 380 TRC GOLD", 45000.0, 1),
            ("STERN WEBER", "SURGICAL CART", 6950.0, 1),
            ("SILVERFOX", "8000 C IMPLANT", 8500.0, 2),
            ("SILVERFOX", "8000 C PRO", 6950.0, 17),
            ("SILVERFOX", "8000 B", 3950.0, 29),
            ("MY RAY", "X9 PRO DC 13x16", 65000.0, 0),
            ("MY RAY", "X9 PRO 10x8", 49500.0, 0),
            ("MY RAY", "X6 PROXIMA - 3D", 39999.0, 4),
            ("MY RAY", "HYPERION X5 - 3D", 34000.0, 1),
            ("MY RAY", "X6 PROXIMA - 2D", 13999.0, 25),
            ("MY RAY", "HYPERION X5 - 2D", 12750.0, 21),
            ("MY RAY", "SEFALOMETRİ SENSÖR ve ATACHMAN", 8500.0, 4),
        ]
        for item in seed_products:
            execute_query(
                "INSERT INTO products (brand, model, price, stock) VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                item,
                commit=True,
            )

    # Tohum veriler: Satışlar
    sales_count = execute_query("SELECT COUNT(*) as count FROM sales", fetch_one=True)
    if sales_count and sales_count["count"] == 0:
        seed_sales = [
            ("2026-08-21", "NEVZAT KİRTİŞ", "İstanbul Üniversitesi Çapa Diş Hekimliği Fakültesi", "İstanbul", "STERN WEBER", "S300", 15500.0, 1, 15500.0),
            ("2026-07-22", "SAMET ŞEN", "Ercan TAŞ", "Tekirdağ", "SILVERFOX", "8000 B", 3950.0, 1, 3950.0),
            ("2026-02-23", "HAKAN BEHRAMOĞLU", "Özel Armineh Ağız ve Diş Sağlığı Polikliniği", "İstanbul", "SILVERFOX", "8000 C PRO", 6950.0, 1, 6950.0),
            ("2026-01-24", "SEDAT TUTKA", "Murat ULUKÖYLÜ", "İstanbul", "MY RAY", "SEFALOMETRİ SENSÖR ve ATACHMAN", 8500.0, 1, 8500.0),
            ("2026-02-25", "ALİ CAN ÇIPA", "Gotham ADSM", "İstanbul", "STERN WEBER", "S200 ORTHO", 9500.0, 2, 19000.0),
            ("2026-08-21", "HAKAN BEHRAMOĞLU", "Ahmet Klinik", "Erzincan", "STERN WEBER", "S 380 TRC", 25000.0, 4, 100000.0),
        ]
        for item in seed_sales:
            execute_query(
                "INSERT INTO sales (date, staff_name, customer_name, customer_location, brand, model, price, quantity, total) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                item,
                commit=True,
            )


init_db()


# --- AUTH YARDIMCILARI ---
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Geçersiz kimlik")
    except JWTError:
        raise HTTPException(status_code=401, detail="Oturum süresi doldu")
    return username


# --- PYDANTIC MODELLERİ ---
class SaleCreate(BaseModel):
    date: str
    staff_name: str
    customer_name: str
    customer_location: str
    brand: str
    model: str
    price: float
    quantity: int


class ProductUpdate(BaseModel):
    price: float
    stock: int


class InteractionCreate(BaseModel):
    date: str
    customer_name: str
    devices: str
    notes: str
    staff_name: Optional[str] = "HAKAN BEHRAMOĞLU"
    offer_url: Optional[str] = ""


class PinLoginRequest(BaseModel):
    pin: str


def _normalize_iso_date(raw_date: Optional[str]) -> str:
    """GG.AA.YYYY veya YYYY-AA-GG formatındaki tarihi PostgreSQL/SQLite uyumlu YYYY-AA-GG formatına çevirir."""
    val = (raw_date or "").strip()
    if not val:
        return datetime.now().strftime("%Y-%m-%d")
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(val, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return datetime.now().strftime("%Y-%m-%d")


# --- İKON & PWA MANIFEST ROTALARI ---
FALLBACK_ICON_SVG = r"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="110" fill="#050811"/>
  <defs>
    <linearGradient id="topF" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#60a5fa"/><stop offset="100%" stop-color="#2563eb"/>
    </linearGradient>
    <linearGradient id="leftF" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0ea5e9"/><stop offset="100%" stop-color="#0369a1"/>
    </linearGradient>
    <linearGradient id="rightF" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1e3a8a"/><stop offset="100%" stop-color="#0f172a"/>
    </linearGradient>
  </defs>
  <polygon points="256,64 432,162 256,260 80,162" fill="url(#topF)" stroke="#93c5fd" stroke-width="5" stroke-linejoin="round"/>
  <polygon points="80,162 256,260 256,448 80,350" fill="url(#leftF)" stroke="#38bdf8" stroke-width="5" stroke-linejoin="round"/>
  <polygon points="256,260 432,162 432,350 256,448" fill="url(#rightF)" stroke="#60a5fa" stroke-width="5" stroke-linejoin="round"/>
  <g transform="translate(256,155)" stroke="#ffffff" stroke-width="10" stroke-linecap="round" stroke-linejoin="round" fill="none">
    <path d="M-55,15 L-12,0 L28,-18 L60,-30"/>
    <path d="M-12,0 L-4,34 L22,28"/>
    <circle cx="48" cy="-42" r="10" fill="#e0f2fe" stroke="none"/>
  </g>
  <g stroke="#bae6fd" stroke-width="8" stroke-linecap="round" fill="none">
    <path d="M115,245 Q155,230 210,265"/>
    <path d="M110,285 Q155,270 215,305"/>
    <path d="M118,325 Q158,312 212,345"/>
  </g>
  <g stroke="#93c5fd" stroke-width="7" stroke-linecap="round" fill="none">
    <line x1="290" y1="275" x2="395" y2="215" stroke-dasharray="10 8"/>
    <line x1="290" y1="325" x2="395" y2="265"/>
    <line x1="290" y1="375" x2="395" y2="315" stroke-dasharray="10 8"/>
    <polygon points="335,280 370,300 370,342 335,322" fill="#38bdf8" fill-opacity="0.35" stroke="#ffffff" stroke-width="5"/>
  </g>
</svg>"""

# --- PWA İÇİN GERÇEK PNG İKON VE EKRAN GÖRÜNTÜSÜ ÜRETİCİ ---
_PNG_CACHE = {}


def _ensure_pillow():
    """Pillow kütüphanesini yükler; kurulu değilse otomatik kurmayı dener."""
    try:
        from PIL import Image, ImageDraw
        return Image, ImageDraw
    except ImportError:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
            from PIL import Image, ImageDraw
            return Image, ImageDraw
        except Exception:
            return None, None


def _pure_python_png(width: int, height: int, rgb=(9, 13, 22), accent=(14, 165, 233)) -> bytes:
    """Pillow kullanılamazsa sıfır bağımlılıkla geçerli PNG üretir."""
    raw = bytearray()
    cx, cy = width // 2, height // 2
    r_outer = min(width, height) // 3
    for y in range(height):
        raw.append(0)
        for x in range(width):
            if abs(x - cx) + abs(y - cy) < r_outer:
                raw.extend(accent)
            else:
                raw.extend(rgb)

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack("!I", len(data)) + tag + data + struct.pack("!I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw), 6)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def _build_png_icon(size: int) -> bytes:
    """icon.jpg / icon.png dosyasını tam size x size PNG olarak dönüştürür veya vektörel PNG çizer."""
    cache_key = f"icon_{size}"
    if cache_key in _PNG_CACHE:
        return _PNG_CACHE[cache_key]

    Image, ImageDraw = _ensure_pillow()
    if Image is not None:
        try:
            for fname in ("icon.jpg", "icon.png"):
                fpath = os.path.join(BASE_DIR, fname)
                if os.path.exists(fpath):
                    with Image.open(fpath) as im:
                        im = im.convert("RGBA").resize((size, size), Image.LANCZOS)
                        buf = io.BytesIO()
                        im.save(buf, format="PNG", optimize=True)
                        _PNG_CACHE[cache_key] = buf.getvalue()
                        return _PNG_CACHE[cache_key]

            # Dosya yoksa Klinik Matrix 3D küp ikonunu PNG olarak çiz
            img = Image.new("RGBA", (size, size), (9, 13, 22, 255))
            draw = ImageDraw.Draw(img)
            s = size / 512.0
            draw.polygon([(256*s, 64*s), (432*s, 162*s), (256*s, 260*s), (80*s, 162*s)], fill=(56, 189, 248, 255))
            draw.polygon([(80*s, 162*s), (256*s, 260*s), (256*s, 448*s), (80*s, 350*s)], fill=(2, 132, 199, 255))
            draw.polygon([(256*s, 260*s), (432*s, 162*s), (432*s, 350*s), (256*s, 448*s)], fill=(30, 58, 138, 255))
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            _PNG_CACHE[cache_key] = buf.getvalue()
            return _PNG_CACHE[cache_key]
        except Exception:
            pass

    _PNG_CACHE[cache_key] = _pure_python_png(size, size)
    return _PNG_CACHE[cache_key]


def _build_screenshot_png(width: int, height: int) -> bytes:
    """PWABuilder mağaza önizlemesi için geçerli ekran görüntüsü PNG üretir."""
    cache_key = f"shot_{width}x{height}"
    if cache_key in _PNG_CACHE:
        return _PNG_CACHE[cache_key]

    Image, ImageDraw = _ensure_pillow()
    if Image is not None:
        try:
            img = Image.new("RGB", (width, height), (9, 13, 22))
            draw = ImageDraw.Draw(img)
            # Üst başlık barı
            draw.rectangle([0, 0, width, 72], fill=(15, 23, 42))
            draw.rectangle([0, 72, width, 75], fill=(14, 165, 233))
            # KPI kartları
            pad = 24
            cols = 2 if width < 800 else 4
            card_w = (width - pad * (cols + 1)) // cols
            for i in range(cols):
                x0 = pad + i * (card_w + pad)
                draw.rounded_rectangle([x0, 100, x0 + card_w, 210], radius=16, fill=(17, 24, 39), outline=(56, 189, 248))
            # İçerik paneli
            draw.rounded_rectangle([pad, 235, width - pad, height - pad], radius=20, fill=(17, 24, 39), outline=(30, 41, 59))
            # Merkeze uygulama ikonunu yerleştir
            icon_size = 160 if width < 800 else 192
            icon_bytes = _build_png_icon(icon_size)
            with Image.open(io.BytesIO(icon_bytes)) as ic:
                ic = ic.convert("RGBA")
                ix = (width - icon_size) // 2
                iy = 235 + ((height - pad - 235) - icon_size) // 2
                img.paste(ic, (ix, iy), ic)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            _PNG_CACHE[cache_key] = buf.getvalue()
            return _PNG_CACHE[cache_key]
        except Exception:
            pass

    _PNG_CACHE[cache_key] = _pure_python_png(width, height)
    return _PNG_CACHE[cache_key]


@app.get("/icon-192.png")
def get_icon_192():
    return Response(content=_build_png_icon(192), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/icon-512.png")
def get_icon_512():
    return Response(content=_build_png_icon(512), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/screenshot-mobile.png")
def get_screenshot_mobile():
    return Response(content=_build_screenshot_png(540, 720), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/screenshot-desktop.png")
def get_screenshot_desktop():
    return Response(content=_build_screenshot_png(1280, 720), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/icon.jpg")
@app.get("/icon.png")
@app.get("/icon.svg")
def get_app_icon():
    for fname, media in [("icon.jpg", "image/jpeg"), ("icon.png", "image/png")]:
        fpath = os.path.join(BASE_DIR, fname)
        if os.path.exists(fpath):
            return FileResponse(fpath, media_type=media)
    return Response(content=FALLBACK_ICON_SVG, media_type="image/svg+xml")


@app.get("/manifest.json")
def get_manifest():
    return {
        "id": "/",
        "name": "Klinik Matrix CRM & Konfigüratör",
        "short_name": "Klinik Matrix",
        "description": "Dental Satış, Stok, Müşteri Görüşmeleri ve İZDO 2026 Teklif Yönetim Portalı",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#090D16",
        "theme_color": "#090D16",
        "categories": ["business", "medical", "productivity"],
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "screenshots": [
            {
                "src": "/screenshot-mobile.png",
                "sizes": "540x720",
                "type": "image/png",
                "form_factor": "narrow",
                "label": "Klinik Matrix Mobil Görünüm",
            },
            {
                "src": "/screenshot-desktop.png",
                "sizes": "1280x720",
                "type": "image/png",
                "form_factor": "wide",
                "label": "Klinik Matrix Masaüstü Paneli",
            },
        ],
    }


@app.get("/sw.js")
def get_service_worker():
    sw_code = """
const CACHE_NAME = 'klinik-matrix-v1';

self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;
    event.respondWith(
        fetch(event.request).catch(() => caches.match(event.request))
    );
});
"""
    return Response(
        content=sw_code,
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


# --- API ENDPOINT'LERİ ---
@app.post("/api/token")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = execute_query("SELECT * FROM users WHERE username = ?", (form_data.username.strip().lower(),), fetch_one=True)
    if not user or not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Hatalı kullanıcı adı veya şifre")
    access_token = create_access_token(data={"sub": user["username"], "name": user["full_name"]})
    return {"access_token": access_token, "token_type": "bearer", "full_name": user["full_name"]}


@app.post("/api/pin-login")
def pin_login(payload: PinLoginRequest):
    """Konfigüratör PIN ekranından girildiğinde de geçerli CRM oturum token'ı üretir."""
    user = execute_query("SELECT * FROM users WHERE username = ?", ("hakan",), fetch_one=True)
    if not user or not verify_password(payload.pin.strip(), user["password_hash"]):
        raise HTTPException(status_code=400, detail="Hatalı PIN kodu")
    access_token = create_access_token(data={"sub": user["username"], "name": user["full_name"]})
    return {"access_token": access_token, "token_type": "bearer", "full_name": user["full_name"]}


@app.get("/api/me")
def get_me(username: str = Depends(get_current_user)):
    user = execute_query("SELECT username, full_name, role FROM users WHERE username = ?", (username,), fetch_one=True)
    if not user:
        raise HTTPException(status_code=401, detail="Kullanıcı bulunamadı")
    return user


@app.get("/api/dashboard")
def get_dashboard(_: str = Depends(get_current_user)):
    kpi = execute_query("SELECT SUM(total) as rev, SUM(quantity) as qty, COUNT(id) as cnt FROM sales", fetch_one=True)
    stock_kpi = execute_query("SELECT SUM(stock) as total_stock, COUNT(id) as total_sku FROM products", fetch_one=True)
    staff_sales = execute_query("SELECT staff_name, SUM(total) as revenue FROM sales GROUP BY staff_name ORDER BY revenue DESC", fetch_all=True)
    brand_sales = execute_query("SELECT brand, SUM(total) as revenue FROM sales GROUP BY brand ORDER BY revenue DESC", fetch_all=True)

    return {
        "kpis": {
            "total_revenue": (kpi["rev"] if kpi and kpi["rev"] else 0.0),
            "total_units": (kpi["qty"] if kpi and kpi["qty"] else 0),
            "total_sales_count": (kpi["cnt"] if kpi and kpi["cnt"] else 0),
            "total_stock": (stock_kpi["total_stock"] if stock_kpi and stock_kpi["total_stock"] else 0),
            "total_sku": (stock_kpi["total_sku"] if stock_kpi and stock_kpi["total_sku"] else 0),
        },
        "charts": {"staff_sales": staff_sales or [], "brand_sales": brand_sales or []},
    }


@app.get("/api/products")
def get_products(_: str = Depends(get_current_user)):
    return execute_query("SELECT * FROM products ORDER BY brand, model", fetch_all=True)


@app.put("/api/products/{product_id}")
def update_product(product_id: int, item: ProductUpdate, _: str = Depends(get_current_user)):
    execute_query("UPDATE products SET price = ?, stock = ? WHERE id = ?", (item.price, item.stock, product_id), commit=True)
    return {"status": "ok"}


@app.get("/api/sales")
def get_sales(_: str = Depends(get_current_user)):
    return execute_query("SELECT * FROM sales ORDER BY date DESC, id DESC", fetch_all=True)


@app.post("/api/sales")
def add_sale(sale: SaleCreate, _: str = Depends(get_current_user)):
    total = round(sale.price * sale.quantity, 2)
    execute_query(
        """INSERT INTO sales
        (date, staff_name, customer_name, customer_location, brand, model, price, quantity, total)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (sale.date, sale.staff_name, sale.customer_name, sale.customer_location, sale.brand, sale.model, sale.price, sale.quantity, total),
        commit=True,
    )
    if IS_POSTGRES:
        execute_query("UPDATE products SET stock = GREATEST(0, stock - ?) WHERE model = ?", (sale.quantity, sale.model), commit=True)
    else:
        execute_query("UPDATE products SET stock = MAX(0, stock - ?) WHERE model = ?", (sale.quantity, sale.model), commit=True)
    return {"status": "ok"}


@app.delete("/api/sales/{sale_id}")
def delete_sale(sale_id: int, _: str = Depends(get_current_user)):
    execute_query("DELETE FROM sales WHERE id = ?", (sale_id,), commit=True)
    return {"status": "ok"}


@app.get("/api/staff")
def get_staff(_: str = Depends(get_current_user)):
    return execute_query("SELECT * FROM staff ORDER BY name", fetch_all=True)


@app.get("/api/interactions")
def get_interactions(_: str = Depends(get_current_user)):
    rows = execute_query("SELECT * FROM interactions ORDER BY id DESC", fetch_all=True)
    normalized = []
    for r in rows:
        normalized.append({
            "id": r.get("id"),
            "date": str(r.get("date") or ""),
            "customer_name": r.get("customer_name") or "",
            "devices": r.get("devices") or "",
            "notes": r.get("notes") or "",
            "staff_name": r.get("YETKİLİ PERSONEL") or r.get("staff_name") or "",
            "offer_url": r.get("TEKLİF URL'si") or r.get("offer_url") or "",
        })
    return normalized


@app.post("/api/interactions")
def add_interaction(item: InteractionCreate, _: str = Depends(get_current_user)):
    clean_date = _normalize_iso_date(item.date)
    clean_customer = (item.customer_name or "").strip()
    clean_devices = (item.devices or "").strip()
    clean_notes = (item.notes or "").strip()
    clean_staff = (item.staff_name or "HAKAN BEHRAMOĞLU").strip()
    clean_url = (item.offer_url or "").strip()

    if not clean_customer:
        raise HTTPException(status_code=400, detail="Müşteri / Doktor adı boş olamaz")

    execute_query(
        'INSERT INTO interactions (date, customer_name, devices, notes, "YETKİLİ PERSONEL", "TEKLİF URL\'si") VALUES (?, ?, ?, ?, ?, ?)',
        (clean_date, clean_customer, clean_devices, clean_notes, clean_staff, clean_url),
        commit=True,
    )
    return {"status": "ok"}


@app.delete("/api/interactions/{interaction_id}")
def delete_interaction(interaction_id: int, _: str = Depends(get_current_user)):
    execute_query("DELETE FROM interactions WHERE id = ?", (interaction_id,), commit=True)
    return {"status": "ok"}


# --- ANA CRM ARAYÜZÜ (MASAÜSTÜ + MOBİL + PWA) ---
@app.get("/", response_class=HTMLResponse)
def index():
    return r"""<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="theme-color" content="#0f172a">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="Klinik Matrix">
    <link rel="manifest" href="/manifest.json">
    <link rel="icon" type="image/png" sizes="192x192" href="/icon-192.png">
    <link rel="apple-touch-icon" sizes="512x512" href="/icon-512.png">
    <title>Klinik Matrix | Dental Satış & CRM Portalı</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        .sidebar-active { background-color: #1e293b; border-left: 4px solid #3b82f6; color: #ffffff !important; }
        .mobile-nav-active { color: #38bdf8 !important; }
        body { -webkit-tap-highlight-color: transparent; }
    </style>
</head>
<body class="bg-slate-50 text-slate-900 min-h-screen flex flex-col font-sans">

    <!-- LOGIN EKRANI -->
    <div id="login-modal" class="fixed inset-0 bg-slate-950/90 backdrop-blur-md z-50 flex items-center justify-center p-4">
        <div class="bg-white p-7 sm:p-8 rounded-3xl shadow-2xl w-full max-w-md border border-slate-100">
            <div class="text-center mb-6">
                <img src="/icon.jpg" alt="Klinik Matrix" class="w-20 h-20 mx-auto rounded-2xl shadow-lg object-cover border border-slate-200 mb-3 bg-slate-950">
                <h2 class="text-2xl font-extrabold tracking-tight text-slate-900">Klinik Matrix</h2>
                <p class="text-xs text-slate-500 mt-1">Yetkili kullanıcı girişi yapın</p>
            </div>
            <div id="login-error" class="hidden mb-4 p-3 bg-rose-50 border border-rose-200 text-rose-600 text-xs rounded-xl font-medium"></div>
            <form id="login-form" onsubmit="handleLogin(event)" autocomplete="off" class="space-y-4">
                <div>
                    <label class="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">Kullanıcı Adı</label>
                    <input type="text" id="username" required placeholder="Kullanıcı adınız" class="w-full px-4 py-3 rounded-xl border border-slate-300 focus:ring-2 focus:ring-blue-500 focus:outline-none text-sm">
                </div>
                <div>
                    <label class="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">Şifre</label>
                    <input type="password" id="password" required placeholder="••••" class="w-full px-4 py-3 rounded-xl border border-slate-300 focus:ring-2 focus:ring-blue-500 focus:outline-none text-sm">
                </div>
                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl text-sm shadow-lg shadow-blue-600/25 transition">Giriş Yap</button>
            </form>
        </div>
    </div>

    <!-- ANA UYGULAMA -->
    <div id="app" class="flex-1 flex flex-col md:flex-row hidden min-h-screen">

        <!-- MOBİL ÜST BAR -->
        <header class="md:hidden sticky top-0 z-30 bg-slate-900 text-white px-4 py-3 flex items-center justify-between shadow-md">
            <div class="flex items-center gap-2.5">
                <img src="/icon.jpg" alt="Klinik Matrix" class="w-9 h-9 rounded-xl object-cover bg-slate-950 border border-slate-700">
                <div>
                    <div class="font-bold text-sm leading-tight">Klinik Matrix</div>
                    <div class="text-[10px] text-sky-400 font-medium">Dental CRM & Stüdyo</div>
                </div>
            </div>
            <button onclick="logout()" class="px-3 py-1.5 bg-red-950/60 text-red-300 border border-red-800/50 rounded-lg text-xs font-semibold">
                <i class="fa-solid fa-right-from-bracket"></i> Çıkış
            </button>
        </header>

        <!-- MASAÜSTÜ SOL MENÜ -->
        <aside class="hidden md:flex w-64 bg-slate-900 text-slate-300 flex-col justify-between flex-shrink-0 sticky top-0 h-screen">
            <div>
                <div class="px-5 py-5 border-b border-slate-800 flex items-center gap-3">
                    <img src="/icon.jpg" alt="Klinik Matrix" class="w-11 h-11 rounded-xl object-cover bg-slate-950 border border-slate-700 shadow">
                    <div>
                        <div class="font-extrabold text-white text-base leading-tight">Klinik Matrix</div>
                        <div class="text-[11px] text-sky-400 font-medium">Dental CRM & Stüdyo</div>
                    </div>
                </div>
                <nav class="p-3.5 space-y-1 text-sm font-medium">
                    <button onclick="switchTab('dashboard')" id="nav-dashboard" class="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-slate-800 sidebar-active transition">
                        <i class="fa-solid fa-chart-pie w-5 text-blue-400"></i> Gösterge Paneli
                    </button>
                    <button onclick="switchTab('sales')" id="nav-sales" class="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-slate-800 hover:text-white transition">
                        <i class="fa-solid fa-receipt w-5 text-emerald-400"></i> Satışlar
                    </button>
                    <button onclick="switchTab('products')" id="nav-products" class="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-slate-800 hover:text-white transition">
                        <i class="fa-solid fa-boxes-stacked w-5 text-amber-400"></i> Ürünler & Stok
                    </button>
                    <button onclick="switchTab('interactions')" id="nav-interactions" class="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-slate-800 hover:text-white transition">
                        <i class="fa-solid fa-comments w-5 text-purple-400"></i> Görüşmeler
                    </button>
                    <button onclick="switchTab('configurator')" id="nav-configurator" class="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-slate-800 hover:text-white transition">
                        <i class="fa-solid fa-wand-magic-sparkles w-5 text-cyan-400"></i> Konfigüratör & Teklif
                    </button>
                    <button onclick="switchTab('staff')" id="nav-staff" class="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-slate-800 hover:text-white transition">
                        <i class="fa-solid fa-id-card-clip w-5 text-sky-400"></i> Ekip / Personel
                    </button>
                </nav>
            </div>
            <div class="p-4 border-t border-slate-800 text-xs">
                <div class="flex items-center justify-between mb-3 px-2">
                    <span id="user-display" class="font-semibold text-slate-200">Hakan Behramoğlu</span>
                    <span class="bg-blue-900/60 text-blue-300 px-2 py-0.5 rounded text-[10px] font-bold uppercase">Admin</span>
                </div>
                <button onclick="logout()" class="w-full py-2.5 px-3 bg-red-950/40 hover:bg-red-900/60 text-red-300 border border-red-900/50 rounded-xl flex items-center justify-center gap-2 transition font-semibold">
                    <i class="fa-solid fa-right-from-bracket"></i> Çıkış Yap
                </button>
            </div>
        </aside>

        <!-- ANA İÇERİK -->
        <main class="flex-1 p-4 md:p-7 pb-24 md:pb-8 overflow-y-auto">

            <!-- DASHBOARD -->
            <div id="section-dashboard" class="space-y-6">
                <div class="flex items-center justify-between">
                    <div>
                        <h1 class="text-xl md:text-2xl font-extrabold text-slate-800">Genel Durum Paneli</h1>
                        <p class="text-xs text-slate-500">Klinik Matrix canlı satış ve stok özeti</p>
                    </div>
                    <span class="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 px-3 py-1.5 rounded-xl font-semibold">
                        <i class="fa-solid fa-circle text-[8px] mr-1"></i> Bulut Aktif
                    </span>
                </div>

                <div class="grid grid-cols-2 lg:grid-cols-4 gap-3.5 md:gap-5">
                    <div class="bg-white p-4 md:p-5 rounded-2xl shadow-sm border border-slate-200/80">
                        <span class="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Toplam Ciro</span>
                        <div class="text-lg md:text-2xl font-extrabold text-slate-800 mt-1.5" id="kpi-revenue">€ 0,00</div>
                        <div class="text-[11px] text-emerald-600 mt-1 font-medium"><i class="fa-solid fa-arrow-trend-up"></i> Güncel ciro</div>
                    </div>
                    <div class="bg-white p-4 md:p-5 rounded-2xl shadow-sm border border-slate-200/80">
                        <span class="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Satılan Cihaz</span>
                        <div class="text-lg md:text-2xl font-extrabold text-slate-800 mt-1.5" id="kpi-units">0</div>
                        <div class="text-[11px] text-slate-500 mt-1 font-medium">İşlem: <span id="kpi-count">0</span></div>
                    </div>
                    <div class="bg-white p-4 md:p-5 rounded-2xl shadow-sm border border-slate-200/80">
                        <span class="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Depo Stoğu</span>
                        <div class="text-lg md:text-2xl font-extrabold text-amber-600 mt-1.5" id="kpi-stock">0</div>
                        <div class="text-[11px] text-slate-500 mt-1 font-medium"><span id="kpi-sku">0</span> model</div>
                    </div>
                    <div class="bg-white p-4 md:p-5 rounded-2xl shadow-sm border border-slate-200/80">
                        <span class="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Satış Ekibi</span>
                        <div class="text-lg md:text-2xl font-extrabold text-blue-600 mt-1.5" id="kpi-staff">5</div>
                        <div class="text-[11px] text-slate-500 mt-1 font-medium">Aktif personel</div>
                    </div>
                </div>

                <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
                    <div class="bg-white p-5 rounded-2xl shadow-sm border border-slate-200/80">
                        <h3 class="font-bold text-slate-800 mb-4 text-sm">Personele Göre Ciro Dağılımı (€)</h3>
                        <canvas id="staffChart" height="220"></canvas>
                    </div>
                    <div class="bg-white p-5 rounded-2xl shadow-sm border border-slate-200/80">
                        <h3 class="font-bold text-slate-800 mb-4 text-sm">Markalara Göre Satış Hacmi (€)</h3>
                        <canvas id="brandChart" height="220"></canvas>
                    </div>
                </div>
            </div>

            <!-- SATIŞLAR -->
            <div id="section-sales" class="hidden space-y-5">
                <div class="flex items-center justify-between gap-2">
                    <div>
                        <h1 class="text-xl md:text-2xl font-extrabold text-slate-800">Gerçekleşen Satışlar</h1>
                        <p class="text-xs text-slate-500 mt-0.5">Tüm faturalı satış kayıtları</p>
                    </div>
                    <button onclick="toggleModal('modal-add-sale')" class="bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold px-4 py-2.5 rounded-xl shadow transition flex items-center gap-2 shrink-0">
                        <i class="fa-solid fa-plus"></i> Yeni Satış
                    </button>
                </div>

                <div class="hidden md:block bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-x-auto">
                    <table class="w-full text-left text-xs">
                        <thead class="bg-slate-50 text-slate-500 font-semibold border-b uppercase text-[10px]">
                            <tr>
                                <th class="p-4">Tarih</th>
                                <th class="p-4">Yetkili</th>
                                <th class="p-4">Müşteri / Kurum</th>
                                <th class="p-4">Konum</th>
                                <th class="p-4">Cihaz & Model</th>
                                <th class="p-4">Birim Fiyat</th>
                                <th class="p-4">Adet</th>
                                <th class="p-4">Toplam</th>
                                <th class="p-4 text-center">Sil</th>
                            </tr>
                        </thead>
                        <tbody id="sales-table-body" class="divide-y divide-slate-100 font-medium text-slate-700"></tbody>
                    </table>
                </div>
                <div id="sales-mobile-list" class="md:hidden space-y-3"></div>
            </div>

            <!-- ÜRÜNLER -->
            <div id="section-products" class="hidden space-y-5">
                <div>
                    <h1 class="text-xl md:text-2xl font-extrabold text-slate-800">Ürün & Stok Yönetimi</h1>
                    <p class="text-xs text-slate-500 mt-0.5">Katalog fiyatları ve anlık depo stokları</p>
                </div>
                <div class="hidden md:block bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-x-auto">
                    <table class="w-full text-left text-xs">
                        <thead class="bg-slate-50 text-slate-500 font-semibold border-b uppercase text-[10px]">
                            <tr>
                                <th class="p-4">Marka</th>
                                <th class="p-4">Model</th>
                                <th class="p-4">Liste Fiyatı</th>
                                <th class="p-4">Stok</th>
                                <th class="p-4">Durum</th>
                                <th class="p-4 text-center">Düzenle</th>
                            </tr>
                        </thead>
                        <tbody id="products-table-body" class="divide-y divide-slate-100 font-medium text-slate-700"></tbody>
                    </table>
                </div>
                <div id="products-mobile-list" class="md:hidden space-y-3"></div>
            </div>

            <!-- GÖRÜŞMELER -->
            <div id="section-interactions" class="hidden space-y-5">
                <div class="flex items-center justify-between gap-2">
                    <div>
                        <h1 class="text-xl md:text-2xl font-extrabold text-slate-800">Müşteri Görüşmeleri</h1>
                        <p class="text-xs text-slate-500 mt-0.5">Ziyaret, teklif linki ve yetkili personel takibi</p>
                    </div>
                    <button onclick="toggleModal('modal-add-interaction')" class="bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold px-4 py-2.5 rounded-xl shadow transition flex items-center gap-2 shrink-0">
                        <i class="fa-solid fa-plus"></i> Not Ekle
                    </button>
                </div>

                <div class="hidden md:block bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-x-auto">
                    <table class="w-full text-left text-xs">
                        <thead class="bg-slate-50 text-slate-500 font-semibold border-b uppercase text-[10px]">
                            <tr>
                                <th class="p-4">Tarih</th>
                                <th class="p-4">Müşteri Adı</th>
                                <th class="p-4">İlgilenilen Cihazlar</th>
                                <th class="p-4">Notlar</th>
                                <th class="p-4">Yetkili Personel</th>
                                <th class="p-4">Teklif URL</th>
                                <th class="p-4 text-center">Sil</th>
                            </tr>
                        </thead>
                        <tbody id="interactions-table-body" class="divide-y divide-slate-100 font-medium text-slate-700"></tbody>
                    </table>
                </div>
                <div id="interactions-mobile-list" class="md:hidden space-y-3"></div>
            </div>

            <!-- KONFİGÜRATÖR & TEKLİF (IFRAME) -->
            <div id="section-configurator" class="hidden space-y-3">
                <div class="flex items-center justify-between">
                    <div>
                        <h1 class="text-xl md:text-2xl font-extrabold text-slate-800">Klinik Matrix Konfigüratör & Teklif Stüdyosu</h1>
                        <p class="text-xs text-slate-500">İZDO 2026 Kampanya Listesi, Stern Weber 19 Renk Kartelası ve A4 PDF Teklif Motoru</p>
                    </div>
                    <a href="/konfigurator" target="_blank" class="px-3.5 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold flex items-center gap-2 shrink-0">
                        <i class="fa-solid fa-up-right-from-square"></i> Tam Ekran Aç
                    </a>
                </div>
                <div class="rounded-2xl overflow-hidden border border-slate-200 shadow-lg bg-slate-950" style="height: calc(100vh - 150px); min-height: 620px;">
                    <iframe id="konfigurator-iframe" src="" class="w-full h-full border-0"></iframe>
                </div>
            </div>

            <!-- PERSONEL -->
            <div id="section-staff" class="hidden space-y-5">
                <h1 class="text-xl md:text-2xl font-extrabold text-slate-800">Ekip / Personel Listesi</h1>
                <div class="bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-x-auto">
                    <table class="w-full text-left text-xs">
                        <thead class="bg-slate-50 text-slate-500 font-semibold border-b uppercase text-[10px]">
                            <tr>
                                <th class="p-4">Personel Adı</th>
                                <th class="p-4">Departman</th>
                                <th class="p-4">Unvan</th>
                            </tr>
                        </thead>
                        <tbody id="staff-table-body" class="divide-y divide-slate-100 font-medium text-slate-700"></tbody>
                    </table>
                </div>
            </div>

        </main>

        <!-- MOBİL ALT GEZİNME ÇUBUĞU -->
        <nav class="md:hidden fixed bottom-0 left-0 right-0 z-30 bg-slate-900 text-slate-400 border-t border-slate-800 grid grid-cols-5 py-2 text-[10px] font-semibold">
            <button onclick="switchTab('dashboard')" id="mnav-dashboard" class="flex flex-col items-center gap-1 mobile-nav-active">
                <i class="fa-solid fa-chart-pie text-base"></i><span>Panel</span>
            </button>
            <button onclick="switchTab('sales')" id="mnav-sales" class="flex flex-col items-center gap-1">
                <i class="fa-solid fa-receipt text-base"></i><span>Satış</span>
            </button>
            <button onclick="switchTab('products')" id="mnav-products" class="flex flex-col items-center gap-1">
                <i class="fa-solid fa-boxes-stacked text-base"></i><span>Stok</span>
            </button>
            <button onclick="switchTab('interactions')" id="mnav-interactions" class="flex flex-col items-center gap-1">
                <i class="fa-solid fa-comments text-base"></i><span>Görüşme</span>
            </button>
            <button onclick="switchTab('configurator')" id="mnav-configurator" class="flex flex-col items-center gap-1">
                <i class="fa-solid fa-wand-magic-sparkles text-base"></i><span>Stüdyo</span>
            </button>
        </nav>
    </div>

    <!-- MODAL: YENİ SATIŞ -->
    <div id="modal-add-sale" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 hidden">
        <div class="bg-white p-6 rounded-2xl shadow-2xl w-full max-w-lg border max-h-[90vh] overflow-y-auto">
            <h3 class="text-lg font-bold text-slate-800 mb-4">Yeni Satış Kaydı</h3>
            <form id="sale-form" onsubmit="submitSale(event)" class="space-y-3 text-xs">
                <div>
                    <label class="font-semibold text-slate-600">Tarih</label>
                    <input type="date" id="sale-date" required class="w-full p-2.5 border rounded-xl mt-1">
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Satış Yetkilisi</label>
                    <select id="sale-staff" required class="w-full p-2.5 border rounded-xl mt-1"></select>
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Müşteri / Kurum Adı</label>
                    <input type="text" id="sale-customer" required class="w-full p-2.5 border rounded-xl mt-1" placeholder="Örn: Dent Klinik">
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Konum (Şehir)</label>
                    <input type="text" id="sale-location" required class="w-full p-2.5 border rounded-xl mt-1" placeholder="Örn: İstanbul">
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Ürün</label>
                    <select id="sale-product" onchange="onProductSelect()" required class="w-full p-2.5 border rounded-xl mt-1"></select>
                </div>
                <div class="grid grid-cols-2 gap-3">
                    <div>
                        <label class="font-semibold text-slate-600">Birim Fiyat (€)</label>
                        <input type="number" step="0.01" id="sale-price" required class="w-full p-2.5 border rounded-xl mt-1">
                    </div>
                    <div>
                        <label class="font-semibold text-slate-600">Adet</label>
                        <input type="number" min="1" id="sale-qty" value="1" required class="w-full p-2.5 border rounded-xl mt-1">
                    </div>
                </div>
                <div class="flex justify-end gap-2 pt-4">
                    <button type="button" onclick="toggleModal('modal-add-sale')" class="px-4 py-2 border rounded-xl font-medium text-slate-600">İptal</button>
                    <button type="submit" class="px-5 py-2 bg-blue-600 text-white rounded-xl font-bold hover:bg-blue-700">Kaydet</button>
                </div>
            </form>
        </div>
    </div>

    <!-- MODAL: STOK/FİYAT DÜZENLE -->
    <div id="modal-edit-product" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 hidden">
        <div class="bg-white p-6 rounded-2xl shadow-2xl w-full max-w-sm border">
            <h3 class="text-lg font-bold text-slate-800 mb-1">Ürün Güncelle</h3>
            <p id="edit-prod-title" class="text-xs text-slate-500 mb-4"></p>
            <form onsubmit="submitProductUpdate(event)" class="space-y-3 text-xs">
                <input type="hidden" id="edit-prod-id">
                <div>
                    <label class="font-semibold text-slate-600">Liste Fiyatı (€)</label>
                    <input type="number" step="0.01" id="edit-prod-price" required class="w-full p-2.5 border rounded-xl mt-1">
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Depo Stok Adedi</label>
                    <input type="number" min="0" id="edit-prod-stock" required class="w-full p-2.5 border rounded-xl mt-1">
                </div>
                <div class="flex justify-end gap-2 pt-3">
                    <button type="button" onclick="toggleModal('modal-edit-product')" class="px-4 py-2 border rounded-xl font-medium text-slate-600">İptal</button>
                    <button type="submit" class="px-5 py-2 bg-blue-600 text-white rounded-xl font-bold hover:bg-blue-700">Güncelle</button>
                </div>
            </form>
        </div>
    </div>

    <!-- MODAL: YENİ GÖRÜŞME -->
    <div id="modal-add-interaction" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 hidden">
        <div class="bg-white p-6 rounded-2xl shadow-2xl w-full max-w-lg border max-h-[90vh] overflow-y-auto">
            <h3 class="text-lg font-bold text-slate-800 mb-4">Yeni Görüşme Notu</h3>
            <form id="interaction-form" onsubmit="submitInteraction(event)" class="space-y-3 text-xs">
                <div class="grid grid-cols-2 gap-3">
                    <div>
                        <label class="font-semibold text-slate-600">Tarih</label>
                        <input type="date" id="inter-date" required class="w-full p-2.5 border rounded-xl mt-1">
                    </div>
                    <div>
                        <label class="font-semibold text-slate-600">Yetkili Personel</label>
                        <select id="inter-staff" class="w-full p-2.5 border rounded-xl mt-1"></select>
                    </div>
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Müşteri Adı</label>
                    <input type="text" id="inter-customer" required class="w-full p-2.5 border rounded-xl mt-1" placeholder="Dr. Adı veya Poliklinik">
                </div>
                <div>
                    <label class="font-semibold text-slate-600">İlgilenilen Cihazlar</label>
                    <input type="text" id="inter-devices" required class="w-full p-2.5 border rounded-xl mt-1" placeholder="Örn: S300, ProXima X6">
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Teklif URL'si (Opsiyonel)</label>
                    <input type="url" id="inter-url" class="w-full p-2.5 border rounded-xl mt-1" placeholder="https://1drv.ms/...">
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Notlar / Detaylar</label>
                    <textarea id="inter-notes" rows="3" required class="w-full p-2.5 border rounded-xl mt-1" placeholder="Görüşme detayları..."></textarea>
                </div>
                <div class="flex justify-end gap-2 pt-3">
                    <button type="button" onclick="toggleModal('modal-add-interaction')" class="px-4 py-2 border rounded-xl font-medium text-slate-600">İptal</button>
                    <button type="submit" class="px-5 py-2 bg-purple-600 text-white rounded-xl font-bold hover:bg-purple-700">Kaydet</button>
                </div>
            </form>
        </div>
    </div>

    <!-- MODAL: SİLME ONAYI -->
    <div id="modal-confirm" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 hidden">
        <div class="bg-white p-6 rounded-2xl shadow-2xl w-full max-w-sm border text-center space-y-4">
            <div class="w-12 h-12 mx-auto rounded-full bg-rose-100 text-rose-600 flex items-center justify-center text-xl">
                <i class="fa-solid fa-trash-can"></i>
            </div>
            <div>
                <h3 class="text-base font-bold text-slate-800">Kaydı Sil</h3>
                <p id="confirm-msg" class="text-xs text-slate-500 mt-1">Bu kaydı silmek istediğinize emin misiniz?</p>
            </div>
            <div class="flex justify-center gap-2 pt-2">
                <button onclick="toggleModal('modal-confirm')" class="px-4 py-2 border rounded-xl text-xs font-semibold text-slate-600">Vazgeç</button>
                <button id="confirm-yes-btn" class="px-5 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-bold">Evet, Sil</button>
            </div>
        </div>
    </div>

    <!-- TOAST BİLDİRİMİ -->
    <div id="crm-toast" class="fixed bottom-20 md:bottom-6 right-5 z-50 hidden bg-slate-900 text-white px-4 py-3 rounded-xl shadow-2xl text-xs font-semibold border border-slate-700 flex items-center gap-2">
        <i class="fa-solid fa-circle-check text-emerald-400"></i>
        <span id="crm-toast-text">İşlem başarılı</span>
    </div>

    <script>
        if ("serviceWorker" in navigator) {
            window.addEventListener("load", () => {
                navigator.serviceWorker.register("/sw.js").catch(() => {});
            });
        }

        let token = localStorage.getItem("token");
        let rawProducts = [];
        let rawStaff = [];
        let staffChartInstance = null;
        let brandChartInstance = null;
        let pendingConfirmAction = null;

        function showToast(msg) {
            const box = document.getElementById("crm-toast");
            document.getElementById("crm-toast-text").textContent = msg;
            box.classList.remove("hidden");
            setTimeout(() => box.classList.add("hidden"), 3000);
        }

        function askConfirm(msg, onYes) {
            document.getElementById("confirm-msg").textContent = msg;
            pendingConfirmAction = onYes;
            toggleModal("modal-confirm");
        }

        document.getElementById("confirm-yes-btn").addEventListener("click", async () => {
            toggleModal("modal-confirm");
            if (pendingConfirmAction) {
                await pendingConfirmAction();
                pendingConfirmAction = null;
            }
        });

        document.addEventListener("DOMContentLoaded", async () => {
            const today = new Date().toISOString().split("T")[0];
            document.getElementById("sale-date").value = today;
            document.getElementById("inter-date").value = today;

            if (token) {
                try {
                    const res = await fetch("/api/me", { headers: { "Authorization": "Bearer " + token } });
                    if (res.ok) {
                        const user = await res.json();
                        localStorage.setItem("user_name", user.full_name);
                        document.getElementById("login-modal").classList.add("hidden");
                        initPortal();
                        return;
                    }
                } catch (e) {}
                localStorage.clear();
                token = null;
            }
            document.getElementById("login-modal").classList.remove("hidden");
        });

        async function handleLogin(e) {
            e.preventDefault();
            const errDiv = document.getElementById("login-error");
            errDiv.classList.add("hidden");

            const formData = new FormData();
            formData.append("username", document.getElementById("username").value);
            formData.append("password", document.getElementById("password").value);

            try {
                const res = await fetch("/api/token", { method: "POST", body: formData });
                if (!res.ok) throw new Error("Hatalı kullanıcı adı veya şifre!");
                const data = await res.json();
                token = data.access_token;
                localStorage.setItem("token", token);
                localStorage.setItem("user_name", data.full_name);
                document.getElementById("login-modal").classList.add("hidden");
                document.getElementById("login-form").reset();
                initPortal();
            } catch (err) {
                errDiv.textContent = err.message;
                errDiv.classList.remove("hidden");
            }
        }

        function logout() {
            localStorage.clear();
            location.reload();
        }

        async function authFetch(url, options = {}) {
            options.headers = { ...options.headers, "Authorization": "Bearer " + token };
            const res = await fetch(url, options);
            if (res.status === 401) logout();
            return res;
        }

        async function initPortal() {
            document.getElementById("app").classList.remove("hidden");
            document.getElementById("user-display").textContent = localStorage.getItem("user_name") || "Hakan Behramoğlu";
            await Promise.all([loadStaff(), loadProducts(), loadDashboard(), loadSales(), loadInteractions()]);
        }

        function switchTab(tab) {
            ['dashboard', 'sales', 'products', 'interactions', 'configurator', 'staff'].forEach(t => {
                document.getElementById("section-" + t).classList.add("hidden");
                const nav = document.getElementById("nav-" + t);
                if (nav) nav.classList.remove("sidebar-active");
                const mnav = document.getElementById("mnav-" + t);
                if (mnav) mnav.classList.remove("mobile-nav-active");
            });
            document.getElementById("section-" + tab).classList.remove("hidden");
            const activeNav = document.getElementById("nav-" + tab);
            if (activeNav) activeNav.classList.add("sidebar-active");
            const activeMnav = document.getElementById("mnav-" + tab);
            if (activeMnav) activeMnav.classList.add("mobile-nav-active");

            if (tab === "configurator") {
                const iframe = document.getElementById("konfigurator-iframe");
                if (!iframe.src) iframe.src = "/konfigurator?embed=1";
            }
            if (tab === "interactions") {
                loadInteractions();
            }
        }

        function toggleModal(id) {
            document.getElementById(id).classList.toggle("hidden");
        }

        const fmtEUR = (num) => "€ " + Number(num || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

        async function loadDashboard() {
            const res = await authFetch("/api/dashboard");
            const data = await res.json();

            document.getElementById("kpi-revenue").textContent = fmtEUR(data.kpis.total_revenue);
            document.getElementById("kpi-units").textContent = data.kpis.total_units;
            document.getElementById("kpi-count").textContent = data.kpis.total_sales_count;
            document.getElementById("kpi-stock").textContent = data.kpis.total_stock;
            document.getElementById("kpi-sku").textContent = data.kpis.total_sku;

            const staffLabels = data.charts.staff_sales.map(s => s.staff_name);
            const staffValues = data.charts.staff_sales.map(s => s.revenue);
            if (staffChartInstance) staffChartInstance.destroy();
            staffChartInstance = new Chart(document.getElementById('staffChart'), {
                type: 'bar',
                data: {
                    labels: staffLabels,
                    datasets: [{ label: 'Ciro (€)', data: staffValues, backgroundColor: '#2563eb', borderRadius: 6 }]
                },
                options: { responsive: true, plugins: { legend: { display: false } } }
            });

            const brandLabels = data.charts.brand_sales.map(b => b.brand);
            const brandValues = data.charts.brand_sales.map(b => b.revenue);
            if (brandChartInstance) brandChartInstance.destroy();
            brandChartInstance = new Chart(document.getElementById('brandChart'), {
                type: 'doughnut',
                data: {
                    labels: brandLabels,
                    datasets: [{ data: brandValues, backgroundColor: ['#0284c7', '#10b981', '#f59e0b', '#6366f1'] }]
                },
                options: { responsive: true }
            });
        }

        async function loadProducts() {
            const res = await authFetch("/api/products");
            rawProducts = await res.json();
            const tbody = document.getElementById("products-table-body");
            const mobileList = document.getElementById("products-mobile-list");
            const select = document.getElementById("sale-product");
            tbody.innerHTML = "";
            mobileList.innerHTML = "";
            select.innerHTML = "<option value=''>Ürün seçiniz...</option>";

            rawProducts.forEach(p => {
                const badge = p.stock > 0
                    ? '<span class="bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-md text-[10px] font-bold">Mevcut</span>'
                    : '<span class="bg-rose-50 text-rose-700 px-2 py-0.5 rounded-md text-[10px] font-bold">Tükendi</span>';

                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td class="p-4 font-bold text-slate-800">${p.brand}</td>
                    <td class="p-4">${p.model}</td>
                    <td class="p-4 font-semibold">${fmtEUR(p.price)}</td>
                    <td class="p-4 font-bold ${p.stock <= 2 ? 'text-rose-600' : 'text-slate-800'}">${p.stock}</td>
                    <td class="p-4">${badge}</td>
                    <td class="p-4 text-center">
                        <button onclick="openProductEdit(${p.id})" class="text-slate-400 hover:text-blue-600"><i class="fa-solid fa-pen-to-square"></i></button>
                    </td>`;
                tbody.appendChild(tr);

                const card = document.createElement("div");
                card.className = "bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex items-center justify-between";
                card.innerHTML = `
                    <div>
                        <div class="text-[10px] font-bold text-blue-600 uppercase">${p.brand}</div>
                        <div class="font-bold text-slate-800 text-sm">${p.model}</div>
                        <div class="text-xs text-slate-500 mt-0.5">${fmtEUR(p.price)} • Stok: <strong class="${p.stock <= 2 ? 'text-rose-600' : 'text-slate-800'}">${p.stock}</strong> ${badge}</div>
                    </div>
                    <button onclick="openProductEdit(${p.id})" class="p-2.5 bg-slate-100 rounded-xl text-slate-600"><i class="fa-solid fa-pen"></i></button>`;
                mobileList.appendChild(card);

                const opt = document.createElement("option");
                opt.value = p.id;
                opt.textContent = `${p.brand} - ${p.model} (Stok: ${p.stock})`;
                select.appendChild(opt);
            });
        }

        function openProductEdit(id) {
            const p = rawProducts.find(x => x.id === id);
            if (!p) return;
            document.getElementById("edit-prod-id").value = p.id;
            document.getElementById("edit-prod-title").textContent = `${p.brand} - ${p.model}`;
            document.getElementById("edit-prod-price").value = p.price;
            document.getElementById("edit-prod-stock").value = p.stock;
            toggleModal("modal-edit-product");
        }

        async function submitProductUpdate(e) {
            e.preventDefault();
            const id = document.getElementById("edit-prod-id").value;
            const price = parseFloat(document.getElementById("edit-prod-price").value);
            const stock = parseInt(document.getElementById("edit-prod-stock").value, 10);
            const res = await authFetch(`/api/products/${id}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ price, stock })
            });
            if (res.ok) {
                toggleModal("modal-edit-product");
                showToast("Ürün bilgileri güncellendi.");
                await Promise.all([loadProducts(), loadDashboard()]);
            }
        }

        function onProductSelect() {
            const id = document.getElementById("sale-product").value;
            const p = rawProducts.find(x => x.id == id);
            if (p) document.getElementById("sale-price").value = p.price;
        }

        async function loadSales() {
            const res = await authFetch("/api/sales");
            const sales = await res.json();
            const tbody = document.getElementById("sales-table-body");
            const mobileList = document.getElementById("sales-mobile-list");
            tbody.innerHTML = "";
            mobileList.innerHTML = "";

            sales.forEach(s => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td class="p-4 text-slate-500 whitespace-nowrap">${s.date}</td>
                    <td class="p-4 font-semibold text-slate-900">${s.staff_name}</td>
                    <td class="p-4">${s.customer_name}</td>
                    <td class="p-4 text-slate-500">${s.customer_location}</td>
                    <td class="p-4"><span class="font-bold text-slate-800">${s.brand}</span> ${s.model}</td>
                    <td class="p-4 whitespace-nowrap">${fmtEUR(s.price)}</td>
                    <td class="p-4 font-bold">${s.quantity}</td>
                    <td class="p-4 font-extrabold text-blue-600 whitespace-nowrap">${fmtEUR(s.total)}</td>
                    <td class="p-4 text-center">
                        <button onclick="deleteSale(${s.id})" class="text-slate-300 hover:text-rose-600 transition"><i class="fa-solid fa-trash"></i></button>
                    </td>`;
                tbody.appendChild(tr);

                const card = document.createElement("div");
                card.className = "bg-white p-4 rounded-2xl border border-slate-200 shadow-sm space-y-2";
                card.innerHTML = `
                    <div class="flex justify-between items-start">
                        <div>
                            <div class="text-[10px] text-slate-400 font-semibold">${s.date} • ${s.customer_location}</div>
                            <div class="font-bold text-slate-800 text-sm">${s.customer_name}</div>
                        </div>
                        <button onclick="deleteSale(${s.id})" class="text-slate-400 hover:text-rose-600 p-1"><i class="fa-solid fa-trash text-xs"></i></button>
                    </div>
                    <div class="text-xs text-slate-600"><strong>${s.brand}</strong> ${s.model} (${s.quantity} adet)</div>
                    <div class="flex justify-between items-center pt-2 border-t border-slate-100 text-xs">
                        <span class="text-slate-500">${s.staff_name}</span>
                        <span class="font-extrabold text-blue-600 text-sm">${fmtEUR(s.total)}</span>
                    </div>`;
                mobileList.appendChild(card);
            });
        }

        async function submitSale(e) {
            e.preventDefault();
            const prodId = document.getElementById("sale-product").value;
            const p = rawProducts.find(x => x.id == prodId);
            if (!p) return;

            const payload = {
                date: document.getElementById("sale-date").value,
                staff_name: document.getElementById("sale-staff").value,
                customer_name: document.getElementById("sale-customer").value,
                customer_location: document.getElementById("sale-location").value,
                brand: p.brand,
                model: p.model,
                price: parseFloat(document.getElementById("sale-price").value),
                quantity: parseInt(document.getElementById("sale-qty").value, 10)
            };

            const res = await authFetch("/api/sales", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                toggleModal("modal-add-sale");
                document.getElementById("sale-form").reset();
                document.getElementById("sale-date").value = new Date().toISOString().split("T")[0];
                showToast("Yeni satış veritabanına kaydedildi.");
                await Promise.all([loadSales(), loadProducts(), loadDashboard()]);
            }
        }

        function deleteSale(id) {
            askConfirm("Bu satış kaydını silmek istediğinize emin misiniz?", async () => {
                await authFetch(`/api/sales/${id}`, { method: "DELETE" });
                showToast("Satış kaydı silindi.");
                await Promise.all([loadSales(), loadDashboard()]);
            });
        }

        async function loadStaff() {
            const res = await authFetch("/api/staff");
            rawStaff = await res.json();
            const tbody = document.getElementById("staff-table-body");
            const saleSelect = document.getElementById("sale-staff");
            const interSelect = document.getElementById("inter-staff");
            tbody.innerHTML = "";
            saleSelect.innerHTML = "";
            interSelect.innerHTML = "";

            rawStaff.forEach(s => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td class="p-4 font-bold text-slate-800">${s.name}</td>
                    <td class="p-4"><span class="bg-slate-100 text-slate-700 px-2 py-0.5 rounded text-[11px]">${s.department}</span></td>
                    <td class="p-4 text-slate-500">${s.title}</td>`;
                tbody.appendChild(tr);

                const opt1 = document.createElement("option");
                opt1.value = s.name;
                opt1.textContent = s.name;
                saleSelect.appendChild(opt1);

                const opt2 = document.createElement("option");
                opt2.value = s.name;
                opt2.textContent = s.name;
                if (s.name === "HAKAN BEHRAMOĞLU") opt2.selected = true;
                interSelect.appendChild(opt2);
            });
            document.getElementById("kpi-staff").textContent = rawStaff.length;
        }

        async function loadInteractions() {
            const res = await authFetch("/api/interactions");
            const data = await res.json();
            const tbody = document.getElementById("interactions-table-body");
            const mobileList = document.getElementById("interactions-mobile-list");
            tbody.innerHTML = "";
            mobileList.innerHTML = "";

            if (data.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" class="p-6 text-center text-slate-400">Kayıtlı görüşme bulunmamaktadır.</td></tr>`;
                mobileList.innerHTML = `<div class="bg-white p-6 rounded-2xl text-center text-xs text-slate-400 border">Kayıtlı görüşme bulunmamaktadır.</div>`;
                return;
            }

            data.forEach(i => {
                const urlBtn = i.offer_url && i.offer_url.trim().startsWith("http")
                    ? `<a href="${i.offer_url}" target="_blank" class="inline-flex items-center gap-1 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 px-2.5 py-1 rounded-lg font-bold text-[11px] whitespace-nowrap"><i class="fa-solid fa-file-lines"></i> Teklifi Aç</a>`
                    : `<span class="text-slate-400">-</span>`;

                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td class="p-4 text-slate-500 whitespace-nowrap">${i.date}</td>
                    <td class="p-4 font-bold text-slate-800">${i.customer_name}</td>
                    <td class="p-4 font-semibold text-purple-700">${i.devices}</td>
                    <td class="p-4 text-slate-600 max-w-md">${i.notes}</td>
                    <td class="p-4 font-semibold text-slate-700 whitespace-nowrap">${i.staff_name || '-'}</td>
                    <td class="p-4">${urlBtn}</td>
                    <td class="p-4 text-center">
                        <button onclick="deleteInteraction(${i.id})" class="text-slate-300 hover:text-rose-600 transition"><i class="fa-solid fa-trash"></i></button>
                    </td>`;
                tbody.appendChild(tr);

                const card = document.createElement("div");
                card.className = "bg-white p-4 rounded-2xl border border-slate-200 shadow-sm space-y-2";
                card.innerHTML = `
                    <div class="flex justify-between items-start">
                        <div>
                            <div class="text-[10px] text-slate-400 font-semibold">${i.date} • ${i.staff_name || 'Yetkili Yok'}</div>
                            <div class="font-bold text-slate-800 text-sm">${i.customer_name}</div>
                        </div>
                        <button onclick="deleteInteraction(${i.id})" class="text-slate-400 hover:text-rose-600 p-1"><i class="fa-solid fa-trash text-xs"></i></button>
                    </div>
                    <div class="text-xs font-semibold text-purple-700">${i.devices}</div>
                    <div class="text-xs text-slate-600">${i.notes}</div>
                    <div class="pt-1">${urlBtn}</div>`;
                mobileList.appendChild(card);
            });
        }

        async function submitInteraction(e) {
            e.preventDefault();
            const payload = {
                date: document.getElementById("inter-date").value,
                customer_name: document.getElementById("inter-customer").value,
                devices: document.getElementById("inter-devices").value,
                notes: document.getElementById("inter-notes").value,
                staff_name: document.getElementById("inter-staff").value,
                offer_url: document.getElementById("inter-url").value.trim()
            };

            const res = await authFetch("/api/interactions", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                toggleModal("modal-add-interaction");
                document.getElementById("interaction-form").reset();
                document.getElementById("inter-date").value = new Date().toISOString().split("T")[0];
                showToast("Görüşme notu kaydedildi.");
                await loadInteractions();
            }
        }

        function deleteInteraction(id) {
            askConfirm("Bu görüşme kaydını silmek istediğinize emin misiniz?", async () => {
                await authFetch(`/api/interactions/${id}`, { method: "DELETE" });
                showToast("Görüşme kaydı silindi.");
                await loadInteractions();
            });
        }

        // Konfigüratör iframe'inden yeni teklif kaydedildiğinde CRM Görüşmeler listesini anında yenile
        window.addEventListener("message", (event) => {
            if (event.data && event.data.type === "CRM_INTERACTION_SAVED") {
                loadInteractions();
                showToast("Teklif CRM Görüşmelerine aktarıldı!");
            }
        });
    </script>
</body>
</html>"""


# --- KLİNİK MATRIX KONFİGÜRATÖR & RESMİ TEKLİF MOTORU ---
@app.get("/konfigurator", response_class=HTMLResponse)
def konfigurator_page():
    return r"""<!DOCTYPE html>
<html lang="tr" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Klinik Matrix | İZDO 2026 Konfigürasyon & Teklif Altyapısı</title>
    <link rel="icon" href="/icon.jpg">
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/@phosphor-icons/web"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['Inter', 'sans-serif'],
                        display: ['Space Grotesk', 'sans-serif'],
                    }
                }
            }
        }
    </script>
    <style>
        body { background-color: #090D16; color: #F3F4F6; overflow-x: hidden; }
        .glass-panel {
            background: rgba(17, 24, 39, 0.78);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .glass-card {
            background: linear-gradient(145deg, rgba(31, 41, 55, 0.6) 0%, rgba(17, 24, 39, 0.8) 100%);
            border: 1px solid rgba(255, 255, 255, 0.07);
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .glass-card:hover {
            border-color: rgba(56, 189, 248, 0.35);
            transform: translateY(-2px);
            box-shadow: 0 12px 30px -10px rgba(14, 165, 233, 0.18);
        }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #090D16; }
        ::-webkit-scrollbar-thumb { background: #1F2937; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #38bdf8; }
        @media print {
            body { background-color: #ffffff !important; color: #111827 !important; }
            header, #pin-lock-overlay, #view-configurator, #view-imaging, #view-calculator, #view-ideas, .no-print, #toast-box { display: none !important; }
            #view-proposal, #a4-printable-paper { display: block !important; }
            .glass-panel { background: #ffffff !important; border: none !important; box-shadow: none !important; padding: 0 !important; }
        }
    </style>
</head>
<body class="min-h-screen flex flex-col selection:bg-sky-500 selection:text-white">

    <!-- PIN GÜVENLİK EKRANI -->
    <div id="pin-lock-overlay" class="fixed inset-0 z-50 bg-[#090D16]/95 backdrop-blur-2xl flex items-center justify-center p-4">
        <div class="glass-panel max-w-md w-full rounded-3xl p-8 border border-sky-500/30 shadow-2xl text-center space-y-6 relative overflow-hidden">
            <img src="/icon.jpg" alt="Klinik Matrix" class="w-24 h-24 mx-auto rounded-3xl object-cover shadow-2xl border border-sky-400/30 bg-slate-950">
            <div class="space-y-1">
                <span class="text-[11px] font-mono uppercase tracking-widest text-sky-400 font-bold">MANNAS DİŞ DEPOSU • GÜVENLİ ERİŞİM</span>
                <h1 class="font-display text-2xl font-bold text-white tracking-tight">Klinik<span class="text-transparent bg-clip-text bg-gradient-to-r from-sky-400 via-blue-400 to-purple-400">Matrix</span></h1>
                <p class="text-xs text-gray-300 font-medium">İZDO 2026 Konfigürasyon & Teklif Altyapısı</p>
                <p class="text-[11px] text-gray-400 pt-1">Devam etmek için 4 haneli PIN kodunu girin.</p>
            </div>
            <div class="flex justify-center gap-3 py-2">
                <input type="password" id="pin-input" maxlength="4" inputmode="numeric" placeholder="••••" oninput="handlePinTyping(this.value)" onkeydown="if(event.key==='Enter') verifyPinCode()" class="w-44 text-center font-mono text-3xl tracking-[0.5em] bg-gray-900/90 border border-white/15 focus:border-sky-400 rounded-2xl py-3 text-white focus:outline-none shadow-inner">
            </div>
            <div id="pin-error-msg" class="hidden text-xs font-semibold text-rose-400">
                <i class="ph-fill ph-warning-circle"></i> Hatalı PIN kodu! Lütfen tekrar deneyin.
            </div>
            <div class="grid grid-cols-3 gap-2.5 max-w-[260px] mx-auto pt-1">
                <button onclick="pressPinKey('1')" class="py-3 rounded-xl bg-gray-900 hover:bg-gray-800 border border-white/10 font-display font-bold text-lg text-white">1</button>
                <button onclick="pressPinKey('2')" class="py-3 rounded-xl bg-gray-900 hover:bg-gray-800 border border-white/10 font-display font-bold text-lg text-white">2</button>
                <button onclick="pressPinKey('3')" class="py-3 rounded-xl bg-gray-900 hover:bg-gray-800 border border-white/10 font-display font-bold text-lg text-white">3</button>
                <button onclick="pressPinKey('4')" class="py-3 rounded-xl bg-gray-900 hover:bg-gray-800 border border-white/10 font-display font-bold text-lg text-white">4</button>
                <button onclick="pressPinKey('5')" class="py-3 rounded-xl bg-gray-900 hover:bg-gray-800 border border-white/10 font-display font-bold text-lg text-white">5</button>
                <button onclick="pressPinKey('6')" class="py-3 rounded-xl bg-gray-900 hover:bg-gray-800 border border-white/10 font-display font-bold text-lg text-white">6</button>
                <button onclick="pressPinKey('7')" class="py-3 rounded-xl bg-gray-900 hover:bg-gray-800 border border-white/10 font-display font-bold text-lg text-white">7</button>
                <button onclick="pressPinKey('8')" class="py-3 rounded-xl bg-gray-900 hover:bg-gray-800 border border-white/10 font-display font-bold text-lg text-white">8</button>
                <button onclick="pressPinKey('9')" class="py-3 rounded-xl bg-gray-900 hover:bg-gray-800 border border-white/10 font-display font-bold text-lg text-white">9</button>
                <button onclick="clearPinInput()" class="py-3 rounded-xl bg-rose-500/15 hover:bg-rose-500/25 border border-rose-500/30 font-semibold text-xs text-rose-300">Temizle</button>
                <button onclick="pressPinKey('0')" class="py-3 rounded-xl bg-gray-900 hover:bg-gray-800 border border-white/10 font-display font-bold text-lg text-white">0</button>
                <button onclick="verifyPinCode()" class="py-3 rounded-xl bg-sky-500 hover:bg-sky-400 font-semibold text-xs text-white">Giriş</button>
            </div>
        </div>
    </div>

    <!-- ÜST BAR -->
    <header class="glass-panel sticky top-0 z-40 border-b border-white/10 px-4 lg:px-8 py-3.5">
        <div class="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
            <div class="flex items-center gap-3">
                <img src="/icon.jpg" alt="Klinik Matrix" class="w-11 h-11 rounded-2xl object-cover shadow-lg border border-sky-400/30 bg-slate-950 shrink-0">
                <div>
                    <div class="flex items-center gap-2">
                        <span class="font-display font-black text-lg tracking-tight text-white">KLINIK<span class="text-transparent bg-clip-text bg-gradient-to-r from-sky-400 via-blue-400 to-purple-400">MATRIX</span></span>
                        <span class="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full bg-orange-500/15 text-orange-400 border border-orange-500/30 font-bold">İZDO 2026</span>
                    </div>
                    <p class="text-xs text-gray-400 hidden sm:block">Stern Weber • MyRay • Dabi Atlante • Silverfox • MGF</p>
                </div>
            </div>

            <nav class="flex items-center gap-1.5 bg-gray-900/90 p-1.5 rounded-2xl border border-white/10 overflow-x-auto max-w-full">
                <button onclick="switchTab('configurator')" id="tab-configurator" class="tab-btn active-tab flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs sm:text-sm font-medium transition-all bg-sky-500 text-white shadow-md">
                    <i class="ph-bold ph-armchair text-base"></i><span>Ünit Stüdyosu & Föy</span>
                </button>
                <button onclick="switchTab('imaging')" id="tab-imaging" class="tab-btn flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs sm:text-sm font-medium text-gray-400 hover:text-white transition-all">
                    <i class="ph-bold ph-scan text-base"></i><span>Görüntüleme & Paketler</span>
                </button>
                <button onclick="switchTab('calculator')" id="tab-calculator" class="tab-btn flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs sm:text-sm font-medium text-gray-400 hover:text-white transition-all">
                    <i class="ph-bold ph-cpu text-base"></i><span>MGF & Sterilizasyon</span>
                </button>
                <button onclick="switchTab('proposal')" id="tab-proposal" class="tab-btn flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs sm:text-sm font-medium text-gray-400 hover:text-white transition-all">
                    <i class="ph-bold ph-file-xls text-base"></i><span>Resmi Teklif</span>
                    <span id="tab-proposal-count" class="px-1.5 py-0.2 rounded-full bg-sky-500/30 text-sky-200 text-[10px] font-mono font-bold">0</span>
                </button>
                <button onclick="switchTab('ideas')" id="tab-ideas" class="tab-btn flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs sm:text-sm font-medium text-gray-400 hover:text-white transition-all">
                    <i class="ph-bold ph-wrench text-base"></i><span>Şantiye & Servis</span>
                </button>
            </nav>

            <div class="hidden xl:flex items-center gap-2">
                <button onclick="switchTab('proposal')" class="flex items-center gap-2.5 px-4 py-2 rounded-xl bg-sky-500/10 hover:bg-sky-500/20 border border-sky-500/30 text-xs font-medium text-gray-200 transition-all">
                    <span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
                    <span>Teklif:</span>
                    <span id="header-total-badge" class="px-2 py-0.5 rounded-md bg-sky-500 text-white font-bold">0 €</span>
                </button>
                <button onclick="lockAppSession()" title="Ekranı Kilitle" class="p-2 rounded-xl bg-gray-900 hover:bg-rose-500/20 border border-white/10 text-gray-400 hover:text-rose-300 transition-all">
                    <i class="ph-bold ph-lock-key text-base"></i>
                </button>
            </div>
        </div>
    </header>

    <main class="flex-1 max-w-7xl w-full mx-auto px-4 lg:px-8 py-6">

        <!-- SEKME 1: ÜNİT STÜDYOSU & FÖY -->
        <section id="view-configurator" class="space-y-6">
            <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
                <!-- Görsel Stüdyo -->
                <div class="lg:col-span-7 glass-panel rounded-3xl p-6 relative overflow-hidden border border-white/10 flex flex-col justify-between min-h-[560px]">
                    <div id="studio-glow" class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 rounded-full blur-3xl opacity-30 transition-all duration-700 pointer-events-none" style="background: #1b589d;"></div>

                    <div class="relative z-10 flex flex-wrap items-center justify-between gap-2 border-b border-white/10 pb-4">
                        <div>
                            <div class="flex items-center gap-2">
                                <span id="unit-brand-badge" class="text-[11px] uppercase tracking-widest text-sky-400 font-bold">STERN WEBER • İZDO 33. KONGRE</span>
                                <span id="unit-price-badge" class="px-2.5 py-0.5 rounded-md bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-xs font-mono font-bold">12.000 € Baz</span>
                            </div>
                            <h2 id="unit-title-display" class="font-display text-2xl font-bold text-white mt-0.5">Stern Weber S200 Kamçılı</h2>
                        </div>
                        <div class="flex items-center gap-2">
                            <span id="unit-badge-delivery" class="px-3 py-1 rounded-full bg-white/10 text-xs font-medium text-gray-200 border border-white/10">Kamçılı (Continental)</span>
                            <span id="color-name-badge" class="px-3 py-1 rounded-full bg-sky-500/20 text-sky-300 text-xs font-semibold border border-sky-500/30">102 Atlantic Blue</span>
                        </div>
                    </div>

                    <div class="relative z-10 my-auto py-6 flex items-center justify-center">
                        <svg viewBox="0 0 650 360" class="w-full max-w-[520px] drop-shadow-2xl">
                            <defs>
                                <linearGradient id="metalGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                                    <stop offset="0%" stop-color="#f8fafc" /><stop offset="100%" stop-color="#94a3b8" />
                                </linearGradient>
                                <linearGradient id="darkMetal" x1="0%" y1="0%" x2="0%" y2="100%">
                                    <stop offset="0%" stop-color="#334155" /><stop offset="100%" stop-color="#0f172a" />
                                </linearGradient>
                                <filter id="ledGlow" x="-30%" y="-30%" width="160%" height="160%">
                                    <feGaussianBlur stdDeviation="8" result="blur" />
                                    <feComposite in="SourceGraphic" in2="blur" operator="over" />
                                </filter>
                                <linearGradient id="lightBeam" x1="0%" y1="0%" x2="0%" y2="100%">
                                    <stop offset="0%" stop-color="#fef08a" stop-opacity="0.75" /><stop offset="100%" stop-color="#38bdf8" stop-opacity="0" />
                                </linearGradient>
                            </defs>
                            <ellipse cx="320" cy="335" rx="220" ry="15" fill="rgba(0,0,0,0.55)" />
                            <path d="M180 320 L340 320 L325 295 L195 295 Z" fill="url(#metalGrad)" />
                            <path d="M235 295 L265 225 L295 225 L275 295 Z" fill="url(#darkMetal)" />
                            <rect x="155" y="150" width="46" height="150" rx="12" fill="url(#metalGrad)" />
                            <rect id="svg-ambient-led" x="175" y="165" width="6" height="115" rx="3" fill="#1b589d" filter="url(#ledGlow)" />
                            <path d="M130 165 Q155 195 180 165 Z" fill="#e2e8f0" />
                            <path d="M178 150 L178 40 Q178 20 200 20 L395 20 L395 50" fill="none" stroke="#cbd5e1" stroke-width="10" stroke-linecap="round" />
                            <g transform="translate(370, 45)">
                                <rect x="0" y="0" width="52" height="24" rx="10" fill="#f8fafc" stroke="#64748b" stroke-width="2" />
                                <ellipse cx="26" cy="24" rx="18" ry="6" fill="#fef08a" filter="url(#ledGlow)" />
                                <polygon points="12,28 40,28 85,170 -35,170" fill="url(#lightBeam)" opacity="0.18" />
                            </g>
                            <path d="M201 175 L295 135 L355 145" fill="none" stroke="#e2e8f0" stroke-width="9" stroke-linecap="round" />
                            <g transform="translate(320, 128)">
                                <rect x="0" y="0" width="90" height="26" rx="8" fill="#f8fafc" stroke="#94a3b8" stroke-width="2" />
                                <rect x="65" y="-14" width="28" height="20" rx="4" fill="#0f172a" stroke="#38bdf8" stroke-width="1.5" />
                                <g id="svg-whip-arms">
                                    <path d="M12 0 Q18 -28 32 -6" fill="none" stroke="#475569" stroke-width="3" />
                                    <path d="M26 0 Q32 -28 46 -6" fill="none" stroke="#475569" stroke-width="3" />
                                    <path d="M40 0 Q46 -28 60 -6" fill="none" stroke="#475569" stroke-width="3" />
                                </g>
                            </g>
                            <g id="svg-upholstery" fill="#1b589d" class="transition-colors duration-500">
                                <path d="M475 102 Q505 90 515 112 L492 135 Q472 125 475 102 Z" />
                                <path d="M365 205 L465 125 Q482 115 492 135 L400 228 Z" />
                                <path d="M235 222 L385 212 Q405 212 400 232 L235 242 Z" />
                                <path d="M235 224 L175 295 Q162 305 152 290 L218 218 Z" />
                            </g>
                            <line x1="468" y1="132" x2="482" y2="118" stroke="#cbd5e1" stroke-width="6" stroke-linecap="round" />
                        </svg>
                    </div>

                    <div class="relative z-10 grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-center pt-4 border-t border-white/10">
                        <div class="bg-gray-900/80 rounded-xl p-2 border border-white/10">
                            <span class="block text-[10px] uppercase text-gray-400">Reflektör</span>
                            <span id="spec-reflector" class="font-display font-semibold text-xs text-amber-300">Venus L-LED</span>
                        </div>
                        <div class="bg-gray-900/80 rounded-xl p-2 border border-white/10">
                            <span class="block text-[10px] uppercase text-gray-400">Kontrol Paneli</span>
                            <span id="spec-panel" class="font-display font-semibold text-xs text-sky-400">LCD Dokunmatik</span>
                        </div>
                        <div class="bg-gray-900/80 rounded-xl p-2 border border-white/10">
                            <span class="block text-[10px] uppercase text-gray-400">Mikromotor</span>
                            <span id="spec-motor" class="font-display font-semibold text-xs text-white">i-XR3-L Kömürsüz</span>
                        </div>
                        <div class="bg-gray-900/80 rounded-xl p-2 border border-white/10">
                            <span class="block text-[10px] uppercase text-gray-400">Ödeme Koşulu</span>
                            <span id="spec-payment" class="font-display font-semibold text-xs text-emerald-400">İZDO Kongre Vadesi</span>
                        </div>
                    </div>
                </div>

                <!-- Sağ Panel: İZDO 2026 Model & 19 Renk Seçimi -->
                <div class="lg:col-span-5 glass-panel rounded-3xl p-6 space-y-4 border border-white/10">
                    <div>
                        <h3 class="font-display text-lg font-bold text-white flex items-center gap-2">
                            <i class="ph-fill ph-sliders text-sky-400"></i>
                            <span>İZDO 2026 Kampanyalı Ünit Seçimi</span>
                        </h3>
                        <p class="text-xs text-gray-400">İZDO 33. Kongre fiyat listesindeki birebir konfigürasyonu seçin.</p>
                    </div>

                    <div class="grid grid-cols-2 gap-2 max-h-60 overflow-y-auto pr-1">
                        <button onclick="selectUnitModel('S200_ORTHO')" id="model-S200_ORTHO" class="model-btn p-2.5 rounded-xl border border-white/10 bg-gray-900/60 text-left transition-all hover:border-sky-500/40">
                            <div class="font-bold text-xs text-white">S200 ORTHO</div>
                            <div class="text-[11px] font-mono text-emerald-400">9.500 €</div>
                        </button>
                        <button onclick="selectUnitModel('S200')" id="model-S200" class="model-btn p-2.5 rounded-xl border border-sky-500 bg-sky-500/15 text-left transition-all">
                            <div class="font-bold text-xs text-white">S200 Standart</div>
                            <div class="text-[11px] font-mono text-sky-300">12.000 €</div>
                        </button>
                        <button onclick="selectUnitModel('S220TR')" id="model-S220TR" class="model-btn p-2.5 rounded-xl border border-white/10 bg-gray-900/60 text-left transition-all hover:border-sky-500/40">
                            <div class="font-bold text-xs text-white">220 TR</div>
                            <div class="text-[11px] font-mono text-emerald-400">13.500 €</div>
                        </button>
                        <button onclick="selectUnitModel('S200_GOLD')" id="model-S200_GOLD" class="model-btn p-2.5 rounded-xl border border-white/10 bg-gray-900/60 text-left transition-all hover:border-sky-500/40">
                            <div class="font-bold text-xs text-white">S200 GOLD</div>
                            <div class="text-[11px] font-mono text-emerald-400">14.500 €</div>
                        </button>
                        <button onclick="selectUnitModel('S300')" id="model-S300" class="model-btn p-2.5 rounded-xl border border-white/10 bg-gray-900/60 text-left transition-all hover:border-sky-500/40">
                            <div class="font-bold text-xs text-white">S300 (Hediyeli)</div>
                            <div class="text-[11px] font-mono text-emerald-400">15.500 €</div>
                        </button>
                        <button onclick="selectUnitModel('S280TRC')" id="model-S280TRC" class="model-btn p-2.5 rounded-xl border border-white/10 bg-gray-900/60 text-left transition-all hover:border-sky-500/40">
                            <div class="font-bold text-xs text-white">280 TRC Asansörlü</div>
                            <div class="text-[11px] font-mono text-emerald-400">17.500 €</div>
                        </button>
                        <button onclick="selectUnitModel('S380TRC_VIP')" id="model-S380TRC_VIP" class="model-btn p-2.5 rounded-xl border border-white/10 bg-gray-900/60 text-left transition-all hover:border-sky-500/40">
                            <div class="font-bold text-xs text-white">VIP 380 TRC</div>
                            <div class="text-[11px] font-mono text-emerald-400">25.000 €</div>
                        </button>
                        <button onclick="selectUnitModel('S380TRC_GOLD')" id="model-S380TRC_GOLD" class="model-btn p-2.5 rounded-xl border border-white/10 bg-gray-900/60 text-left transition-all hover:border-sky-500/40">
                            <div class="font-bold text-xs text-white">VIP 380 TRC GOLD</div>
                            <div class="text-[11px] font-mono text-amber-300">45.000 €</div>
                        </button>
                        <button onclick="selectUnitModel('SF8000C_IMP')" id="model-SF8000C_IMP" class="model-btn p-2.5 rounded-xl border border-white/10 bg-gray-900/60 text-left transition-all hover:border-sky-500/40">
                            <div class="font-bold text-xs text-white">Silverfox C Implant</div>
                            <div class="text-[11px] font-mono text-purple-300">8.500 $</div>
                        </button>
                        <button onclick="selectUnitModel('SF8000C')" id="model-SF8000C" class="model-btn p-2.5 rounded-xl border border-white/10 bg-gray-900/60 text-left transition-all hover:border-sky-500/40">
                            <div class="font-bold text-xs text-white">Silverfox C Pro</div>
                            <div class="text-[11px] font-mono text-sky-400">6.950 $</div>
                        </button>
                        <button onclick="selectUnitModel('SF8000B')" id="model-SF8000B" class="model-btn p-2.5 rounded-xl border border-white/10 bg-gray-900/60 text-left transition-all hover:border-sky-500/40 col-span-2">
                            <div class="flex justify-between items-center">
                                <span class="font-bold text-xs text-white">Silverfox Model B</span>
                                <span class="text-[11px] font-mono text-sky-400">3.950 $</span>
                            </div>
                        </button>
                    </div>

                    <div class="grid grid-cols-2 gap-2 pt-1">
                        <button onclick="setArmType('continental')" id="arm-continental" class="py-2 px-3 rounded-xl border border-sky-500 bg-sky-500/15 text-xs font-semibold text-white flex items-center justify-center gap-1.5">
                            <i class="ph-bold ph-bezier-curve text-sky-400"></i> Kamçılı
                        </button>
                        <button onclick="setArmType('international')" id="arm-international" class="py-2 px-3 rounded-xl border border-white/10 bg-gray-900/60 text-xs font-medium text-gray-300 flex items-center justify-center gap-1.5">
                            <i class="ph-bold ph-arrow-down-right"></i> Askılı
                        </button>
                    </div>

                    <!-- Tam Renk Kartelası (Marka ve Modele Göre Dinamik) -->
                    <div class="space-y-2">
                        <div class="flex flex-wrap justify-between items-center gap-1 text-xs">
                            <div id="upholstery-type-tabs" class="flex items-center gap-1 bg-gray-900 p-0.5 rounded-lg border border-white/10"></div>
                            <span id="selected-color-label" class="font-semibold text-sky-400 text-[11px]">102 Atlantic Blue</span>
                        </div>
                        <div id="upholstery-swatches-container" class="grid grid-cols-5 gap-1.5 max-h-48 overflow-y-auto pr-1"></div>
                    </div>

                    <div class="pt-2 flex items-center gap-2">
                        <div class="bg-gray-900 border border-white/15 rounded-xl px-2.5 py-2 flex items-center gap-1.5 shrink-0">
                            <span class="text-xs text-gray-400">Adet:</span>
                            <input type="number" id="unit-qty-input" value="1" min="1" max="20" onchange="recalcUnitPrice()" class="w-10 bg-transparent text-white font-bold text-sm text-center focus:outline-none">
                        </div>
                        <button onclick="addConfiguredUnitSummaryToProposal()" class="flex-1 py-2.5 px-3 rounded-xl bg-sky-500 hover:bg-sky-400 text-white font-bold text-xs shadow-lg flex items-center justify-center gap-1.5 transition-all">
                            <i class="ph-bold ph-plus-circle text-base"></i>
                            <span id="btn-add-unit-summary">Özet Olarak Teklife Ekle</span>
                        </button>
                    </div>
                </div>
            </div>

            <!-- CANLI KONFİGÜRASYON FÖYÜ -->
            <div class="glass-panel rounded-3xl p-6 border border-white/10 space-y-4">
                <div class="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
                    <div>
                        <div class="flex items-center gap-2">
                            <span class="px-2.5 py-0.5 rounded-full bg-sky-500/20 text-sky-300 text-[11px] font-bold">CANLI KONFİGÜRASYON FÖYÜ</span>
                            <span id="sheet-unit-name" class="font-display font-bold text-lg text-white">Stern Weber S200 (12.000 €)</span>
                        </div>
                        <p class="text-xs text-gray-400 mt-0.5">Satırları doğrudan düzenleyebilir, opsiyonel eklenti ekleyebilir ve teklife aktarabilirsiniz.</p>
                    </div>
                    <div class="flex flex-wrap items-center gap-2">
                        <button onclick="resetCurrentUnitSheet()" class="px-3 py-1.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs font-semibold flex items-center gap-1">
                            <i class="ph-bold ph-arrow-counter-clockwise"></i> Föyü Sıfırla
                        </button>
                        <button onclick="pushEntireSheetToProposal()" class="px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white text-xs font-bold shadow-lg flex items-center gap-1.5">
                            <i class="ph-bold ph-file-arrow-up text-base"></i> Tüm Satırları Teklife Aktar
                        </button>
                    </div>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-12 gap-3 p-3 rounded-2xl bg-gray-900/80 border border-white/10 items-center text-xs">
                    <div class="md:col-span-7">
                        <label class="block text-gray-400 mb-1 font-semibold">İZDO / TDB Opsiyonel Eklenti Kütüphanesi (55 Kalem):</label>
                        <select id="tdb-opt-select" onchange="handleTdbOptSelectChange()" class="w-full bg-gray-800 border border-white/15 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-sky-400"></select>
                    </div>
                    <div class="md:col-span-3">
                        <label class="block text-gray-400 mb-1 font-semibold">Durum / Fiyat:</label>
                        <div class="flex items-center gap-2">
                            <input type="text" id="tdb-opt-status-input" value="OPSİYONEL" class="w-24 bg-gray-800 border border-white/15 rounded-xl px-2 py-2 text-white text-center font-bold">
                            <input type="number" id="tdb-opt-price-input" value="0" class="w-24 bg-gray-800 border border-white/15 rounded-xl px-2 py-2 text-white text-right font-mono font-bold">
                            <span class="text-gray-400 font-bold">€</span>
                        </div>
                    </div>
                    <div class="md:col-span-2 flex items-end">
                        <button onclick="addSelectedTdbOptionToSheet()" class="w-full py-2 rounded-xl bg-sky-500 hover:bg-sky-400 text-white font-bold flex items-center justify-center gap-1 transition-all mt-4 md:mt-0">
                            <i class="ph-bold ph-plus"></i> Listeye Ekle
                        </button>
                    </div>
                </div>

                <div class="overflow-x-auto rounded-2xl border border-white/10">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-gray-900 text-[11px] font-mono uppercase text-gray-400 border-b border-white/10">
                                <th class="py-2.5 px-3 w-10 text-center">#</th>
                                <th class="py-2.5 px-3 w-32">Kategori</th>
                                <th class="py-2.5 px-3">Donanım Açıklaması</th>
                                <th class="py-2.5 px-3 w-28 text-center">Durum</th>
                                <th class="py-2.5 px-3 w-28 text-right">Fiyat</th>
                                <th class="py-2.5 px-2 w-20 text-center">İşlem</th>
                            </tr>
                        </thead>
                        <tbody id="unit-sheet-tbody" class="divide-y divide-white/5 text-xs bg-gray-950/50"></tbody>
                        <tfoot>
                            <tr class="bg-gray-900/90 border-t border-white/15 font-bold text-xs">
                                <td colspan="3" class="py-3 px-4 text-sky-400" id="sheet-footer-note">Fiyatlara KDV dahil değildir.</td>
                                <td class="py-3 px-3 text-right text-gray-300">TOPLAM:</td>
                                <td id="sheet-total-price" class="py-3 px-3 text-right font-mono text-base text-emerald-400 font-bold">12.000 €</td>
                                <td></td>
                            </tr>
                        </tfoot>
                    </table>
                </div>

                <div class="flex flex-wrap sm:flex-nowrap items-center gap-2 pt-1 text-xs">
                    <input type="text" id="sheet-custom-cat" placeholder="Bölüm (Örn: HİJYEN)" class="w-32 bg-gray-800 border border-white/10 rounded-xl px-3 py-2 text-white">
                    <input type="text" id="sheet-custom-desc" placeholder="Özel donanım veya not girin..." class="flex-1 bg-gray-800 border border-white/10 rounded-xl px-3 py-2 text-white">
                    <input type="text" id="sheet-custom-status" value="STANDART" class="w-24 bg-gray-800 border border-white/10 rounded-xl px-2 py-2 text-center text-white font-semibold">
                    <input type="number" id="sheet-custom-price" value="0" placeholder="€" class="w-20 bg-gray-800 border border-white/10 rounded-xl px-2 py-2 text-right text-white font-mono">
                    <button onclick="addCustomRowToSheet()" class="px-4 py-2 rounded-xl bg-sky-500/20 hover:bg-sky-500 text-sky-300 hover:text-white border border-sky-500/30 font-bold whitespace-nowrap">+ Yeni Satır</button>
                </div>
            </div>
        </section>

        <!-- SEKME 2: MYRAY, DABI ATLANTE & İZDO 2026 PAKETLERİ -->
        <section id="view-imaging" class="hidden space-y-6">
            <div class="glass-panel rounded-3xl p-6 sm:p-8 border border-white/10 space-y-6">
                <div class="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-5">
                    <div>
                        <span class="text-xs uppercase tracking-widest text-purple-400 font-bold">İZDO 33. DİŞ HEKİMLİĞİ KONGRESİ • GÖRÜNTÜLEME & KAMPANYA PAKETLERİ</span>
                        <h2 class="font-display text-2xl sm:text-3xl font-bold text-white mt-1">MyRay, Dabi Atlante Tomografi, Tarayıcı & Özel Klinik Paketleri</h2>
                        <p class="text-xs sm:text-sm text-gray-400 mt-1">İZDO 2026 Kampanyalı Fiyat Listesindeki birebir hediye ve vade avantajlarıyla.</p>
                    </div>
                    <button onclick="switchTab('proposal')" class="px-4 py-2.5 rounded-xl bg-purple-500/20 hover:bg-purple-500/30 border border-purple-500/40 text-purple-300 text-xs font-semibold flex items-center gap-2">
                        <i class="ph-bold ph-file-xls"></i> Teklif Tablosuna Git
                    </button>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                    <div class="glass-card rounded-2xl p-5 border border-purple-500/30 flex flex-col justify-between space-y-3">
                        <div>
                            <div class="flex justify-between items-center">
                                <span class="text-[10px] font-mono text-purple-300 bg-purple-500/20 px-2 py-0.5 rounded font-bold">MYSCAN WR AI HEDİYE</span>
                                <span class="font-bold text-base text-emerald-400">39.999 €</span>
                            </div>
                            <h4 class="font-display font-bold text-white text-lg mt-1.5">MyRay ProXima X6 Air 3D+2D</h4>
                            <p class="text-xs text-gray-400 mt-1">11x11 / 11x15 FOV, 80 µm Voxel, NeoWise AI, 25 Kullanıcı Lisansı + PC ve <strong class="text-purple-300">MyScan WR AI Tarayıcı Hediye</strong>. (9.999 € Peşin + 20 Ay Vade)</p>
                        </div>
                        <button onclick="addItemToProposal('GÖRÜNTÜLEME', 'MYRAY PROXIMA X6 AIR 3D+2D TOMOGRAFİ 11X15 FOV + PC + NEOWISE AI + MYSCAN WR TARAYICI HEDİYE (İTALYA)', 1, 39999)" class="w-full py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold transition-all">
                            + ProXima X6 3D Ekle (39.999 €)
                        </button>
                    </div>

                    <div class="glass-card rounded-2xl p-5 border border-sky-500/30 flex flex-col justify-between space-y-3">
                        <div>
                            <div class="flex justify-between items-center">
                                <span class="text-[10px] font-mono text-sky-300 bg-sky-500/20 px-2 py-0.5 rounded font-bold">X-VS AI RVG HEDİYE</span>
                                <span class="font-bold text-base text-sky-400">13.999 €</span>
                            </div>
                            <h4 class="font-display font-bold text-white text-lg mt-1.5">MyRay ProXima X6 Panoramik</h4>
                            <p class="text-xs text-gray-400 mt-1">Katmanlı Panoramik, NeoWise AI, Sınırsız Kullanıcı + PC ve <strong class="text-sky-300">MyRay X-VS HD RVG Size 1 Hediye</strong>. (3.999 € Peşin + 10 Ay Vade)</p>
                        </div>
                        <button onclick="addItemToProposal('GÖRÜNTÜLEME', 'MYRAY PROXIMA X6 PANORAMİK + PC + NEOWISE AI + MYRAY X-VS HD RVG SENSÖR HEDİYE (İTALYA)', 1, 13999)" class="w-full py-2 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-bold transition-all">
                            + ProXima X6 Panoramik Ekle (13.999 €)
                        </button>
                    </div>

                    <div class="glass-card rounded-2xl p-5 border border-indigo-500/30 flex flex-col justify-between space-y-3">
                        <div>
                            <div class="flex justify-between items-center">
                                <span class="text-[10px] font-mono text-indigo-300 bg-indigo-500/20 px-2 py-0.5 rounded font-bold">10x8 / 13x16 DC FOV</span>
                                <span class="font-bold text-base text-white">49.500 € / 65.000 €</span>
                            </div>
                            <h4 class="font-display font-bold text-white text-lg mt-1.5">MyRay Hyperion X9 Pro</h4>
                            <p class="text-xs text-gray-400 mt-1">10x8 FOV (Tablet Dahil) 49.500 € veya Direct Sensör DC 13x16 FOV (10 Kullanıcı) 65.000 €.</p>
                        </div>
                        <div class="grid grid-cols-2 gap-2">
                            <button onclick="addItemToProposal('GÖRÜNTÜLEME', 'MYRAY X9 PRO 10X8 FOV ALANI TABLET DAHİL (İTALYA)', 1, 49500)" class="py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-[11px] font-semibold">
                                + X9 Pro (49.500 €)
                            </button>
                            <button onclick="addItemToProposal('GÖRÜNTÜLEME', 'MYRAY X9 PRO DIRECT SENSÖR DC 13X16 FOV TABLET DAHİL (İTALYA)', 1, 65000)" class="py-1.5 rounded-lg bg-indigo-800 hover:bg-indigo-700 text-white text-[11px] font-semibold">
                                + X9 DC (65.000 €)
                            </button>
                        </div>
                    </div>

                    <div class="glass-card rounded-2xl p-5 border border-amber-500/30 flex flex-col justify-between space-y-3">
                        <div>
                            <div class="flex justify-between items-center">
                                <span class="text-[10px] font-mono text-amber-300 bg-amber-500/20 px-2 py-0.5 rounded font-bold">DABI ATLANTE • RVG/IOS HEDİYE</span>
                                <span class="font-bold text-base text-amber-300">29.999 $ / 59.999 $</span>
                            </div>
                            <h4 class="font-display font-bold text-white text-lg mt-1.5">Dabi Atlante Eagle Edge 3D</h4>
                            <p class="text-xs text-gray-400 mt-1">9x14 FOV + New IDA RVG Hediye (29.999 $) veya 16x21 FOV + Eagle iOS Tarayıcı + RVG Hediye (59.999 $).</p>
                        </div>
                        <div class="grid grid-cols-2 gap-2">
                            <button onclick="addItemToProposal('GÖRÜNTÜLEME', 'DABI ATLANTE EAGLE EDGE 9X14 FOV TOMOGRAFİ + PC + NEW IDA RVG HEDİYE ($)', 1, 29999)" class="py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-[11px] font-semibold">
                                + 9x14 (29.999 $)
                            </button>
                            <button onclick="addItemToProposal('GÖRÜNTÜLEME', 'DABI ATLANTE EAGLE EDGE 16X21 FOV TOMOGRAFİ + EAGLE IOS TARAYICI + RVG HEDİYE ($)', 1, 59999)" class="py-1.5 rounded-lg bg-amber-800 hover:bg-amber-700 text-white text-[11px] font-semibold">
                                + 16x21 (59.999 $)
                            </button>
                        </div>
                    </div>

                    <div class="glass-card rounded-2xl p-5 border border-emerald-500/40 flex flex-col justify-between space-y-3">
                        <div>
                            <div class="flex justify-between items-center">
                                <span class="text-[10px] font-mono text-emerald-300 bg-emerald-500/20 px-2 py-0.5 rounded font-bold">İZDO ÖZEL KLİNİK PAKETİ</span>
                                <span class="font-bold text-base text-emerald-400">23.000 $</span>
                            </div>
                            <h4 class="font-display font-bold text-white text-lg mt-1.5">Anahtar Teslim Klinik Paketi</h4>
                            <p class="text-xs text-gray-400 mt-1">Dabi Atlante Edge AI Panoramik + PC + Silverfox Model B Full Ünit + Yeson 23L Otoklav Set + GAP 100L Kompresör + Woodpecker Miniray + i-Sensör + Strong.</p>
                        </div>
                        <button onclick="addItemToProposal('KLİNİK PAKETİ', 'İZDO 33. KONGRE KOMPLE KLİNİK PAKETİ: DABI ATLANTE PANORAMİK + PC + SILVERFOX B FULL ÜNİT + YESON 23L OTOKLAV SET + GAP 100L KOMPRESÖR + MINIRAY + I-SENSOR + STRONG ($)', 1, 23000)" class="w-full py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition-all">
                            + Komple Klinik Paketini Ekle (23.000 $)
                        </button>
                    </div>

                    <div class="glass-card rounded-2xl p-5 border border-white/10 flex flex-col justify-between space-y-3">
                        <div>
                            <div class="flex justify-between items-center">
                                <span class="text-[10px] font-mono text-gray-300 bg-gray-800 px-2 py-0.5 rounded font-bold">MYRAY & Hİ-SCAN</span>
                                <span class="font-bold text-base text-white">3.350 € - 34.000 €</span>
                            </div>
                            <h4 class="font-display font-bold text-white text-lg mt-1.5">X5 Air 3D, Hi-Scan & X-Pod</h4>
                            <p class="text-xs text-gray-400 mt-1">X5 Air 3D 10x10 + PC (34.000 €), X5 Air 2D (12.750 €), Hi-Scan Fosfor Plak (3.500 €), X-Pod RVG (3.350 €).</p>
                        </div>
                        <div class="grid grid-cols-2 gap-2">
                            <button onclick="addItemToProposal('GÖRÜNTÜLEME', 'MYRAY X5 AIR 3D 10X10 + PC (İTALYA)', 1, 34000)" class="py-1.5 rounded-lg bg-gray-800 hover:bg-sky-500 text-white text-[11px] font-semibold">
                                + X5 3D (34.000 €)
                            </button>
                            <button onclick="addItemToProposal('GÖRÜNTÜLEME', 'HI-SCAN FOSFOR PLAK TARAYICI 0,1,2,3,4 PLAK SETİ', 1, 3500)" class="py-1.5 rounded-lg bg-gray-800 hover:bg-sky-500 text-white text-[11px] font-semibold">
                                + Hi-Scan (3.500 €)
                            </button>
                        </div>
                    </div>
                </div>

                <!-- PAKETSİZ TEKİL GÖRÜNTÜLEME CİHAZLARI KATALOĞU -->
                <div class="pt-6 border-t border-white/10 space-y-4">
                    <div class="flex flex-wrap items-center justify-between gap-3">
                        <div>
                            <span class="text-[11px] font-mono uppercase tracking-widest text-sky-400 font-bold">PAKETSİZ TEKİL CİHAZ SEÇİMİ</span>
                            <h3 class="font-display text-xl font-bold text-white">MyRay, Dabi Atlante & Woodpecker Tekil Ürün Listesi</h3>
                            <p class="text-xs text-gray-400">Kampanya paketi olmadan dilediğiniz cihazı, sensörü veya ataçmanı tek tek teklife ekleyin.</p>
                        </div>
                        <div class="flex flex-wrap items-center gap-2">
                            <div class="flex items-center gap-1 bg-gray-900 p-1 rounded-xl border border-white/10 text-xs">
                                <button onclick="filterSingleImaging('ALL')" id="img-flt-ALL" class="px-3 py-1.5 rounded-lg bg-sky-500 text-white font-bold">Tümü</button>
                                <button onclick="filterSingleImaging('MYRAY')" id="img-flt-MYRAY" class="px-3 py-1.5 rounded-lg text-gray-400 hover:text-white font-semibold">MyRay</button>
                                <button onclick="filterSingleImaging('DABI')" id="img-flt-DABI" class="px-3 py-1.5 rounded-lg text-gray-400 hover:text-white font-semibold">Dabi Atlante</button>
                                <button onclick="filterSingleImaging('WOODPECKER')" id="img-flt-WOODPECKER" class="px-3 py-1.5 rounded-lg text-gray-400 hover:text-white font-semibold">Woodpecker</button>
                            </div>
                            <input type="text" id="single-imaging-search" oninput="renderSingleImagingList()" placeholder="Cihaz veya model ara..." class="bg-gray-900 border border-white/15 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-sky-400 w-48">
                        </div>
                    </div>

                    <div id="single-imaging-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3"></div>
                </div>
            </div>
        </section>

        <!-- SEKME 3: MGF & STERİLİZASYON -->
        <section id="view-calculator" class="hidden space-y-6">
            <div class="glass-panel rounded-3xl p-6 sm:p-8 border border-white/10 space-y-6">
                <div>
                    <span class="text-xs uppercase tracking-widest text-emerald-400 font-bold">MGF COMPRESSORS İTALYA (PRIME & HYBRID KATALOĞU) & STERİLİZASYON</span>
                    <h2 class="font-display text-2xl sm:text-3xl font-bold text-white mt-1">MGF Prime Kompresör, Hybrid Aspiratör, Aspir-Comp & Otoklav Sihirbazı</h2>
                    <p class="text-xs text-gray-400 mt-1">Resmi MGF Prime & Aspirazione katalog verilerine (debi, vakum mbar, tank hacmi ve dB) göre birebir mühendislik eşleştirmesi.</p>
                </div>
                <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
                    <div class="lg:col-span-5 space-y-4 bg-gray-900/70 p-5 rounded-2xl border border-white/10">
                        <div class="space-y-2">
                            <div class="flex justify-between items-center">
                                <label class="text-xs font-semibold text-gray-200">Klinikteki Ünit Sayısı</label>
                                <span id="calc-unit-val" class="px-2.5 py-0.5 rounded-lg bg-sky-500/20 text-sky-300 font-bold text-base">1 Ünit</span>
                            </div>
                            <input type="range" id="calc-units" min="1" max="18" value="1" oninput="updateEngineeringCalc()" class="w-full accent-sky-500 cursor-pointer h-2 bg-gray-800 rounded-lg">
                            <div class="flex justify-between text-[10px] text-gray-500 font-mono">
                                <span>1</span><span>3</span><span>6</span><span>9</span><span>12</span><span>15</span><span>18 Ünit</span>
                            </div>
                        </div>
                        <div class="space-y-1.5">
                            <label class="text-xs font-semibold uppercase text-gray-400">Kompresör Tipi (Kurutucu / Kabin)</label>
                            <select id="calc-comp-type" onchange="updateEngineeringCalc()" class="w-full bg-gray-800 border border-white/15 rounded-xl px-3 py-2 text-xs text-white">
                                <option value="M" selected>PRIME M: Membran Kurutuculu (-20°C)</option>
                                <option value="CS-M">CS / MINI BOX PRIME M: Sessiz Kabinli + Kurutuculu</option>
                                <option value="S">PRIME S: Standart (Kurutucusuz)</option>
                                <option value="CS-S">CS / MINI BOX PRIME S: Sessiz Kabinli (Kurutucusuz)</option>
                            </select>
                        </div>
                        <div class="space-y-1.5">
                            <label class="text-xs font-semibold uppercase text-gray-400">Aspiratör Teknolojisi</label>
                            <div class="grid grid-cols-2 gap-2">
                                <button onclick="setSuctionType('hybrid')" id="suction-hybrid" class="py-2 px-3 rounded-xl border border-sky-500 bg-sky-500/15 text-xs font-semibold text-white">MGF HYBRID (Yarı Islak)</button>
                                <button onclick="setSuctionType('dry')" id="suction-dry" class="py-2 px-3 rounded-xl border border-white/10 bg-gray-800 text-xs font-medium text-gray-400">MGF ASPIR / SILENT (Kuru)</button>
                            </div>
                        </div>
                        <label class="flex items-center justify-between p-2.5 rounded-xl bg-gray-800/80 border border-white/10 cursor-pointer">
                            <span class="text-xs font-semibold text-white">ECO II+ Amalgam Ayırıcı (-AS, %99.3)</span>
                            <input type="checkbox" id="calc-amalgam" onchange="updateEngineeringCalc()" class="w-4 h-4 accent-emerald-500 rounded">
                        </label>
                        <label class="flex items-center justify-between p-2.5 rounded-xl bg-gray-800/80 border border-white/10 cursor-pointer">
                            <span class="text-xs font-semibold text-white">Aspiratör Sessiz Kabin / Kapak (-S / CA-CR-060)</span>
                            <input type="checkbox" id="calc-vac-cabinet" onchange="updateEngineeringCalc()" class="w-4 h-4 accent-sky-500 rounded">
                        </label>
                        <div class="space-y-1.5">
                            <label class="text-xs font-semibold uppercase text-gray-400">Otoklav Seçimi</label>
                            <select id="calc-steril-brand" onchange="updateEngineeringCalc()" class="w-full bg-gray-800 border border-white/15 rounded-xl px-3 py-2 text-xs text-white">
                                <option value="YESON" selected>Yeson Daslav S 23L B-Class Set (2.000 €)</option>
                                <option value="SW_PLATINUM">Stern Weber SW Platinum 22/28 (Millseal Dahil)</option>
                                <option value="SW_PLUS">Stern Weber SW 22/28 3'lü Set</option>
                            </select>
                        </div>
                    </div>

                    <div class="lg:col-span-7 grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <!-- KOMPRESÖR KARTI -->
                        <div class="glass-card rounded-2xl p-4 border border-sky-500/30 flex flex-col justify-between space-y-3">
                            <div class="space-y-1.5">
                                <div class="flex items-center justify-between">
                                    <span class="text-[10px] font-mono uppercase text-sky-400 font-bold">MGF PRIME KOMPRESÖR</span>
                                    <span id="out-comp-tank" class="text-[10px] font-mono text-gray-400">24 L • 1 HP</span>
                                </div>
                                <h4 id="out-comp-title" class="font-bold text-white text-base">MGF 30/7 PRIME M</h4>
                                <div id="out-comp-code" class="text-xs font-mono text-sky-300">PR-OF100-024-M</div>
                                <div class="text-xs text-gray-400 space-y-0.5 pt-2 border-t border-white/10">
                                    <div class="flex justify-between"><span>Debi (@ 5 bar):</span> <strong id="out-air-lpm" class="text-white">85 l/dk</strong></div>
                                    <div class="flex justify-between"><span>Ses Seviyesi:</span> <span id="out-comp-noise" class="text-emerald-400">65 dB(A)</span></div>
                                    <div class="flex justify-between"><span>Kapasite:</span> <span id="out-comp-cap" class="text-gray-200">1 Ünit</span></div>
                                </div>
                            </div>
                            <div class="pt-2 flex items-center justify-between">
                                <span id="out-comp-price" class="font-bold text-sm text-emerald-400">1.650 €</span>
                                <button onclick="addCalculatedCompToProposal()" class="px-3 py-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-white text-xs font-bold">+ Ekle</button>
                            </div>
                        </div>

                        <!-- ASPİRATÖR KARTI -->
                        <div class="glass-card rounded-2xl p-4 border border-emerald-500/30 flex flex-col justify-between space-y-3">
                            <div class="space-y-1.5">
                                <div class="flex items-center justify-between">
                                    <span class="text-[10px] font-mono uppercase text-emerald-400 font-bold">MGF CERRAHİ ASPİRATÖR</span>
                                    <span id="out-vac-noise" class="text-[10px] font-mono text-gray-400">63 dB(A)</span>
                                </div>
                                <h4 id="out-vac-title" class="font-bold text-white text-base">MGF HYBRID 1S</h4>
                                <div id="out-vac-code" class="text-xs font-mono text-emerald-300">AS-075-EX</div>
                                <div class="text-xs text-gray-400 space-y-0.5 pt-2 border-t border-white/10">
                                    <div class="flex justify-between"><span>Emiş Debisi:</span> <strong id="out-vac-lpm" class="text-white">1.100 l/dk</strong></div>
                                    <div class="flex justify-between"><span>Maks. Vakum:</span> <span id="out-vac-mbar" class="text-gray-200">120/140 mbar</span></div>
                                    <div class="flex justify-between"><span>Kapasite:</span> <span id="out-vac-cap" class="text-gray-200">1 Simultane / 1-2 Ünit</span></div>
                                </div>
                            </div>
                            <div class="pt-2 flex items-center justify-between">
                                <span id="out-vac-price" class="font-bold text-sm text-emerald-400">1.300 €</span>
                                <button onclick="addCalculatedVacToProposal()" class="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold">+ Ekle</button>
                            </div>
                        </div>

                        <!-- ASPIR-COMP 2-IN-1 ÖNERİ KARTI (1-4 ÜNİT) -->
                        <div id="aspir-comp-card" class="glass-card rounded-2xl p-4 border border-cyan-500/30 flex flex-col justify-between space-y-3 sm:col-span-2">
                            <div class="space-y-1">
                                <div class="flex items-center justify-between">
                                    <span class="text-[10px] font-mono uppercase text-cyan-400 font-bold">2-IN-1 ENTEGRE ÇÖZÜM (KOMPRESÖR + ASPİRATÖR TEK KABİN)</span>
                                    <span id="out-ac-noise" class="text-[10px] font-mono text-emerald-400">52-55 dB(A)</span>
                                </div>
                                <div class="flex justify-between items-center gap-2">
                                    <h4 id="out-ac-title" class="font-bold text-white text-sm">ASPIR-COMP 24/10 GENESI MC (Hybrid 1S)</h4>
                                    <span id="out-ac-price" class="font-bold text-sm text-cyan-300 shrink-0">6.500 €</span>
                                </div>
                                <p id="out-ac-desc" class="text-xs text-gray-400">Kod: D-AC150-024-MC • 1-2 Ünitlik kompakt sessiz kabin (0.26 m²).</p>
                            </div>
                            <button onclick="addCalculatedAspirCompToProposal()" class="w-full py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-bold">+ 2-in-1 Aspir-Comp Sistemini Teklife Ekle</button>
                        </div>

                        <!-- STERİLİZASYON KARTI -->
                        <div class="glass-card rounded-2xl p-4 border border-amber-500/30 flex flex-col justify-between space-y-3 sm:col-span-2">
                            <div class="space-y-1.5">
                                <span class="text-[10px] font-mono uppercase text-amber-400 font-bold">STERİLİZASYON PARKURU</span>
                                <div class="flex justify-between items-center">
                                    <h4 id="out-steril-cap" class="font-bold text-white text-base">Yeson Daslav S 23L B-Class Set</h4>
                                    <span id="out-steril-price" class="font-bold text-base text-amber-300">2.000 €</span>
                                </div>
                                <p class="text-xs text-gray-400">Kapama Cihazı + Distile Su + Dahili Yazıcı Dahil Komple Set.</p>
                            </div>
                            <button onclick="addCalculatedSterilToProposal()" class="w-full py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold">+ Otoklav Paketini Teklife Ekle</button>
                        </div>
                    </div>
                </div>

                <!-- MGF TEKİL ÜRÜN & AKSESUAR KATALOĞU (İZDO 2026 FİYATLARI) -->
                <div class="pt-5 border-t border-white/10 space-y-3">
                    <div class="flex flex-wrap items-center justify-between gap-2">
                        <div>
                            <span class="text-[10px] font-mono uppercase text-sky-400 font-bold">İZDO 2026 MGF TEKİL LİSTE & AKSESUARLAR</span>
                            <h3 class="font-display text-lg font-bold text-white">Doğrudan Tekil MGF Modeli veya Kabin Ekle</h3>
                        </div>
                    </div>
                    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 text-xs">
                        <button onclick="addItemToProposal('ASPİRATÖR', 'MGF ASPİRATÖR HYBRID 1S (AS-075-EX • 1-2 ÜNİT • 1.100 Lt/dk) (İTALYA)', 1, 1300)" class="p-3 rounded-xl bg-gray-900/80 hover:bg-emerald-600/20 border border-white/10 hover:border-emerald-500/40 text-left transition-all">
                            <div class="font-bold text-white">MGF Hybrid 1S</div>
                            <div class="text-[10px] text-gray-400">1 Ünit • 1.100 l/dk • AS-075-EX</div>
                            <div class="font-mono font-bold text-emerald-400 mt-1">1.300 €</div>
                        </button>
                        <button onclick="addItemToProposal('ASPİRATÖR', 'MGF ASPİRATÖR HYBRID 1 (AS-094-EX • 2 ÜNİT • 1.300 Lt/dk) (İTALYA)', 1, 2250)" class="p-3 rounded-xl bg-gray-900/80 hover:bg-emerald-600/20 border border-white/10 hover:border-emerald-500/40 text-left transition-all">
                            <div class="font-bold text-white">MGF Hybrid 1</div>
                            <div class="text-[10px] text-gray-400">2 Ünit • 1.300 l/dk • AS-094-EX</div>
                            <div class="font-mono font-bold text-emerald-400 mt-1">2.250 €</div>
                        </button>
                        <button onclick="addItemToProposal('ASPİRATÖR', 'MGF ASPİRATÖR HYBRID 2 (AS-100-EX • 3 ÜNİT • 1.500 Lt/dk) (İTALYA)', 1, 2950)" class="p-3 rounded-xl bg-gray-900/80 hover:bg-emerald-600/20 border border-white/10 hover:border-emerald-500/40 text-left transition-all">
                            <div class="font-bold text-white">MGF Hybrid 2</div>
                            <div class="text-[10px] text-gray-400">3 Ünit • 1.500 l/dk • AS-100-EX</div>
                            <div class="font-mono font-bold text-emerald-400 mt-1">2.950 €</div>
                        </button>
                        <button onclick="addItemToProposal('ASPİRATÖR', 'MGF ASPİRATÖR HYBRID 5 İNVERTERLİ (AS-150-EX • 4-6 ÜNİT • 2.500 Lt/dk) (İTALYA)', 1, 4150)" class="p-3 rounded-xl bg-gray-900/80 hover:bg-emerald-600/20 border border-white/10 hover:border-emerald-500/40 text-left transition-all">
                            <div class="font-bold text-white">MGF Hybrid 5</div>
                            <div class="text-[10px] text-gray-400">4-6 Ünit • 2.500 l/dk • AS-150-EX</div>
                            <div class="font-mono font-bold text-emerald-400 mt-1">4.150 €</div>
                        </button>
                        <button onclick="addItemToProposal('KOMPRESÖR', 'MGF KOMPRESÖR PRIME S 50/15 (PR-OF200-040 • 2-3 ÜNİT • 170 Lt/dk) (İTALYA)', 1, 1650)" class="p-3 rounded-xl bg-gray-900/80 hover:bg-sky-600/20 border border-white/10 hover:border-sky-500/40 text-left transition-all">
                            <div class="font-bold text-white">Prime S 50/15</div>
                            <div class="text-[10px] text-gray-400">2-3 Ünit • 170 l/dk • 40L</div>
                            <div class="font-mono font-bold text-sky-400 mt-1">1.650 €</div>
                        </button>
                        <button onclick="addItemToProposal('KOMPRESÖR', 'MGF KOMPRESÖR PRIME M 50/15 KURUTUCULU (PR-OF200-040-M • 2-3 ÜNİT) (İTALYA)', 1, 2350)" class="p-3 rounded-xl bg-gray-900/80 hover:bg-sky-600/20 border border-white/10 hover:border-sky-500/40 text-left transition-all">
                            <div class="font-bold text-white">Prime M 50/15</div>
                            <div class="text-[10px] text-gray-400">2-3 Ünit • Kurutuculu • 152 l/dk</div>
                            <div class="font-mono font-bold text-sky-400 mt-1">2.350 €</div>
                        </button>
                        <button onclick="addItemToProposal('KOMPRESÖR', 'MGF KOMPRESÖR PRIME S 50/25 (PR-OF300-040 • 3-4 ÜNİT • 250 Lt/dk) (İTALYA)', 1, 2350)" class="p-3 rounded-xl bg-gray-900/80 hover:bg-sky-600/20 border border-white/10 hover:border-sky-500/40 text-left transition-all">
                            <div class="font-bold text-white">Prime S 50/25</div>
                            <div class="text-[10px] text-gray-400">3-4 Ünit • 250 l/dk • 40L</div>
                            <div class="font-mono font-bold text-sky-400 mt-1">2.350 €</div>
                        </button>
                        <button onclick="addItemToProposal('KOMPRESÖR', 'MGF KOMPRESÖR PRIME M 50/25 KURUTUCULU (PR-OF300-040-M • 3-4 ÜNİT) (İTALYA)', 1, 3250)" class="p-3 rounded-xl bg-gray-900/80 hover:bg-sky-600/20 border border-white/10 hover:border-sky-500/40 text-left transition-all">
                            <div class="font-bold text-white">Prime M 50/25</div>
                            <div class="text-[10px] text-gray-400">3-4 Ünit • Kurutuculu • 225 l/dk</div>
                            <div class="font-mono font-bold text-sky-400 mt-1">3.250 €</div>
                        </button>
                        <button onclick="addItemToProposal('KOMPRESÖR', 'MGF KOMPRESÖR TANDEM 100/30 PRIME M (PR-OF400-090-MT • 4-6 ÜNİT) (İTALYA)', 1, 7000)" class="p-3 rounded-xl bg-gray-900/80 hover:bg-sky-600/20 border border-white/10 hover:border-sky-500/40 text-left transition-all">
                            <div class="font-bold text-white">Tandem 100/30 M</div>
                            <div class="text-[10px] text-gray-400">4-6 Ünit • 305 l/dk • 90L</div>
                            <div class="font-mono font-bold text-sky-400 mt-1">7.000 €</div>
                        </button>
                        <button onclick="addItemToProposal('KOMPRESÖR', 'MGF KOMPRESÖR TANDEM 100/50 PRIME M (PR-OF600-090-MT • 6-8 ÜNİT) (İTALYA)', 1, 8000)" class="p-3 rounded-xl bg-gray-900/80 hover:bg-sky-600/20 border border-white/10 hover:border-sky-500/40 text-left transition-all">
                            <div class="font-bold text-white">Tandem 100/50 M</div>
                            <div class="text-[10px] text-gray-400">6-8 Ünit • 450 l/dk • 90L</div>
                            <div class="font-mono font-bold text-sky-400 mt-1">8.000 €</div>
                        </button>
                        <button onclick="addItemToProposal('AKSESUAR', 'MGF KOMPRESÖR SESSİZ KABİNİ (HAVALANDIRMA TERTİBATI İLE)', 1, 1650)" class="p-3 rounded-xl bg-gray-900/80 hover:bg-amber-600/20 border border-white/10 hover:border-amber-500/40 text-left transition-all">
                            <div class="font-bold text-white">Kompresör Kabini</div>
                            <div class="text-[10px] text-gray-400">Havalandırmalı Akustik Kabin</div>
                            <div class="font-mono font-bold text-amber-300 mt-1">1.650 €</div>
                        </button>
                        <button onclick="addItemToProposal('AKSESUAR', 'MGF ASPİRATÖR SESSİZ KABİNİ HYBRID 2-5 (CA-CR-060 • 47 dB)', 1, 1250)" class="p-3 rounded-xl bg-gray-900/80 hover:bg-amber-600/20 border border-white/10 hover:border-amber-500/40 text-left transition-all">
                            <div class="font-bold text-white">Aspiratör Kabini</div>
                            <div class="text-[10px] text-gray-400">Hybrid 2-5 • CA-CR-060 (47 dB)</div>
                            <div class="font-mono font-bold text-amber-300 mt-1">1.250 €</div>
                        </button>
                    </div>
                </div>
            </div>
        </section>

        <!-- SEKME 4: RESMİ TEKLİF OLUŞTURUCU -->
        <section id="view-proposal" class="hidden space-y-6">
            <div class="glass-panel rounded-3xl p-6 sm:p-8 border border-white/10 space-y-6">
                <div class="no-print flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
                    <div>
                        <span class="text-xs font-mono uppercase text-orange-400 font-bold">MANNAS DİŞ DEPOSU TİC. VE SAN. LTD. ŞTİ.</span>
                        <h2 class="font-display text-2xl font-bold text-white mt-0.5">Resmi Fiyat Teklifi (V.03 Şablonu)</h2>
                    </div>
                    <div class="flex flex-wrap items-center gap-2">
                        <button onclick="resetToBlankTemplate()" class="px-3 py-1.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs font-semibold">Boş Şablon</button>
                        <button onclick="clearProposalItems()" class="px-3 py-1.5 rounded-xl bg-rose-500/20 text-rose-300 hover:bg-rose-500 hover:text-white text-xs font-semibold">Temizle</button>
                        <button onclick="saveProposalToCRM()" class="px-3.5 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold flex items-center gap-1.5">
                            <i class="ph-bold ph-database"></i> CRM Görüşmelerine Kaydet
                        </button>
                        <button onclick="copyOfficialProposal()" class="px-3.5 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center gap-1.5">
                            <i class="ph-bold ph-whatsapp-logo"></i> Kopyala
                        </button>
                        <button onclick="openOfficialPrintModal()" class="px-3.5 py-1.5 rounded-xl bg-amber-500/20 hover:bg-amber-500 text-amber-300 hover:text-white border border-amber-500/40 text-xs font-bold flex items-center gap-1.5">
                            <i class="ph-bold ph-printer"></i> Önizle
                        </button>
                        <button onclick="downloadDirectPdf()" class="px-4 py-2 rounded-xl bg-gradient-to-r from-sky-500 to-blue-600 hover:from-sky-400 hover:to-blue-500 text-white text-xs font-bold shadow-lg flex items-center gap-1.5">
                            <i class="ph-bold ph-download-simple"></i> PDF İndir
                        </button>
                    </div>
                </div>

                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 bg-gray-900/70 p-4 rounded-2xl border border-white/10 text-xs">
                    <div>
                        <label class="text-gray-400 block mb-1 font-semibold">UNVAN (Müşteri / Hekim)</label>
                        <input type="text" id="prop-customer" placeholder="Örn: Sn. Dt. ..." class="w-full bg-gray-800 border border-white/10 rounded-lg px-3 py-2 text-white font-semibold">
                    </div>
                    <div>
                        <label class="text-gray-400 block mb-1 font-semibold">ADRES / ŞEHİR</label>
                        <input type="text" id="prop-city" placeholder="Örn: İSTANBUL" class="w-full bg-gray-800 border border-white/10 rounded-lg px-3 py-2 text-white font-semibold">
                    </div>
                    <div>
                        <label class="text-gray-400 block mb-1 font-semibold">CEP TEL</label>
                        <input type="text" id="prop-phone" placeholder="05XX XXX XX XX" class="w-full bg-gray-800 border border-white/10 rounded-lg px-3 py-2 text-white font-semibold">
                    </div>
                    <div>
                        <label class="text-gray-400 block mb-1 font-semibold">TC / VERGİ NO</label>
                        <input type="text" id="prop-tax" placeholder="TC / Vergi No" class="w-full bg-gray-800 border border-white/10 rounded-lg px-3 py-2 text-white font-semibold">
                    </div>
                    <div>
                        <label class="text-gray-400 block mb-1 font-semibold">KONU</label>
                        <input type="text" id="prop-subject" value="FİYAT TEKLİFİ" class="w-full bg-gray-800 border border-white/10 rounded-lg px-3 py-2 text-white font-semibold">
                    </div>
                    <div>
                        <label class="text-gray-400 block mb-1 font-semibold">TARİH</label>
                        <input type="text" id="prop-date" class="w-full bg-gray-800 border border-white/10 rounded-lg px-3 py-2 text-white font-semibold">
                    </div>
                    <div class="sm:col-span-2">
                        <label class="text-gray-400 block mb-1 font-semibold">İŞ GELİŞTİRME UZMANI</label>
                        <input type="text" id="prop-rep" value="Hakan BEHRAMOĞLU (0546 291 82 43 | hakan.behramoglu@mannas.com.tr)" class="w-full bg-gray-800 border border-white/10 rounded-lg px-3 py-2 text-sky-300 font-semibold">
                    </div>
                </div>

                <div class="overflow-x-auto rounded-2xl border border-white/10">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-gray-900 text-[11px] font-mono uppercase text-gray-400 border-b border-white/10">
                                <th class="py-3 px-4">ÜRÜNLER</th>
                                <th class="py-3 px-4">ÜRÜN ADI</th>
                                <th class="py-3 px-4 text-center">ADET</th>
                                <th class="py-3 px-4 text-right">BİRİM FİYATI</th>
                                <th class="py-3 px-4 text-right">TUTARI</th>
                                <th class="py-3 px-2 text-center no-print">Sil</th>
                            </tr>
                        </thead>
                        <tbody id="proposal-tbody" class="divide-y divide-white/5 text-xs bg-gray-950/60"></tbody>
                        <tfoot>
                            <tr class="bg-gray-900 border-t border-white/15">
                                <td colspan="2" class="py-3.5 px-4 font-mono text-xs text-amber-400 font-semibold">FİYATLARIMIZA KDV DAHİL DEĞİLDİR</td>
                                <td colspan="2" class="py-3.5 px-4 text-right font-display font-bold text-sm text-gray-300">TOPLAM:</td>
                                <td id="proposal-total-cell" class="py-3.5 px-4 text-right font-display font-bold text-xl text-sky-400">0,00 €</td>
                                <td class="no-print"></td>
                            </tr>
                        </tfoot>
                    </table>
                </div>

                <div class="no-print flex flex-wrap sm:flex-nowrap items-center gap-2 p-3 rounded-2xl bg-gray-900/60 border border-white/10 text-xs">
                    <input type="text" id="custom-item-cat" placeholder="Kategori" class="w-32 bg-gray-800 border border-white/10 rounded-lg px-2.5 py-2 text-white">
                    <input type="text" id="custom-item-name" placeholder="Ürün açıklaması..." class="flex-1 bg-gray-800 border border-white/10 rounded-lg px-3 py-2 text-white">
                    <input type="number" id="custom-item-qty" value="1" min="1" class="w-16 bg-gray-800 border border-white/10 rounded-lg px-2 py-2 text-center text-white font-bold">
                    <input type="number" id="custom-item-price" placeholder="Birim" class="w-24 bg-gray-800 border border-white/10 rounded-lg px-2.5 py-2 text-right text-white font-mono">
                    <button onclick="addCustomRow()" class="px-4 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-white font-bold whitespace-nowrap">+ Satır Ekle</button>
                </div>

                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 bg-gray-900/50 p-4 rounded-2xl border border-white/10 text-xs">
                    <div>
                        <label class="text-gray-400 block mb-1 font-semibold">✔ ANLAŞILAN FİYAT</label>
                        <input type="text" id="prop-agreed-price" placeholder="... €" class="w-full bg-gray-800 border border-white/10 rounded-lg px-3 py-2 text-emerald-400 font-bold">
                    </div>
                    <div>
                        <label class="text-gray-400 block mb-1 font-semibold">✔ KDV TUTARI</label>
                        <input type="text" id="prop-vat" placeholder="%10 / %20" class="w-full bg-gray-800 border border-white/10 rounded-lg px-3 py-2 text-white font-semibold">
                    </div>
                    <div>
                        <label class="text-gray-400 block mb-1 font-semibold">✔ PEŞİN VERİLECEK</label>
                        <input type="text" id="prop-downpayment" placeholder="... €" class="w-full bg-gray-800 border border-white/10 rounded-lg px-3 py-2 text-white font-semibold">
                    </div>
                    <div>
                        <label class="text-gray-400 block mb-1 font-semibold">✔ VADE SAYISI</label>
                        <input type="text" id="prop-installments" placeholder="... Ay x ... €" class="w-full bg-gray-800 border border-white/10 rounded-lg px-3 py-2 text-white font-semibold">
                    </div>
                    <div>
                        <label class="text-gray-400 block mb-1 font-semibold">✔ İLK SENET TARİHİ</label>
                        <input type="text" id="prop-first-date" placeholder="GG.AA.YYYY" class="w-full bg-gray-800 border border-white/10 rounded-lg px-3 py-2 text-white font-semibold">
                    </div>
                </div>
            </div>
        </section>

        <!-- SEKME 5: ŞANTİYE & SERVİS -->
        <section id="view-ideas" class="hidden space-y-6">
            <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
                <div class="lg:col-span-7 glass-panel rounded-3xl p-6 border border-white/10 space-y-4">
                    <span class="text-xs font-mono uppercase text-amber-400">SAHA OPERASYON</span>
                    <h3 class="font-display text-xl font-bold text-white">Klinik Kurulum Öncesi Teknik Kontrol</h3>
                    <div class="space-y-2 pt-2 text-xs">
                        <label class="flex items-center gap-3 p-3 rounded-xl bg-gray-900/70 border border-white/10 cursor-pointer">
                            <input type="checkbox" checked class="w-4 h-4 accent-emerald-500 rounded">
                            <span class="text-gray-200 flex-1">Stern Weber zemin temiz su, pis su ve elektrik uçları hazır</span>
                        </label>
                        <label class="flex items-center gap-3 p-3 rounded-xl bg-gray-900/70 border border-white/10 cursor-pointer">
                            <input type="checkbox" checked class="w-4 h-4 accent-emerald-500 rounded">
                            <span class="text-gray-200 flex-1">MGF Kompresör ve Aspiratör odası havalandırma / drenaj hattı hazır</span>
                        </label>
                        <label class="flex items-center gap-3 p-3 rounded-xl bg-gray-900/70 border border-white/10 cursor-pointer">
                            <input type="checkbox" checked class="w-4 h-4 accent-emerald-500 rounded">
                            <span class="text-gray-200 flex-1">MyRay / Dabi Atlante odası kurşunlama ve lisans hazırlığı tamam</span>
                        </label>
                    </div>
                </div>
                <div class="lg:col-span-5 glass-panel rounded-3xl p-6 border border-white/10 space-y-4">
                    <span class="text-xs font-mono uppercase text-sky-400">TEKNİK DESTEK</span>
                    <h3 class="font-display text-xl font-bold text-white">Cihaz Bakım & Destek</h3>
                    <div class="bg-gray-950 p-4 rounded-2xl border border-sky-500/30 text-xs space-y-2">
                        <div class="font-bold text-white">Mannas Dental Teknik Servis</div>
                        <p class="text-gray-400">Cihaz seri no ve arıza kodlarını doğrudan teknik servise iletebilirsiniz.</p>
                        <button onclick="showToast('Teknik servis hattı: 0212 635 77 26')" class="w-full py-2 rounded-xl bg-sky-500 hover:bg-sky-400 text-white font-bold">
                            Teknik Servis Çağır (0212 635 77 26)
                        </button>
                    </div>
                </div>
            </div>
        </section>
    </main>

    <div id="toast-box" class="fixed bottom-5 right-5 z-50 hidden glass-panel px-4 py-3 rounded-2xl border border-sky-400/40 text-xs sm:text-sm text-white shadow-2xl flex items-center gap-2.5">
        <i class="ph-fill ph-check-circle text-emerald-400 text-lg"></i>
        <span id="toast-text">İşlem tamamlandı.</span>
    </div>

    <!-- A4 ÖNİZLEME MODALI -->
    <div id="a4-preview-modal" class="fixed inset-0 z-50 hidden bg-black/85 backdrop-blur-md flex flex-col items-center justify-start overflow-y-auto p-4 sm:p-6">
        <div class="max-w-[210mm] w-full flex flex-wrap items-center justify-between gap-3 bg-gray-900 border border-white/15 rounded-2xl px-4 py-3 mb-4 sticky top-0 z-10 shadow-xl">
            <div class="flex items-center gap-2 text-white text-xs sm:text-sm font-semibold">
                <i class="ph-fill ph-file-pdf text-rose-400 text-lg"></i>
                <span>Resmi A4 Fiyat Teklifi Önizlemesi</span>
            </div>
            <div class="flex items-center gap-2">
                <button onclick="downloadDirectPdf()" class="px-3.5 py-2 rounded-xl bg-sky-500 hover:bg-sky-400 text-white text-xs font-bold">PDF İndir</button>
                <button onclick="triggerPopupPrint()" class="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold">Yazdır</button>
                <button onclick="closeOfficialPrintModal()" class="px-3 py-2 rounded-xl bg-gray-800 text-gray-300 hover:text-white text-xs font-semibold">Kapat ✕</button>
            </div>
        </div>
        <div id="a4-printable-paper" class="bg-white text-gray-900 w-full max-w-[210mm] min-h-[297mm] p-8 sm:p-10 shadow-2xl rounded-sm font-sans"></div>
    </div>

    <script>
        const MANNAS_PIN = '7659';

        function pressPinKey(digit) {
            const input = document.getElementById('pin-input');
        async function verifyPinCode() {
            const input = document.getElementById('pin-input');
            const enteredPin = input.value.trim();
            if (enteredPin === MANNAS_PIN) {
                try {
                    const res = await fetch('/api/pin-login', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ pin: enteredPin })
                    });
                    if (res.ok) {
                        const data = await res.json();
                        localStorage.setItem('token', data.access_token);
                        localStorage.setItem('user_name', data.full_name || 'Hakan Behramoğlu');
                    }
                } catch (e) {}
                document.getElementById('pin-lock-overlay').classList.add('hidden');
                input.value = '';
                showToast('Klinik Matrix yetkili girişi onaylandı.');
            } else {
                document.getElementById('pin-error-msg').classList.remove('hidden');
                input.value = '';
            }
        }
        function lockAppSession() {
            document.getElementById('pin-lock-overlay').classList.remove('hidden');
            document.getElementById('pin-input').value = '';
        }

        // İZDO / TDB 55 KALEMLİK OPSİYONEL EKLENTİLER LİSTESİ
        const TDB_OPTIONS_LIBRARY = [
            { no: 1, name: "S200-S300-S280TRC İÇİN VİSKO DÖŞEME FARKI", price: 950 },
            { no: 2, name: "S380TRC İÇİN VİSCO DÖŞEME FARKI", price: 1200 },
            { no: 3, name: "VENUS PLUS LED - VENUS LED MCT FARKI", price: 475 },
            { no: 4, name: "MCT - MCT VİEW KAMERALI REFLEKTÖR FARKI", price: 4250 },
            { no: 5, name: "ATLAXİS 3-AKSLI PNÖMATİK TETİYER FARKI", price: 425 },
            { no: 6, name: "FİZYODİSPENSER + KİT (PERİSTALTİK POMPA)", price: 1250 },
            { no: 7, name: "ENTEGRE APEX LOCATOR + KİT", price: 750 },
            { no: 8, name: "RECIPROC SİSTEM + KİT", price: 590 },
            { no: 9, name: "W.H.E. HİJYEN SİSTEMİ İLAVESİ", price: 1050 },
            { no: 10, name: "BIOSTER İLAVESİ + IWFC SİSTEMİ", price: 860 },
            { no: 11, name: "FLUSHING HORTUM YIKAMA SİSTEMİ", price: 450 },
            { no: 12, name: "ACWS SİSTEM İLAVESİ", price: 490 },
            { no: 13, name: "STERN WEBER i-XR3 IŞIKSIZ MİKROMOTOR", price: 1150 },
            { no: 14, name: "STERN WEBER i-XR3-L IŞIKLI MİKROMOTOR", price: 1300 },
            { no: 15, name: "STERN WEBER i-XS4-L IŞIKLI MİKROMOTOR (5.3 Ncm)", price: 1700 },
            { no: 16, name: "STERN WEBER FLUO MİKROMOTOR FARKI", price: 375 },
            { no: 17, name: "ASİSTAN İLAVE TEPSİ (TAŞIYICI İLE)", price: 340 },
            { no: 18, name: "ASİSTAN İLAVE ASKI APARATI (2'Lİ)", price: 290 },
            { no: 19, name: "SICAK SU TERTİBATI (BOILER)", price: 290 },
            { no: 20, name: "CATTANI DRENAJ SİSTEMİ POMPA İLE", price: 470 },
            { no: 21, name: "CATTANİ UNİJECT MOTOR", price: 490 },
            { no: 22, name: "DÜRR CS1 DRENAJ SİSTEMİ KLEPESİ İLE", price: 880 },
            { no: 23, name: "MERKEZİ SİSTEM KLEPESİ", price: 375 },
            { no: 24, name: "CUSPIDOR SİSTEM DRENAJ", price: 540 },
            { no: 25, name: "HAVALI EMİCİ SİSTEMİ", price: 310 },
            { no: 26, name: "T9 TABURE (STOKTAKİ RENKLER)", price: 550 },
            { no: 27, name: "T9 TABURE EYER TİPİ", price: 900 },
            { no: 28, name: "T8 ASİSTAN TABURESİ", price: 490 },
            { no: 29, name: "T7 HEKİM TABURESİ", price: 590 },
            { no: 30, name: "TABURE UZATMA APARATI 10 CM", price: 95 },
            { no: 31, name: "MONİTÖR KOLU MULTİMEDYA KABLOLU TEK MAFSAL", price: 475 },
            { no: 32, name: "MONİTÖR KOLU MULTİMEDYA KABLOLU ÇİFT MAFSAL", price: 650 },
            { no: 33, name: "MONİTÖR KOLU YAN SANAYİ TEK MAFSAL", price: 275 },
            { no: 34, name: "HAREKETLİ SAĞ KOLÇAK", price: 390 },
            { no: 35, name: "T-LED IŞINLI DOLGU CİHAZI İLAVESİ", price: 650 },
            { no: 36, name: "C-U2 HD ENTEGRE KAMERA İLAVESİ", price: 2250 },
            { no: 37, name: "C-U2 USB KAMERA", price: 1450 },
            { no: 38, name: "RXDC HYPERSPHERE KABLOSUZ RÖNTGEN İLAVESİ", price: 4750 },
            { no: 39, name: "ENTEGRE ZEN-X SENSÖR NO:1", price: 4250 },
            { no: 40, name: "EVO GOLDSPEED S1-L 1:1 IŞIKLI ANGULDRUVA", price: 750 },
            { no: 41, name: "EVO GOLDSPEED M5-L 1:5 IŞIKLI KIRMIZI KUŞAK", price: 890 },
            { no: 42, name: "EVO GOLDSPEED 1:1 PİYESEMEN FİBEROPTİK", price: 850 },
            { no: 43, name: "EVO GOLDSPEED E4 4:1 ENDODONTİK ANGULDRUVA", price: 500 },
            { no: 44, name: "EVO GOLDSPEED 1:20 İMPLANT ANGULDRUVASI", price: 1250 },
            { no: 45, name: "SILENT POWER EVO 4L AERATÖR BAŞLIĞI", price: 750 },
            { no: 46, name: "3F İLAVE ŞIRINGA", price: 415 },
            { no: 47, name: "STERN WEBER XVS RVG SIZE 1", price: 2500 },
            { no: 48, name: "STERN WEBER XVS RVG SIZE 2", price: 2850 },
            { no: 49, name: "SC-A2 KAVİTRON EL PARÇASI", price: 650 },
            { no: 50, name: "SC-A3 IŞIKLI KAVİTRON EL PARÇASI", price: 750 },
            { no: 51, name: "DÖŞEME ŞEFFAF AYAK KORUYUCU", price: 45 },
            { no: 52, name: "DÖŞEME KOMPLE ŞEFFAF OTURAK KORUYUCU", price: 120 },
            { no: 53, name: "WIRELESS (KABLOSUZ) AYAK PEDALI", price: 550 },
            { no: 54, name: "S300 SLIDING ÖZELLİĞİ & SOFT MOTION İLAVESİ", price: 650 },
            { no: 55, name: "SURGICAL CART (i-XS4 + SC-A3 + T-LED + IŞIKLI AERATÖR + 3F)", price: 6950 }
        ];

        // İZDO 33. DİŞ HEKİMLİĞİ KONGRESİ 2026 KAMPANYALI ÜNİT FÖYLERİ
        const UNIT_CATALOG = {
            'S200_ORTHO': {
                brand: 'STERN WEBER • İZDO 33. KONGRE',
                name: 'Stern Weber S200 Ortho',
                basePrice: 9500,
                currency: '€',
                paymentNote: '1.500 € + KDV Peşinat, Kalan 10 Ay Euro Vade',
                reflector: 'Venus L-LED (50.000 Lux)',
                panel: 'Geniş Hekim Çalışma Tepsisi',
                motor: 'Midwest Türbin + Y-S Işıklı Aeratör',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern 300 P elektromekanik hareketli senkronize Trendelenburg koltuk, Ergonomik sırtlık, Sol kolçak", status: "STANDART", price: 0 },
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern Weber Atlaxis 3 akslı pnömatik vertikal ve horizontal kilitli tetiyer + Standart döşeme", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "Geniş Hekim Çalışma Tepsisi (Ortodonti Özel)", status: "STANDART", price: 0 },
                    { cat: "ASİSTAN TABLETİ", desc: "Yüksekliği ayarlanabilir 5 modül kapasiteli Asistan tableti + Çok fonksiyonlu asistan paneli", status: "STANDART", price: 0 },
                    { cat: "ASİSTAN TABLETİ", desc: "Stern Weber 3F Hava-Su şırıngası + Işıklı Midwest Türbin + Y-S DENT Coupling'li LED Işıklı Aeratör", status: "STANDART", price: 0 },
                    { cat: "ASİSTAN TABLETİ", desc: "Stern Weber ışıklı SC-A3 kavitron (4 adet kavitron ucu ve anahtarı ile)", status: "STANDART", price: 0 },
                    { cat: "KREŞUAR & HİJYEN", desc: "270° dönebilen seramik kreşuar + Sanaspray 1.8L acil su sistemi + Ayaktan cerrahi emiş aktivasyonu", status: "STANDART", price: 0 },
                    { cat: "REFLEKTÖR & TABURE", desc: "Venus L-LED 50.000 Lux reflektör + Power Pedal + Stern Weber T7 hekim taburesi", status: "STANDART", price: 0 }
                ]
            },
            'S200': {
                brand: 'STERN WEBER • İZDO 33. KONGRE',
                name: 'Stern Weber S200',
                basePrice: 12000,
                currency: '€',
                paymentNote: 'İZDO 33. Kongre Özel Peşin/Vade Kampanyası',
                reflector: 'Venus L-LED (50.000 Lux)',
                panel: 'LCD Dokunmatik Ekran (5 Modül)',
                motor: 'i-XR3-L Kömürsüz (3.3 Ncm)',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern 300 P elektromekanik senkronize Trendelenburg koltuk, Ergonomik sırtlık, Sol kolçak", status: "STANDART", price: 0 },
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern Weber Üniversal Standart tetiyer 2 akslı + Standart koltuk döşemesi", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "LCD Dokunmatik Ekran, Pnömatik frenli 5 modüllü hekim tableti (Askılı/Kamçılı)", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "Stern Weber 3F Hava-Su şırıngası + 2x Işıklı Midwest Türbin modülü", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "Stern Weber i-XR3-L ışıklı kömürsüz mikromotor (100-40.000 rpm / 3.3 Ncm)", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "Stern Weber ışıklı SC-A3 kavitron (4 adet ALTIN kavitron ucu ve anahtarı ile)", status: "STANDART", price: 0 },
                    { cat: "BAŞLIK HEDİYESİ", desc: "Y-S DENT Aeratör Coupling'li hızlı su ayarlı Midwest 6 delikli", status: "HEDİYE", price: 0 },
                    { cat: "ASİSTAN & KREŞUAR", desc: "3 modül kapasiteli Asistan tableti + 270° seramik kreşuar + Sanaspray 1.8L", status: "STANDART", price: 0 },
                    { cat: "REFLEKTÖR & TABURE", desc: "Venus L-LED 50.000 Lux reflektör + Power Pedal + Stern Weber T7 hekim taburesi", status: "STANDART", price: 0 }
                ]
            },
            'S220TR': {
                brand: 'STERN WEBER • İZDO 33. KONGRE',
                name: 'Stern Weber 220 TR',
                basePrice: 13500,
                currency: '€',
                paymentNote: '2.500 € + KDV Peşinat, Kalan 10 Ay Euro Vade',
                reflector: 'Venus Plus LED (50.000 Lux)',
                panel: 'LCD Dokunmatik Ekran (4 Modül)',
                motor: 'i-XR3-L Kömürsüz Mikromotor',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern 300 P elektromekanik hareketli senkronize Trendelenburg koltuk, Ergonomik sırtlık, Sol kolçak", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "LCD Dokunmatik Ekran, Pnömatik frenli 4 modüllü hekim tableti + 3F Hava-Su şırıngası", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "2x Işıklı Midwest Türbin + i-XR3-L ışıklı kömürsüz mikromotor + SC-A3 kavitron (4 altın uç)", status: "STANDART", price: 0 },
                    { cat: "BAŞLIK HEDİYESİ", desc: "Y-S DENT Aeratör Coupling'li hızlı su ayarlı Midwest 6 delikli", status: "HEDİYE", price: 0 },
                    { cat: "BAŞLIK HEDİYESİ", desc: "Y-S DENT Anguldruva 1:1 Mavi Kuşak Işıklı", status: "HEDİYE", price: 0 },
                    { cat: "KREŞUAR & REFLEKTÖR", desc: "270° seramik kreşuar + Sanaspray 1.8L + Venus Plus LED reflektör + T7 hekim taburesi", status: "STANDART", price: 0 }
                ]
            },
            'S200_GOLD': {
                brand: 'STERN WEBER • İZDO 33. KONGRE',
                name: 'Stern Weber S200 GOLD',
                basePrice: 14500,
                currency: '€',
                paymentNote: '3.500 € + KDV Peşinat, Kalan 11 Ay Euro Vade',
                reflector: 'Venus LED MCT (3 Renk Isısı)',
                panel: 'LCD Dokunmatik Ekran + Y-S Monitör Kolu',
                motor: 'i-XR3-L + SW EVO Başlık Seti',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern 300 P elektromekanik senkronize koltuk + Atlaxis 3 akslı pnömatik tetiyer", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "LCD Dokunmatik Ekran, 5 modüllü pnömatik frenli tablet + i-XR3-L mikromotor + SC-A3 kavitron", status: "STANDART", price: 0 },
                    { cat: "SW EVO BAŞLIK", desc: "Stern Weber Silent Power EVO 4L Işıklı Türbin (350.000 rpm, 57 dB) SW Coupling ile", status: "STANDART", price: 0 },
                    { cat: "SW EVO BAŞLIK", desc: "Stern Weber Goldspeed EVO S1-L ışıklı mavi kuşak 1:1 anguldruva", status: "STANDART", price: 0 },
                    { cat: "SW EVO BAŞLIK", desc: "Stern Weber Goldspeed EVO M5-L ışıklı kırmızı kuşak 1:5 anguldruva", status: "STANDART", price: 0 },
                    { cat: "BAŞLIK HEDİYESİ", desc: "Y-S DENT Aeratör Coupling'li hızlı su ayarlı Midwest 6 delikli", status: "HEDİYE", price: 0 },
                    { cat: "ASİSTAN & MULTİMEDYA", desc: "T-LED Işınlı Dolgu + Y-S Monitör Kolu + Venus LED MCT Reflektör + T7 Tabure", status: "STANDART", price: 0 }
                ]
            },
            'S300': {
                brand: 'STERN WEBER • İZDO 33. KONGRE',
                name: 'Stern Weber S300 (Kongre Hediyeli)',
                basePrice: 15500,
                currency: '€',
                paymentNote: '3.500 € + KDV Peşinat, Kalan 12.000 € 12 Ay Euro Vade',
                reflector: 'Venus LED MCT (50.000 Lux)',
                panel: '7" Full Touch HD (Endo+İmplant)',
                motor: 'i-XS4 (5.3 Ncm) + Peristaltik + Apex',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern 300 P elektromekanik senkronize Trendelenburg koltuk, döküm sırtlık, Sol kolçak", status: "STANDART", price: 0 },
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern Weber Atlaxis 3 akslı pnömatik vertikal ve horizontal kilitli tetiyer", status: "HEDİYE", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "NEW IPS 7\" Full Touch HD Ekran (Endo+İmplant Yazılımlı) + 6F Isıtmalı Hava-Su şırıngası", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "Stern Weber i-XS4 ışıklı kömürsüz mikromotor (5.3 Ncm tork ayarlı) + SC-A3 kavitron (4 altın uç)", status: "STANDART", price: 0 },
                    { cat: "KONGRE HEDİYESİ", desc: "2 enstrüman için irrigasyon seti ile Peristaltik Pompa Modülü", status: "HEDİYE", price: 0 },
                    { cat: "KONGRE HEDİYESİ", desc: "Doktor tabletinde görüntüleme imkanı ile Entegre LAEC Apex Locator", status: "HEDİYE", price: 0 },
                    { cat: "KONGRE HEDİYESİ", desc: "Stern Weber Silent Power EVO 4L Işıklı Türbin (350.000 rpm, 57 dB) SW Coupling ile", status: "HEDİYE", price: 0 },
                    { cat: "KONGRE HEDİYESİ", desc: "Stern Weber Goldspeed EVO E4 Endodontik Anguldruva (Resiproc & Apex uyumlu)", status: "HEDİYE", price: 0 },
                    { cat: "KONGRE HEDİYESİ", desc: "Y-S DENT Aeratör + Y-S DENT 20:1 Yeşil Kuşak İmplant Anguldruvası + Y-S 1:1 Mavi Kuşak", status: "HEDİYE", price: 0 },
                    { cat: "ASİSTAN & REFLEKTÖR", desc: "T-LED Işınlı Dolgu + Boiler + Sanaspray 1.8L + VENUS LED MCT Reflektör + T7 Tabure", status: "HEDİYE", price: 0 }
                ]
            },
            'S280TRC': {
                brand: 'STERN WEBER • İZDO 33. KONGRE',
                name: 'Stern Weber 280 TRC Asansörlü',
                basePrice: 17500,
                currency: '€',
                paymentNote: '5.500 € + KDV Peşinat, Kalan 12.000 € 10 Ay Euro Vade',
                reflector: 'Venus LED MCT (50.000 Lux)',
                panel: '7" Full Touch HD + SideFlex + NFC',
                motor: 'i-XS4 (5.3 Ncm Endo+İmplant)',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern 280 P kreşuar bloğuna bağlı Trendelenburg yapan asansörlü koltuk, döküm sırtlık, Atlaxis tetiyer", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "NEW IPS 7\" Full Touch HD Ekran (Endo+İmplant Yazılımlı) + NFC + SideFlex döner kamçı kolları", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "6F ısıtmalı Hava-Su şırıngası + 2x Işıklı Midwest + i-XS4 kömürsüz mikromotor + SC-A3 kavitron", status: "STANDART", price: 0 },
                    { cat: "BAŞLIK HEDİYESİ", desc: "Y-S DENT Aeratör Coupling'li hızlı su ayarlı Midwest 6 delikli", status: "HEDİYE", price: 0 },
                    { cat: "BAŞLIK HEDİYESİ", desc: "Y-S DENT Anguldruva 1:1 Mavi Kuşak Işıklı", status: "HEDİYE", price: 0 },
                    { cat: "ASİSTAN & REFLEKTÖR", desc: "T-LED Işınlı Dolgu + Motorize 270° seramik kreşuar + Boiler + VENUS LED MCT + T7 Tabure", status: "STANDART", price: 0 }
                ]
            },
            'S380TRC_VIP': {
                brand: 'STERN WEBER • İZDO 33. KONGRE',
                name: 'Stern Weber VIP 380 TRC (Kampanya)',
                basePrice: 25000,
                currency: '€',
                paymentNote: '8.000 € + KDV Peşin, Kalan 18 Ay Euro Vade',
                reflector: 'Venus LED MCT (Fotoselli)',
                panel: '7" Full Touch + Interactive LED + NFC',
                motor: 'i-XS4 + Peristaltik + Apex + 4x SW EVO',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern 380 P kreşuar bloğuna bağlı asansör sistemli 90° döner koltuk, döküm sırtlık", status: "STANDART", price: 0 },
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern Weber Atlaxis 3 akslı pnömatik tetiyer + Patient Presence Sensor", status: "HEDİYE", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "NEW IPS 7\" Full Touch HD Ekran + NFC + SideFlex kamçı kolları + 6F Isıtmalı şırınga + i-XS4 + SC-A3", status: "STANDART", price: 0 },
                    { cat: "KONGRE HEDİYESİ", desc: "2 enstrüman için irrigasyon seti ile Peristaltik Pompa + Entegre LAEC Apex Locator", status: "HEDİYE", price: 0 },
                    { cat: "KONGRE HEDİYESİ", desc: "Stern Weber Silent Power EVO 4L Işıklı Türbin (350.000 rpm, 57 dB) SW Coupling ile", status: "HEDİYE", price: 0 },
                    { cat: "KONGRE HEDİYESİ", desc: "Stern Weber Goldspeed EVO S1-L (1:1) + EVO M5-L (1:5) + EVO E4 Endo Anguldruva Seti", status: "HEDİYE", price: 0 },
                    { cat: "KREŞUAR & REFLEKTÖR", desc: "NEW Interactive LED Pack + VENUS LED MCT 50.000 Lux Reflektör + Motorize 270° kreşuar + T7 Tabure", status: "HEDİYE", price: 0 }
                ]
            },
            'S380TRC_GOLD': {
                brand: 'STERN WEBER • İZDO 33. KONGRE',
                name: 'Stern Weber VIP 380 TRC GOLD (Full)',
                basePrice: 45000,
                currency: '€',
                paymentNote: 'Özel Kongre Finansmanı',
                reflector: 'Venus LED MCT (Fotoselli)',
                panel: '7" Full Touch + RXDC + Zen-X + C-U2 HD',
                motor: '2x i-XS4 + Full Goldspeed EVO Set',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern 380 P 90° döner asansörlü koltuk + VISCO Döşeme + Atlaxis Tetiyer + Patient Presence Sensor", status: "STANDART", price: 0 },
                    { cat: "CERRAHİ / ENDO", desc: "2x i-XS4 kömürsüz mikromotor + Resiproc modülü + Peristaltik Pompa + Entegre LAEC Apex Locator", status: "STANDART", price: 0 },
                    { cat: "SW EVO BAŞLIK", desc: "Silent Power EVO 4L Türbin + EVO S1-L (1:1) + EVO M5-L (1:5) + EVO R20-L İmplant + EVO E4 Endo", status: "STANDART", price: 0 },
                    { cat: "MULTİMEDYA & RÖNTGEN", desc: "Entegre Wireless Kumandalı RXDC HyperSphere Periapikal Röntgen + Zen-X Size 1 RVG Sensör", status: "STANDART", price: 0 },
                    { cat: "MULTİMEDYA & KAMERA", desc: "Entegre C-U2 HD Kamera + Stern Weber Monitör Kolu ve PC Multimedya Bağlantısı", status: "STANDART", price: 0 },
                    { cat: "HİJYEN & TABURE", desc: "Interactive LED Pack + ACWS Hortum Dezenfeksiyonu + Wi-Fi Ayak Pedalı + T7 & T8 Tabureler", status: "STANDART", price: 0 }
                ]
            },
            'SF8000C_IMP': {
                brand: 'MEDARC • SILVERFOX (İZDO ÖZEL)',
                name: 'Silverfox C Implant (8.500 $)',
                basePrice: 8500,
                currency: '$',
                paymentNote: '%30 + KDV Peşinat, Kalan 10 Ay TL Vade',
                reflector: '26 LED Cerrahi Reflektör (90.000 Lux)',
                panel: '7" HD Full Touch + 17" Monitör & Kamera',
                motor: 'Elektrikli Işıklı Mikromotor',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Silverfox senkronizasyonlu tedavi koltuğu, Metal sırtlık, Orijinal Visko hafızalı döşeme, 6 program", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "7\" HD Full Touch ekran + HD İntraoral Kamera ve entegre 17\" LED Monitör dahil", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "Elektrikli Mikromotor (ekrandan devir/anguldruva seçimi) + 1:1 Mavi Kuşak + Silverfox Aeratör + Woodpecker Kavitron", status: "STANDART", price: 0 },
                    { cat: "ASİSTAN & REFLEKTÖR", desc: "Jerry JL 3 programlı ışınlı dolgu + 26 LED ampullü 30.000-90.000 Lux Cerrahi Reflektör", status: "STANDART", price: 0 },
                    { cat: "HİJYEN & TABURE", desc: "Otomatik dezenfeksiyon sistemi + Boiler + Hekim Taburesi + Asistan Taburesi", status: "STANDART", price: 0 }
                ]
            },
            'SF8000C': {
                brand: 'MEDARC • SILVERFOX (İZDO ÖZEL)',
                name: 'Silverfox C Pro (6.950 $)',
                basePrice: 6950,
                currency: '$',
                paymentNote: '%30 + KDV Peşinat, Kalan 10 Ay TL Vade',
                reflector: 'Firefly LED Reflektör (30.000 Lux)',
                panel: '7" HD Full Touch + All-in-One PC',
                motor: 'Elektrikli Işıklı Mikromotor',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Silverfox senkronizasyonlu tedavi koltuğu, Metal sırtlık, Memory Foam hafızalı döşeme", status: "STANDART", price: 0 },
                    { cat: "MULTİMEDYA", desc: "All-in-One Dokunmatik Bilgisayar ve Ağız İçi Kamerası ile birlikte", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "7\" HD Full Touch ekran + Elektrikli Mikromotor + Silverfox Aeratör + 1:1 Mavi Kuşak + Woodpecker Kavitron", status: "STANDART", price: 0 },
                    { cat: "ASİSTAN & TABURE", desc: "Jerry JL Işınlı Dolgu + Otomatik dezenfeksiyon + Hekim Taburesi + Asistan Taburesi", status: "STANDART", price: 0 }
                ]
            },
            'SF8000B': {
                brand: 'MEDARC • SILVERFOX (İZDO ÖZEL)',
                name: 'Silverfox Model B (3.950 $)',
                basePrice: 3950,
                currency: '$',
                paymentNote: '%30 + KDV Peşinat, Kalan 10 Ay TL Vade',
                reflector: 'Firefly LED Reflektör (30.000 Lux)',
                panel: '7" HD Full Touch Ekran',
                motor: 'Havalı Mikromotor + Başlık Seti',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Trendelenburg yapabilen tedavi koltuğu, Metal sırtlık, 6 program, Sıkışma sensörleri", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "7\" HD Full Touch ekran + 1:1 Mavi Kuşak Anguldruva + Işıklı Aeratör + Havalı Mikromotor + Woodpecker Işıklı Kavitron", status: "STANDART", price: 0 },
                    { cat: "ASİSTAN & REFLEKTÖR", desc: "Jerry JL Işınlı Dolgu + Boiler + Firefly LED fotoselli reflektör + Hekim Taburesi", status: "STANDART", price: 0 }
                ]
            }
        };

        const appState = {
            selectedModelKey: 'S200',
            armType: 'Kamçılı (Continental)',
            upholsteryType: 'standard',
            colorName: '102 Atlantic Blue',
            colorHex: '#1b589d',
            suctionType: 'hybrid',
            calcUnits: 1,
            currentUnitSheetItems: [],
            proposalItems: [],
            currentCalcComp: { name: 'MGF 30/7 PRIME M KURUTUCULU DENTAL KOMPRESÖR (PR-OF100-024-M) (İTALYA)', qty: 1, unitPrice: 1650 },
            currentCalcVac: { name: 'MGF HYBRID 1S DENTAL ASPİRATÖR (AS-075-EX • 1.100 Lt/dk) (İTALYA)', qty: 1, unitPrice: 1300 },
            currentCalcAspirComp: { name: 'MGF ASPIR-COMP 24/10 GENESI MC (HYBRID 1S) (D-AC150-024-MC) (İTALYA)', qty: 1, unitPrice: 6500 },
            currentCalcSteril: { name: 'YESON DASLAV S 23 Lt B-CLASS OTOKLAV SETİ (ÇİN)', qty: 1, unitPrice: 2000 }
        };

        // STERN WEBER TAM 19 RENK KARTELASI (Standard & Memory Foam Kodları)
        const SW_COLORS = [
            { stdCode: '102', memCode: '198', name: 'Atlantic Blue', hex: '#1b589d' },
            { stdCode: '106', memCode: '196', name: 'Mediterranean Blue', hex: '#3876b5' },
            { stdCode: '113', memCode: '183', name: 'Pacific Blue', hex: '#639dd5' },
            { stdCode: '136', memCode: '186', name: 'Indian Blue', hex: '#4f718d' },
            { stdCode: '132', memCode: '192', name: 'Blueberry Violet', hex: '#5f3577' },
            { stdCode: '134', memCode: '184', name: 'Japanese Wisteria', hex: '#9474a5' },
            { stdCode: '135', memCode: '194', name: 'Venetian Red', hex: '#6e1928' },
            { stdCode: '115', memCode: '195', name: 'Scottish Salmon', hex: '#b64346' },
            { stdCode: '103', memCode: '182', name: 'Nevada Yellow', hex: '#cc521d' },
            { stdCode: '123', memCode: '193', name: 'Polynesian Green', hex: '#88ad3b' },
            { stdCode: '101', memCode: '197', name: 'Caribbean Green', hex: '#14847e' },
            { stdCode: '137', memCode: '187', name: 'Bright Silver', hex: '#a9b0b5' },
            { stdCode: '121', memCode: '199', name: 'Anthracite Grey', hex: '#565a5e' },
            { stdCode: '130', memCode: '180', name: 'Graphite Black', hex: '#26282a' },
            { stdCode: '142', memCode: '172', name: 'Anatolian Hazelnut', hex: '#9e704c' },
            { stdCode: '141', memCode: '171', name: 'Papyrus Beige', hex: '#d3bd9a' },
            { stdCode: '143', memCode: '173', name: 'Arabian Gold', hex: '#ab874b' },
            { stdCode: '140', memCode: '170', name: 'Brazilian Brown', hex: '#583f35' },
            { stdCode: '144', memCode: '174', name: 'Ruby Red', hex: '#9c202c' }
        ];

        // SILVERFOX 8000 B - FORMED UPHOLSTERY (PVC SERİSİ - 10 RENK)
        const SF_PVC_COLORS = [
            { code: 'PVC-1', name: 'Sky Blue', hex: '#6e9cc9' },
            { code: 'PVC-2', name: 'Ocean Blue', hex: '#2b72a8' },
            { code: 'PVC-3', name: 'Turquoise', hex: '#009895' },
            { code: 'PVC-4', name: 'Steel Grey', hex: '#8b8d8c' },
            { code: 'PVC-5', name: 'Royal Navy', hex: '#1b2f7a' },
            { code: 'PVC-7', name: 'Terracotta', hex: '#cf5d2f' },
            { code: 'PVC-8', name: 'Burgundy', hex: '#692a30' },
            { code: 'PVC-11', name: 'Sand Beige', hex: '#b9b498' },
            { code: 'PVC-12', name: 'Light Silver', hex: '#bfc1c6' },
            { code: 'PVC-15', name: 'Jet Black', hex: '#14191b' }
        ];

        // SILVERFOX 8000 C SERİSİ - SEWN UPHOLSTERY (C SERİSİ MICROFIBER - 10 RENK)
        const SF_C_COLORS = [
            { code: 'C1', name: 'Cobalt Blue', hex: '#3373cc' },
            { code: 'C3', name: 'Mint Green', hex: '#69ad88' },
            { code: 'C4', name: 'Mocha Brown', hex: '#7d4a34' },
            { code: 'C7', name: 'Coral Orange', hex: '#dc5334' },
            { code: 'C9', name: 'Slate Blue', hex: '#6c7a86' },
            { code: 'C10', name: 'Stone Grey', hex: '#9c9b97' },
            { code: 'C12', name: 'Crimson Red', hex: '#9e2529' },
            { code: 'C16', name: 'Plum Purple', hex: '#873377' },
            { code: 'C22', name: 'Indigo Blue', hex: '#5459c4' },
            { code: 'C23', name: 'Charcoal Black', hex: '#262729' }
        ];

        // SILVERFOX 8000 C SERİSİ - PREMIUM SILICONE UPHOLSTERY (S SERİSİ - 19 RENK)
        const SF_S_COLORS = [
            { code: 'S1', name: 'Oceania', hex: '#1b468f' },
            { code: 'S2', name: 'Amber', hex: '#cc6d30' },
            { code: 'S3', name: 'Cement', hex: '#81898e' },
            { code: 'S4', name: 'Meteorite', hex: '#504e4d' },
            { code: 'S5', name: 'Coal', hex: '#121212' },
            { code: 'S6', name: 'Apple Green', hex: '#a1b479' },
            { code: 'S7', name: 'Sky', hex: '#85b2cc' },
            { code: 'S8', name: 'Kahki', hex: '#a2978d' },
            { code: 'S9', name: 'Caramel', hex: '#7e6745' },
            { code: 'S10', name: 'Ruby', hex: '#4d1c1d' },
            { code: 'S11', name: 'Concord', hex: '#5e3e5e' },
            { code: 'S12', name: 'Chestnut', hex: '#41342c' },
            { code: 'S13', name: 'Gravel', hex: '#a9a8a4' },
            { code: 'S14', name: 'Navy', hex: '#253140' },
            { code: 'S15', name: 'Warm Grey', hex: '#999c8e' },
            { code: 'S16', name: 'Techno Blue', hex: '#5b4fa0' },
            { code: 'S17', name: 'Flaming Rose', hex: '#ce047a' },
            { code: 'S18', name: 'Heather', hex: '#a36788' },
            { code: 'S19', name: 'Neon Green', hex: '#21c40e' }
        ];

        // PAKETSİZ TEKİL GÖRÜNTÜLEME CİHAZLARI KATALOĞU (MYRAY • DABI ATLANTE • WOODPECKER)
        const SINGLE_IMAGING_CATALOG = [
            // MYRAY
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'MYRAY X5 AIR 2D PANORAMİK + PC', desc: 'Kompakt 2D Panoramik Görüntüleme + Orijinal PC', price: 12750, curr: '€' },
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'MYRAY PROXIMA X6 AIR 2D PANORAMİK + PC', desc: 'Katmanlı 2D Panoramik + NeoWise AI + PC', price: 13500, curr: '€' },
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'MYRAY X5 AIR 3D 10x10 FOV + PC', desc: '3D CBCT + 2D Panoramik 10x10 FOV + PC', price: 34000, curr: '€' },
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'MYRAY X6 AIR 3D 11x15 FOV + PC', desc: '3D CBCT + 2D Panoramik 11x15 FOV + PC', price: 39999, curr: '€' },
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'MYRAY X5-X6 AIR 2D CEPH ATAÇMAN FARKI', desc: 'Sefalometrik kol ve ataçman ilavesi', price: 8500, curr: '€' },
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'MYRAY X5-X6 AIR 2D CEPH SENSÖR FARKI', desc: 'İkinci ayrı sefalometrik sensör farkı', price: 6500, curr: '€' },
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'MYRAY AYAK FARKI (FREE STANDING)', desc: 'Duvar bağlantısız zemin sabitleme ayağı', price: 650, curr: '€' },
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'MYRAY X9 PRO 10x8 FOV (TABLET DAHİL)', desc: '3D+2D FullView Tomografi 10x8 FOV', price: 49500, curr: '€' },
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'MYRAY X9 PRO DIRECT SENSÖR DC 13x16 FOV', desc: 'Direct Conversion DC Sensör + Tablet + 10 Kullanıcı', price: 65000, curr: '€' },
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'MYRAY X9 PRO DIRECT SENSÖR FARKI', desc: 'Direct Conversion sensör yükseltme farkı', price: 9500, curr: '€' },
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'MYRAY X9 PRO CEPH TEK SENSÖRLÜ 10x8 FOV', desc: 'Sefalometrik dahil 10x8 FOV + Tablet', price: 53400, curr: '€' },
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'MYRAY X9 PRO 2D (3D READY)', desc: '3D yükseltmeye hazır 2D Panoramik', price: 17500, curr: '€' },
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'MYRAY X9 PRO 2D PAN/CEPH (3D READY)', desc: '3D yükseltmeye hazır Panoramik + Sefalometrik', price: 23500, curr: '€' },
            { brand: 'MYRAY', cat: 'TARAYICI', name: 'MYRAY MYSCAN WL KABLOSUZ AĞIZ İÇİ TARAYICI', desc: '20 µm hassasiyet, 245 gr, ScanPro AI yazılımı', price: 11500, curr: '€' },
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'MYRAY HYPERSPHERE DUVAR TİP PERİAPİKAL', desc: '0.4mm focal spot, küresel mafsal, kablosuz kumanda', price: 4250, curr: '€' },
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'STERN WEBER RX DC MOBİL DUVAR RÖNTGEN', desc: 'Yüksek frekanslı DC duvar tipi periapikal', price: 2750, curr: '€' },
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'STERN WEBER RX DC MOBİL AYAKLI RÖNTGEN', desc: 'Tekerlekli mobil ayaklı DC periapikal', price: 3250, curr: '€' },
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'MYRAY ZEN-X DCIS KABLOSUZ RVG SENSÖR', desc: 'Direct Conversion kablosuz IP67 RVG sensör', price: 5000, curr: '€' },
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'MYRAY X-POD RVG SİSTEMİ', desc: 'Taşınabilir dokunmatik ekranlı RVG sistemi', price: 3350, curr: '€' },
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'HI-SCAN FOSFOR PLAK TARAYICI SETİ', desc: '0,1,2,3,4 plaklar + 100 tek kullanımlık kılıf + 40 koruma', price: 3500, curr: '€' },
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'HI-SCAN YEDEK PLAK SETİ (2 PLAK + KILIF)', desc: '2 adet yedek plak + 20 koruma + 50 kılıf', price: 215, curr: '€' },
            { brand: 'MYRAY', cat: 'GÖRÜNTÜLEME', name: 'HI-SCAN SADECE YEDEK PLAK (2\'Lİ)', desc: '2 adet orijinal fosfor plak', price: 165, curr: '€' },
            // DABI ATLANTE
            { brand: 'DABI', cat: 'GÖRÜNTÜLEME', name: 'DABI ATLANTE EDGE AXR120 2D/3D MFOV 16x21 + PC', desc: '16x21 Complete Cranium MFOV + OnDemand 3D AI + PC', price: 65000, curr: '$' },
            { brand: 'DABI', cat: 'GÖRÜNTÜLEME', name: 'DABI ATLANTE EDGE AXR120 2D/3D SFOV 9x14 + PC', desc: '9x14 FOV 3D CBCT + OnDemand 3D AI + PC', price: 35000, curr: '$' },
            { brand: 'DABI', cat: 'GÖRÜNTÜLEME', name: 'DABI ATLANTE EDGE AXR90 3D 0.2 FS 9x14 + PC', desc: '0.2 Focal Spot yüksek çözünürlük 9x14 FOV + PC', price: 42000, curr: '$' },
            { brand: 'DABI', cat: 'GÖRÜNTÜLEME', name: 'DABI ATLANTE EDGE AXR90 2D PANORAMİK + PC', desc: '41 katmanlı 2D AI Panoramik + Orijinal PC', price: 14500, curr: '$' },
            { brand: 'DABI', cat: 'GÖRÜNTÜLEME', name: 'DABI ATLANTE NEW IDA RVG SIZE 1', desc: 'Değiştirilebilir kablolu 16-bit HD RVG Size 1', price: 1700, curr: '$' },
            { brand: 'DABI', cat: 'GÖRÜNTÜLEME', name: 'DABI ATLANTE NEW IDA RVG SIZE 2', desc: 'Değiştirilebilir kablolu 16-bit HD RVG Size 2', price: 2100, curr: '$' },
            // WOODPECKER
            { brand: 'WOODPECKER', cat: 'GÖRÜNTÜLEME', name: 'WOODPECKER MINIRAY 2mA MOBİL PERİAPİKAL', desc: '0.4mm focal spot, taşınabilir bataryalı el röntgeni', price: 770, curr: '€' },
            { brand: 'WOODPECKER', cat: 'GÖRÜNTÜLEME', name: 'WOODPECKER I-SENSOR H1 RVG SENSÖR SIZE 1', desc: '16-bit yüksek çözünürlük USB RVG sensör Size 1', price: 725, curr: '€' },
            { brand: 'WOODPECKER', cat: 'GÖRÜNTÜLEME', name: 'WOODPECKER I-SENSOR H2 RVG SENSÖR SIZE 2', desc: '16-bit geniş aktif alan USB RVG sensör Size 2', price: 850, curr: '€' },
            { brand: 'WOODPECKER', cat: 'EKİPMAN', name: 'WOODPECKER LED H ORTODONTİK IŞINLI DOLGU', desc: 'Valo tip geniş spektrumlu LED ışınlı dolgu cihazı', price: 250, curr: '$' }
        ];

        let activeSingleImagingBrand = 'ALL';

        function filterSingleImaging(brand) {
            activeSingleImagingBrand = brand;
            ['ALL', 'MYRAY', 'DABI', 'WOODPECKER'].forEach(b => {
                const btn = document.getElementById('img-flt-' + b);
                if (btn) {
                    btn.className = b === brand
                        ? 'px-3 py-1.5 rounded-lg bg-sky-500 text-white font-bold'
                        : 'px-3 py-1.5 rounded-lg text-gray-400 hover:text-white font-semibold';
                }
            });
            renderSingleImagingList();
        }

        function renderSingleImagingList() {
            const grid = document.getElementById('single-imaging-grid');
            if (!grid) return;
            const q = (document.getElementById('single-imaging-search')?.value || '').trim().toLowerCase();
            grid.innerHTML = '';

            const filtered = SINGLE_IMAGING_CATALOG.filter(item => {
                const brandMatch = activeSingleImagingBrand === 'ALL' || item.brand === activeSingleImagingBrand;
                const textMatch = !q || item.name.toLowerCase().includes(q) || item.desc.toLowerCase().includes(q) || item.brand.toLowerCase().includes(q);
                return brandMatch && textMatch;
            });

            if (filtered.length === 0) {
                grid.innerHTML = `<div class="col-span-full text-center py-6 text-xs text-gray-500">Aramanıza uygun tekil cihaz bulunamadı.</div>`;
                return;
            }

            filtered.forEach(item => {
                const brandColors = {
                    'MYRAY': 'text-purple-300 bg-purple-500/20 border-purple-500/30',
                    'DABI': 'text-amber-300 bg-amber-500/20 border-amber-500/30',
                    'WOODPECKER': 'text-sky-300 bg-sky-500/20 border-sky-500/30'
                };
                const badgeCls = brandColors[item.brand] || 'text-gray-300 bg-gray-800 border-white/10';
                const currTag = item.curr === '$' ? ' (USD $)' : '';
                const safeName = `${item.name}${currTag}`.replace(/'/g, "\\'");

                const card = document.createElement('div');
                card.className = 'glass-card rounded-2xl p-4 border border-white/10 flex flex-col justify-between gap-3';
                card.innerHTML = `
                    <div>
                        <div class="flex items-center justify-between gap-2">
                            <span class="text-[10px] font-mono px-2 py-0.5 rounded border font-bold ${badgeCls}">${item.brand === 'DABI' ? 'DABI ATLANTE' : item.brand}</span>
                            <span class="font-mono font-bold text-sm text-emerald-400">${item.price.toLocaleString('tr-TR')} ${item.curr}</span>
                        </div>
                        <h4 class="font-bold text-white text-xs mt-2 leading-snug">${item.name}</h4>
                        <p class="text-[11px] text-gray-400 mt-1">${item.desc}</p>
                    </div>
                    <button onclick="addItemToProposal('${item.cat}', '${safeName}', 1, ${item.price})" class="w-full py-1.5 rounded-xl bg-gray-800 hover:bg-sky-500 text-white text-[11px] font-bold transition-all">
                        + Teklife Ekle (${item.price.toLocaleString('tr-TR')} ${item.curr})
                    </button>`;
                grid.appendChild(card);
            });
        }

        function switchTab(tabId) {
            ['configurator', 'imaging', 'calculator', 'proposal', 'ideas'].forEach(v => {
                document.getElementById('view-' + v).classList.add('hidden');
                const btn = document.getElementById('tab-' + v);
                if (btn) btn.className = 'tab-btn flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs sm:text-sm font-medium text-gray-400 hover:text-white transition-all';
            });
            document.getElementById('view-' + tabId).classList.remove('hidden');
            const activeBtn = document.getElementById('tab-' + tabId);
            if (activeBtn) activeBtn.className = 'tab-btn active-tab flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs sm:text-sm font-medium transition-all bg-sky-500 text-white shadow-md';
        }

        function populateTdbOptionsDropdown() {
            const sel = document.getElementById('tdb-opt-select');
            sel.innerHTML = '<option value="">-- Listeden Opsiyonel Donanım Seçin --</option>';
            TDB_OPTIONS_LIBRARY.forEach((opt, i) => {
                const op = document.createElement('option');
                op.value = i;
                op.textContent = `${opt.no}. ${opt.name} (+${opt.price} €)`;
                sel.appendChild(op);
            });
        }

        function handleTdbOptSelectChange() {
            const idx = document.getElementById('tdb-opt-select').value;
            if (idx !== "") document.getElementById('tdb-opt-price-input').value = TDB_OPTIONS_LIBRARY[idx].price;
        }

        function addSelectedTdbOptionToSheet() {
            const idx = document.getElementById('tdb-opt-select').value;
            if (idx === "") { showToast("Lütfen listeden bir opsiyon seçin."); return; }
            const item = TDB_OPTIONS_LIBRARY[idx];
            const status = document.getElementById('tdb-opt-status-input').value.trim() || 'OPSİYONEL';
            const price = parseFloat(document.getElementById('tdb-opt-price-input').value || 0);
            appState.currentUnitSheetItems.push({ cat: "OPSİYONEL", desc: item.name, status, price });
            renderUnitSheetTable();
            showToast("Opsiyon listeye eklendi.");
        }

        function selectUnitModel(modelKey) {
            appState.selectedModelKey = modelKey;
            const data = UNIT_CATALOG[modelKey];
            const curr = data.currency || '€';

            Object.keys(UNIT_CATALOG).forEach(k => {
                const b = document.getElementById('model-' + k);
                if (b) {
                    const span2 = k === 'SF8000B' ? ' col-span-2' : '';
                    b.className = (k === modelKey
                        ? 'model-btn p-2.5 rounded-xl border border-sky-500 bg-sky-500/15 text-left transition-all'
                        : 'model-btn p-2.5 rounded-xl border border-white/10 bg-gray-900/60 text-left transition-all hover:border-sky-500/40') + span2;
                }
            });

            document.getElementById('unit-brand-badge').textContent = data.brand;
            document.getElementById('unit-price-badge').textContent = data.basePrice.toLocaleString('tr-TR') + ' ' + curr + ' Baz';
            document.getElementById('unit-title-display').textContent = data.name + ' ' + appState.armType.split(' ')[0];
            document.getElementById('spec-reflector').textContent = data.reflector;
            document.getElementById('spec-panel').textContent = data.panel;
            document.getElementById('spec-motor').textContent = data.motor;
            document.getElementById('spec-payment').textContent = data.paymentNote;
            document.getElementById('sheet-unit-name').textContent = `${data.name} (${data.basePrice.toLocaleString('tr-TR')} ${curr})`;
            document.getElementById('sheet-footer-note').textContent = `Ödeme Koşulu: ${data.paymentNote} • Fiyatlara KDV Dahil Değildir.`;

            // Modele göre doğru renk kartelasını otomatik yükle
            if (modelKey === 'SF8000B') {
                appState.upholsteryType = 'sf_pvc';
                setUpholstery(SF_PVC_COLORS[0].hex, `${SF_PVC_COLORS[0].code} ${SF_PVC_COLORS[0].name}`);
            } else if (modelKey === 'SF8000C' || modelKey === 'SF8000C_IMP') {
                if (appState.upholsteryType !== 'sf_c' && appState.upholsteryType !== 'sf_s') {
                    appState.upholsteryType = 'sf_c';
                }
                const list = appState.upholsteryType === 'sf_s' ? SF_S_COLORS : SF_C_COLORS;
                setUpholstery(list[0].hex, `${list[0].code} ${list[0].name}`);
            } else {
                if (appState.upholsteryType !== 'standard' && appState.upholsteryType !== 'memory') {
                    appState.upholsteryType = 'standard';
                }
                const firstSw = SW_COLORS[0];
                const code = appState.upholsteryType === 'memory' ? firstSw.memCode : firstSw.stdCode;
                setUpholstery(firstSw.hex, `${code} ${firstSw.name}`);
            }

            appState.currentUnitSheetItems = JSON.parse(JSON.stringify(data.items));
            renderUnitSheetTable();
            recalcUnitPrice();
        }

        function resetCurrentUnitSheet() {
            appState.currentUnitSheetItems = JSON.parse(JSON.stringify(UNIT_CATALOG[appState.selectedModelKey].items));
            renderUnitSheetTable();
            showToast("Konfigürasyon föyü sıfırlandı.");
        }

        function renderUnitSheetTable() {
            const tbody = document.getElementById('unit-sheet-tbody');
            tbody.innerHTML = '';
            appState.currentUnitSheetItems.forEach((it, idx) => {
                const tr = document.createElement('tr');
                tr.className = 'hover:bg-white/5 transition-colors';
                tr.innerHTML = `
                    <td class="py-2.5 px-3 text-center text-gray-500 font-mono text-[11px]">${idx + 1}</td>
                    <td class="py-2 px-2"><input type="text" value="${it.cat}" onchange="updateSheetItem(${idx}, 'cat', this.value)" class="w-full bg-gray-900 border border-white/10 rounded px-2 py-1 text-[11px] font-bold text-sky-400"></td>
                    <td class="py-2 px-2"><input type="text" value="${it.desc.replace(/"/g, '&quot;')}" onchange="updateSheetItem(${idx}, 'desc', this.value)" class="w-full bg-gray-900 border border-white/10 rounded px-2 py-1 text-xs text-gray-200"></td>
                    <td class="py-2 px-2 text-center"><input type="text" value="${it.status}" onchange="updateSheetItem(${idx}, 'status', this.value)" class="w-24 text-center bg-gray-900 border border-white/10 rounded px-1.5 py-1 text-[10px] font-bold ${it.status === 'HEDİYE' ? 'text-emerald-400' : (it.status === 'OPSİYONEL' ? 'text-amber-400' : 'text-gray-300')}"></td>
                    <td class="py-2 px-2 text-right"><input type="number" value="${it.price || 0}" step="10" onchange="updateSheetItem(${idx}, 'price', this.value)" class="w-20 text-right bg-gray-900 border border-white/10 rounded px-2 py-1 text-xs font-mono font-bold text-white"></td>
                    <td class="py-2 px-2 text-center whitespace-nowrap">
                        <button onclick="moveSheetItem(${idx}, -1)" class="text-gray-400 hover:text-white p-1">▲</button>
                        <button onclick="moveSheetItem(${idx}, 1)" class="text-gray-400 hover:text-white p-1">▼</button>
                        <button onclick="deleteSheetItem(${idx})" class="text-gray-500 hover:text-rose-400 p-1">✕</button>
                    </td>`;
                tbody.appendChild(tr);
            });
            recalcUnitPrice();
        }

        function updateSheetItem(index, key, val) {
            appState.currentUnitSheetItems[index][key] = key === 'price' ? parseFloat(val || 0) : val;
            renderUnitSheetTable();
        }
        function moveSheetItem(index, dir) {
            const ni = index + dir;
            if (ni < 0 || ni >= appState.currentUnitSheetItems.length) return;
            const tmp = appState.currentUnitSheetItems[index];
            appState.currentUnitSheetItems[index] = appState.currentUnitSheetItems[ni];
            appState.currentUnitSheetItems[ni] = tmp;
            renderUnitSheetTable();
        }
        function deleteSheetItem(index) {
            appState.currentUnitSheetItems.splice(index, 1);
            renderUnitSheetTable();
        }
        function addCustomRowToSheet() {
            const cat = document.getElementById('sheet-custom-cat').value.trim() || 'DONANIM';
            const desc = document.getElementById('sheet-custom-desc').value.trim();
            const status = document.getElementById('sheet-custom-status').value.trim() || 'STANDART';
            const price = parseFloat(document.getElementById('sheet-custom-price').value || 0);
            if (!desc) { showToast("Donanım açıklaması girin."); return; }
            appState.currentUnitSheetItems.push({ cat, desc, status, price });
            document.getElementById('sheet-custom-desc').value = '';
            document.getElementById('sheet-custom-price').value = '0';
            renderUnitSheetTable();
        }

        function recalcUnitPrice() {
            const data = UNIT_CATALOG[appState.selectedModelKey];
            const curr = data.currency || '€';
            let singlePrice = data.basePrice;
            appState.currentUnitSheetItems.forEach(it => { singlePrice += (it.price || 0); });
            const qty = Math.max(1, parseInt(document.getElementById('unit-qty-input').value || 1, 10));
            const total = singlePrice * qty;
            document.getElementById('unit-price-badge').textContent = singlePrice.toLocaleString('tr-TR') + ' ' + curr + ' / Adet';
            document.getElementById('sheet-total-price').textContent = singlePrice.toLocaleString('tr-TR') + ' ' + curr;
            document.getElementById('btn-add-unit-summary').textContent = `Özet Olarak Ekle (${qty} Adet • ${total.toLocaleString('tr-TR')} ${curr})`;
        }

        function addConfiguredUnitSummaryToProposal() {
            const data = UNIT_CATALOG[appState.selectedModelKey];
            const curr = data.currency || '€';
            let singlePrice = data.basePrice;
            const extraDescs = [];
            appState.currentUnitSheetItems.forEach(it => {
                if (it.price > 0) { singlePrice += it.price; extraDescs.push(`${it.desc} (+${it.price}€)`); }
            });
            const qty = Math.max(1, parseInt(document.getElementById('unit-qty-input').value || 1, 10));
            const uphLabels = {
                'memory': ' [Memory Foam]',
                'sf_pvc': ' [PVC Serisi]',
                'sf_c': ' [C Serisi Microfiber]',
                'sf_s': ' [S Serisi Silikon]'
            };
            const uphTag = uphLabels[appState.upholsteryType] || '';
            const addInfo = extraDescs.length ? ` [Ekstralar: ${extraDescs.join(', ')}]` : '';
            const currTag = curr === '$' ? ' (USD $)' : '';
            const fullName = `${data.name.toUpperCase()} ${appState.armType.toUpperCase()} - ${appState.colorName}${uphTag} (${data.reflector})${addInfo}${currTag}`;
            addItemToProposal('ÜNİTE', fullName, qty, singlePrice);
        }

        function pushEntireSheetToProposal() {
            const data = UNIT_CATALOG[appState.selectedModelKey];
            const curr = data.currency || '€';
            const qty = Math.max(1, parseInt(document.getElementById('unit-qty-input').value || 1, 10));
            const uphLabels = {
                'memory': 'Memory Foam ',
                'sf_pvc': 'PVC ',
                'sf_c': 'Microfiber ',
                'sf_s': 'Silikon '
            };
            const uphTag = uphLabels[appState.upholsteryType] || '';
            const currTag = curr === '$' ? ' (USD $)' : '';
            addItemToProposal('ÜNİTE', `${data.name.toUpperCase()} ${appState.armType.toUpperCase()} (İZDO 33. Kongre - ${uphTag}${appState.colorName})${currTag}`, qty, data.basePrice);
            appState.currentUnitSheetItems.forEach(it => {
                const isPaid = (it.price || 0) > 0;
                const statusTag = it.status ? `[${it.status}] ` : '';
                addItemToProposal(it.cat, `  ↳ ${statusTag}${it.desc}`, qty, isPaid ? it.price : 0);
            });
            showToast("Tüm konfigürasyon satırları detaylı teklif tablosuna aktarıldı!");
            switchTab('proposal');
        }

        function setArmType(type) {
            const whipGroup = document.getElementById('svg-whip-arms');
            const btnCont = document.getElementById('arm-continental');
            const btnIntl = document.getElementById('arm-international');
            const badge = document.getElementById('unit-badge-delivery');
            const data = UNIT_CATALOG[appState.selectedModelKey];

            if (type === 'continental') {
                if (whipGroup) whipGroup.style.display = 'block';
                appState.armType = 'Kamçılı (Continental)';
                btnCont.className = 'py-2 px-3 rounded-xl border border-sky-500 bg-sky-500/15 text-xs font-semibold text-white flex items-center justify-center gap-1.5';
                btnIntl.className = 'py-2 px-3 rounded-xl border border-white/10 bg-gray-900/60 text-xs font-medium text-gray-300 flex items-center justify-center gap-1.5';
            } else {
                if (whipGroup) whipGroup.style.display = 'none';
                appState.armType = 'Askılı (International)';
                btnIntl.className = 'py-2 px-3 rounded-xl border border-sky-500 bg-sky-500/15 text-xs font-semibold text-white flex items-center justify-center gap-1.5';
                btnCont.className = 'py-2 px-3 rounded-xl border border-white/10 bg-gray-900/60 text-xs font-medium text-gray-300 flex items-center justify-center gap-1.5';
            }
            if (badge) badge.textContent = appState.armType;
            document.getElementById('unit-title-display').textContent = data.name + ' ' + appState.armType.split(' ')[0];
        }

        function renderUpholsteryTabs() {
            const tabsBox = document.getElementById('upholstery-type-tabs');
            if (!tabsBox) return;
            const modelKey = appState.selectedModelKey;
            tabsBox.innerHTML = '';

            let tabs = [];
            if (modelKey === 'SF8000B') {
                tabs = [{ id: 'sf_pvc', label: 'PVC Serisi (10)', activeCls: 'bg-sky-500 text-white' }];
            } else if (modelKey === 'SF8000C' || modelKey === 'SF8000C_IMP') {
                tabs = [
                    { id: 'sf_c', label: 'C Serisi Microfiber (10)', activeCls: 'bg-sky-500 text-white' },
                    { id: 'sf_s', label: 'S Serisi Silikon (19)', activeCls: 'bg-purple-500 text-white' }
                ];
            } else {
                tabs = [
                    { id: 'standard', label: 'Standard (19)', activeCls: 'bg-sky-500 text-white' },
                    { id: 'memory', label: 'Memory Foam (19)', activeCls: 'bg-purple-500 text-white' }
                ];
            }

            tabs.forEach(t => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.onclick = () => setUpholsteryType(t.id);
                const isActive = appState.upholsteryType === t.id;
                btn.className = `px-2 py-0.5 rounded-md font-bold text-[10px] transition-all ${isActive ? t.activeCls : 'text-gray-400 hover:text-white'}`;
                btn.textContent = t.label;
                tabsBox.appendChild(btn);
            });
        }

        function setUpholsteryType(type) {
            appState.upholsteryType = type;
            if (type === 'sf_pvc') {
                setUpholstery(SF_PVC_COLORS[0].hex, `${SF_PVC_COLORS[0].code} ${SF_PVC_COLORS[0].name}`);
            } else if (type === 'sf_c') {
                setUpholstery(SF_C_COLORS[0].hex, `${SF_C_COLORS[0].code} ${SF_C_COLORS[0].name}`);
            } else if (type === 'sf_s') {
                setUpholstery(SF_S_COLORS[0].hex, `${SF_S_COLORS[0].code} ${SF_S_COLORS[0].name}`);
            } else {
                const currentObj = SW_COLORS.find(c => appState.colorName.includes(c.name)) || SW_COLORS[0];
                const activeCode = type === 'memory' ? currentObj.memCode : currentObj.stdCode;
                setUpholstery(currentObj.hex, `${activeCode} ${currentObj.name}`);
            }
        }

        function setUpholstery(hex, label) {
            appState.colorHex = hex;
            appState.colorName = label;
            document.getElementById('svg-upholstery').setAttribute('fill', hex);
            document.getElementById('studio-glow').style.background = hex;
            document.getElementById('svg-ambient-led').setAttribute('fill', hex);
            document.getElementById('selected-color-label').textContent = label;
            document.getElementById('color-name-badge').textContent = label;
            renderUpholsteryTabs();
            renderColorSwatches();
        }

        function renderColorSwatches() {
            const box = document.getElementById('upholstery-swatches-container');
            box.innerHTML = '';

            let palette = [];
            if (appState.upholsteryType === 'sf_pvc') {
                palette = SF_PVC_COLORS;
            } else if (appState.upholsteryType === 'sf_c') {
                palette = SF_C_COLORS;
            } else if (appState.upholsteryType === 'sf_s') {
                palette = SF_S_COLORS;
            } else {
                palette = SW_COLORS.map(c => ({
                    code: appState.upholsteryType === 'memory' ? c.memCode : c.stdCode,
                    name: c.name,
                    hex: c.hex
                }));
            }

            palette.forEach(c => {
                const btn = document.createElement('button');
                btn.type = 'button';
                const fullLabel = `${c.code} ${c.name}`;
                const isSelected = appState.colorName === fullLabel;
                btn.onclick = () => setUpholstery(c.hex, fullLabel);
                btn.title = fullLabel;
                btn.className = `p-1.5 rounded-xl border transition-all flex flex-col items-center text-center ${isSelected ? 'border-sky-400 bg-sky-500/25 shadow-sm' : 'border-white/10 bg-gray-900/70 hover:border-white/30'}`;
                btn.innerHTML = `
                    <span class="w-5 h-5 rounded-full border border-white/40 shadow-inner" style="background-color: ${c.hex}"></span>
                    <span class="text-[9px] font-mono font-bold mt-1 text-white leading-none">${c.code}</span>
                    <span class="text-[8px] text-gray-300 mt-0.5 leading-tight line-clamp-1 w-full">${c.name}</span>`;
                box.appendChild(btn);
            });
        }

        function updateEngineeringCalc() {
            const units = parseInt(document.getElementById('calc-units').value, 10);
            const compType = document.getElementById('calc-comp-type').value;
            const hasAmalgam = document.getElementById('calc-amalgam').checked;
            const hasVacCabinet = document.getElementById('calc-vac-cabinet').checked;
            const sterilBrand = document.getElementById('calc-steril-brand').value;
            appState.calcUnits = units;
            document.getElementById('calc-unit-val').textContent = units + ' Ünit';

            const isDryer = (compType === 'M' || compType === 'CS-M');
            const isSilent = (compType === 'CS-M' || compType === 'CS-S');

            // 1) MGF PRIME KOMPRESÖR HESABI (Resmi MGF Prime Kataloğu + İZDO 2026)
            let compName = "", compCode = "", compLpm = "", compNoise = "", compTank = "", compCap = "", compPrice = 0, compQty = 1;

            if (units === 1) {
                compName = isSilent
                    ? (isDryer ? "MGF MINI BOX 24/7 PRIME M" : "MGF MINI BOX 24/7 PRIME S")
                    : (isDryer ? "MGF 30/7 PRIME M" : "MGF 30/7 PRIME S");
                compCode = isSilent
                    ? (isDryer ? "PR-MB100-024-M-15" : "PR-MB100-024-15")
                    : (isDryer ? "PR-OF100-024-M" : "PR-OF100-024");
                compLpm = "85 l/dk";
                compNoise = isSilent ? "50 dB(A)" : "65 dB(A)";
                compTank = "24 L • 0.75 kW / 1 HP";
                compCap = "1 Simultane / 1 Ünit";
                compPrice = (isDryer ? 1650 : 1250) + (isSilent ? 750 : 0);
            } else if (units <= 3) {
                compName = isSilent
                    ? (isDryer ? "MGF CS 30/15 PRIME M" : "MGF CS 30/15 PRIME S")
                    : (isDryer ? "MGF 50/15 PRIME M" : "MGF 50/15 PRIME S");
                compCode = isSilent
                    ? (isDryer ? "PR-CS200-040-M" : "PR-CS200-040")
                    : (isDryer ? "PR-OF200-040-M" : "PR-OF200-040");
                compLpm = isDryer ? "152 l/dk" : "170 l/dk";
                compNoise = isSilent ? "53 dB(A)" : "66 dB(A)";
                compTank = "40 L • 1.5 kW / 2 HP";
                compCap = "2 Simultane / 2-3 Ünit";
                compPrice = (isDryer ? 2350 : 1650) + (isSilent ? 1650 : 0);
            } else if (units <= 4) {
                compName = isSilent
                    ? (isDryer ? "MGF CS 50/25 PRIME M" : "MGF CS 50/25 PRIME S")
                    : (isDryer ? "MGF 50/25 PRIME M" : "MGF 50/25 PRIME S");
                compCode = isSilent
                    ? (isDryer ? "PR-CS300-040-M" : "PR-CS300-040")
                    : (isDryer ? "PR-OF300-040-M" : "PR-OF300-040");
                compLpm = isDryer ? "225 l/dk" : "250 l/dk";
                compNoise = isSilent ? "53 dB(A)" : "66 dB(A)";
                compTank = "40 L • 2.2 kW / 3 HP";
                compCap = "3 Simultane / 3-4 Ünit";
                compPrice = (isDryer ? 3250 : 2350) + (isSilent ? 1650 : 0);
            } else if (units <= 6) {
                compName = isSilent
                    ? (isDryer ? "MGF CS 100/30 TANDEM PRIME M" : "MGF CS 100/30 TANDEM PRIME S")
                    : (isDryer ? "MGF 100/30 TANDEM PRIME M" : "MGF 100/30 TANDEM PRIME S");
                compCode = isSilent
                    ? (isDryer ? "PR-CS400-090-MT" : "PR-CS400-090-T")
                    : (isDryer ? "PR-OF400-090-MT" : "PR-OF400-090-T");
                compLpm = isDryer ? "305 l/dk" : "340 l/dk";
                compNoise = isSilent ? "56 dB(A)" : "69 dB(A)";
                compTank = "90 L • 3 kW / 4 HP";
                compCap = "4 Simultane / 5-6 Ünit";
                compPrice = (isDryer ? 7000 : 5600) + (isSilent ? 2200 : 0);
            } else if (units <= 8) {
                compName = isSilent
                    ? (isDryer ? "MGF CS 100/50 TANDEM PRIME M" : "MGF CS 100/50 TANDEM PRIME S")
                    : (isDryer ? "MGF 100/50 TANDEM PRIME M" : "MGF 100/50 TANDEM PRIME S");
                compCode = isSilent
                    ? (isDryer ? "PR-CS600-090-MT" : "PR-CS600-090-T")
                    : (isDryer ? "PR-OF600-090-MT" : "PR-OF600-090-T");
                compLpm = isDryer ? "450 l/dk" : "500 l/dk";
                compNoise = isSilent ? "56 dB(A)" : "69 dB(A)";
                compTank = "90 L • 4.4 kW / 6 HP";
                compCap = "6 Simultane / 7-8 Ünit";
                compPrice = (isDryer ? 8000 : 6600) + (isSilent ? 2200 : 0);
            } else if (units <= 10) {
                compName = isDryer ? "MGF 200/75 PRIME M (400V)" : "MGF 200/75 PRIME S (400V)";
                compCode = isDryer ? "PR-OF900-200-MT3" : "PR-OF900-200-T3";
                compLpm = isDryer ? "660 l/dk" : "750 l/dk";
                compNoise = "72 dB(A)";
                compTank = "200 L • 6.6 kW / 9 HP";
                compCap = "9 Simultane / 9-10 Ünit";
                compPrice = isDryer ? 11500 : 9500;
            } else if (units <= 14) {
                compName = isDryer ? "MGF 270/100 TANDEM PRIME M (IoT)" : "MGF 270/100 TANDEM PRIME S (IoT)";
                compCode = isDryer ? "PR-OF1200-270-MT3-HD" : "PR-OF1200-270-T3-HD";
                compLpm = isDryer ? "780 l/dk" : "900 l/dk";
                compNoise = "75 dB(A)";
                compTank = "270 L • 8 kW / 11 HP";
                compCap = "12 Simultane / 14-15 Ünit";
                compPrice = isDryer ? 15500 : 13200;
            } else {
                compName = "MGF 500/150 PRIME S (IoT • 100% Duty)";
                compCode = "PR-OF1800-500-T3-HD";
                compLpm = "1.350 l/dk";
                compNoise = "78 dB(A)";
                compTank = "500 L • 12 kW / 16.5 HP";
                compCap = "18 Simultane / 20 Ünit";
                compPrice = 19500;
            }

            document.getElementById('out-comp-title').textContent = compName;
            document.getElementById('out-comp-code').textContent = compCode;
            document.getElementById('out-air-lpm').textContent = compLpm;
            document.getElementById('out-comp-noise').textContent = compNoise;
            document.getElementById('out-comp-tank').textContent = compTank;
            document.getElementById('out-comp-cap').textContent = compCap;
            document.getElementById('out-comp-price').textContent = `${compQty > 1 ? compQty + ' x ' : ''}${compPrice.toLocaleString('tr-TR')} €`;
            appState.currentCalcComp = { name: `${compName} DENTAL KOMPRESÖR (${compCode} • ${compLpm}) (İTALYA)`, qty: compQty, unitPrice: compPrice };

            // 2) MGF CERRAHİ ASPİRATÖR HESABI (Resmi MGF Aspirazione 24.07.24 Kataloğu + İZDO 2026)
            let vacName = "", vacCode = "", vacLpm = "", vacMbar = "", vacNoise = "", vacCap = "", vacPrice = 0, vacQty = 1;

            if (appState.suctionType === 'hybrid') {
                const amgExtra = hasAmalgam ? 850 : 0;
                const amgSuffix = hasAmalgam ? "-AS" : "";
                if (units === 1) {
                    vacName = hasAmalgam ? "MGF HYBRID A1S (Amalgam Ayırıcılı)" : "MGF HYBRID 1S";
                    vacCode = hasVacCabinet ? ("AS-075-EX-S" + amgSuffix) : ("AS-075-EX" + amgSuffix);
                    vacLpm = "1.100 l/dk";
                    vacMbar = "120/140 mbar";
                    vacNoise = hasVacCabinet ? "52 dB(A) (Kabinli)" : "63 dB(A)";
                    vacCap = "1 Simultane / 1-2 Ünit";
                    vacPrice = 1300 + amgExtra + (hasVacCabinet ? 450 : 0);
                } else if (units === 2) {
                    vacName = hasAmalgam ? "MGF HYBRID A1 (Amalgam Ayırıcılı)" : "MGF HYBRID 1";
                    vacCode = "AS-094-EX" + amgSuffix;
                    vacLpm = "1.100 / 1.300 l/dk";
                    vacMbar = "180 mbar";
                    vacNoise = hasVacCabinet ? "47 dB(A) (CA-CR-060)" : "57/62 dB(A)";
                    vacCap = "2 Simultane / 2 Ünit";
                    vacPrice = 2250 + amgExtra + (hasVacCabinet ? 1250 : 0);
                } else if (units === 3) {
                    vacName = hasAmalgam ? "MGF HYBRID A2 (Amalgam Ayırıcılı)" : "MGF HYBRID 2";
                    vacCode = "AS-100-EX" + amgSuffix;
                    vacLpm = "1.500 l/dk";
                    vacMbar = "180 mbar";
                    vacNoise = hasVacCabinet ? "47 dB(A) (CA-CR-060)" : "63 dB(A)";
                    vacCap = "3 Simultane / 3 Ünit";
                    vacPrice = 2950 + amgExtra + (hasVacCabinet ? 1250 : 0);
                } else if (units <= 6) {
                    vacName = hasAmalgam ? "MGF HYBRID A5 (İnverterli + Amalgam)" : "MGF HYBRID 5 (İnverterli)";
                    vacCode = "AS-150-EX" + amgSuffix;
                    vacLpm = "2.500 l/dk";
                    vacMbar = "180 mbar";
                    vacNoise = hasVacCabinet ? "47 dB(A) (CA-CR-060)" : "65 dB(A)";
                    vacCap = "4 Simultane / 4-6 Ünit";
                    vacPrice = 4150 + amgExtra + (hasVacCabinet ? 1250 : 0);
                } else if (units <= 12) {
                    vacName = hasAmalgam ? "2x MGF HYBRID A5 Merkezi (HEPA 14)" : "2x MGF HYBRID 5 Merkezi (HEPA 14)";
                    vacCode = "AS-300-EX" + amgSuffix;
                    vacLpm = "5.000 l/dk";
                    vacMbar = "180 mbar";
                    vacNoise = "70 dB(A)";
                    vacCap = "8 Simultane / 7-12 Ünit";
                    vacPrice = 8300 + (amgExtra * 2);
                } else {
                    vacName = hasAmalgam ? "3x MGF HYBRID A5 Merkezi (HEPA 14)" : "3x MGF HYBRID 5 Merkezi (HEPA 14)";
                    vacCode = "AS-450-EX" + amgSuffix;
                    vacLpm = "7.500 l/dk";
                    vacMbar = "180 mbar";
                    vacNoise = "70 dB(A)";
                    vacCap = "12 Simultane / 13-18 Ünit";
                    vacPrice = 12450 + (amgExtra * 3);
                }
            } else {
                // Kuru Sistem: ASPIR QC / SILENT Serisi
                if (units === 1) {
                    vacName = hasVacCabinet ? "MGF SILENT 1 (Kabinli Kuru)" : "MGF ASPIR 1QC (Kuru)";
                    vacCode = hasVacCabinet ? "AS-050-S" : "AS-050-QC";
                    vacLpm = "1.230 l/dk";
                    vacMbar = "120 mbar";
                    vacNoise = hasVacCabinet ? "50 dB(A)" : "58 dB(A)";
                    vacCap = "1 Ünit (0.37 kW)";
                    vacPrice = hasVacCabinet ? 1350 : 950;
                } else if (units === 2) {
                    vacName = hasVacCabinet ? "MGF SILENT 2 (Kabinli Kuru)" : "MGF ASPIR 2QC (Kuru)";
                    vacCode = hasVacCabinet ? "AS-100-S" : "AS-100-QC";
                    vacLpm = "2.280 l/dk";
                    vacMbar = "140 mbar";
                    vacNoise = hasVacCabinet ? "54 dB(A)" : "62 dB(A)";
                    vacCap = "2 Ünit (0.75 kW)";
                    vacPrice = hasVacCabinet ? 1850 : 1400;
                } else if (units === 3) {
                    vacName = hasVacCabinet ? "MGF SILENT 3 (Kabinli Kuru)" : "MGF ASPIR 3QC (Kuru)";
                    vacCode = hasVacCabinet ? "AS-150-S" : "AS-150-QC";
                    vacLpm = "2.280 l/dk";
                    vacMbar = "170 mbar";
                    vacNoise = hasVacCabinet ? "55 dB(A)" : "63 dB(A)";
                    vacCap = "3 Ünit (1.1 kW)";
                    vacPrice = hasVacCabinet ? 2250 : 1750;
                } else if (units <= 6) {
                    vacName = hasVacCabinet ? "MGF SILENT 4 (Kabinli Kuru)" : "MGF ASPIR 4QC (Kuru)";
                    vacCode = hasVacCabinet ? "AS-200-S" : "AS-200-QC";
                    vacLpm = "3.650 l/dk";
                    vacMbar = "175 mbar";
                    vacNoise = hasVacCabinet ? "59 dB(A)" : "67 dB(A)";
                    vacCap = "4-6 Ünit (1.5 kW)";
                    vacPrice = hasVacCabinet ? 2900 : 2300;
                } else {
                    vacName = hasVacCabinet ? "2x MGF SILENT 4 (Çift Hat Kuru)" : "2x MGF ASPIR 4QC (Çift Hat Kuru)";
                    vacCode = hasVacCabinet ? "2x AS-200-S" : "2x AS-200-QC";
                    vacLpm = "7.300 l/dk";
                    vacMbar = "175 mbar";
                    vacNoise = hasVacCabinet ? "59 dB(A)" : "67 dB(A)";
                    vacCap = "7+ Ünit (2x 1.5 kW)";
                    vacPrice = hasVacCabinet ? 2900 : 2300;
                    vacQty = 2;
                }
            }

            document.getElementById('out-vac-title').textContent = vacName;
            document.getElementById('out-vac-code').textContent = vacCode;
            document.getElementById('out-vac-lpm').textContent = vacLpm;
            document.getElementById('out-vac-mbar').textContent = vacMbar;
            document.getElementById('out-vac-noise').textContent = vacNoise;
            document.getElementById('out-vac-cap').textContent = vacCap;
            document.getElementById('out-vac-price').textContent = `${vacQty > 1 ? vacQty + ' x ' : ''}${vacPrice.toLocaleString('tr-TR')} €`;
            appState.currentCalcVac = { name: `${vacName} DENTAL ASPİRATÖR (${vacCode} • ${vacLpm}) (İTALYA)`, qty: vacQty, unitPrice: vacPrice };

            // 3) 2-IN-1 ASPIR-COMP ENTEGRE KABİN (1-4 ÜNİT)
            const acCard = document.getElementById('aspir-comp-card');
            if (units <= 4) {
                acCard.classList.remove('hidden');
                let acTitle = "", acCode = "", acDesc = "", acNoise = "52 dB(A)", acPrice = 0;
                if (units <= 2) {
                    acTitle = isDryer ? "ASPIR-COMP 24/10 GENESI MC (Hybrid 1S)" : "ASPIR-COMP 24/10 GENESI SC (Hybrid 1S)";
                    acCode = isDryer ? "D-AC150-024-MC" : "D-AC150-024-C";
                    acDesc = `Kod: ${acCode} • 1-2 Ünit • 24L Tank • Hybrid 1S Yarı Islak • 53x50x130 cm`;
                    acNoise = isDryer ? "52 dB(A)" : "53 dB(A)";
                    acPrice = isDryer ? 6500 : 5800;
                } else if (units === 3) {
                    acTitle = isDryer ? "ASPIR-COMP 30/15 PRIME MC (Hybrid 2)" : "ASPIR-COMP 30/15 PRIME SC (Hybrid 2)";
                    acCode = isDryer ? "PR-AC200-040-MC" : "PR-AC200-040-C";
                    acDesc = `Kod: ${acCode} • 2-3 Ünit • 40L Tank • Hybrid 2 Yarı Islak • 49x75x155 cm`;
                    acNoise = "55 dB(A)";
                    acPrice = isDryer ? 8250 : 7500;
                } else {
                    acTitle = isDryer ? "ASPIR-COMP 30/25 PRIME MC (Hybrid 5)" : "ASPIR-COMP 30/25 PRIME SC (Hybrid 5)";
                    acCode = isDryer ? "PR-AC300-040-MC" : "PR-AC300-040-C";
                    acDesc = `Kod: ${acCode} • 3-4 Ünit • 40L Tank • Hybrid 5 İnverterli • 49x75x155 cm`;
                    acNoise = "55 dB(A)";
                    acPrice = isDryer ? 9900 : 9100;
                }
                if (hasAmalgam) {
                    acTitle += " + ECO II+ Amalgam";
        function parseProposalDateToIso(rawVal) {
            const val = (rawVal || '').trim();
            if (/^\d{4}-\d{2}-\d{2}$/.test(val)) return val;
            const m = val.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
            if (m) {
                const dd = m[1].padStart(2, '0');
                const mm = m[2].padStart(2, '0');
                return `${m[3]}-${mm}-${dd}`;
            }
            return new Date().toISOString().split('T')[0];
        }

        async function saveProposalToCRM() {
            let token = localStorage.getItem("token");
            if (!token) {
                // Bağımsız ekrandan PIN ile girildiyse otomatik token almayı dene
                try {
                    const pinRes = await fetch("/api/pin-login", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ pin: MANNAS_PIN })
                    });
                    if (pinRes.ok) {
                        const pinData = await pinRes.json();
                        token = pinData.access_token;
                        localStorage.setItem("token", token);
                    }
                } catch (e) {}
            }
            if (!token) {
                showToast("CRM'e kaydetmek için ana portaldan giriş yapın.");
                return;
            }

            const customer = document.getElementById('prop-customer').value.trim();
            if (!customer) {
                showToast("Lütfen UNVAN (Doktor / Müşteri Adı) alanını doldurun.");
                document.getElementById('prop-customer').focus();
                return;
            }
            if (appState.proposalItems.length === 0) {
                showToast("Lütfen teklife en az 1 ürün ekleyin.");
                return;
            }

            const isoDate = parseProposalDateToIso(document.getElementById('prop-date').value);
            const city = document.getElementById('prop-city').value.trim();
            const phone = document.getElementById('prop-phone').value.trim();
            const agreed = document.getElementById('prop-agreed-price').value.trim();
            const vat = document.getElementById('prop-vat').value.trim();
            const down = document.getElementById('prop-downpayment').value.trim();
            const inst = document.getElementById('prop-installments').value.trim();
            const firstDate = document.getElementById('prop-first-date').value.trim();
            const repRaw = document.getElementById('prop-rep').value.trim();
            const staffName = (repRaw.split('(')[0].trim() || 'HAKAN BEHRAMOĞLU').toUpperCase();

            // Ana kalemler (alt föy satırları hariç)
            const mainItems = appState.proposalItems.filter(x => !x.name.trim().startsWith('↳'));
            const sourceItems = mainItems.length > 0 ? mainItems : appState.proposalItems;

            // Cihazlar sütunu: Gerçek ürün adlarını özetle
            const devicesSummary = sourceItems.map(x => {
                const shortName = x.name.split('(')[0].split('[')[0].trim();
                return `${x.qty}x ${shortName || x.cat}`;
            }).join(', ');

            // Teklif toplamı ve satır detayları
            let total = 0;
            const itemLines = [];
            appState.proposalItems.forEach(x => {
                const sub = (x.qty || 1) * (x.price || 0);
                total += sub;
                const isSub = x.name.trim().startsWith('↳');
                if (!isSub || sub > 0) {
                    const priceTxt = sub > 0 ? ` (${sub.toLocaleString('tr-TR')} €)` : '';
                    itemLines.push(`${x.qty}x ${x.name.trim()}${priceTxt}`);
                }
            });

            const metaParts = [];
            if (city) metaParts.push(`Şehir: ${city}`);
            if (phone) metaParts.push(`Tel: ${phone}`);
            if (agreed) metaParts.push(`Anlaşılan: ${agreed}`);
            if (vat) metaParts.push(`KDV: ${vat}`);
            if (down) metaParts.push(`Peşinat: ${down}`);
            if (inst) metaParts.push(`Vade: ${inst}`);
            if (firstDate) metaParts.push(`İlk Senet: ${firstDate}`);

            const notesParts = [
                `Teklif Toplamı: ${total.toLocaleString('tr-TR', { minimumFractionDigits: 2 })} € + KDV`,
                `İçerik: ${itemLines.join(' | ')}`
            ];
            if (metaParts.length > 0) notesParts.push(metaParts.join(' • '));

            try {
                const res = await fetch("/api/interactions", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + token },
                    body: JSON.stringify({
                        date: isoDate,
                        customer_name: customer,
                        devices: devicesSummary,
                        notes: notesParts.join(' || '),
                        staff_name: staffName,
                        offer_url: ""
                    })
                });

                if (res.ok) {
                    showToast(`${customer} teklifi CRM Görüşmelerine kaydedildi!`);
                    if (window.parent && window.parent !== window) {
                        window.parent.postMessage({ type: 'CRM_INTERACTION_SAVED' }, '*');
                    }
                } else {
                    const errData = await res.json().catch(() => ({}));
                    showToast(`CRM kayıt hatası: ${errData.detail || res.status}`);
                }
            } catch (err) {
                showToast("Sunucuya bağlanılamadı, kayıt yapılamadı.");
            }
        }

        function getMannasLogoDataUrl() {
            const canvas = document.createElement('canvas');
            canvas.width = 620; canvas.height = 230;
            const ctx = canvas.getContext('2d');
            const grad = ctx.createLinearGradient(20, 200, 200, 20);
            grad.addColorStop(0, '#f97316'); grad.addColorStop(0.5, '#ea580c'); grad.addColorStop(1, '#f97316');
            ctx.beginPath(); ctx.strokeStyle = grad; ctx.lineWidth = 26; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
            ctx.moveTo(192, 152);
            ctx.bezierCurveTo(144, 216, 24, 192, 24, 92);
            ctx.bezierCurveTo(24, 20, 88, 8, 124, 48);
            ctx.bezierCurveTo(150, 76, 166, 76, 192, 48);
            ctx.bezierCurveTo(228, 8, 280, 24, 296, 76);
            ctx.stroke();
            ctx.font = '900 70px Inter, Arial, sans-serif'; ctx.fillStyle = '#ea580c'; ctx.fillText('MANNAS', 228, 154);
            ctx.font = '700 36px Inter, Arial, sans-serif'; ctx.fillStyle = '#f97316'; ctx.fillText('DENTAL', 232, 204);
            return canvas.toDataURL('image/png', 1.0);
        }

        function buildOfficialA4Html() {
            const customer = document.getElementById('prop-customer').value || '-';
            const city = document.getElementById('prop-city').value || '-';
            const phone = document.getElementById('prop-phone').value || '-';
            const tax = document.getElementById('prop-tax').value || '-';
            const subject = document.getElementById('prop-subject').value || 'FİYAT TEKLİFİ';
            const dateVal = document.getElementById('prop-date').value || new Date().toLocaleDateString('tr-TR');
            const agreed = document.getElementById('prop-agreed-price').value || '';
            const vat = document.getElementById('prop-vat').value || '';
            const down = document.getElementById('prop-downpayment').value || '';
            const inst = document.getElementById('prop-installments').value || '';
            const firstDate = document.getElementById('prop-first-date').value || '';

            let total = 0, rowsHtml = '';
            if (appState.proposalItems.length === 0) {
                rowsHtml = `<tr><td colspan="5" style="padding:16px;text-align:center;color:#6b7280;font-size:11px;border:1px solid #cbd5e1;">Teklif tablosu boş.</td></tr>`;
            } else {
                appState.proposalItems.forEach(it => {
                    const sub = it.qty * it.price; total += sub;
                    rowsHtml += `<tr>
                        <td style="padding:7px 9px;border:1px solid #cbd5e1;font-weight:700;font-size:10px;color:#0c4a6e;white-space:nowrap;">${it.cat}</td>
                        <td style="padding:7px 9px;border:1px solid #cbd5e1;font-size:10px;color:#111827;">${it.name}</td>
                        <td style="padding:7px 9px;border:1px solid #cbd5e1;text-align:center;font-weight:700;font-size:10.5px;">${it.qty}</td>
                        <td style="padding:7px 9px;border:1px solid #cbd5e1;text-align:right;font-size:10.5px;white-space:nowrap;">${it.price.toLocaleString('tr-TR', { minimumFractionDigits: 2 })} €</td>
                        <td style="padding:7px 9px;border:1px solid #cbd5e1;text-align:right;font-weight:700;font-size:10.5px;white-space:nowrap;">${sub.toLocaleString('tr-TR', { minimumFractionDigits: 2 })} €</td>
                    </tr>`;
                });
            }
            const logoPng = getMannasLogoDataUrl();
            return `<div style="font-family:Inter,Arial,sans-serif;color:#111827;background:#fff;">
                <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:3px solid #ea580c;padding-bottom:10px;margin-bottom:12px;">
                    <div style="display:flex;align-items:center;gap:12px;">
                        <img src="${logoPng}" style="width:150px;height:auto;" alt="Mannas Dental">
                        <div>
                            <div style="font-size:13px;font-weight:800;color:#0f172a;">MANNAS DİŞ DEPOSU TİCARET ve SANAYİ LİMİTED ŞİRKETİ</div>
                            <div style="font-size:9.5px;color:#4b5563;">STERN WEBER • MYRAY • MGF • TÜRKİYE DİSTRİBÜTÖRÜ</div>
                            <div style="font-size:9px;color:#64748b;">Oğuzhan Cad. No:39 Fındıkzade-Fatih / İSTANBUL • Tel: 0212 635 77 26</div>
                        </div>
                    </div>
                    <div style="text-align:right;">
                        <div style="background:#ea580c;color:#fff;font-weight:800;font-size:12px;padding:4px 10px;border-radius:6px;display:inline-block;">${subject}</div>
                        <div style="font-size:10.5px;font-weight:700;margin-top:4px;">TARİH: ${dateVal}</div>
                    </div>
                </div>
                <table style="width:100%;border-collapse:collapse;margin-bottom:12px;font-size:10.5px;">
                    <tr><td style="padding:5px 8px;border:1px solid #cbd5e1;background:#f8fafc;font-weight:700;width:18%;">UNVAN:</td><td style="padding:5px 8px;border:1px solid #cbd5e1;font-weight:700;width:32%;">${customer}</td><td style="padding:5px 8px;border:1px solid #cbd5e1;background:#f8fafc;font-weight:700;width:18%;">TC / VERGİ NO:</td><td style="padding:5px 8px;border:1px solid #cbd5e1;">${tax}</td></tr>
                    <tr><td style="padding:5px 8px;border:1px solid #cbd5e1;background:#f8fafc;font-weight:700;">ADRES / ŞEHİR:</td><td style="padding:5px 8px;border:1px solid #cbd5e1;">${city}</td><td style="padding:5px 8px;border:1px solid #cbd5e1;background:#f8fafc;font-weight:700;">CEP TEL:</td><td style="padding:5px 8px;border:1px solid #cbd5e1;">${phone}</td></tr>
                </table>
                <table style="width:100%;border-collapse:collapse;margin-bottom:12px;">
                    <thead><tr style="background:#0c4a6e;color:#fff;font-size:10px;text-transform:uppercase;"><th style="padding:7px 9px;text-align:left;">ÜRÜNLER</th><th style="padding:7px 9px;text-align:left;">ÜRÜN ADI</th><th style="padding:7px 9px;text-align:center;">ADET</th><th style="padding:7px 9px;text-align:right;">BİRİM</th><th style="padding:7px 9px;text-align:right;">TUTAR</th></tr></thead>
                    <tbody>${rowsHtml}</tbody>
                    <tfoot><tr style="background:#f1f5f9;"><td colspan="2" style="padding:8px 9px;border:1px solid #cbd5e1;font-weight:700;font-size:10px;color:#b45309;">FİYATLARIMIZA KDV DAHİL DEĞİLDİR</td><td colspan="2" style="padding:8px 9px;border:1px solid #cbd5e1;text-align:right;font-weight:800;font-size:11px;">TOPLAM:</td><td style="padding:8px 9px;border:1px solid #cbd5e1;text-align:right;font-weight:800;font-size:12px;color:#0284c7;">${total.toLocaleString('tr-TR', { minimumFractionDigits: 2 })} €</td></tr></tfoot>
                </table>
                <table style="width:100%;border-collapse:collapse;margin-bottom:12px;font-size:10px;">
                    <tr><td style="padding:5px 8px;border:1px solid #cbd5e1;background:#f8fafc;font-weight:800;width:34%;">✔ TOPLAM ANLAŞILAN FİYAT:</td><td style="padding:5px 8px;border:1px solid #cbd5e1;font-weight:800;color:#047857;">${agreed}</td></tr>
                    <tr><td style="padding:5px 8px;border:1px solid #cbd5e1;background:#f8fafc;font-weight:800;">✔ KDV TUTARI:</td><td style="padding:5px 8px;border:1px solid #cbd5e1;">${vat}</td></tr>
                    <tr><td style="padding:5px 8px;border:1px solid #cbd5e1;background:#f8fafc;font-weight:800;">✔ PEŞİN VERİLECEK:</td><td style="padding:5px 8px;border:1px solid #cbd5e1;">${down}</td></tr>
                    <tr><td style="padding:5px 8px;border:1px solid #cbd5e1;background:#f8fafc;font-weight:800;">✔ VADE SAYISI VE RAKAMI:</td><td style="padding:5px 8px;border:1px solid #cbd5e1;">${inst}</td></tr>
                    <tr><td style="padding:5px 8px;border:1px solid #cbd5e1;background:#f8fafc;font-weight:800;">✔ İLK SENET ÖDEME TARİHİ:</td><td style="padding:5px 8px;border:1px solid #cbd5e1;">${firstDate}</td></tr>
                </table>
                <div style="display:flex;justify-content:space-between;align-items:flex-end;border-top:2px solid #e2e8f0;padding-top:10px;font-size:9px;color:#475569;">
                    <div><div style="font-weight:800;color:#0f172a;font-size:10px;">MANNAS DİŞ DEPOSU TİC. ve SAN. LTD. ŞTİ.</div><div>Oğuzhan Cad. No:39 Fındıkzade-Fatih İSTANBUL • 0212 635 77 26</div></div>
                    <div style="text-align:right;border:1px solid #bae6fd;background:#f0f9ff;padding:6px 12px;border-radius:6px;"><div style="font-weight:800;font-size:11px;color:#0c4a6e;">HAKAN BEHRAMOĞLU</div><div style="font-weight:700;font-size:10px;color:#0284c7;">İŞ GELİŞTİRME UZMANI</div><div>0090 (546) 291 82 43</div></div>
                </div>
            </div>`;
        }

        function openOfficialPrintModal() {
            document.getElementById('a4-printable-paper').innerHTML = buildOfficialA4Html();
            document.getElementById('a4-preview-modal').classList.remove('hidden');
        }
        function closeOfficialPrintModal() { document.getElementById('a4-preview-modal').classList.add('hidden'); }

        function downloadDirectPdf() {
            const paper = document.getElementById('a4-printable-paper');
            paper.innerHTML = buildOfficialA4Html();
            const modal = document.getElementById('a4-preview-modal');
            if (modal.classList.contains('hidden')) modal.classList.remove('hidden');
            const safeName = (document.getElementById('prop-customer').value.trim() || 'Musteri').replace(/[^a-zA-Z0-9ğüşıöçĞÜŞİÖÇ\s_-]/g, '').replace(/\s+/g, '_');
            showToast('PDF hazırlanıyor...');
            if (typeof html2pdf !== 'undefined') {
                html2pdf().set({
                    margin: [8, 8, 8, 8],
                    filename: `KlinikMatrix_Teklif_${safeName}.pdf`,
                    image: { type: 'jpeg', quality: 0.98 },
                    html2canvas: { scale: 2, useCORS: true, backgroundColor: '#ffffff' },
                    jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
                }).from(paper).save().then(() => showToast('PDF indirildi!')).catch(() => triggerPopupPrint());
            } else {
                triggerPopupPrint();
            }
        }

        function triggerPopupPrint() {
            const htmlContent = buildOfficialA4Html();
            const win = window.open('', '_blank', 'width=900,height=1000');
            if (win) {
                win.document.open();
                win.document.write(`<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Teklif Yazdır</title><style>@page{size:A4 portrait;margin:8mm;}body{margin:0;background:#fff;}</style></head><body>${htmlContent}<script>window.onload=function(){setTimeout(function(){window.print();},300);};<\/script></body></html>`);
                win.document.close();
            } else window.print();
        }

        function copyOfficialProposal() {
            const customer = document.getElementById('prop-customer').value || '-';
            const dateVal = document.getElementById('prop-date').value || new Date().toLocaleDateString('tr-TR');
            let total = 0;
            let txt = `MANNAS DİŞ DEPOSU - FİYAT TEKLİFİ\nUNVAN: ${customer} | TARİH: ${dateVal}\n----------------------------------\n`;
            appState.proposalItems.forEach((it, i) => {
                const sub = it.qty * it.price; total += sub;
                txt += `${i + 1}. [${it.cat}] ${it.name} (${it.qty} x ${it.price.toLocaleString('tr-TR')} € = ${sub.toLocaleString('tr-TR')} €)\n`;
            });
            txt += `----------------------------------\nTOPLAM: ${total.toLocaleString('tr-TR', { minimumFractionDigits: 2 })} € (KDV Hariç)\nHakan BEHRAMOĞLU (0546 291 82 43)\n`;
            navigator.clipboard.writeText(txt).then(() => showToast("Teklif metni kopyalandı!")).catch(() => showToast("Kopyalama başarısız."));
        }

        function resetToBlankTemplate() {
            ['prop-customer','prop-city','prop-phone','prop-tax','prop-agreed-price','prop-vat','prop-downpayment','prop-installments','prop-first-date'].forEach(id => {
                document.getElementById(id).value = '';
            });
            document.getElementById('prop-date').value = new Date().toLocaleDateString('tr-TR');
            appState.proposalItems = [];
            renderProposalTable();
        }

        function showToast(msg) {
            const box = document.getElementById('toast-box');
            document.getElementById('toast-text').textContent = msg;
            box.classList.remove('hidden');
            setTimeout(() => box.classList.add('hidden'), 3500);
        }

        window.onload = function() {
            const params = new URLSearchParams(window.location.search);
            if (params.get('embed') === '1' && localStorage.getItem('token')) {
                document.getElementById('pin-lock-overlay').classList.add('hidden');
            }
            populateTdbOptionsDropdown();
            selectUnitModel('S200');
            renderSingleImagingList();
            updateEngineeringCalc();
            resetToBlankTemplate();
        };
    </script>
</body>
</html>"""


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=False)