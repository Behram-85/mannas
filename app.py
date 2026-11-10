import os
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse, Response, JSONResponse, FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
import uvicorn

# PostgreSQL veya SQLite otomatik seçimi
DATABASE_URL = os.getenv("DATABASE_URL")
IS_POSTGRES = DATABASE_URL is not None and DATABASE_URL.startswith("postgres")

if IS_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    import sqlite3

SECRET_KEY = "mannas-super-secret-jwt-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crm_database.db")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/token")
app = FastAPI(title="Klinik Matrix - CRM & Satış Takip Portalı")

# Yüklenen 3D İzometrik Dental Küp (Ünit, 3D Röntgen, Hava Sterilizasyon) Vektörel Karşılığı
LOGO_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600" width="100%" height="100%">
  <defs>
    <linearGradient id="topFace" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#60b5ff"/>
      <stop offset="100%" stop-color="#2b82d9"/>
    </linearGradient>
    <linearGradient id="leftFace" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#2687a5"/>
      <stop offset="100%" stop-color="#0e4f68"/>
    </linearGradient>
    <linearGradient id="rightFace" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#153969"/>
      <stop offset="100%" stop-color="#091d3e"/>
    </linearGradient>
    <linearGradient id="chairBlue" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#2575fc"/>
      <stop offset="100%" stop-color="#0b3d91"/>
    </linearGradient>
    <linearGradient id="beamGrad" x1="100%" y1="0%" x2="0%" y2="50%">
      <stop offset="0%" stop-color="#00f2fe" stop-opacity="0.75"/>
      <stop offset="100%" stop-color="#0072ff" stop-opacity="0.12"/>
    </linearGradient>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="5" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>
  </defs>

  <!-- Siyah Arka Plan -->
  <rect width="600" height="600" rx="100" fill="#000000"/>

  <!-- İZOMETRİK KÜP YÜZEYLERİ -->
  <!-- Üst Yüzey -->
  <polygon points="300,85 515,205 300,325 85,205" fill="url(#topFace)"/>
  <!-- Sol Yüzey -->
  <polygon points="85,205 300,325 300,560 85,440" fill="url(#leftFace)"/>
  <!-- Sağ Yüzey -->
  <polygon points="300,325 515,205 515,440 300,560" fill="url(#rightFace)"/>
  <!-- Küp Kenar Çizgisi -->
  <polyline points="85,205 300,325 515,205" fill="none" stroke="#85d7ff" stroke-width="1.5" opacity="0.5"/>
  <line x1="300" y1="325" x2="300" y2="560" stroke="#38bdf8" stroke-width="1.5" opacity="0.4"/>

  <!-- SOL YÜZEY: HAVA STERİLİZASYON CİHAZI & HAVA AKIŞI -->
  <!-- Cihaz Gövdesi -->
  <polygon points="105,260 145,282 145,442 105,420" fill="#e2e8f0" stroke="#94a3b8" stroke-width="1"/>
  <polygon points="145,282 162,272 162,432 145,442" fill="#cbd5e1"/>
  <polygon points="105,260 122,250 162,272 145,282" fill="#f8fafc"/>
  <!-- Izgara -->
  <polygon points="147,295 159,288 159,395 147,402" fill="#1e293b"/>
  <!-- Parlayan Mavi Hava Dalgaları -->
  <g filter="url(#glow)" fill="none" stroke="#38bdf8" stroke-linecap="round">
    <path d="M158,305 C195,295 215,345 255,335 C275,330 285,345 292,350" stroke-width="4" opacity="0.85"/>
    <path d="M158,330 C195,320 215,375 255,365 C275,360 285,375 292,380" stroke-width="5" stroke="#7dd3fc" opacity="0.95"/>
    <path d="M158,355 C195,345 215,405 255,395 C275,390 285,405 292,410" stroke-width="4" opacity="0.85"/>
    <path d="M158,380 C195,370 215,435 255,425 C275,420 285,435 292,440" stroke-width="3.5" opacity="0.75"/>
  </g>
  <!-- Partiküller -->
  <g fill="#bae6fd" filter="url(#glow)">
    <circle cx="195" cy="325" r="2.5"/><circle cx="225" cy="355" r="3"/><circle cx="260" cy="348" r="2"/>
    <circle cx="210" cy="385" r="2.5"/><circle cx="245" cy="398" r="3"/><circle cx="275" cy="415" r="2.5"/>
    <circle cx="185" cy="365" r="2"/><circle cx="235" cy="430" r="2.5"/><circle cx="270" cy="380" r="3"/>
  </g>

  <!-- SAĞ YÜZEY: 3D PANORAMİK RÖNTGEN (CBCT) & KAFATASI HOLOGRAMI -->
  <!-- Cihaz Sütunu ve Kolu -->
  <polygon points="465,240 495,255 495,465 465,450" fill="#cbd5e1"/>
  <polygon points="445,250 465,240 465,450 445,460" fill="#e2e8f0"/>
  <path d="M405,260 L465,225 L495,240 L495,345 L470,360 L470,285 L430,305 L430,360 L405,345 Z" fill="#f8fafc" stroke="#94a3b8" stroke-width="1"/>
  <!-- Hologram Işın Konisi -->
  <polygon points="455,345 320,375 320,485 365,510" fill="url(#beamGrad)"/>
  <!-- Hologram 3D Çerçeve -->
  <polygon points="320,375 365,400 365,510 320,485" fill="none" stroke="#38bdf8" stroke-width="2" filter="url(#glow)"/>
  <polygon points="335,365 380,390 380,500 335,475" fill="none" stroke="#00f2fe" stroke-width="1" opacity="0.6"/>
  <!-- Röntgen Çene / Kafatası Silüeti -->
  <g fill="none" stroke="#bae6fd" stroke-width="2" filter="url(#glow)" opacity="0.9">
    <path d="M332,405 Q348,392 360,410 Q365,430 355,445 L355,468 Q342,478 332,462 Z" fill="#0284c7" fill-opacity="0.35"/>
    <!-- Diş Sırası -->
    <path d="M334,445 Q344,452 354,446" stroke="#ffffff" stroke-width="2.5" stroke-dasharray="3,2"/>
    <path d="M335,452 Q344,459 353,453" stroke="#ffffff" stroke-width="2.5" stroke-dasharray="3,2"/>
  </g>

  <!-- ÜST YÜZEY: MAVİ DENTAL ÜNİT KOLTUĞU -->
  <!-- Ünit Tabanı -->
  <polygon points="225,205 295,175 345,205 275,238" fill="#475569"/>
  <polygon points="240,198 295,175 335,198 280,222" fill="#f1f5f9"/>
  <path d="M250,195 L285,160 L325,180 L315,215 L265,220 Z" fill="#e2e8f0" stroke="#94a3b8" stroke-width="1"/>
  <!-- Kreşuar & Su Ünitesi -->
  <ellipse cx="295" cy="128" rx="18" ry="10" fill="#ffffff" stroke="#cbd5e1" stroke-width="2"/>
  <!-- Mavi Koltuk Sırtlığı ve Oturma Yeri -->
  <path d="M215,105 Q205,135 230,158 L268,142 Q255,112 235,98 Z" fill="url(#chairBlue)" stroke="#1e3a8a" stroke-width="1.5"/>
  <!-- Tetiyer (Başlık) -->
  <ellipse cx="222" cy="82" rx="14" ry="9" transform="rotate(-15 222 82)" fill="url(#chairBlue)"/>
  <!-- Koltuk Minderi ve Ayak Kısmı -->
  <path d="M235,158 L295,138 L345,168 L362,202 L322,215 L292,175 L245,175 Z" fill="url(#chairBlue)" stroke="#1e3a8a" stroke-width="1.5"/>
  <!-- Doktor Tableti ve Kamçı Kollar -->
  <polygon points="325,125 375,142 362,160 312,142" fill="#f8fafc" stroke="#94a3b8" stroke-width="1"/>
  <path d="M330,152 Q332,205 342,205 M342,155 Q345,210 355,208 M354,158 Q358,212 368,210" fill="none" stroke="#64748b" stroke-width="2"/>
  <!-- Monitör Ekranı -->
  <polygon points="365,78 408,92 396,128 355,114" fill="#f8fafc" stroke="#475569" stroke-width="2"/>
  <polygon points="369,83 403,95 393,123 360,111" fill="#0f172a"/>
  <circle cx="381" cy="103" r="9" fill="none" stroke="#38bdf8" stroke-width="1.5"/>
  <!-- Reflektör (Üst Işık Kolu) -->
  <polyline points="335,128 345,52 295,35" fill="none" stroke="#e2e8f0" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
  <ellipse cx="292" cy="42" rx="18" ry="11" fill="#e2e8f0" stroke="#64748b" stroke-width="1.5"/>
  <ellipse cx="292" cy="44" rx="13" ry="7" fill="#bae6fd" filter="url(#glow)"/>
</svg>'''

@app.get("/icon.svg")
def get_icon_svg():
    # Klasörde icon.jpg veya icon.png varsa doğrudan orijinal resmi sunar, yoksa gömülü 3D SVG'yi döner
    base_dir = os.path.dirname(os.path.abspath(__file__))
    jpg_path = os.path.join(base_dir, "icon.jpg")
    png_path = os.path.join(base_dir, "icon.png")
    if os.path.exists(jpg_path):
        return FileResponse(jpg_path, media_type="image/jpeg")
    if os.path.exists(png_path):
        return FileResponse(png_path, media_type="image/png")
    return Response(content=LOGO_SVG, media_type="image/svg+xml")

@app.get("/manifest.json")
def get_manifest():
    return JSONResponse({
        "name": "Klinik Matrix CRM",
        "short_name": "Klinik Matrix",
        "description": "Klinik Matrix - Satış ve Stok Yönetim Portalı",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#0d47ff",
        "icons": [
            {
                "src": "/icon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any maskable"
            }
        ]
    })

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hash_password(plain_password) == hashed_password

def get_db():
    if IS_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        return conn

def execute_query(query: str, params=(), fetch_one=False, fetch_all=False, commit=False):
    conn = get_db()
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
    conn.close()
    return result

def init_db():
    auto_id = "SERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    
    execute_query(f'''CREATE TABLE IF NOT EXISTS users (
        id {auto_id},
        username TEXT UNIQUE,
        password_hash TEXT,
        full_name TEXT,
        role TEXT
    )''', commit=True)

    execute_query(f'''CREATE TABLE IF NOT EXISTS staff (
        id {auto_id},
        name TEXT UNIQUE,
        department TEXT,
        title TEXT
    )''', commit=True)

    execute_query(f'''CREATE TABLE IF NOT EXISTS products (
        id {auto_id},
        brand TEXT,
        model TEXT UNIQUE,
        price REAL,
        stock INTEGER
    )''', commit=True)

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

    execute_query(f'''CREATE TABLE IF NOT EXISTS interactions (
        id {auto_id},
        date TEXT,
        customer_name TEXT,
        devices TEXT,
        notes TEXT,
        "YETKİLİ PERSONEL" TEXT,
        "TEKLİF URL'si" TEXT
    )''', commit=True)

    # Eski 'admin' kullanıcısını temizle ve yalnızca 'hakan' (şifre: 7659) kullanıcısını aktif et
    execute_query("DELETE FROM users WHERE username != ?", ("hakan",), commit=True)
    user = execute_query("SELECT id FROM users WHERE username = ?", ("hakan",), fetch_one=True)
    if not user:
        execute_query("INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                      ("hakan", hash_password("7659"), "Hakan Behramoğlu", "Admin"), commit=True)
    else:
        execute_query("UPDATE users SET password_hash = ?, full_name = ? WHERE username = 'hakan'",
                      (hash_password("7659"), "Hakan Behramoğlu"), commit=True)

    staff_count = execute_query("SELECT COUNT(*) as count FROM staff", fetch_one=True)
    if staff_count and staff_count["count"] == 0:
        seed_staff = [
            ("NEVZAT KİRTİŞ", "KURUMSAL SATIŞ", "KURUMSAL İLİŞKİLER DİREKTÖRÜ"),
            ("SAMET ŞEN", "GENEL SATIŞ", "SATIŞ MÜDÜRÜ"),
            ("HAKAN BEHRAMOĞLU", "SATIŞ VE PAZARLAMA", "SATIŞ TEMSİLCİSİ"),
            ("SEDAT TUTKA", "SATIŞ", "SATIŞ TEMSİLCİSİ"),
            ("ALİ CAN ÇIPA", "KURUMSAL SATIŞ", "KURUMSAL SATIŞ TEMSİLCİSİ")
        ]
        for item in seed_staff:
            execute_query("INSERT INTO staff (name, department, title) VALUES (?, ?, ?) ON CONFLICT DO NOTHING", item, commit=True)

    prod_count = execute_query("SELECT COUNT(*) as count FROM products", fetch_one=True)
    if prod_count and prod_count["count"] == 0:
        seed_products = [
            ("STERN WEBER", "S200 ORTHO", 9500.0, 1),
            ("STERN WEBER", "S200 +", 12000.0, 40),
            ("STERN WEBER", "TR 220", 14000.0, 0),
            ("STERN WEBER", "S300", 15500.0, 27),
            ("STERN WEBER", "TR 320", 30000.0, 0),
            ("STERN WEBER", "S 280 TRC", 17500.0, 1),
            ("STERN WEBER", "S 380 TRC", 25000.0, 59),
            ("STERN WEBER", "SURGICAL CART", 6000.0, 1),
            ("SILVERFOX", "S 8", 9000.0, 1),
            ("SILVERFOX", "8000 C IMPLANT", 9000.0, 2),
            ("SILVERFOX", "8000 C PRO", 6500.0, 17),
            ("SILVERFOX", "8000 C KLASİK", 5650.0, 0),
            ("SILVERFOX", "8000 B", 3900.0, 29),
            ("SILVERFOX", "8000 B BASIC", 3500.0, 8),
            ("MY RAY", "X9 PRO FULLVIEW", 80000.0, 0),
            ("MY RAY", "X9 PRO DC", 75000.0, 0),
            ("MY RAY", "X6 PROXIMA - 3D", 42500.0, 4),
            ("MY RAY", "HYPERION X5 - 3D", 38000.0, 1),
            ("MY RAY", "X6 PROXIMA - 2D", 14500.0, 25),
            ("MY RAY", "HYPERION X5 - 2D", 13500.0, 21),
            ("MY RAY", "SEFALOMETRİ SENSÖR ve ATACHMAN", 8000.0, 4)
        ]
        for item in seed_products:
            execute_query("INSERT INTO products (brand, model, price, stock) VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING", item, commit=True)

    sales_count = execute_query("SELECT COUNT(*) as count FROM sales", fetch_one=True)
    if sales_count and sales_count["count"] == 0:
        seed_sales = [
            ("2026-08-21", "NEVZAT KİRTİŞ", "İstanbul Üniversitesi Çapa Diş Hekimliği Fakültesi", "İstanbul", "STERN WEBER", "S300", 15500.0, 1, 15500.0),
            ("2026-07-22", "SAMET ŞEN", "Ercan TAŞ", "Tekirdağ", "MY RAY", "8000 B", 3900.0, 1, 3900.0),
            ("2026-02-23", "HAKAN BEHRAMOĞLU", "Özel Armineh Ağız ve Diş Sağlığı Polikliniği", "İstanbul", "SILVERFOX", "8000 C PRO", 6500.0, 1, 6500.0),
            ("2026-01-24", "SEDAT TUTKA", "Murat ULUKÖYLÜ", "İstanbul", "MY RAY", "SEFALOMETRİ SENSÖR ve ATACHMAN", 8000.0, 1, 8000.0),
            ("2026-02-25", "ALİ CAN ÇIPA", "Gotham ADSM", "İstanbul", "STERN WEBER", "S200 ORTHO", 9500.0, 2, 19000.0),
            ("2026-08-21", "HAKAN BEHRAMOĞLU", "ahmet", "erzincan", "STERN WEBER", "S 380 TRC", 25000.0, 4, 100000.0)
        ]
        for item in seed_sales:
            execute_query("INSERT INTO sales (date, staff_name, customer_name, customer_location, brand, model, price, quantity, total) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", item, commit=True)

init_db()

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username != "hakan":
            raise HTTPException(status_code=401, detail="Geçersiz kimlik")
    except JWTError:
        raise HTTPException(status_code=401, detail="Oturum süresi doldu")
    return username

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

@app.post("/api/token")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = execute_query("SELECT * FROM users WHERE username = ?", (form_data.username,), fetch_one=True)
    if not user or not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Hatalı kullanıcı adı veya şifre")
    access_token = create_access_token(data={"sub": user["username"], "name": user["full_name"]})
    return {"access_token": access_token, "token_type": "bearer", "full_name": user["full_name"]}

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
            "total_sku": (stock_kpi["total_sku"] if stock_kpi and stock_kpi["total_sku"] else 0)
        },
        "charts": {"staff_sales": staff_sales or [], "brand_sales": brand_sales or []}
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
    execute_query('''INSERT INTO sales 
        (date, staff_name, customer_name, customer_location, brand, model, price, quantity, total) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (sale.date, sale.staff_name, sale.customer_name, sale.customer_location, sale.brand, sale.model, sale.price, sale.quantity, total),
        commit=True
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
    return execute_query("SELECT * FROM staff", fetch_all=True)

@app.get("/api/interactions")
def get_interactions(_: str = Depends(get_current_user)):
    return execute_query("SELECT * FROM interactions ORDER BY id DESC", fetch_all=True)

@app.post("/api/interactions")
def add_interaction(item: InteractionCreate, _: str = Depends(get_current_user)):
    execute_query(
        'INSERT INTO interactions (date, customer_name, devices, notes, "YETKİLİ PERSONEL", "TEKLİF URL\'si") VALUES (?, ?, ?, ?, ?, ?)',
        (item.date, item.customer_name, item.devices, item.notes, item.staff_name, item.offer_url or None),
        commit=True
    )
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def index():
    return """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Klinik Matrix | CRM</title>
    
    <!-- PWA & Mobil İkon Tanımlamaları -->
    <link rel="icon" href="/icon.svg">
    <link rel="apple-touch-icon" href="/icon.svg">
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#0d47ff">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="Klinik Matrix">

    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        .sidebar-active { background-color: #1e293b; border-left: 4px solid #ff7b00; color: #fff !important; }
        .bottom-nav-active { color: #0d47ff !important; font-weight: 700; }
        body { -webkit-tap-highlight-color: transparent; }
        .safe-bottom { padding-bottom: env(safe-area-inset-bottom); }
    </style>
</head>
<body class="bg-slate-50 text-slate-900 min-h-screen flex flex-col font-sans">

    <!-- LOGIN EKRANI -->
    <div id="login-modal" class="fixed inset-0 bg-slate-900/95 backdrop-blur-md z-50 flex items-center justify-center p-4">
        <div class="bg-white p-6 sm:p-8 rounded-3xl shadow-2xl w-full max-w-sm border border-slate-100">
            <div class="text-center mb-6">
                <img src="/icon.svg" alt="Klinik Matrix Logo" class="w-32 h-32 mx-auto mb-3 rounded-3xl shadow-lg border border-slate-800 object-cover bg-black">
                <h2 class="text-xl font-black tracking-tight text-slate-800">Klinik <span class="text-orange-500">Matrix</span></h2>
                <p class="text-xs font-semibold text-blue-600 mt-0.5">Satış & Stok Yönetim Sistemi</p>
            </div>
            <div id="login-error" class="hidden mb-4 p-3 bg-red-50 border border-red-200 text-red-600 text-xs rounded-xl font-medium"></div>
            <form id="login-form" onsubmit="handleLogin(event)" class="space-y-4" autocomplete="off">
                <div>
                    <label class="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">Kullanıcı Adı</label>
                    <input type="text" id="username" placeholder="Kullanıcı adınızı girin" required class="w-full px-4 py-3 rounded-xl border border-slate-300 focus:ring-2 focus:ring-blue-500 focus:outline-none text-sm">
                </div>
                <div>
                    <label class="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">Şifre</label>
                    <input type="password" id="password" placeholder="••••" required class="w-full px-4 py-3 rounded-xl border border-slate-300 focus:ring-2 focus:ring-blue-500 focus:outline-none text-sm">
                </div>
                <button type="submit" class="w-full bg-blue-600 active:bg-blue-800 hover:bg-blue-700 text-white font-bold py-3.5 rounded-xl text-sm shadow-lg shadow-blue-600/20 transition duration-200">
                    Sisteme Giriş Yap
                </button>
            </form>
        </div>
    </div>

    <!-- MOBİL ÜST BAR (Sadece Mobil/Tablet) -->
    <header id="mobile-header" class="md:hidden sticky top-0 z-30 bg-slate-900 text-white px-4 py-3 flex items-center justify-between shadow-md hidden">
        <div class="flex items-center gap-2.5">
            <img src="/icon.svg" alt="Logo" class="w-10 h-10 rounded-xl bg-black border border-slate-700 object-cover">
            <div>
                <div class="font-black text-sm leading-tight tracking-tight">Klinik <span class="text-orange-400">Matrix</span></div>
                <div class="text-[10px] text-blue-400 font-medium">CRM Yönetim Sistemi</div>
            </div>
        </div>
        <button onclick="logout()" class="p-2 text-slate-300 hover:text-red-400 active:scale-95 transition" title="Çıkış Yap">
            <i class="fa-solid fa-right-from-bracket text-lg"></i>
        </button>
    </header>

    <!-- ANA UYGULAMA KAPSAYICI -->
    <div id="app" class="flex-1 flex flex-col md:flex-row hidden min-h-screen">
        
        <!-- MASAÜSTÜ SIDEBAR (Mobilde Gizli) -->
        <aside class="hidden md:flex w-64 bg-slate-900 text-slate-300 flex-col justify-between flex-shrink-0">
            <div>
                <div class="px-5 py-5 border-b border-slate-800 flex items-center gap-3">
                    <img src="/icon.svg" alt="Logo" class="w-12 h-12 rounded-xl bg-black border border-slate-700 shrink-0 object-cover">
                    <div class="overflow-hidden">
                        <div class="font-black text-white text-sm leading-tight truncate">Klinik <span class="text-orange-400">Matrix</span></div>
                        <div class="text-[11px] text-blue-400 font-semibold mt-0.5">CRM PORTALI</div>
                    </div>
                </div>
                <nav class="p-4 space-y-1.5 text-sm font-medium">
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
                    <button onclick="switchTab('staff')" id="nav-staff" class="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-slate-800 hover:text-white transition">
                        <i class="fa-solid fa-id-card-clip w-5 text-sky-400"></i> Ekip / Personel
                    </button>
                </nav>
            </div>
            <div class="p-4 border-t border-slate-800 text-xs">
                <div class="flex items-center justify-between mb-3 px-2">
                    <span id="user-display" class="font-medium text-slate-300 truncate">Yönetici</span>
                    <span class="bg-blue-900/60 text-blue-300 px-2 py-0.5 rounded text-[10px] font-semibold uppercase">Admin</span>
                </div>
                <button onclick="logout()" class="w-full py-2.5 px-3 bg-red-950/40 hover:bg-red-900/60 text-red-300 border border-red-900/50 rounded-xl flex items-center justify-center gap-2 transition">
                    <i class="fa-solid fa-right-from-bracket"></i> Çıkış Yap
                </button>
            </div>
        </aside>

        <!-- ANA İÇERİK ALANI -->
        <main class="flex-1 p-4 sm:p-6 md:p-8 pb-24 md:pb-8 overflow-y-auto">
            
            <!-- SECTION: DASHBOARD -->
            <div id="section-dashboard" class="space-y-5">
                <div class="flex items-center justify-between">
                    <div>
                        <h1 class="text-xl sm:text-2xl font-bold text-slate-800">Genel Durum Paneli</h1>
                        <p class="text-xs text-slate-500">Anlık satış ve envanter özeti</p>
                    </div>
                    <span class="text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-full font-semibold flex items-center gap-1.5">
                        <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> Canlı
                    </span>
                </div>

                <!-- KPI KARTLARI (Mobilde 2x2 Grid) -->
                <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-5">
                    <div class="bg-white p-4 sm:p-5 rounded-2xl shadow-sm border border-slate-200/80">
                        <span class="text-[10px] sm:text-xs font-bold text-slate-400 uppercase tracking-wider">Toplam Ciro</span>
                        <div class="text-lg sm:text-2xl font-extrabold text-slate-800 mt-1 sm:mt-2 truncate" id="kpi-revenue">€ 0,00</div>
                        <div class="text-[11px] text-emerald-600 mt-1 font-medium"><i class="fa-solid fa-arrow-trend-up"></i> Faturalı</div>
                    </div>
                    <div class="bg-white p-4 sm:p-5 rounded-2xl shadow-sm border border-slate-200/80">
                        <span class="text-[10px] sm:text-xs font-bold text-slate-400 uppercase tracking-wider">Satılan Cihaz</span>
                        <div class="text-lg sm:text-2xl font-extrabold text-slate-800 mt-1 sm:mt-2" id="kpi-units">0</div>
                        <div class="text-[11px] text-slate-500 mt-1 font-medium">İşlem: <span id="kpi-count">0</span></div>
                    </div>
                    <div class="bg-white p-4 sm:p-5 rounded-2xl shadow-sm border border-slate-200/80">
                        <span class="text-[10px] sm:text-xs font-bold text-slate-400 uppercase tracking-wider">Depo Stok</span>
                        <div class="text-lg sm:text-2xl font-extrabold text-amber-600 mt-1 sm:mt-2" id="kpi-stock">0</div>
                        <div class="text-[11px] text-slate-500 mt-1 font-medium"><span id="kpi-sku">0</span> model</div>
                    </div>
                    <div class="bg-white p-4 sm:p-5 rounded-2xl shadow-sm border border-slate-200/80">
                        <span class="text-[10px] sm:text-xs font-bold text-slate-400 uppercase tracking-wider">Satış Ekibi</span>
                        <div class="text-lg sm:text-2xl font-extrabold text-blue-600 mt-1 sm:mt-2" id="kpi-staff">5</div>
                        <div class="text-[11px] text-slate-500 mt-1 font-medium">Aktif Temsilci</div>
                    </div>
                </div>

                <!-- HIZLI İŞLEM BUTONLARI (Mobil İçin Pratik) -->
                <div class="grid grid-cols-2 gap-3 md:hidden">
                    <button onclick="toggleModal('modal-add-sale')" class="bg-blue-600 active:bg-blue-700 text-white py-3 px-4 rounded-xl font-bold text-xs shadow-sm flex items-center justify-center gap-2">
                        <i class="fa-solid fa-plus-circle text-sm"></i> Hızlı Satış Ekle
                    </button>
                    <button onclick="toggleModal('modal-add-interaction')" class="bg-purple-600 active:bg-purple-700 text-white py-3 px-4 rounded-xl font-bold text-xs shadow-sm flex items-center justify-center gap-2">
                        <i class="fa-solid fa-comment-medical text-sm"></i> Görüşme Notu
                    </button>
                </div>

                <!-- GRAFİKLER -->
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
                    <div class="bg-white p-4 sm:p-6 rounded-2xl shadow-sm border border-slate-200/80">
                        <h3 class="font-bold text-slate-800 mb-3 text-xs sm:text-sm">Personele Göre Ciro Dağılımı (€)</h3>
                        <canvas id="staffChart" height="220"></canvas>
                    </div>
                    <div class="bg-white p-4 sm:p-6 rounded-2xl shadow-sm border border-slate-200/80">
                        <h3 class="font-bold text-slate-800 mb-3 text-xs sm:text-sm">Markalara Göre Satış Hacmi (€)</h3>
                        <canvas id="brandChart" height="220"></canvas>
                    </div>
                </div>
            </div>

            <!-- SECTION: SATIŞLAR -->
            <div id="section-sales" class="hidden space-y-4">
                <div class="flex items-center justify-between">
                    <div>
                        <h1 class="text-xl sm:text-2xl font-bold text-slate-800">Satış Kayıtları</h1>
                        <p class="text-xs text-slate-500">Faturalandırılan tüm cihaz satışları</p>
                    </div>
                    <button onclick="toggleModal('modal-add-sale')" class="bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold px-3.5 py-2.5 rounded-xl shadow transition flex items-center gap-1.5">
                        <i class="fa-solid fa-plus"></i> <span>Yeni Satış</span>
                    </button>
                </div>

                <!-- Mobil Kart Görünümü -->
                <div id="sales-mobile-list" class="md:hidden space-y-3"></div>

                <!-- Masaüstü Tablo Görünümü -->
                <div class="hidden md:block bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-x-auto">
                    <table class="w-full text-left text-xs">
                        <thead class="bg-slate-50 text-slate-500 font-semibold border-b uppercase text-[10px]">
                            <tr>
                                <th class="p-4">Tarih</th>
                                <th class="p-4">Satış Yetkilisi</th>
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
            </div>

            <!-- SECTION: ÜRÜNLER & STOK -->
            <div id="section-products" class="hidden space-y-4">
                <div class="flex items-center justify-between">
                    <div>
                        <h1 class="text-xl sm:text-2xl font-bold text-slate-800">Ürün & Stok</h1>
                        <p class="text-xs text-slate-500">Güncel liste fiyatları ve depo durumu</p>
                    </div>
                </div>

                <!-- Mobil Ürün Kartları -->
                <div id="products-mobile-list" class="md:hidden grid grid-cols-1 gap-2.5"></div>

                <!-- Masaüstü Ürün Tablosu -->
                <div class="hidden md:block bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-x-auto">
                    <table class="w-full text-left text-xs">
                        <thead class="bg-slate-50 text-slate-500 font-semibold border-b uppercase text-[10px]">
                            <tr>
                                <th class="p-4">Marka</th>
                                <th class="p-4">Model Tanımı</th>
                                <th class="p-4">Liste Fiyatı (€)</th>
                                <th class="p-4">Depo Stok</th>
                                <th class="p-4">Durum</th>
                                <th class="p-4 text-center">Stok Güncelle</th>
                            </tr>
                        </thead>
                        <tbody id="products-table-body" class="divide-y divide-slate-100 font-medium text-slate-700"></tbody>
                    </table>
                </div>
            </div>

            <!-- SECTION: GÖRÜŞMELER -->
            <div id="section-interactions" class="hidden space-y-4">
                <div class="flex items-center justify-between">
                    <div>
                        <h1 class="text-xl sm:text-2xl font-bold text-slate-800">Müşteri Görüşmeleri</h1>
                        <p class="text-xs text-slate-500">Ziyaret ve teklif takip notları</p>
                    </div>
                    <button onclick="toggleModal('modal-add-interaction')" class="bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold px-3.5 py-2.5 rounded-xl shadow transition flex items-center gap-1.5">
                        <i class="fa-solid fa-plus"></i> <span>Not Ekle</span>
                    </button>
                </div>

                <!-- Mobil Görüşme Kartları -->
                <div id="interactions-mobile-list" class="md:hidden space-y-3"></div>

                <!-- Masaüstü Görüşme Tablosu -->
                <div class="hidden md:block bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-x-auto">
                    <table class="w-full text-left text-xs">
                        <thead class="bg-slate-50 text-slate-500 font-semibold border-b uppercase text-[10px]">
                            <tr>
                                <th class="p-4">Tarih</th>
                                <th class="p-4">Müşteri Adı</th>
                                <th class="p-4">İlgilenilen Cihazlar</th>
                                <th class="p-4">Notlar</th>
                                <th class="p-4">Yetkili Personel</th>
                                <th class="p-4 text-center">Teklif</th>
                            </tr>
                        </thead>
                        <tbody id="interactions-table-body" class="divide-y divide-slate-100 font-medium text-slate-700"></tbody>
                    </table>
                </div>
            </div>

            <!-- SECTION: PERSONEL -->
            <div id="section-staff" class="hidden space-y-4">
                <div>
                    <h1 class="text-xl sm:text-2xl font-bold text-slate-800">Satış Ekibi</h1>
                    <p class="text-xs text-slate-500">Saha ve kurumsal satış temsilcileri</p>
                </div>
                <div id="staff-mobile-list" class="md:hidden space-y-2.5"></div>
                <div class="hidden md:block bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-hidden">
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
    </div>

    <!-- MOBİL ALT NAVİGASYON BARI (Sadece Telefonda Görünür) -->
    <nav id="mobile-bottom-nav" class="md:hidden fixed bottom-0 left-0 right-0 bg-white border-t border-slate-200 z-30 flex justify-around items-center py-2 safe-bottom shadow-lg hidden">
        <button onclick="switchTab('dashboard')" id="bnav-dashboard" class="flex flex-col items-center gap-1 text-slate-400 bottom-nav-active w-full py-1">
            <i class="fa-solid fa-chart-pie text-base"></i>
            <span class="text-[10px]">Panel</span>
        </button>
        <button onclick="switchTab('sales')" id="bnav-sales" class="flex flex-col items-center gap-1 text-slate-400 w-full py-1">
            <i class="fa-solid fa-receipt text-base"></i>
            <span class="text-[10px]">Satışlar</span>
        </button>
        <button onclick="switchTab('products')" id="bnav-products" class="flex flex-col items-center gap-1 text-slate-400 w-full py-1">
            <i class="fa-solid fa-boxes-stacked text-base"></i>
            <span class="text-[10px]">Stok</span>
        </button>
        <button onclick="switchTab('interactions')" id="bnav-interactions" class="flex flex-col items-center gap-1 text-slate-400 w-full py-1">
            <i class="fa-solid fa-comments text-base"></i>
            <span class="text-[10px]">Görüşme</span>
        </button>
        <button onclick="switchTab('staff')" id="bnav-staff" class="flex flex-col items-center gap-1 text-slate-400 w-full py-1">
            <i class="fa-solid fa-users text-base"></i>
            <span class="text-[10px]">Ekip</span>
        </button>
    </nav>

    <!-- MODAL: SATIŞ EKLE -->
    <div id="modal-add-sale" class="fixed inset-0 bg-slate-900/60 backdrop-blur-xs z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 hidden">
        <div class="bg-white p-6 rounded-t-3xl sm:rounded-2xl shadow-2xl w-full max-w-lg border max-h-[90vh] overflow-y-auto">
            <div class="flex items-center justify-between mb-4">
                <h3 class="text-base sm:text-lg font-bold text-slate-800">Yeni Satış Kaydı</h3>
                <button onclick="toggleModal('modal-add-sale')" class="text-slate-400 hover:text-slate-600 p-1"><i class="fa-solid fa-xmark text-lg"></i></button>
            </div>
            <form id="sale-form" onsubmit="submitSale(event)" class="space-y-3.5 text-xs">
                <div>
                    <label class="font-semibold text-slate-600">Tarih</label>
                    <input type="date" id="sale-date" required class="w-full p-2.5 border rounded-xl mt-1 text-sm bg-slate-50">
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Satış Yetkilisi</label>
                    <select id="sale-staff" required class="w-full p-2.5 border rounded-xl mt-1 text-sm bg-slate-50"></select>
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Müşteri / Kurum Adı</label>
                    <input type="text" id="sale-customer" required class="w-full p-2.5 border rounded-xl mt-1 text-sm" placeholder="Örn: Özel Dent Polikliniği">
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Müşteri Konumu (Şehir)</label>
                    <input type="text" id="sale-location" required class="w-full p-2.5 border rounded-xl mt-1 text-sm" placeholder="Örn: İstanbul">
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Ürün Seçiniz</label>
                    <select id="sale-product" onchange="onProductSelect()" required class="w-full p-2.5 border rounded-xl mt-1 text-sm bg-slate-50"></select>
                </div>
                <div class="grid grid-cols-2 gap-3">
                    <div>
                        <label class="font-semibold text-slate-600">Birim Fiyat (€)</label>
                        <input type="number" step="0.01" id="sale-price" required class="w-full p-2.5 border rounded-xl mt-1 text-sm">
                    </div>
                    <div>
                        <label class="font-semibold text-slate-600">Adet</label>
                        <input type="number" min="1" id="sale-qty" value="1" required class="w-full p-2.5 border rounded-xl mt-1 text-sm">
                    </div>
                </div>
                <div class="flex justify-end gap-2 pt-4">
                    <button type="button" onclick="toggleModal('modal-add-sale')" class="w-1/3 py-3 border rounded-xl font-semibold text-slate-600">İptal</button>
                    <button type="submit" class="w-2/3 py-3 bg-blue-600 text-white rounded-xl font-bold hover:bg-blue-700 shadow-md">Satışı Kaydet</button>
                </div>
            </form>
        </div>
    </div>

    <!-- MODAL: GÖRÜŞME EKLE -->
    <div id="modal-add-interaction" class="fixed inset-0 bg-slate-900/60 backdrop-blur-xs z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 hidden">
        <div class="bg-white p-6 rounded-t-3xl sm:rounded-2xl shadow-2xl w-full max-w-lg border max-h-[90vh] overflow-y-auto">
            <div class="flex items-center justify-between mb-4">
                <h3 class="text-base sm:text-lg font-bold text-slate-800">Yeni Görüşme Notu</h3>
                <button onclick="toggleModal('modal-add-interaction')" class="text-slate-400 hover:text-slate-600 p-1"><i class="fa-solid fa-xmark text-lg"></i></button>
            </div>
            <form id="interaction-form" onsubmit="submitInteraction(event)" class="space-y-3.5 text-xs">
                <div>
                    <label class="font-semibold text-slate-600">Tarih</label>
                    <input type="date" id="inter-date" required class="w-full p-2.5 border rounded-xl mt-1 text-sm bg-slate-50">
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Müşteri / Hekim Adı</label>
                    <input type="text" id="inter-customer" required class="w-full p-2.5 border rounded-xl mt-1 text-sm" placeholder="Dr. Adı veya Klinik">
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Görüşülen Cihazlar</label>
                    <input type="text" id="inter-devices" required class="w-full p-2.5 border rounded-xl mt-1 text-sm" placeholder="Örn: S300, Hyperion X5">
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Yetkili Personel</label>
                    <select id="inter-staff" class="w-full p-2.5 border rounded-xl mt-1 text-sm bg-slate-50"></select>
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Teklif URL'si (İsteğe Bağlı)</label>
                    <input type="url" id="inter-url" class="w-full p-2.5 border rounded-xl mt-1 text-sm" placeholder="https://1drv.ms/...">
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Açıklama / Detaylar</label>
                    <textarea id="inter-notes" rows="3" required class="w-full p-2.5 border rounded-xl mt-1 text-sm" placeholder="Görüşme notları ve teklif durumu..."></textarea>
                </div>
                <div class="flex justify-end gap-2 pt-4">
                    <button type="button" onclick="toggleModal('modal-add-interaction')" class="w-1/3 py-3 border rounded-xl font-semibold text-slate-600">İptal</button>
                    <button type="submit" class="w-2/3 py-3 bg-purple-600 text-white rounded-xl font-bold hover:bg-purple-700 shadow-md">Notu Kaydet</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        let token = localStorage.getItem("token");
        let rawProducts = [];
        let rawStaff = [];
        let staffChartInstance = null;
        let brandChartInstance = null;

        document.addEventListener("DOMContentLoaded", () => {
            const today = new Date().toISOString().split('T')[0];
            document.getElementById("sale-date").value = today;
            document.getElementById("inter-date").value = today;

            if (token) {
                initPortal();
            } else {
                document.getElementById("login-modal").classList.remove("hidden");
            }
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
                if (!res.ok) throw new Error("Kullanıcı adı veya şifre hatalı");
                const data = await res.json();
                token = data.access_token;
                localStorage.setItem("token", token);
                localStorage.setItem("user_name", data.full_name);
                document.getElementById("login-modal").classList.add("hidden");
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
            const res = await authFetch("/api/dashboard");
            if (!res || !res.ok) {
                logout();
                return;
            }
            document.getElementById("login-modal").classList.add("hidden");
            document.getElementById("app").classList.remove("hidden");
            document.getElementById("mobile-header").classList.remove("hidden");
            document.getElementById("mobile-bottom-nav").classList.remove("hidden");
            document.getElementById("user-display").textContent = localStorage.getItem("user_name") || "Hakan Behramoğlu";
            await Promise.all([loadStaff(), loadProducts(), loadDashboard(), loadSales(), loadInteractions()]);
        }

        function switchTab(tab) {
            ['dashboard', 'sales', 'products', 'interactions', 'staff'].forEach(t => {
                document.getElementById("section-" + t).classList.add("hidden");
                
                const nav = document.getElementById("nav-" + t);
                if (nav) {
                    nav.classList.remove("sidebar-active");
                }
                const bnav = document.getElementById("bnav-" + t);
                if (bnav) {
                    bnav.classList.remove("bottom-nav-active");
                }
            });

            document.getElementById("section-" + tab).classList.remove("hidden");
            const activeNav = document.getElementById("nav-" + tab);
            if (activeNav) activeNav.classList.add("sidebar-active");
            
            const activeBnav = document.getElementById("bnav-" + tab);
            if (activeBnav) activeBnav.classList.add("bottom-nav-active");
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        function toggleModal(id) {
            document.getElementById(id).classList.toggle("hidden");
        }

        const fmtEUR = (num) => "€ " + Number(num || 0).toLocaleString('tr-TR', { minimumFractionDigits: 0, maximumFractionDigits: 2 });

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
                    datasets: [{ label: 'Ciro (€)', data: staffValues, backgroundColor: '#3b82f6', borderRadius: 6 }]
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
                    datasets: [{ data: brandValues, backgroundColor: ['#5482ff', '#92d050', '#ffc000', '#6366f1'] }]
                },
                options: { responsive: true }
            });
        }

        async function loadProducts() {
            const res = await authFetch("/api/products");
            rawProducts = await res.json();
            const tbody = document.getElementById("products-table-body");
            const mlist = document.getElementById("products-mobile-list");
            tbody.innerHTML = "";
            mlist.innerHTML = "";
            
            const select = document.getElementById("sale-product");
            select.innerHTML = "<option value=''>Cihaz Seçiniz...</option>";

            rawProducts.forEach(p => {
                // Masaüstü satır
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td class="p-4 font-bold text-slate-800">${p.brand}</td>
                    <td class="p-4">${p.model}</td>
                    <td class="p-4 font-semibold">${fmtEUR(p.price)}</td>
                    <td class="p-4"><span class="font-bold ${p.stock <= 2 ? 'text-rose-600' : 'text-slate-800'}">${p.stock}</span></td>
                    <td class="p-4">
                        ${p.stock > 0 
                            ? '<span class="bg-emerald-50 text-emerald-700 px-2 py-1 rounded text-[10px] font-semibold">Stokta</span>' 
                            : '<span class="bg-rose-50 text-rose-700 px-2 py-1 rounded text-[10px] font-semibold">Tükendi</span>'}
                    </td>
                    <td class="p-4 text-center">
                        <button onclick="quickStockUpdate(${p.id}, ${p.price}, ${p.stock})" class="text-slate-400 hover:text-blue-600 p-1"><i class="fa-solid fa-pen-to-square"></i></button>
                    </td>
                `;
                tbody.appendChild(tr);

                // Mobil Kart
                const card = document.createElement("div");
                card.className = "bg-white p-3.5 rounded-2xl shadow-xs border border-slate-200/80 flex items-center justify-between";
                card.innerHTML = `
                    <div>
                        <div class="text-[10px] font-bold text-blue-600 uppercase">${p.brand}</div>
                        <div class="font-bold text-slate-800 text-sm">${p.model}</div>
                        <div class="text-xs font-semibold text-slate-500 mt-0.5">${fmtEUR(p.price)}</div>
                    </div>
                    <div class="flex items-center gap-3">
                        <div class="text-right">
                            <span class="block text-xs font-extrabold ${p.stock > 0 ? 'text-emerald-600' : 'text-rose-600'}">${p.stock} Adet</span>
                            <span class="text-[10px] text-slate-400">${p.stock > 0 ? 'Mevcut' : 'Stok Yok'}</span>
                        </div>
                        <button onclick="quickStockUpdate(${p.id}, ${p.price}, ${p.stock})" class="w-9 h-9 rounded-xl bg-slate-100 text-slate-600 flex items-center justify-center active:bg-blue-100 active:text-blue-600">
                            <i class="fa-solid fa-pen text-xs"></i>
                        </button>
                    </div>
                `;
                mlist.appendChild(card);

                const opt = document.createElement("option");
                opt.value = p.id;
                opt.textContent = `${p.brand} - ${p.model} (${fmtEUR(p.price)} | Stok: ${p.stock})`;
                select.appendChild(opt);
            });
        }

        function onProductSelect() {
            const id = document.getElementById("sale-product").value;
            const p = rawProducts.find(x => x.id == id);
            if (p) document.getElementById("sale-price").value = p.price;
        }

        async function quickStockUpdate(id, curPrice, curStock) {
            const newStock = prompt("Yeni stok adedini girin:", curStock);
            if (newStock !== null) {
                await authFetch(`/api/products/${id}`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ price: curPrice, stock: parseInt(newStock) || 0 })
                });
                await loadProducts();
                await loadDashboard();
            }
        }

        async function loadSales() {
            const res = await authFetch("/api/sales");
            const sales = await res.json();
            const tbody = document.getElementById("sales-table-body");
            const mlist = document.getElementById("sales-mobile-list");
            tbody.innerHTML = "";
            mlist.innerHTML = "";

            sales.forEach(s => {
                // Masaüstü
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td class="p-4 text-slate-500">${s.date}</td>
                    <td class="p-4 font-semibold text-slate-900">${s.staff_name}</td>
                    <td class="p-4">${s.customer_name}</td>
                    <td class="p-4 text-slate-500">${s.customer_location}</td>
                    <td class="p-4"><span class="font-bold text-slate-800">${s.brand}</span> ${s.model}</td>
                    <td class="p-4">${fmtEUR(s.price)}</td>
                    <td class="p-4 font-bold">${s.quantity}</td>
                    <td class="p-4 font-extrabold text-blue-600">${fmtEUR(s.total)}</td>
                    <td class="p-4 text-center">
                        <button onclick="deleteSale(${s.id})" class="text-slate-300 hover:text-red-600 transition p-1"><i class="fa-solid fa-trash"></i></button>
                    </td>
                `;
                tbody.appendChild(tr);

                // Mobil Kart
                const card = document.createElement("div");
                card.className = "bg-white p-4 rounded-2xl shadow-xs border border-slate-200/80 space-y-2";
                card.innerHTML = `
                    <div class="flex items-start justify-between">
                        <div>
                            <span class="text-[10px] font-bold bg-blue-50 text-blue-700 px-2 py-0.5 rounded-md">${s.brand} • ${s.model}</span>
                            <h4 class="font-bold text-slate-800 text-sm mt-1">${s.customer_name}</h4>
                        </div>
                        <button onclick="deleteSale(${s.id})" class="text-slate-300 hover:text-red-500 p-1"><i class="fa-solid fa-trash text-xs"></i></button>
                    </div>
                    <div class="flex items-center justify-between text-xs text-slate-500 pt-1 border-t border-slate-100">
                        <div>
                            <div><i class="fa-solid fa-user-tie mr-1 text-slate-400"></i> ${s.staff_name}</div>
                            <div class="text-[11px] mt-0.5"><i class="fa-solid fa-location-dot mr-1 text-slate-400"></i> ${s.customer_location} • ${s.date}</div>
                        </div>
                        <div class="text-right">
                            <div class="text-[11px] text-slate-400">${s.quantity} Adet x ${fmtEUR(s.price)}</div>
                            <div class="text-sm font-extrabold text-blue-600">${fmtEUR(s.total)}</div>
                        </div>
                    </div>
                `;
                mlist.appendChild(card);
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
                quantity: parseInt(document.getElementById("sale-qty").value)
            };

            const res = await authFetch("/api/sales", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (!res.ok) {
                alert("Kayıt veritabanına eklenirken bir hata oluştu.");
                return;
            }

            toggleModal('modal-add-sale');
            document.getElementById("sale-form").reset();
            document.getElementById("sale-date").value = new Date().toISOString().split('T')[0];
            await loadSales();
            await loadProducts();
            await loadDashboard();
        }

        async function deleteSale(id) {
            if (confirm("Bu satışı silmek istediğinize emin misiniz?")) {
                await authFetch(`/api/sales/${id}`, { method: "DELETE" });
                await loadSales();
                await loadDashboard();
            }
        }

        async function loadStaff() {
            const res = await authFetch("/api/staff");
            rawStaff = await res.json();
            const tbody = document.getElementById("staff-table-body");
            const mlist = document.getElementById("staff-mobile-list");
            tbody.innerHTML = "";
            mlist.innerHTML = "";
            
            const select = document.getElementById("sale-staff");
            const interSelect = document.getElementById("inter-staff");
            select.innerHTML = "";
            if (interSelect) interSelect.innerHTML = "";

            rawStaff.forEach(s => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td class="p-4 font-bold text-slate-800">${s.name}</td>
                    <td class="p-4"><span class="bg-slate-100 text-slate-700 px-2 py-0.5 rounded text-[11px]">${s.department}</span></td>
                    <td class="p-4 text-slate-500">${s.title}</td>
                `;
                tbody.appendChild(tr);

                const card = document.createElement("div");
                card.className = "bg-white p-3.5 rounded-2xl shadow-xs border border-slate-200/80 flex items-center gap-3";
                card.innerHTML = `
                    <div class="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 font-bold flex items-center justify-center text-sm shrink-0">
                        ${s.name.split(' ').map(n => n[0]).join('')}
                    </div>
                    <div>
                        <div class="font-bold text-slate-800 text-sm">${s.name}</div>
                        <div class="text-xs text-slate-500">${s.title} • <span class="text-blue-600 font-medium">${s.department}</span></div>
                    </div>
                `;
                mlist.appendChild(card);

                const opt = document.createElement("option");
                opt.value = s.name;
                opt.textContent = s.name;
                select.appendChild(opt);

                if (interSelect) {
                    const opt2 = document.createElement("option");
                    opt2.value = s.name;
                    opt2.textContent = s.name;
                    if (s.name === "HAKAN BEHRAMOĞLU") opt2.selected = true;
                    interSelect.appendChild(opt2);
                }
            });
            document.getElementById("kpi-staff").textContent = rawStaff.length;
        }

        async function loadInteractions() {
            const res = await authFetch("/api/interactions");
            const data = await res.json();
            const tbody = document.getElementById("interactions-table-body");
            const mlist = document.getElementById("interactions-mobile-list");
            tbody.innerHTML = "";
            mlist.innerHTML = "";

            if (data.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" class="p-4 text-center text-slate-400">Kayıtlı görüşme bulunmamaktadır.</td></tr>`;
                mlist.innerHTML = `<div class="bg-white p-6 rounded-2xl text-center text-xs text-slate-400 border">Henüz görüşme kaydı girilmemiş.</div>`;
                return;
            }
            data.forEach(i => {
                const staffName = i["YETKİLİ PERSONEL"] || i.staff_name || "-";
                const offerUrl = i["TEKLİF URL'si"] || i.offer_url || "";
                const hasValidUrl = offerUrl && offerUrl !== "NULL" && offerUrl.trim() !== "";

                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td class="p-4 text-slate-500 whitespace-nowrap">${i.date}</td>
                    <td class="p-4 font-bold text-slate-800">${i.customer_name}</td>
                    <td class="p-4 font-medium text-purple-700">${i.devices}</td>
                    <td class="p-4 text-slate-600">${i.notes}</td>
                    <td class="p-4 whitespace-nowrap">
                        <span class="bg-blue-50 text-blue-700 px-2.5 py-1 rounded-lg text-[11px] font-semibold">${staffName}</span>
                    </td>
                    <td class="p-4 text-center whitespace-nowrap">
                        ${hasValidUrl 
                            ? `<a href="${offerUrl}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 px-3 py-1.5 rounded-xl text-[11px] font-bold transition shadow-2xs">
                                <i class="fa-solid fa-file-Lines"></i> Teklifi Aç <i class="fa-solid fa-arrow-up-right-from-square text-[9px]"></i>
                               </a>` 
                            : '<span class="text-slate-300 text-[11px]">-</span>'}
                    </td>
                `;
                tbody.appendChild(tr);

                const card = document.createElement("div");
                card.className = "bg-white p-4 rounded-2xl shadow-xs border border-slate-200/80 space-y-2";
                card.innerHTML = `
                    <div class="flex items-center justify-between">
                        <span class="font-bold text-slate-800 text-sm">${i.customer_name}</span>
                        <span class="text-[11px] text-slate-400">${i.date}</span>
                    </div>
                    <div class="flex items-center justify-between gap-2">
                        <div class="text-xs font-semibold text-purple-600"><i class="fa-solid fa-tooth mr-1"></i> ${i.devices}</div>
                        <span class="bg-blue-50 text-blue-700 px-2 py-0.5 rounded text-[10px] font-bold">${staffName}</span>
                    </div>
                    <p class="text-xs text-slate-600 bg-slate-50 p-2.5 rounded-xl">${i.notes}</p>
                    ${hasValidUrl ? `
                    <div class="pt-1">
                        <a href="${offerUrl}" target="_blank" rel="noopener noreferrer" class="w-full flex items-center justify-center gap-1.5 bg-emerald-50 text-emerald-700 border border-emerald-200 py-2 rounded-xl text-xs font-bold">
                            <i class="fa-solid fa-arrow-up-right-from-square"></i> Teklif Dosyasını Görüntüle
                        </a>
                    </div>` : ''}
                `;
                mlist.appendChild(card);
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
                offer_url: document.getElementById("inter-url").value
            };

            await authFetch("/api/interactions", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            toggleModal('modal-add-interaction');
            document.getElementById("interaction-form").reset();
            document.getElementById("inter-date").value = new Date().toISOString().split('T')[0];
            await loadInteractions();
        }
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)