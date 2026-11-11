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
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError:
        import subprocess
        import sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "psycopg2-binary"])
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

KLINIK_MATRIX_STUDIO_HTML = """<!DOCTYPE html>
<html lang="tr" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KlinikMatrix | Eksiksiz Klinik Konfigürasyon Altyapısı</title>
    <link rel="icon" href="/icon.svg">
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
                    },
                    colors: {
                        mannas: {
                            50: '#f0f7ff',
                            100: '#e0effe',
                            400: '#38bdf8',
                            500: '#0ea5e9',
                            600: '#0284c7',
                            900: '#0c4a6e',
                            950: '#082f49',
                        },
                        darkbg: '#090D16',
                        cardbg: '#111827',
                    }
                }
            }
        }
    </script>
    <style>
        body {
            background-color: #090D16;
            color: #F3F4F6;
            overflow-x: hidden;
        }
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
            #view-proposal, #print-official-sheet { display: block !important; }
            .glass-panel { background: #ffffff !important; border: none !important; box-shadow: none !important; padding: 0 !important; }
        }
    </style>
</head>
<body class="min-h-screen flex flex-col selection:bg-sky-500 selection:text-white">

    <!-- PIN SECURITY OVERLAY -->
    <div id="pin-lock-overlay" class="fixed inset-0 z-50 bg-[#090D16]/95 backdrop-blur-2xl flex items-center justify-center p-4">
        <div class="glass-panel max-w-md w-full rounded-3xl p-8 border border-sky-500/30 shadow-2xl text-center space-y-6 relative overflow-hidden">
            <div class="absolute -top-20 left-1/2 -translate-x-1/2 w-56 h-56 bg-sky-500/20 rounded-full blur-3xl pointer-events-none"></div>
            
            <!-- KlinikMatrix 3D Modüler Küp Logo (Stern Weber + MyRay + MGF) -->
            <div class="w-24 h-24 mx-auto rounded-3xl bg-gradient-to-b from-gray-900 to-[#0c162d] p-3 flex flex-col items-center justify-center shadow-2xl shadow-sky-500/30 border border-sky-400/30 relative">
                <svg viewBox="0 0 120 120" class="w-full h-full drop-shadow-[0_0_12px_rgba(14,165,233,0.5)]">
                    <defs>
                        <linearGradient id="pinTop" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stop-color="#38bdf8" />
                            <stop offset="100%" stop-color="#0284c7" />
                        </linearGradient>
                        <linearGradient id="pinLeft" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stop-color="#0369a1" />
                            <stop offset="100%" stop-color="#082f49" />
                        </linearGradient>
                        <linearGradient id="pinRight" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stop-color="#a855f7" />
                            <stop offset="100%" stop-color="#581c87" />
                        </linearGradient>
                        <linearGradient id="pinGold" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%" stop-color="#f59e0b" />
                            <stop offset="100%" stop-color="#f97316" />
                        </linearGradient>
                    </defs>
                    <polygon points="60,14 102,38 60,62 18,38" fill="url(#pinTop)" stroke="#7dd3fc" stroke-width="1.5" stroke-linejoin="round" />
                    <polygon points="18,38 60,62 60,106 18,82" fill="url(#pinLeft)" stroke="#38bdf8" stroke-width="1.5" stroke-linejoin="round" />
                    <polygon points="60,62 102,38 102,82 60,106" fill="url(#pinRight)" stroke="#c084fc" stroke-width="1.5" stroke-linejoin="round" />
                    <g transform="translate(60, 38) scale(0.62)" stroke="#ffffff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" fill="none">
                        <path d="M -24 4 L -8 0 L 8 -6 L 24 -12" />
                        <path d="M -8 0 L -4 14 L 6 12" />
                        <circle cx="20" cy="-16" r="3" fill="#ffffff" />
                    </g>
                    <g stroke="#38bdf8" stroke-width="2.2" stroke-linecap="round" fill="none">
                        <path d="M 28 55 Q 38 52 48 58" />
                        <path d="M 26 67 Q 38 63 50 71" />
                        <path d="M 30 79 Q 39 76 48 83" />
                    </g>
                    <g stroke="#f3e8ff" stroke-width="1.8" stroke-linecap="round" fill="none">
                        <line x1="68" y1="58" x2="94" y2="43" stroke-dasharray="2 2" />
                        <line x1="68" y1="73" x2="94" y2="58" />
                        <line x1="68" y1="88" x2="94" y2="73" stroke-dasharray="2 2" />
                        <polygon points="81,59 89,64 89,73 81,68" fill="#a855f7" stroke="#ffffff" stroke-width="1" />
                    </g>
                    <circle cx="60" cy="62" r="3.5" fill="url(#pinGold)" />
                </svg>
            </div>

            <div class="space-y-1">
                <span class="text-[11px] font-mono uppercase tracking-widest text-sky-400 font-bold">MANNAS DİŞ DEPOSU • GÜVENLİ ERİŞİM</span>
                <h1 class="font-display text-2xl font-bold text-white tracking-tight">Klinik<span class="text-transparent bg-clip-text bg-gradient-to-r from-sky-400 via-blue-400 to-purple-400">Matrix</span></h1>
                <p class="text-xs text-gray-300 font-medium">Eksiksiz Klinik Konfigürasyon Altyapısı</p>
                <p class="text-[11px] text-gray-400 pt-1">Fiyat listesi, canlı konfigüratör ve teklif motoruna erişmek için 4 haneli PIN kodunu girin.</p>
            </div>

            <!-- PIN Display -->
            <div class="flex justify-center gap-3 py-2">
                <input type="password" id="pin-input" maxlength="4" placeholder="••••" oninput="handlePinTyping(this.value)" class="w-44 text-center font-mono text-3xl tracking-[0.5em] bg-gray-900/90 border border-white/15 focus:border-sky-400 rounded-2xl py-3 text-white focus:outline-none shadow-inner">
            </div>
            <div id="pin-error-msg" class="hidden text-xs font-semibold text-rose-400">
                <i class="ph-fill ph-warning-circle"></i> Hatalı PIN kodu! Lütfen tekrar deneyin.
            </div>

            <!-- Keypad -->
            <div class="grid grid-cols-3 gap-2.5 max-w-[260px] mx-auto pt-1">
                <button onclick="pressPinKey('1')" class="py-3 rounded-xl bg-gray-900 hover:bg-gray-800 border border-white/10 font-display font-bold text-lg text-white transition-all active:scale-95">1</button>
                <button onclick="pressPinKey('2')" class="py-3 rounded-xl bg-gray-900 hover:bg-gray-800 border border-white/10 font-display font-bold text-lg text-white transition-all active:scale-95">2</button>
                <button onclick="pressPinKey('3')" class="py-3 rounded-xl bg-gray-900 hover:bg-gray-800 border border-white/10 font-display font-bold text-lg text-white transition-all active:scale-95">3</button>
                <button onclick="pressPinKey('4')" class="py-3 rounded-xl bg-gray-900 hover:bg-gray-800 border border-white/10 font-display font-bold text-lg text-white transition-all active:scale-95">4</button>
                <button onclick="pressPinKey('5')" class="py-3 rounded-xl bg-gray-900 hover:bg-gray-800 border border-white/10 font-display font-bold text-lg text-white transition-all active:scale-95">5</button>
                <button onclick="pressPinKey('6')" class="py-3 rounded-xl bg-gray-900 hover:bg-gray-800 border border-white/10 font-display font-bold text-lg text-white transition-all active:scale-95">6</button>
                <button onclick="pressPinKey('7')" class="py-3 rounded-xl bg-gray-900 hover:bg-gray-800 border border-white/10 font-display font-bold text-lg text-white transition-all active:scale-95">7</button>
                <button onclick="pressPinKey('8')" class="py-3 rounded-xl bg-gray-900 hover:bg-gray-800 border border-white/10 font-display font-bold text-lg text-white transition-all active:scale-95">8</button>
                <button onclick="pressPinKey('9')" class="py-3 rounded-xl bg-gray-900 hover:bg-gray-800 border border-white/10 font-display font-bold text-lg text-white transition-all active:scale-95">9</button>
                <button onclick="clearPinInput()" class="py-3 rounded-xl bg-rose-500/15 hover:bg-rose-500/25 border border-rose-500/30 font-semibold text-xs text-rose-300 transition-all">Temizle</button>
                <button onclick="pressPinKey('0')" class="py-3 rounded-xl bg-gray-900 hover:bg-gray-800 border border-white/10 font-display font-bold text-lg text-white transition-all active:scale-95">0</button>
                <button onclick="verifyPinCode()" class="py-3 rounded-xl bg-sky-500 hover:bg-sky-400 font-semibold text-xs text-white shadow-lg shadow-sky-500/25 transition-all">Giriş</button>
            </div>

            <div class="text-[11px] text-gray-500 pt-2">
                Oğuzhan Cad. No:39 Fındıkzade-Fatih / İSTANBUL • 0212 635 77 26
            </div>
        </div>
    </div>

    <!-- TOP HEADER -->
    <header class="glass-panel sticky top-0 z-40 border-b border-white/10 px-4 lg:px-8 py-3.5">
        <div class="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
            <!-- Brand Logo (KlinikMatrix) -->
            <div class="flex items-center gap-3">
                <div class="w-12 h-12 rounded-2xl bg-gradient-to-b from-gray-900 to-[#0c162d] p-1.5 flex items-center justify-center shadow-lg shadow-sky-500/20 border border-sky-400/30 shrink-0">
                    <svg viewBox="0 0 120 120" class="w-full h-full drop-shadow-[0_0_8px_rgba(14,165,233,0.5)]">
                        <defs>
                            <linearGradient id="hdrTop" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" stop-color="#38bdf8" />
                                <stop offset="100%" stop-color="#0284c7" />
                            </linearGradient>
                            <linearGradient id="hdrLeft" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" stop-color="#0369a1" />
                                <stop offset="100%" stop-color="#082f49" />
                            </linearGradient>
                            <linearGradient id="hdrRight" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" stop-color="#a855f7" />
                                <stop offset="100%" stop-color="#581c87" />
                            </linearGradient>
                        </defs>
                        <polygon points="60,14 102,38 60,62 18,38" fill="url(#hdrTop)" stroke="#7dd3fc" stroke-width="1.5" stroke-linejoin="round" />
                        <polygon points="18,38 60,62 60,106 18,82" fill="url(#hdrLeft)" stroke="#38bdf8" stroke-width="1.5" stroke-linejoin="round" />
                        <polygon points="60,62 102,38 102,82 60,106" fill="url(#hdrRight)" stroke="#c084fc" stroke-width="1.5" stroke-linejoin="round" />
                        <g transform="translate(60, 38) scale(0.65)" stroke="#ffffff" stroke-width="3" stroke-linecap="round" fill="none">
                            <path d="M -24 4 L -8 0 L 8 -6 L 24 -12" />
                            <path d="M -8 0 L -4 14 L 6 12" />
                            <circle cx="20" cy="-16" r="3" fill="#ffffff" />
                        </g>
                        <g stroke="#38bdf8" stroke-width="2.2" stroke-linecap="round" fill="none">
                            <path d="M 28 55 Q 38 52 48 58" />
                            <path d="M 26 67 Q 38 63 50 71" />
                            <path d="M 30 79 Q 39 76 48 83" />
                        </g>
                        <g stroke="#f3e8ff" stroke-width="1.8" stroke-linecap="round" fill="none">
                            <line x1="68" y1="58" x2="94" y2="43" stroke-dasharray="2 2" />
                            <line x1="68" y1="73" x2="94" y2="58" />
                            <polygon points="81,59 89,64 89,73 81,68" fill="#a855f7" stroke="#ffffff" stroke-width="1" />
                        </g>
                        <circle cx="60" cy="62" r="3" fill="#f97316" />
                    </svg>
                </div>
                <div>
                    <div class="flex items-center gap-2">
                        <span class="font-display font-black text-lg tracking-tight text-white">KLINIK<span class="text-transparent bg-clip-text bg-gradient-to-r from-sky-400 via-blue-400 to-purple-400">MATRIX</span></span>
                        <span class="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full bg-orange-500/15 text-orange-400 border border-orange-500/30 font-bold">Mannas Dental</span>
                    </div>
                    <p class="text-xs text-gray-400 hidden sm:block">Eksiksiz Klinik Konfigürasyon Altyapısı • Stern Weber • MyRay • Silverfox • MGF</p>
                </div>
            </div>

            <!-- Navigation -->
            <nav class="flex items-center gap-1.5 bg-gray-900/90 p-1.5 rounded-2xl border border-white/10 overflow-x-auto max-w-full">
                <button onclick="switchTab('configurator')" id="tab-configurator" class="tab-btn active-tab flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs sm:text-sm font-medium transition-all bg-sky-500 text-white shadow-md shadow-sky-500/25">
                    <i class="ph-bold ph-armchair text-base"></i>
                    <span>Ünit Stüdyosu & Föy</span>
                </button>
                <button onclick="switchTab('imaging')" id="tab-imaging" class="tab-btn flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs sm:text-sm font-medium text-gray-400 hover:text-white transition-all">
                    <i class="ph-bold ph-scan text-base"></i>
                    <span>MyRay Dijital & Görüntüleme</span>
                </button>
                <button onclick="switchTab('calculator')" id="tab-calculator" class="tab-btn flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs sm:text-sm font-medium text-gray-400 hover:text-white transition-all">
                    <i class="ph-bold ph-cpu text-base"></i>
                    <span>MGF & Sterilizasyon</span>
                </button>
                <button onclick="switchTab('proposal')" id="tab-proposal" class="tab-btn flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs sm:text-sm font-medium text-gray-400 hover:text-white transition-all">
                    <i class="ph-bold ph-file-xls text-base"></i>
                    <span>Resmi Teklif Oluşturucu</span>
                    <span id="tab-proposal-count" class="px-1.5 py-0.2 rounded-full bg-sky-500/30 text-sky-200 text-[10px] font-mono font-bold">0</span>
                </button>
                <button onclick="switchTab('ideas')" id="tab-ideas" class="tab-btn flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs sm:text-sm font-medium text-gray-400 hover:text-white transition-all">
                    <i class="ph-bold ph-wrench text-base"></i>
                    <span>Şantiye & QR Servis</span>
                </button>
            </nav>

            <!-- Quick Action / Quote Badge -->
            <div class="hidden xl:flex items-center gap-2">
                <button onclick="switchTab('proposal')" class="flex items-center gap-2.5 px-4 py-2 rounded-xl bg-sky-500/10 hover:bg-sky-500/20 border border-sky-500/30 text-xs font-medium text-gray-200 transition-all">
                    <span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
                    <span>Teklif Tutarı:</span>
                    <span id="header-total-badge" class="px-2 py-0.5 rounded-md bg-sky-500 text-white font-bold">0 €</span>
                </button>
                <button onclick="lockAppSession()" title="Ekranı Kilitle" class="p-2 rounded-xl bg-gray-900 hover:bg-rose-500/20 border border-white/10 hover:border-rose-500/40 text-gray-400 hover:text-rose-300 transition-all">
                    <i class="ph-bold ph-lock-key text-base"></i>
                </button>
            </div>
        </div>
    </header>

    <!-- MAIN CONTAINER -->
    <main class="flex-1 max-w-7xl w-full mx-auto px-4 lg:px-8 py-6">

        <!-- TAB 1: UNIT STUDIO & LIVE CONFIGURATION SHEET -->
        <section id="view-configurator" class="space-y-6">
            <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
                
                <!-- Left Column: Visual Unit Representation (7 cols) -->
                <div class="lg:col-span-7 glass-panel rounded-3xl p-6 relative overflow-hidden border border-white/10 flex flex-col justify-between min-h-[560px]">
                    <div id="studio-glow" class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 rounded-full blur-3xl opacity-30 transition-all duration-700 pointer-events-none" style="background: #0284c7;"></div>

                    <!-- Top Bar inside Visualizer -->
                    <div class="relative z-10 flex flex-wrap items-center justify-between gap-2 border-b border-white/10 pb-4">
                        <div>
                            <div class="flex items-center gap-2">
                                <span id="unit-brand-badge" class="text-[11px] uppercase tracking-widest text-sky-400 font-bold">STERN WEBER • CEFLA İTALYA</span>
                                <span id="unit-price-badge" class="px-2.5 py-0.5 rounded-md bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-xs font-mono font-bold">12.000 € Baz Fiyat</span>
                            </div>
                            <h2 id="unit-title-display" class="font-display text-2xl font-bold text-white mt-0.5">Stern Weber S200 Continental</h2>
                        </div>
                        <div class="flex items-center gap-2">
                            <span id="unit-badge-delivery" class="px-3 py-1 rounded-full bg-white/10 text-xs font-medium text-gray-200 border border-white/10">Kamçılı (Continental)</span>
                            <span id="color-name-badge" class="px-3 py-1 rounded-full bg-sky-500/20 text-sky-300 text-xs font-semibold border border-sky-500/30">102 Atlantic Blue</span>
                        </div>
                    </div>

                    <!-- Interactive SVG Unit Representation -->
                    <div class="relative z-10 my-auto py-6 flex items-center justify-center">
                        <svg viewBox="0 0 650 360" class="w-full max-w-[520px] drop-shadow-2xl">
                            <defs>
                                <linearGradient id="metalGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                                    <stop offset="0%" stop-color="#f8fafc" />
                                    <stop offset="100%" stop-color="#94a3b8" />
                                </linearGradient>
                                <linearGradient id="darkMetal" x1="0%" y1="0%" x2="0%" y2="100%">
                                    <stop offset="0%" stop-color="#334155" />
                                    <stop offset="100%" stop-color="#0f172a" />
                                </linearGradient>
                                <filter id="ledGlow" x="-30%" y="-30%" width="160%" height="160%">
                                    <feGaussianBlur stdDeviation="8" result="blur" />
                                    <feComposite in="SourceGraphic" in2="blur" operator="over" />
                                </filter>
                                <linearGradient id="lightBeam" x1="0%" y1="0%" x2="0%" y2="100%">
                                    <stop offset="0%" stop-color="#fef08a" stop-opacity="0.75" />
                                    <stop offset="100%" stop-color="#38bdf8" stop-opacity="0" />
                                </linearGradient>
                            </defs>
                            <ellipse cx="320" cy="335" rx="220" ry="15" fill="rgba(0,0,0,0.55)" />
                            <path d="M180 320 L340 320 L325 295 L195 295 Z" fill="url(#metalGrad)" />
                            <path d="M235 295 L265 225 L295 225 L275 295 Z" fill="url(#darkMetal)" />
                            <rect x="155" y="150" width="46" height="150" rx="12" fill="url(#metalGrad)" />
                            <rect id="svg-ambient-led" x="175" y="165" width="6" height="115" rx="3" fill="#0284c7" filter="url(#ledGlow)" />
                            <path d="M130 165 Q155 195 180 165 Z" fill="#e2e8f0" />
                            <path d="M178 150 L178 40 Q178 20 200 20 L395 20 L395 50" fill="none" stroke="#cbd5e1" stroke-width="10" stroke-linecap="round" />
                            <g id="svg-lamp-group" transform="translate(370, 45)">
                                <rect x="0" y="0" width="52" height="24" rx="10" fill="#f8fafc" stroke="#64748b" stroke-width="2" />
                                <ellipse cx="26" cy="24" rx="18" ry="6" fill="#fef08a" filter="url(#ledGlow)" />
                                <polygon points="12,28 40,28 85,170 -35,170" fill="url(#lightBeam)" opacity="0.18" />
                            </g>
                            <g id="svg-multimedia" transform="translate(230, 52)" style="opacity: 0.15;">
                                <line x1="-52" y1="35" x2="10" y2="25" stroke="#94a3b8" stroke-width="6" />
                                <rect x="0" y="0" width="76" height="48" rx="6" fill="#0f172a" stroke="#e2e8f0" stroke-width="3" />
                                <rect x="5" y="5" width="66" height="38" rx="3" fill="#0284c7" opacity="0.35" />
                                <text x="38" y="40" fill="#e0f2fe" font-size="6" text-anchor="middle" font-family="monospace">HD MONITOR</text>
                            </g>
                            <path d="M201 175 L295 135 L355 145" fill="none" stroke="#e2e8f0" stroke-width="9" stroke-linecap="round" />
                            <g id="svg-doctor-table" transform="translate(320, 128)">
                                <rect x="0" y="0" width="90" height="26" rx="8" fill="#f8fafc" stroke="#94a3b8" stroke-width="2" />
                                <rect id="svg-panel-screen" x="65" y="-14" width="28" height="20" rx="4" fill="#0f172a" stroke="#38bdf8" stroke-width="1.5" />
                                <g id="svg-whip-arms">
                                    <path d="M12 0 Q18 -28 32 -6" fill="none" stroke="#475569" stroke-width="3" />
                                    <path d="M26 0 Q32 -28 46 -6" fill="none" stroke="#475569" stroke-width="3" />
                                    <path d="M40 0 Q46 -28 60 -6" fill="none" stroke="#475569" stroke-width="3" />
                                </g>
                            </g>
                            <g id="svg-upholstery" fill="#0284c7" class="transition-colors duration-500">
                                <path d="M475 102 Q505 90 515 112 L492 135 Q472 125 475 102 Z" />
                                <path d="M365 205 L465 125 Q482 115 492 135 L400 228 Z" />
                                <path id="svg-seat-cushion" d="M235 222 L385 212 Q405 212 400 232 L235 242 Z" />
                                <path d="M235 224 L175 295 Q162 305 152 290 L218 218 Z" />
                            </g>
                            <line x1="468" y1="132" x2="482" y2="118" stroke="#cbd5e1" stroke-width="6" stroke-linecap="round" />
                        </svg>
                    </div>

                    <!-- Bottom Specs Strip -->
                    <div class="relative z-10 grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-center pt-4 border-t border-white/10">
                        <div class="bg-gray-900/80 rounded-xl p-2 border border-white/10">
                            <span class="block text-[10px] uppercase text-gray-400">Reflektör</span>
                            <span id="spec-reflector" class="font-display font-semibold text-xs text-amber-300">Venus Plus LED</span>
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
                            <span id="spec-payment" class="font-display font-semibold text-xs text-emerald-400">TDB Kongre Vadesi</span>
                        </div>
                    </div>
                </div>

                <!-- Right Column: Model Selection & Actions (5 cols) -->
                <div class="lg:col-span-5 glass-panel rounded-3xl p-6 space-y-4 border border-white/10">
                    <div>
                        <h3 class="font-display text-lg font-bold text-white flex items-center gap-2">
                            <i class="ph-fill ph-sliders text-sky-400"></i>
                            <span>TDB Kongre Ünit Seçimi</span>
                        </h3>
                        <p class="text-xs text-gray-400">TDB 29. Kongre Fiyat Listesindeki birebir konfigürasyonu seçin.</p>
                    </div>

                    <!-- Unit Selector Buttons -->
                    <div class="grid grid-cols-2 gap-2 max-h-56 overflow-y-auto pr-1">
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
                            <div class="font-bold text-xs text-white">S300</div>
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
                        <button onclick="selectUnitModel('SF8000C')" id="model-SF8000C" class="model-btn p-2.5 rounded-xl border border-white/10 bg-gray-900/60 text-left transition-all hover:border-sky-500/40">
                            <div class="font-bold text-xs text-white">Silverfox 8000 C Pro</div>
                            <div class="text-[11px] font-mono text-sky-400">6.400 €</div>
                        </button>
                        <button onclick="selectUnitModel('SF8000B')" id="model-SF8000B" class="model-btn p-2.5 rounded-xl border border-white/10 bg-gray-900/60 text-left transition-all hover:border-sky-500/40">
                            <div class="font-bold text-xs text-white">Silverfox 8000 B</div>
                            <div class="text-[11px] font-mono text-sky-400">3.850 €</div>
                        </button>
                    </div>

                    <!-- Delivery Arm & Upholstery Controls -->
                    <div class="grid grid-cols-2 gap-2 pt-1">
                        <button onclick="setArmType('continental')" id="arm-continental" class="py-2 px-3 rounded-xl border border-sky-500 bg-sky-500/15 text-xs font-semibold text-white flex items-center justify-center gap-1.5">
                            <i class="ph-bold ph-bezier-curve text-sky-400"></i> Kamçılı
                        </button>
                        <button onclick="setArmType('international')" id="arm-international" class="py-2 px-3 rounded-xl border border-white/10 bg-gray-900/60 text-xs font-medium text-gray-300 flex items-center justify-center gap-1.5">
                            <i class="ph-bold ph-arrow-down-right"></i> Askılı
                        </button>
                    </div>

                    <!-- Swatches Container -->
                    <div class="space-y-1.5">
                        <div class="flex justify-between items-center text-xs">
                            <span class="text-gray-400">Döşeme Rengi:</span>
                            <span id="selected-color-label" class="font-semibold text-sky-400">102 Atlantic Blue</span>
                        </div>
                        <div id="upholstery-swatches-container" class="grid grid-cols-6 gap-1.5 max-h-28 overflow-y-auto pr-1"></div>
                    </div>

                    <!-- Quantity & Push Actions -->
                    <div class="pt-2 flex items-center gap-2">
                        <div class="bg-gray-900 border border-white/15 rounded-xl px-2.5 py-2 flex items-center gap-1.5 shrink-0">
                            <span class="text-xs text-gray-400">Adet:</span>
                            <input type="number" id="unit-qty-input" value="1" min="1" max="20" onchange="recalcUnitPrice()" class="w-10 bg-transparent text-white font-bold text-sm text-center focus:outline-none">
                        </div>
                        <button onclick="addConfiguredUnitSummaryToProposal()" class="flex-1 py-2.5 px-3 rounded-xl bg-sky-500 hover:bg-sky-400 text-white font-bold text-xs shadow-lg shadow-sky-500/25 flex items-center justify-center gap-1.5 transition-all">
                            <i class="ph-bold ph-plus-circle text-base"></i>
                            <span id="btn-add-unit-summary">Özet Olarak Teklife Ekle</span>
                        </button>
                    </div>
                </div>
            </div>

            <!-- LIVE EDITABLE CONFIGURATION SHEET (FÖY) -->
            <div class="glass-panel rounded-3xl p-6 border border-white/10 space-y-4">
                <div class="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
                    <div>
                        <div class="flex items-center gap-2">
                            <span class="px-2.5 py-0.5 rounded-full bg-sky-500/20 text-sky-300 text-[11px] font-bold">CANLI KONFİGÜRASYON LİSTESİ</span>
                            <span id="sheet-unit-name" class="font-display font-bold text-lg text-white">Stern Weber S200 (12.000 €)</span>
                        </div>
                        <p class="text-xs text-gray-400 mt-0.5">Aşağıdaki satırları doğrudan düzenleyebilir, silebilir, sırasını değiştirebilir veya TDB opsiyonlarından yeni satır ekleyebilirsiniz.</p>
                    </div>
                    <div class="flex flex-wrap items-center gap-2">
                        <button onclick="resetCurrentUnitSheet()" class="px-3 py-1.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs font-semibold flex items-center gap-1">
                            <i class="ph-bold ph-arrow-counter-clockwise"></i> Föyü Sıfırla
                        </button>
                        <button onclick="pushEntireSheetToProposal()" class="px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white text-xs font-bold shadow-lg shadow-emerald-500/25 flex items-center gap-1.5">
                            <i class="ph-bold ph-file-arrow-up text-base"></i> Tüm Satırları Detaylı Olarak Teklife Aktar
                        </button>
                    </div>
                </div>

                <!-- Add Extra Option Tool from TDB 53-item Library -->
                <div class="grid grid-cols-1 md:grid-cols-12 gap-3 p-3 rounded-2xl bg-gray-900/80 border border-white/10 items-center text-xs">
                    <div class="md:col-span-7">
                        <label class="block text-gray-400 mb-1 font-semibold">TDB 53 Kalemlik Opsiyonel Eklenti Kütüphanesinden Ekle:</label>
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

                <!-- Editable Sheet Table -->
                <div class="overflow-x-auto rounded-2xl border border-white/10">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-gray-900 text-[11px] font-mono uppercase text-gray-400 border-b border-white/10">
                                <th class="py-2.5 px-3 w-10 text-center">#</th>
                                <th class="py-2.5 px-3 w-32">Kategori</th>
                                <th class="py-2.5 px-3">Donanım Açıklaması</th>
                                <th class="py-2.5 px-3 w-28 text-center">Durum</th>
                                <th class="py-2.5 px-3 w-28 text-right">Fiyat (€)</th>
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

                <!-- Add Custom Row Directly to Sheet -->
                <div class="flex flex-wrap sm:flex-nowrap items-center gap-2 pt-1 text-xs">
                    <input type="text" id="sheet-custom-cat" placeholder="Bölüm (Örn: HİJYEN)" class="w-32 bg-gray-800 border border-white/10 rounded-xl px-3 py-2 text-white">
                    <input type="text" id="sheet-custom-desc" placeholder="Özel donanım veya not girin..." class="flex-1 bg-gray-800 border border-white/10 rounded-xl px-3 py-2 text-white">
                    <input type="text" id="sheet-custom-status" value="STANDART" class="w-24 bg-gray-800 border border-white/10 rounded-xl px-2 py-2 text-center text-white font-semibold">
                    <input type="number" id="sheet-custom-price" value="0" placeholder="€" class="w-20 bg-gray-800 border border-white/10 rounded-xl px-2 py-2 text-right text-white font-mono">
                    <button onclick="addCustomRowToSheet()" class="px-4 py-2 rounded-xl bg-sky-500/20 hover:bg-sky-500 text-sky-300 hover:text-white border border-sky-500/30 font-bold whitespace-nowrap transition-all">
                        + Yeni Satır Ekle
                    </button>
                </div>
            </div>
        </section>

        <!-- TAB 2: MYRAY IMAGING & DIGITAL DENTISTRY -->
        <section id="view-imaging" class="hidden space-y-6">
            <div class="glass-panel rounded-3xl p-6 sm:p-8 border border-white/10 space-y-6">
                <div class="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-5">
                    <div>
                        <span class="text-xs uppercase tracking-widest text-purple-400 font-bold">CEFLA • MYRAY DİJİTAL GÖRÜNTÜLEME & TARAMA</span>
                        <h2 class="font-display text-2xl sm:text-3xl font-bold text-white mt-1">3D Tomografi, Ağız İçi Tarayıcı, Periapikal & RVG</h2>
                        <p class="text-xs sm:text-sm text-gray-400 mt-1">Kataloglarımızdaki gerçek FOV, Voxel ve NeoWise AI verileriyle donatılmış sistemler.</p>
                    </div>
                    <button onclick="switchTab('proposal')" class="px-4 py-2.5 rounded-xl bg-purple-500/20 hover:bg-purple-500/30 border border-purple-500/40 text-purple-300 text-xs font-semibold flex items-center gap-2">
                        <i class="ph-bold ph-file-xls"></i> Teklif Tablosuna Git
                    </button>
                </div>

                <!-- Products Grid -->
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                    <!-- ProXima X6 -->
                    <div class="glass-card rounded-2xl p-5 border border-purple-500/30 flex flex-col justify-between space-y-3">
                        <div>
                            <div class="flex justify-between items-center">
                                <span class="text-[10px] font-mono text-purple-300 bg-purple-500/20 px-2 py-0.5 rounded font-bold">11x11 FOV • NEOWISE AI</span>
                                <span class="font-bold text-base text-emerald-400">38.000 €</span>
                            </div>
                            <h4 class="font-display font-bold text-white text-lg mt-1.5">MyRay ProXima X6 HD 3D+2D</h4>
                            <p class="text-xs text-gray-400 mt-1">80 µm Voxel, 6.4 sn QuickScan, 3D SMART metal artefakt engelleyici, sınırsız NeoWise AI yazılımı ve workstation PC dahil.</p>
                        </div>
                        <button onclick="addItemToProposal('GÖRÜNTÜLEME', 'MYRAY X6 PROXIMA HD 3D+2D TOMOGRAFİ CİHAZI 11X11 FOV + WORKSTATION + NEOWISE AI (İTALYA)', 1, 38000)" class="w-full py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold transition-all">
                            + ProXima X6 Ekle (38.000 €)
                        </button>
                    </div>

                    <!-- Hyperion X9 Pro -->
                    <div class="glass-card rounded-2xl p-5 border border-sky-500/30 flex flex-col justify-between space-y-3">
                        <div>
                            <div class="flex justify-between items-center">
                                <span class="text-[10px] font-mono text-sky-300 bg-sky-500/20 px-2 py-0.5 rounded font-bold">4-IN-1 • 50 µm ENDO</span>
                                <span class="font-bold text-base text-sky-400">49.500 €</span>
                            </div>
                            <h4 class="font-display font-bold text-white text-lg mt-1.5">Hyperion X9 Pro FullView</h4>
                            <p class="text-xs text-gray-400 mt-1">10x8 / 13x16 FOV, radyasyonsuz 3D yüz tarama (Digital Portrait), 50 µm ultra-yüksek çözünürlük ve Direct Conversion (DC) opsiyonu.</p>
                        </div>
                        <button onclick="addItemToProposal('GÖRÜNTÜLEME', 'MYRAY HYPERION X9 PRO FULLVIEW 3D+2D+CEPH + DIGITAL PORTRAIT (İTALYA)', 1, 49500)" class="w-full py-2 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-bold transition-all">
                            + Hyperion X9 Pro Ekle (49.500 €)
                        </button>
                    </div>

                    <!-- MyScan WL Scanner -->
                    <div class="glass-card rounded-2xl p-5 border border-emerald-500/30 flex flex-col justify-between space-y-3">
                        <div>
                            <div class="flex justify-between items-center">
                                <span class="text-[10px] font-mono text-emerald-300 bg-emerald-500/20 px-2 py-0.5 rounded font-bold">KABLOSUZ • 245 GR</span>
                                <span class="font-bold text-base text-white">11.500 €</span>
                            </div>
                            <h4 class="font-display font-bold text-white text-lg mt-1.5">MyRay MyScan WL Tarayıcı</h4>
                            <p class="text-xs text-gray-400 mt-1">20 µm tam ark hassasiyeti, 60 vaka kesintisiz pil, 18 mm alan derinliği, dahili jiroskop ve ScanPro AI yazılımı.</p>
                        </div>
                        <button onclick="addItemToProposal('TARAYICI', 'MYRAY MYSCAN WL KABLOSUZ AĞIZ İÇİ TARAYICI 20 µm + SCANPRO AI (İTALYA)', 1, 11500)" class="w-full py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition-all">
                            + MyScan WL Ekle (11.500 €)
                        </button>
                    </div>

                    <!-- RXDC HyperSphere Röntgen -->
                    <div class="glass-card rounded-2xl p-5 border border-rose-500/30 flex flex-col justify-between space-y-3">
                        <div>
                            <div class="flex justify-between items-center">
                                <span class="text-[10px] font-mono text-rose-300 bg-rose-500/20 px-2 py-0.5 rounded font-bold">0.4 MM FOCAL SPOT</span>
                                <span class="font-bold text-base text-rose-300">4.750 €</span>
                            </div>
                            <h4 class="font-display font-bold text-white text-lg mt-1.5">RXDC HyperSphere Röntgen</h4>
                            <p class="text-xs text-gray-400 mt-1">Ünite entegre veya duvara monte, patentli küresel mafsal, kablosuz kumanda ve 70 kV yüksek frekans DC tüp.</p>
                        </div>
                        <button onclick="addItemToProposal('GÖRÜNTÜLEME', 'MYRAY RXDC HYPERSPHERE ENTEGRE PERİAPİKAL RÖNTGEN 0.4MM (İTALYA)', 1, 4750)" class="w-full py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold transition-all">
                            + RXDC HyperSphere Ekle (4.750 €)
                        </button>
                    </div>

                    <!-- Zen-X DCIS Wireless RVG -->
                    <div class="glass-card rounded-2xl p-5 border border-amber-500/30 flex flex-col justify-between space-y-3">
                        <div>
                            <div class="flex justify-between items-center">
                                <span class="text-[10px] font-mono text-amber-300 bg-amber-500/20 px-2 py-0.5 rounded font-bold">KABLOSUZ DC SENSÖR</span>
                                <span class="font-bold text-base text-amber-300">5.000 €</span>
                            </div>
                            <h4 class="font-display font-bold text-white text-lg mt-1.5">Zen-X DCIS Kablosuz RVG</h4>
                            <p class="text-xs text-gray-400 mt-1">Direct Conversion kablosuz teknoloji, kırılmaz sintilatörsüz yapı, IP67 su geçirmezlik ve docking station.</p>
                        </div>
                        <button onclick="addItemToProposal('GÖRÜNTÜLEME', 'MYRAY ZEN-X DCIS KABLOSUZ DIRECT CONVERSION RVG SENSÖR (İTALYA)', 1, 5000)" class="w-full py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold transition-all">
                            + Zen-X DCIS Ekle (5.000 €)
                        </button>
                    </div>

                    <!-- Woodpecker Economic Set -->
                    <div class="glass-card rounded-2xl p-5 border border-white/10 flex flex-col justify-between space-y-3">
                        <div>
                            <div class="flex justify-between items-center">
                                <span class="text-[10px] font-mono text-gray-300 bg-gray-800 px-2 py-0.5 rounded font-bold">EKONOMİK SET</span>
                                <span class="font-bold text-base text-white">770 € / 725 €</span>
                            </div>
                            <h4 class="font-display font-bold text-white text-lg mt-1.5">Woodpecker Miniray & i-Sensor</h4>
                            <p class="text-xs text-gray-400 mt-1">Miniray taşınabilir periapikal röntgen (770 €) ve i-Sensor H1 RVG sensör Size 1 (725 €).</p>
                        </div>
                        <div class="grid grid-cols-2 gap-2">
                            <button onclick="addItemToProposal('GÖRÜNTÜLEME', 'WOODPECKER MINIRAY 2MA MOBİL PERİAPİKAL 0.4 FOCAL SPOT', 1, 770)" class="py-1.5 rounded-lg bg-gray-800 hover:bg-sky-500 text-white text-[11px] font-semibold transition-all">
                                + Miniray
                            </button>
                            <button onclick="addItemToProposal('GÖRÜNTÜLEME', 'WOODPECKER I-SENSOR H1 RVG SENSÖR SIZE 1', 1, 725)" class="py-1.5 rounded-lg bg-gray-800 hover:bg-sky-500 text-white text-[11px] font-semibold transition-all">
                                + i-Sensor
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <!-- TAB 3: MGF & STERILIZATION WIZARD -->
        <section id="view-calculator" class="hidden space-y-6">
            <div class="glass-panel rounded-3xl p-6 sm:p-8 border border-white/10 space-y-6">
                <div>
                    <span class="text-xs uppercase tracking-widest text-emerald-400 font-bold">MGF COMPRESSORS İTALYA (PRIME SERİSİ) & STERİLİZASYON</span>
                    <h2 class="font-display text-2xl sm:text-3xl font-bold text-white mt-1">MGF Prime Kompresör, Hybrid Aspiratör & Otoklav Sihirbazı</h2>
                    <p class="text-sm text-gray-400 mt-1">Klinikteki toplam ünit sayısına göre hava debisi ve cerrahi emiş kapasitesini otomatik hesaplar.</p>
                </div>

                <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
                    <!-- Controls -->
                    <div class="lg:col-span-5 space-y-4 bg-gray-900/70 p-5 rounded-2xl border border-white/10">
                        <div class="space-y-2">
                            <div class="flex justify-between items-center">
                                <label class="text-xs font-semibold text-gray-200">Klinikteki Toplam Ünit Sayısı</label>
                                <span id="calc-unit-val" class="px-2.5 py-0.5 rounded-lg bg-sky-500/20 text-sky-300 font-bold text-base">4 Ünit</span>
                            </div>
                            <input type="range" id="calc-units" min="1" max="18" value="4" oninput="updateEngineeringCalc()" class="w-full accent-sky-500 cursor-pointer h-2 bg-gray-800 rounded-lg">
                        </div>

                        <div class="space-y-1.5">
                            <label class="text-xs font-semibold uppercase text-gray-400">Kurutucu / Kabin Tercihi</label>
                            <select id="calc-comp-type" onchange="updateEngineeringCalc()" class="w-full bg-gray-800 border border-white/15 rounded-xl px-3 py-2 text-xs text-white">
                                <option value="M" selected>PRIME M: Membran Kurutuculu (-20°C Çiğlenme Noktası)</option>
                                <option value="CS-M">CS PRIME M: Sessiz Kabinli (53 dB) + Kurutuculu</option>
                                <option value="S">PRIME S: Kurutucusuz Standart Prime</option>
                            </select>
                        </div>

                        <div class="space-y-1.5">
                            <label class="text-xs font-semibold uppercase text-gray-400">Aspiratör Teknolojisi</label>
                            <div class="grid grid-cols-2 gap-2">
                                <button onclick="setSuctionType('hybrid')" id="suction-hybrid" class="py-2 px-3 rounded-xl border border-sky-500 bg-sky-500/15 text-xs font-semibold text-white">
                                    MGF HYBRID (Islak)
                                </button>
                                <button onclick="setSuctionType('dry')" id="suction-dry" class="py-2 px-3 rounded-xl border border-white/10 bg-gray-800 text-xs font-medium text-gray-400">
                                    MGF DRY (Kuru)
                                </button>
                            </div>
                        </div>

                        <label class="flex items-center justify-between p-2.5 rounded-xl bg-gray-800/80 border border-white/10 cursor-pointer">
                            <span class="text-xs font-semibold text-white">ECO II+ Amalgam Ayırıcı (-AS)</span>
                            <input type="checkbox" id="calc-amalgam" onchange="updateEngineeringCalc()" class="w-4 h-4 accent-emerald-500 rounded">
                        </label>

                        <div class="space-y-1.5">
                            <label class="text-xs font-semibold uppercase text-gray-400">Otoklav Seçimi</label>
                            <select id="calc-steril-brand" onchange="updateEngineeringCalc()" class="w-full bg-gray-800 border border-white/15 rounded-xl px-3 py-2 text-xs text-white">
                                <option value="YESON" selected>Yeson Daslav S 23L B-Class Set (2.000 €)</option>
                                <option value="SW_PLATINUM">Stern Weber SW Platinum 22/28 (Su Geri Dönüşümlü)</option>
                                <option value="SW_PLUS">Stern Weber SW Plus 22/28 (5" Ekranlı)</option>
                            </select>
                        </div>
                    </div>

                    <!-- Wizard Results -->
                    <div class="lg:col-span-7 grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <!-- Compressor Card -->
                        <div class="glass-card rounded-2xl p-4 border border-sky-500/30 flex flex-col justify-between space-y-3">
                            <div class="space-y-1.5">
                                <span class="text-[10px] font-mono uppercase text-sky-400 font-bold">MGF PURE AIR KOMPRESÖR</span>
                                <h4 id="out-comp-title" class="font-bold text-white text-base">MGF 50/25 PRIME M</h4>
                                <div id="out-comp-code" class="text-xs font-mono text-sky-300">PR-OF300-040-M</div>
                                <div class="text-xs text-gray-400 space-y-0.5 pt-2 border-t border-white/10">
                                    <div class="flex justify-between"><span>Debi:</span> <strong id="out-air-lpm" class="text-white">225 l/dk</strong></div>
                                    <div class="flex justify-between"><span>Ses:</span> <span id="out-comp-noise" class="text-emerald-400">66 dB(A)</span></div>
                                </div>
                            </div>
                            <div class="pt-2 flex items-center justify-between">
                                <span id="out-comp-price" class="font-bold text-sm text-emerald-400">3.250 €</span>
                                <button onclick="addCalculatedCompToProposal()" class="px-3 py-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-white text-xs font-bold transition-all">
                                    + Teklife Ekle
                                </button>
                            </div>
                        </div>

                        <!-- Aspirator Card -->
                        <div class="glass-card rounded-2xl p-4 border border-emerald-500/30 flex flex-col justify-between space-y-3">
                            <div class="space-y-1.5">
                                <span class="text-[10px] font-mono uppercase text-emerald-400 font-bold">MGF CERRAHİ ASPİRATÖR</span>
                                <h4 id="out-vac-title" class="font-bold text-white text-base">MGF HYBRID 2</h4>
                                <div id="out-vac-code" class="text-xs font-mono text-emerald-300">AS-100-EX</div>
                                <div class="text-xs text-gray-400 space-y-0.5 pt-2 border-t border-white/10">
                                    <div class="flex justify-between"><span>Emiş:</span> <strong id="out-vac-lpm" class="text-white">1.500 l/dk</strong></div>
                                    <div class="flex justify-between"><span>Vakum:</span> <span id="out-vac-specs" class="text-gray-200">180 mbar</span></div>
                                </div>
                            </div>
                            <div class="pt-2 flex items-center justify-between">
                                <span id="out-vac-price" class="font-bold text-sm text-emerald-400">2.950 €</span>
                                <button onclick="addCalculatedVacToProposal()" class="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition-all">
                                    + Teklife Ekle
                                </button>
                            </div>
                        </div>

                        <!-- Sterilization Card -->
                        <div class="glass-card rounded-2xl p-4 border border-amber-500/30 flex flex-col justify-between space-y-3 sm:col-span-2">
                            <div class="space-y-1.5">
                                <span class="text-[10px] font-mono uppercase text-amber-400 font-bold">STERİLİZASYON PARKURU</span>
                                <div class="flex justify-between items-center">
                                    <h4 id="out-steril-cap" class="font-bold text-white text-base">Yeson Daslav S 23L B-Class Set</h4>
                                    <span id="out-steril-price" class="font-bold text-base text-amber-300">2.000 €</span>
                                </div>
                                <p id="out-steril-sub" class="text-xs text-gray-400">Kapama Cihazı + Distile Su Cihazı + Dahili Yazıcı Dahil Komple Set.</p>
                            </div>
                            <button onclick="addCalculatedSterilToProposal()" class="w-full py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold transition-all">
                                + Otoklav Paketini Teklife Ekle
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <!-- TAB 4: OFFICIAL PROPOSAL GENERATOR -->
        <section id="view-proposal" class="hidden space-y-6">
            <div class="glass-panel rounded-3xl p-6 sm:p-8 border border-white/10 space-y-6">
                <!-- Action Buttons -->
                <div class="no-print flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
                    <div>
                        <span class="text-xs font-mono uppercase text-orange-400 font-bold">MANNAS DİŞ DEPOSU TİC. VE SAN. LTD. ŞTİ.</span>
                        <h2 class="font-display text-2xl font-bold text-white mt-0.5">Resmi Fiyat Teklifi (V.03 Şablonu)</h2>
                    </div>
                    <div class="flex flex-wrap items-center gap-2">
                        <button onclick="resetToBlankTemplate()" class="px-3 py-1.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs font-semibold">Yeni Boş Şablon</button>
                        <button onclick="clearProposalItems()" class="px-3 py-1.5 rounded-xl bg-rose-500/20 text-rose-300 hover:bg-rose-500 hover:text-white text-xs font-semibold">Temizle</button>
                        <button onclick="saveProposalToCrm()" class="px-3.5 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold flex items-center gap-1.5 shadow">
                            <i class="ph-bold ph-database"></i> CRM Görüşmelerine Kaydet
                        </button>
                        <button onclick="copyOfficialProposal()" class="px-3.5 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center gap-1.5">
                            <i class="ph-bold ph-whatsapp-logo"></i> Metin Kopyala
                        </button>
                        <button onclick="openOfficialPrintModal()" class="px-3.5 py-1.5 rounded-xl bg-amber-500/20 hover:bg-amber-500 text-amber-300 hover:text-white border border-amber-500/40 text-xs font-bold flex items-center gap-1.5">
                            <i class="ph-bold ph-printer"></i> Önizle & Yazdır
                        </button>
                        <button onclick="downloadDirectPdf()" class="px-4 py-2 rounded-xl bg-gradient-to-r from-sky-500 to-blue-600 hover:from-sky-400 hover:to-blue-500 text-white text-xs font-bold shadow-lg shadow-sky-500/25 flex items-center gap-1.5">
                            <i class="ph-bold ph-download-simple"></i> PDF İndir (.pdf)
                        </button>
                    </div>
                </div>

                <!-- Customer Metadata Form -->
                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 bg-gray-900/70 p-4 rounded-2xl border border-white/10 text-xs">
                    <div>
                        <label class="text-gray-400 block mb-1 font-semibold">UNVAN (Müşteri / Hekim Adı)</label>
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
                        <input type="text" id="prop-date" value="11.11.2026" class="w-full bg-gray-800 border border-white/10 rounded-lg px-3 py-2 text-white font-semibold">
                    </div>
                    <div class="sm:col-span-2">
                        <label class="text-gray-400 block mb-1 font-semibold">İŞ GELİŞTİRME UZMANI</label>
                        <input type="text" id="prop-rep" value="Hakan BEHRAMOĞLU (0546 291 82 43 | hakan.behramoglu@mannas.com.tr)" class="w-full bg-gray-800 border border-white/10 rounded-lg px-3 py-2 text-sky-300 font-semibold">
                    </div>
                </div>

                <!-- Proposal Items Table -->
                <div class="overflow-x-auto rounded-2xl border border-white/10">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-gray-900 text-[11px] font-mono uppercase text-gray-400 border-b border-white/10">
                                <th class="py-3 px-4">ÜRÜNLER</th>
                                <th class="py-3 px-4">ÜRÜN ADI</th>
                                <th class="py-3 px-4 text-center">ADET</th>
                                <th class="py-3 px-4 text-right">BİRİM FİYATI (€)</th>
                                <th class="py-3 px-4 text-right">TUTARI (€)</th>
                                <th class="py-3 px-2 text-center no-print">İşlem</th>
                            </tr>
                        </thead>
                        <tbody id="proposal-tbody" class="divide-y divide-white/5 text-xs bg-gray-950/60"></tbody>
                        <tfoot>
                            <tr class="bg-gray-900 border-t border-white/15">
                                <td colspan="2" class="py-3.5 px-4 font-mono text-xs text-amber-400 font-semibold">
                                    FİYATLARIMIZA KDV DAHİL DEĞİLDİR
                                </td>
                                <td colspan="2" class="py-3.5 px-4 text-right font-display font-bold text-sm text-gray-300">
                                    TOPLAM:
                                </td>
                                <td id="proposal-total-cell" class="py-3.5 px-4 text-right font-display font-bold text-xl text-sky-400">
                                    0,00 €
                                </td>
                                <td class="no-print"></td>
                            </tr>
                        </tfoot>
                    </table>
                </div>

                <!-- Add Row Manually -->
                <div class="no-print flex flex-wrap sm:flex-nowrap items-center gap-2 p-3 rounded-2xl bg-gray-900/60 border border-white/10 text-xs">
                    <input type="text" id="custom-item-cat" placeholder="Kategori (Örn: ÜNİTE)" class="w-32 bg-gray-800 border border-white/10 rounded-lg px-2.5 py-2 text-white">
                    <input type="text" id="custom-item-name" placeholder="Ürün açıklaması..." class="flex-1 bg-gray-800 border border-white/10 rounded-lg px-3 py-2 text-white">
                    <input type="number" id="custom-item-qty" value="1" min="1" class="w-16 bg-gray-800 border border-white/10 rounded-lg px-2 py-2 text-center text-white font-bold">
                    <input type="number" id="custom-item-price" placeholder="Birim €" class="w-24 bg-gray-800 border border-white/10 rounded-lg px-2.5 py-2 text-right text-white font-mono">
                    <button onclick="addCustomRow()" class="px-4 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-white font-bold whitespace-nowrap">+ Satır Ekle</button>
                </div>

                <!-- Terms -->
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
                        <label class="text-gray-400 block mb-1 font-semibold">✔ VADE SAYISI / RAKAMI</label>
                        <input type="text" id="prop-installments" placeholder="... Ay x ... €" class="w-full bg-gray-800 border border-white/10 rounded-lg px-3 py-2 text-white font-semibold">
                    </div>
                    <div>
                        <label class="text-gray-400 block mb-1 font-semibold">✔ İLK SENET TARİHİ</label>
                        <input type="text" id="prop-first-date" placeholder="GG.AA.YYYY" class="w-full bg-gray-800 border border-white/10 rounded-lg px-3 py-2 text-white font-semibold">
                    </div>
                </div>

                <!-- Official Footer -->
                <div class="bg-gray-900/80 p-4 rounded-2xl border border-white/10 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 text-xs">
                    <div class="space-y-1 text-gray-300">
                        <div class="font-bold text-amber-400">NOT: TESLİMAT ÜRÜNLER HAZIR STOKTADIR YER HAZIR BİLGİSİ GELMESİNE MÜTEAKİBEN 2 HAFTA İÇERİSİNDE PROGRAMA ALINACAKTIR.</div>
                        <div class="text-[11px] text-gray-400">MANNAS DİŞ DEPOSU TİCARET ve SANAYİ LİMİTED ŞİRKETİ • Oğuzhan Cad. No:39 Fındıkzade-Fatih İSTANBUL • 0212 635 77 26</div>
                    </div>
                    <div class="bg-gray-950 px-4 py-2.5 rounded-xl border border-sky-500/30 text-right shrink-0">
                        <div class="font-bold text-white text-sm">HAKAN BEHRAMOĞLU</div>
                        <div class="text-[11px] font-bold text-sky-400">İŞ GELİŞTİRME UZMANI</div>
                        <div class="text-[10px] text-gray-400">0090 (546) 291 82 43</div>
                    </div>
                </div>
            </div>
        </section>

        <!-- TAB 5: SITE & QR PASSPORT -->
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
                            <span class="text-gray-200 flex-1">MyRay ProXima X6 / Hyperion odası kurşunlama ve lisans hazırlığı tamam</span>
                        </label>
                    </div>
                </div>
                <div class="lg:col-span-5 glass-panel rounded-3xl p-6 border border-white/10 space-y-4">
                    <span class="text-xs font-mono uppercase text-sky-400">EASYCHECK PASAPORT</span>
                    <h3 class="font-display text-xl font-bold text-white">Cihaz Bakım & Destek</h3>
                    <div class="bg-gray-950 p-4 rounded-2xl border border-sky-500/30 text-xs space-y-2">
                        <div class="font-bold text-white">Stern Weber Destek Hattı</div>
                        <p class="text-gray-400">Cihaz seri no ve arıza kodlarını doğrudan teknik servise iletebilirsiniz.</p>
                        <button onclick="showToast('Teknik servis çağrısı iletildi: 0212 635 77 26')" class="w-full py-2 rounded-xl bg-sky-500 hover:bg-sky-400 text-white font-bold transition-all">
                            Teknik Servis Çağır (0212 635 77 26)
                        </button>
                    </div>
                </div>
            </div>
        </section>

    </main>

    <!-- TOAST -->
    <div id="toast-box" class="fixed bottom-5 right-5 z-50 hidden glass-panel px-4 py-3 rounded-2xl border border-sky-400/40 text-xs sm:text-sm text-white shadow-2xl flex items-center gap-2.5">
        <i class="ph-fill ph-check-circle text-emerald-400 text-lg"></i>
        <span id="toast-text">İşlem tamamlandı.</span>
    </div>

    <!-- A4 PRINT / PDF MODAL -->
    <div id="a4-preview-modal" class="fixed inset-0 z-50 hidden bg-black/85 backdrop-blur-md flex flex-col items-center justify-start overflow-y-auto p-4 sm:p-6">
        <div class="max-w-[210mm] w-full flex flex-wrap items-center justify-between gap-3 bg-gray-900 border border-white/15 rounded-2xl px-4 py-3 mb-4 sticky top-0 z-10 shadow-xl">
            <div class="flex items-center gap-2 text-white text-xs sm:text-sm font-semibold">
                <i class="ph-fill ph-file-pdf text-rose-400 text-lg"></i>
                <span>Resmi A4 Fiyat Teklifi Önizlemesi</span>
            </div>
            <div class="flex items-center gap-2">
                <button onclick="downloadDirectPdf()" class="px-3.5 py-2 rounded-xl bg-sky-500 hover:bg-sky-400 text-white text-xs font-bold flex items-center gap-1.5 shadow">
                    <i class="ph-bold ph-download-simple"></i> PDF İndir (.pdf)
                </button>
                <button onclick="triggerPopupPrint()" class="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center gap-1.5 shadow">
                    <i class="ph-bold ph-printer"></i> Yazdır
                </button>
                <button onclick="closeOfficialPrintModal()" class="px-3 py-2 rounded-xl bg-gray-800 text-gray-300 hover:text-white text-xs font-semibold">
                    Kapat ✕
                </button>
            </div>
        </div>
        <div id="a4-printable-paper" class="bg-white text-gray-900 w-full max-w-[210mm] min-h-[297mm] p-8 sm:p-10 shadow-2xl rounded-sm font-sans"></div>
    </div>

    <script>
        const MANNAS_PIN = '7659';

        function pressPinKey(digit) {
            const input = document.getElementById('pin-input');
            if (input.value.length < 4) {
                input.value += digit;
                handlePinTyping(input.value);
            }
        }
        function clearPinInput() {
            const input = document.getElementById('pin-input');
            input.value = '';
            document.getElementById('pin-error-msg').classList.add('hidden');
        }
        function handlePinTyping(val) {
            document.getElementById('pin-error-msg').classList.add('hidden');
            if (val.length === 4) verifyPinCode();
        }
        function verifyPinCode() {
            const input = document.getElementById('pin-input');
            if (input.value === MANNAS_PIN) {
                document.getElementById('pin-lock-overlay').classList.add('hidden');
                input.value = '';
                showToast('KlinikMatrix yetkili girişi onaylandı.');
            } else {
                document.getElementById('pin-error-msg').classList.remove('hidden');
                input.value = '';
            }
        }
        function lockAppSession() {
            document.getElementById('pin-lock-overlay').classList.remove('hidden');
            document.getElementById('pin-input').value = '';
        }

        // Eğer CRM'den giriş yapılmışsa PIN ekranını otomatik geç
        if (localStorage.getItem('token')) {
            document.addEventListener('DOMContentLoaded', () => {
                const pinOverlay = document.getElementById('pin-lock-overlay');
                if (pinOverlay) pinOverlay.classList.add('hidden');
            });
        }

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
            { no: 53, name: "WIRELESS (KABLOSUZ) AYAK PEDALI", price: 550 }
        ];

        const UNIT_CATALOG = {
            'S200_ORTHO': {
                brand: 'STERN WEBER • CEFLA İTALYA',
                name: 'Stern Weber S200 Ortho',
                basePrice: 9500,
                paymentNote: '1.500 € + KDV Peşinat, Kalan 10 Ay Euro Vade',
                reflector: 'Venus L-LED (50.000 Lux)',
                panel: 'Geniş Tepsi + Asistan Paneli',
                motor: 'Midwest Türbin Çıkışı',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern 300 P elektromekanik hareketli senkronize Trendelenburg koltuk", status: "STANDART", price: 0 },
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern Weber Ergonomik sırtlık, Sol kolçak", status: "STANDART", price: 0 },
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern Weber Atlaxis 3 akslı pnömatik vertikal ve horizontal kilitli tetiyer", status: "STANDART", price: 0 },
                    { cat: "TEDAVİ KOLTUĞU", desc: "Dikişsiz antibakteriyel standart koltuk döşemesi", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "Geniş Hekim Çalışma Tepsisi (Ortho Özel)", status: "STANDART", price: 0 },
                    { cat: "ASİSTAN TABLETİ", desc: "Yüksekliği ayarlanabilir 5 modül kapasiteli Asistan tableti", status: "STANDART", price: 0 },
                    { cat: "ASİSTAN TABLETİ", desc: "Stern Weber 3 fonksiyonlu Hava-Su şırıngası", status: "STANDART", price: 0 },
                    { cat: "ASİSTAN TABLETİ", desc: "Işıklı Midwest Türbin modülü", status: "STANDART", price: 0 },
                    { cat: "ASİSTAN TABLETİ", desc: "Y-S DENT Coupling'li LED ışıklı Aeratör", status: "HEDİYE", price: 0 },
                    { cat: "ASİSTAN TABLETİ", desc: "Stern Weber ışıklı SC-A3 kavitron (4 adet kavitron ucu ve anahtarı)", status: "STANDART", price: 0 },
                    { cat: "KREŞUAR BLOĞU", desc: "Hasta Koltuğu ile hareket eden kreşuar bloğu, 270° seramik çanak", status: "STANDART", price: 0 },
                    { cat: "HİJYEN & REFLEKTÖR", desc: "Sanaspray 1.8L acil su sistemi + Venus L-LED (50.000 Lux) fotoselli reflektör", status: "STANDART", price: 0 },
                    { cat: "PEDAL & TABURE", desc: "Üstten basmalı Power Pedal + Stern Weber T7 hekim taburesi", status: "STANDART", price: 0 }
                ]
            },
            'S200': {
                brand: 'STERN WEBER • CEFLA İTALYA',
                name: 'Stern Weber S200',
                basePrice: 12000,
                paymentNote: '2.500 € + KDV Peşinat, Kalan 10 Ay Euro Vade',
                reflector: 'Venus LED SCT (50.000 Lux)',
                panel: 'LCD Dokunmatik Ekran (5 Modül)',
                motor: 'i-XR3-L Kömürsüz (3.3 Ncm)',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern 300 P elektromekanik senkronize Trendelenburg koltuk, Ergonomik sırtlık, Sol kolçak", status: "STANDART", price: 0 },
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern Weber Atlaxis 3 akslı pnömatik vertikal ve horizontal kilitli tetiyer", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "LCD Dokunmatik Ekran, pnömatik frenli 5 modüllü hekim tableti (Askılı/Kamçılı)", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "Stern Weber 3 fonksiyonlu Hava-Su şırıngası + 2x Işıklı Midwest Türbin modülü", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "Stern Weber i-XR3-L ışıklı kömürsüz mikromotor (100-40.000 rpm / 3.3 Ncm)", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "Stern Weber ışıklı SC-A3 kavitron (4 adet ALTIN kavitron ucu ve anahtarı)", status: "STANDART", price: 0 },
                    { cat: "BAŞLIK HEDİYESİ", desc: "Y-S DENT 1:1 Mavi Kuşak LED Işıklı Anguldruva", status: "HEDİYE", price: 0 },
                    { cat: "BAŞLIK HEDİYESİ", desc: "Y-S DENT Coupling'li hızlı su ayarlı Midwest 6 delikli Aeratör", status: "HEDİYE", price: 0 },
                    { cat: "ASİSTAN TABLETİ", desc: "3 modül kapasiteli Asistan tableti + Çok fonksiyonlu asistan kontrol paneli", status: "STANDART", price: 0 },
                    { cat: "KREŞUAR BLOĞU", desc: "Hasta koltuğu ile hareket eden kreşuar bloğu, 270° seramik kreşuar, Sanaspray 1.8L", status: "STANDART", price: 0 },
                    { cat: "REFLEKTÖR & TABURE", desc: "Venus LED SCT (50.000 Lux, fotoselli 3 renk) + Power Pedal + T7 hekim taburesi", status: "STANDART", price: 0 }
                ]
            },
            'S220TR': {
                brand: 'STERN WEBER • CEFLA İTALYA',
                name: 'Stern Weber 220 TR',
                basePrice: 13500,
                paymentNote: '2.500 € + KDV Peşinat, Kalan 10 Ay Euro Vade',
                reflector: 'Venus Plus LED (50.000 Lux)',
                panel: 'LCD Dokunmatik Ekran',
                motor: 'i-XR3-L Kömürsüz Mikromotor',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern 300 P elektromekanik senkronize koltuk, Üniversal tetiyer, Sol kolçak", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "LCD Dokunmatik Ekran, pnömatik frenli 4 modüllü hekim tableti", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "Stern Weber i-XR3-L ışıklı kömürsüz mikromotor + Işıklı SC-A3 kavitron (4 altın uç)", status: "STANDART", price: 0 },
                    { cat: "BAŞLIK HEDİYESİ", desc: "Y-S DENT Coupling'li Işıklı Aeratör + 1:1 Mavi Kuşak Işıklı Anguldruva", status: "HEDİYE", price: 0 },
                    { cat: "KREŞUAR & HİJYEN", desc: "270° seramik kreşuar, Sanaspray acil su sistemi, Venus Plus LED reflektör, T7 tabure", status: "STANDART", price: 0 }
                ]
            },
            'S200_GOLD': {
                brand: 'STERN WEBER • CEFLA İTALYA',
                name: 'Stern Weber S200 GOLD',
                basePrice: 14500,
                paymentNote: '3.500 € + KDV Peşinat, Kalan 11 Ay Euro Vade',
                reflector: 'Venus LED MCT (3 Renk Isısı)',
                panel: 'LCD Dokunmatik Ekran',
                motor: 'i-XR3-L + EVO Başlık Paketi',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern 300 P elektromekanik senkronize koltuk + Atlaxis 3 akslı pnömatik tetiyer", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "LCD Dokunmatik Ekran, 5 modüllü pnömatik frenli tablet + i-XR3-L mikromotor + SC-A3 kavitron", status: "STANDART", price: 0 },
                    { cat: "SW EVO BAŞLIK", desc: "Stern Weber Silent Power EVO 4L Işıklı Türbin (350.000 rpm, 57 dB) SW Coupling ile", status: "STANDART", price: 0 },
                    { cat: "SW EVO BAŞLIK", desc: "Stern Weber Goldspeed EVO S1-L Işıklı 1:1 Mavi Kuşak Anguldruva", status: "STANDART", price: 0 },
                    { cat: "SW EVO BAŞLIK", desc: "Stern Weber Goldspeed EVO M5-L Işıklı 1:5 Kırmızı Kuşak Anguldruva", status: "STANDART", price: 0 },
                    { cat: "BAŞLIK HEDİYESİ", desc: "Y-S DENT Coupling'li hızlı su ayarlı Aeratör", status: "HEDİYE", price: 0 },
                    { cat: "ASİSTAN & MULTİMEDYA", desc: "T-LED Işınlı Dolgu + Y-S Monitör Kolu + Venus LED MCT Reflektör + T7 Tabure", status: "STANDART", price: 0 }
                ]
            },
            'S300': {
                brand: 'STERN WEBER • CEFLA İTALYA',
                name: 'Stern Weber S300',
                basePrice: 15500,
                paymentNote: 'TDB Özel Kongre Vadesi',
                reflector: 'Venus LED MCT (50.000 Lux)',
                panel: '7" Full Touch HD (Endo+İmplant)',
                motor: 'i-XS4 Işıklı (5.3 Ncm, Tork Ayarlı)',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern 300 P elektromekanik senkronize koltuk, döküm sırtlık, Atlaxis 3 akslı pnömatik tetiyer", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "7\\" Full Touch HD Ekran (Endo+İmplant Yazılımlı), elektropnömatik frenli 5 modüllü tablet", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "Stern Weber 6 fonksiyonlu ısıtmalı şırınga + 2x Işıklı Midwest Türbin modülü", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "Stern Weber i-XS4 ışıklı kömürsüz mikromotor (5.3 Ncm tork ayarlı) + SC-A3 kavitron (4 altın uç)", status: "STANDART", price: 0 },
                    { cat: "BAŞLIK HEDİYESİ", desc: "Y-S DENT 1:1 Mavi Kuşak LED Anguldruva + Y-S DENT Coupling'li Aeratör", status: "HEDİYE", price: 0 },
                    { cat: "ASİSTAN & KREŞUAR", desc: "T-LED Işınlı Dolgu + Seramik kreşuar + Boiler bardak ısıtıcı + Sanaspray + Venus LED MCT", status: "STANDART", price: 0 },
                    { cat: "TABURE & PEDAL", desc: "Stern Weber T7 hekim taburesi + Power Pedal", status: "STANDART", price: 0 }
                ]
            },
            'S280TRC': {
                brand: 'STERN WEBER • CEFLA İTALYA',
                name: 'Stern Weber 280 TRC Asansörlü',
                basePrice: 17500,
                paymentNote: '5.500 € + KDV Peşinat, Kalan 12.000 € 10 Ay Euro Vade',
                reflector: 'Venus LED MCT (50.000 Lux)',
                panel: '7" Full Touch HD + SideFlex + NFC',
                motor: 'i-XS4 (5.3 Ncm Endo+İmplant)',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern 280 P kreşuar bloğuna bağlı Trendelenburg yapan asansörlü koltuk, döküm sırtlık", status: "STANDART", price: 0 },
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern Weber Atlaxis 3 akslı pnömatik vertikal ve horizontal kilitli tetiyer", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "7\\" Full Touch HD Ekran (Endo+İmplant Yazılımlı) + NFC Silikon Bileklik Tanıma", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "SideFlex teknolojiye sahip (sağ-sol rotasyonlu) kamçı kolları + 6F ısıtmalı şırınga", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "Stern Weber i-XS4 ışıklı kömürsüz mikromotor (5.3 Ncm) + SC-A3 kavitron (4 altın uç)", status: "STANDART", price: 0 },
                    { cat: "BAŞLIK HEDİYESİ", desc: "Y-S DENT Coupling'li Aeratör + Y-S DENT 1:1 Mavi Kuşak Işıklı Anguldruva", status: "HEDİYE", price: 0 },
                    { cat: "ASİSTAN & KREŞUAR", desc: "T-LED Işınlı Dolgu + Motorize hareketli 270° seramik kreşuar + Boiler bardak ısıtıcı", status: "STANDART", price: 0 },
                    { cat: "REFLEKTÖR & TABURE", desc: "Venus LED MCT (4.300K/5.000K/5.500K) + Power Pedal + T7 hekim taburesi", status: "STANDART", price: 0 }
                ]
            },
            'S380TRC_VIP': {
                brand: 'STERN WEBER • CEFLA İTALYA',
                name: 'Stern Weber VIP 380 TRC Asansörlü',
                basePrice: 25000,
                paymentNote: '8.000 € + KDV Peşin, Kalan 18 Ay Euro Vade',
                reflector: 'Venus LED MCT (Fotoselli)',
                panel: '7" Full Touch HD + Interactive LED',
                motor: 'i-XS4 Kömürsüz Mikromotor',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern 380 P kreşuar bloğuna bağlı asansör sistemli 90° döner koltuk, döküm sırtlık", status: "STANDART", price: 0 },
                    { cat: "TEDAVİ KOLTUĞU", desc: "Atlaxis 3 akslı pnömatik tetiyer + Dikişsiz antibakteriyel döşeme + Patient Presence Sensor", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "7\\" Full Touch HD Ekran (Endo+İmplant Yazılımlı) + NFC + SideFlex döner kamçı kolları", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "Stern Weber 6F ısıtmalı şırınga + 2x Işıklı Midwest + i-XS4 kömürsüz mikromotor + SC-A3 kavitron", status: "STANDART", price: 0 },
                    { cat: "KREŞUAR BLOĞU", desc: "Interactive LED Pack (Durum göstergeli) + Motorize 270° seramik kreşuar + Fotoselli bardaklık", status: "STANDART", price: 0 },
                    { cat: "HİJYEN & REFLEKTÖR", desc: "Sanaspray 1.8L + Venus LED MCT 50.000 Lux + İtmeli/Basmalı Pedal + T7 tabure", status: "STANDART", price: 0 }
                ]
            },
            'S380TRC_GOLD': {
                brand: 'STERN WEBER • CEFLA İTALYA',
                name: 'Stern Weber VIP 380 TRC GOLD (Tam Donanım)',
                basePrice: 45000,
                paymentNote: 'Özel Kongre Finansmanı',
                reflector: 'Venus LED MCT View (4K Kamera)',
                panel: '7" Full Touch + Apex + Peristaltik Pompa',
                motor: '2x i-XS4 + Goldspeed EVO Full Set',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Stern 380 P kreşuar bloğuna bağlı 90° döner asansörlü koltuk + VISCO Döşeme + Atlaxis Tetiyer", status: "STANDART", price: 0 },
                    { cat: "CERRAHİ / ENDO", desc: "2x i-XS4 kömürsüz mikromotor + Resiproc modülü + Peristaltik İrrigasyon Pompası + Entegre LAEC Apex Locator", status: "STANDART", price: 0 },
                    { cat: "SW EVO BAŞLIK", desc: "Silent Power EVO 4L Işıklı Türbin + EVO S1-L Mavi Kuşak + EVO M5-L Kırmızı Kuşak", status: "STANDART", price: 0 },
                    { cat: "SW EVO BAŞLIK", desc: "EVO R20-L Dıştan Sulu İmplant Anguldruvası + EVO E4 Endodontik Anguldruva", status: "STANDART", price: 0 },
                    { cat: "MULTİMEDYA & RÖNTGEN", desc: "Entegre Kablosuz Kumandalı RXDC HyperSphere Periapikal Röntgen Cihazı", status: "STANDART", price: 0 },
                    { cat: "MULTİMEDYA & RÖNTGEN", desc: "Zen-X No:1 RVG Sensör + C-U2 HD Kamera + Monitör Kolu ve PC Multimedya Donanımı", status: "STANDART", price: 0 },
                    { cat: "HİJYEN & KREŞUAR", desc: "Interactive LED Pack + ACWS Hortum Dezenfeksiyonu + Sanaspray + Wi-Fi Ayak Pedalı", status: "STANDART", price: 0 },
                    { cat: "TABURE", desc: "Stern Weber T7 hekim taburesi + Stern Weber T8 asistan taburesi", status: "STANDART", price: 0 }
                ]
            },
            'SF8000C': {
                brand: 'MEDARC • SILVERFOX DENTAL',
                name: 'Silverfox 8000 C Pro',
                basePrice: 6400,
                paymentNote: 'Stoktan Hemen Teslim',
                reflector: 'Wings Reflective LED (50.000 Lux)',
                panel: '7" HD Full Touch + All-in-One PC',
                motor: 'Elektrikli Işıklı Mikromotor',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Memory Foam Visco döşeme, metal sırtlık, 3 hekim hafızası", status: "STANDART", price: 0 },
                    { cat: "MULTİMEDYA", desc: "All-in-One Dokunmatik Multitouch Bilgisayar + Ağız İçi Kamera dahil", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "7\\" HD Full Touch ekran (Elektrikli mikromotor devir/tork ekrandan kontrol edilir)", status: "STANDART", price: 0 },
                    { cat: "BAŞLIKLAR", desc: "2x Işıklı Aeratör + 1:1 Mavi Kuşak Anguldruva + Woodpecker Kavitron + Q Led Dolgu Cihazı", status: "STANDART", price: 0 },
                    { cat: "TABURE", desc: "Hekim Taburesi + Asistan Taburesi dahil", status: "STANDART", price: 0 }
                ]
            },
            'SF8000B': {
                brand: 'MEDARC • SILVERFOX DENTAL',
                name: 'Silverfox 8000 B',
                basePrice: 3850,
                paymentNote: 'Stoktan Hemen Teslim (4.500 $ Karşılığı)',
                reflector: 'Firefly LED Reflektör (30.000 Lux)',
                panel: '7" HD Full Touch Ekran',
                motor: 'Havalı Mikromotor + Başlık Seti',
                items: [
                    { cat: "TEDAVİ KOLTUĞU", desc: "Trendelenburg yapabilen 38-73 cm asansörlü koltuk, sıkışma emniyet sensörleri", status: "STANDART", price: 0 },
                    { cat: "HEKİM TABLETİ", desc: "7\\" HD Full Touch ekran, elektropnömatik frenli tablet, 6 modül kapasitesi", status: "STANDART", price: 0 },
                    { cat: "BAŞLIKLAR", desc: "Işıklı Aeratör + 1:1 Mavi Kuşak + Havalı Mikromotor + Woodpecker Kavitron + Q Led Dolgu", status: "STANDART", price: 0 },
                    { cat: "REFLEKTÖR & TABURE", desc: "Firefly LED fotoselli reflektör (sarı kompozit modlu) + Hekim taburesi", status: "STANDART", price: 0 }
                ]
            }
        };

        const appState = {
            selectedModelKey: 'S200',
            armType: 'Kamçılı (Continental)',
            colorName: '102 Atlantic Blue',
            colorHex: '#1e5aa8',
            suctionType: 'hybrid',
            calcUnits: 4,
            currentUnitSheetItems: [],
            proposalItems: [],
            currentCalcComp: { name: 'MGF 50/25 PRIME M KURUTUCULU DENTAL KOMPRESÖR (İTALYA)', qty: 1, unitPrice: 3250 },
            currentCalcVac: { name: 'MGF HYBRID 2 DENTAL ASPİRATÖR CİHAZI 1.500 Lt/dk (İTALYA)', qty: 1, unitPrice: 2950 },
            currentCalcSteril: { name: 'YESON DASLAV S 23 Lt B-CLASS OTOKLAV SETİ (ÇİN)', qty: 1, unitPrice: 2000 }
        };

        const SW_COLORS = [
            { code: '102', name: 'Atlantic Blue', hex: '#1e5aa8' },
            { code: '106', name: 'Mediterranean Blue', hex: '#2980b9' },
            { code: '113', name: 'Pacific Blue', hex: '#38bdf8' },
            { code: '136', name: 'Indian Blue', hex: '#4a6984' },
            { code: '132', name: 'Blueberry Violet', hex: '#5b3277' },
            { code: '134', name: 'Japanese Wisteria', hex: '#9b72aa' },
            { code: '135', name: 'Venetian Red', hex: '#6e1423' },
            { code: '115', name: 'Scottish Salmon', hex: '#c0392b' },
            { code: '103', name: 'Nevada Yellow', hex: '#d35400' },
            { code: '123', name: 'Polynesian Green', hex: '#82b440' },
            { code: '101', name: 'Caribbean Green', hex: '#16a085' },
            { code: '121', name: 'Anthracite Grey', hex: '#4b5563' }
        ];

        function switchTab(tabId) {
            const views = ['configurator', 'imaging', 'calculator', 'proposal', 'ideas'];
            views.forEach(v => {
                document.getElementById('view-' + v).classList.add('hidden');
                const btn = document.getElementById('tab-' + v);
                if (btn) btn.className = 'tab-btn flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs sm:text-sm font-medium text-gray-400 hover:text-white transition-all';
            });
            document.getElementById('view-' + tabId).classList.remove('hidden');
            const activeBtn = document.getElementById('tab-' + tabId);
            if (activeBtn) activeBtn.className = 'tab-btn active-tab flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs sm:text-sm font-medium transition-all bg-sky-500 text-white shadow-md shadow-sky-500/25';
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
            if (idx !== "") {
                const item = TDB_OPTIONS_LIBRARY[idx];
                document.getElementById('tdb-opt-price-input').value = item.price;
            }
        }

        function addSelectedTdbOptionToSheet() {
            const idx = document.getElementById('tdb-opt-select').value;
            if (idx === "") {
                showToast("Lütfen açılır listeden bir opsiyon seçin.");
                return;
            }
            const item = TDB_OPTIONS_LIBRARY[idx];
            const status = document.getElementById('tdb-opt-status-input').value.trim() || 'OPSİYONEL';
            const price = parseFloat(document.getElementById('tdb-opt-price-input').value || 0);

            appState.currentUnitSheetItems.push({
                cat: "OPSİYONEL",
                desc: item.name,
                status: status,
                price: price
            });
            renderUnitSheetTable();
            showToast(`${item.name.substring(0, 30)}... konfigürasyona eklendi.`);
        }

        function selectUnitModel(modelKey) {
            appState.selectedModelKey = modelKey;
            const data = UNIT_CATALOG[modelKey];

            Object.keys(UNIT_CATALOG).forEach(k => {
                const b = document.getElementById('model-' + k);
                if (b) {
                    if (k === modelKey) b.className = 'model-btn p-2.5 rounded-xl border border-sky-500 bg-sky-500/15 text-left transition-all';
                    else b.className = 'model-btn p-2.5 rounded-xl border border-white/10 bg-gray-900/60 text-left transition-all hover:border-sky-500/40';
                }
            });

            document.getElementById('unit-brand-badge').textContent = data.brand;
            document.getElementById('unit-price-badge').textContent = data.basePrice.toLocaleString('tr-TR') + ' € Baz';
            document.getElementById('unit-title-display').textContent = data.name + ' ' + appState.armType.split(' ')[0];
            document.getElementById('spec-reflector').textContent = data.reflector;
            document.getElementById('spec-panel').textContent = data.panel;
            document.getElementById('spec-motor').textContent = data.motor;
            document.getElementById('spec-payment').textContent = data.paymentNote;

            document.getElementById('sheet-unit-name').textContent = `${data.name} (${data.basePrice.toLocaleString('tr-TR')} €)`;
            document.getElementById('sheet-footer-note').textContent = `Ödeme Koşulu: ${data.paymentNote} • Fiyatlara KDV Dahil Değildir.`;

            appState.currentUnitSheetItems = JSON.parse(JSON.stringify(data.items));
            renderUnitSheetTable();
            recalcUnitPrice();
        }

        function resetCurrentUnitSheet() {
            const data = UNIT_CATALOG[appState.selectedModelKey];
            appState.currentUnitSheetItems = JSON.parse(JSON.stringify(data.items));
            renderUnitSheetTable();
            showToast("Konfigürasyon föyü orijinal haline getirildi.");
        }

        function renderUnitSheetTable() {
            const tbody = document.getElementById('unit-sheet-tbody');
            tbody.innerHTML = '';
            const basePrice = UNIT_CATALOG[appState.selectedModelKey].basePrice;
            let extrasTotal = 0;

            appState.currentUnitSheetItems.forEach((it, idx) => {
                extrasTotal += (it.price || 0);
                const tr = document.createElement('tr');
                tr.className = 'hover:bg-white/5 transition-colors';
                tr.innerHTML = `
                    <td class="py-2.5 px-3 text-center text-gray-500 font-mono text-[11px]">${idx + 1}</td>
                    <td class="py-2 px-2">
                        <input type="text" value="${it.cat}" onchange="updateSheetItem(${idx}, 'cat', this.value)" class="w-full bg-gray-900 border border-white/10 rounded px-2 py-1 text-[11px] font-bold text-sky-400">
                    </td>
                    <td class="py-2 px-2">
                        <input type="text" value="${it.desc}" onchange="updateSheetItem(${idx}, 'desc', this.value)" class="w-full bg-gray-900 border border-white/10 rounded px-2 py-1 text-xs text-gray-200">
                    </td>
                    <td class="py-2 px-2 text-center">
                        <input type="text" value="${it.status}" onchange="updateSheetItem(${idx}, 'status', this.value)" class="w-24 text-center bg-gray-900 border border-white/10 rounded px-1.5 py-1 text-[10px] font-bold ${it.status === 'HEDİYE' ? 'text-emerald-400' : (it.status === 'OPSİYONEL' ? 'text-amber-400' : 'text-gray-300')}">
                    </td>
                    <td class="py-2 px-2 text-right">
                        <input type="number" value="${it.price || 0}" step="10" onchange="updateSheetItem(${idx}, 'price', this.value)" class="w-20 text-right bg-gray-900 border border-white/10 rounded px-2 py-1 text-xs font-mono font-bold text-white">
                    </td>
                    <td class="py-2 px-2 text-center whitespace-nowrap">
                        <button onclick="moveSheetItem(${idx}, -1)" class="text-gray-400 hover:text-white p-1" title="Yukarı Taşı">▲</button>
                        <button onclick="moveSheetItem(${idx}, 1)" class="text-gray-400 hover:text-white p-1" title="Aşağı Taşı">▼</button>
                        <button onclick="deleteSheetItem(${idx})" class="text-gray-500 hover:text-rose-400 p-1" title="Sil">✕</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });

            const finalUnitTotal = basePrice + extrasTotal;
            document.getElementById('sheet-total-price').textContent = finalUnitTotal.toLocaleString('tr-TR') + ' €';
            recalcUnitPrice();
        }

        function updateSheetItem(index, key, val) {
            if (key === 'price') val = parseFloat(val || 0);
            appState.currentUnitSheetItems[index][key] = val;
            renderUnitSheetTable();
        }

        function moveSheetItem(index, dir) {
            const newIndex = index + dir;
            if (newIndex < 0 || newIndex >= appState.currentUnitSheetItems.length) return;
            const temp = appState.currentUnitSheetItems[index];
            appState.currentUnitSheetItems[index] = appState.currentUnitSheetItems[newIndex];
            appState.currentUnitSheetItems[newIndex] = temp;
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

            if (!desc) {
                showToast("Lütfen donanım açıklaması girin.");
                return;
            }
            appState.currentUnitSheetItems.push({ cat, desc, status, price });
            document.getElementById('sheet-custom-desc').value = '';
            document.getElementById('sheet-custom-price').value = '0';
            renderUnitSheetTable();
        }

        function recalcUnitPrice() {
            const data = UNIT_CATALOG[appState.selectedModelKey];
            let singlePrice = data.basePrice;
            appState.currentUnitSheetItems.forEach(it => { singlePrice += (it.price || 0); });

            const qty = Math.max(1, parseInt(document.getElementById('unit-qty-input').value || 1, 10));
            const total = singlePrice * qty;

            document.getElementById('unit-price-badge').textContent = singlePrice.toLocaleString('tr-TR') + ' € / Adet';
            document.getElementById('btn-add-unit-summary').textContent = `Özet Olarak Ekle (${qty} Adet • ${total.toLocaleString('tr-TR')} €)`;
        }

        function addConfiguredUnitSummaryToProposal() {
            const data = UNIT_CATALOG[appState.selectedModelKey];
            let singlePrice = data.basePrice;
            const extraDescs = [];

            appState.currentUnitSheetItems.forEach(it => {
                if (it.price > 0) {
                    singlePrice += it.price;
                    extraDescs.push(`${it.desc} (+${it.price}€)`);
                }
            });

            const qty = Math.max(1, parseInt(document.getElementById('unit-qty-input').value || 1, 10));
            const addInfo = extraDescs.length ? ` [Ekstralar: ${extraDescs.join(', ')}]` : '';
            const fullName = `${data.name.toUpperCase()} ${appState.armType.toUpperCase()} - ${appState.colorName} (${data.reflector} • ${data.panel})${addInfo}`;

            addItemToProposal('ÜNİTE', fullName, qty, singlePrice);
        }

        function pushEntireSheetToProposal() {
            const data = UNIT_CATALOG[appState.selectedModelKey];
            const qty = Math.max(1, parseInt(document.getElementById('unit-qty-input').value || 1, 10));

            addItemToProposal('ÜNİTE', `${data.name.toUpperCase()} ${appState.armType.toUpperCase()} (TDB 29. Kongre Fiyat Listesi Baz Paketi - ${appState.colorName})`, qty, data.basePrice);

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
            badge.textContent = appState.armType;
            document.getElementById('unit-title-display').textContent = data.name + ' ' + appState.armType.split(' ')[0];
        }

        function setUpholstery(hex, label) {
            appState.colorHex = hex;
            appState.colorName = label;
            document.getElementById('svg-upholstery').setAttribute('fill', hex);
            document.getElementById('studio-glow').style.background = hex;
            document.getElementById('svg-ambient-led').setAttribute('fill', hex);
            document.getElementById('selected-color-label').textContent = label;
            document.getElementById('color-name-badge').textContent = label;
            renderColorSwatches();
        }

        function renderColorSwatches() {
            const box = document.getElementById('upholstery-swatches-container');
            box.innerHTML = '';
            SW_COLORS.forEach(c => {
                const btn = document.createElement('button');
                btn.type = 'button';
                const isSelected = appState.colorName.includes(c.name);
                btn.onclick = () => setUpholstery(c.hex, `${c.code} ${c.name}`);
                btn.className = `p-1 rounded-lg border transition-all flex flex-col items-center ${isSelected ? 'border-sky-400 bg-sky-500/20' : 'border-white/10 bg-gray-900/60'}`;
                btn.innerHTML = `
                    <span class="w-4 h-4 rounded-full border border-white/30" style="background-color: ${c.hex}"></span>
                    <span class="text-[9px] font-mono mt-0.5 text-gray-300 leading-none">${c.code}</span>
                `;
                box.appendChild(btn);
            });
        }

        function updateEngineeringCalc() {
            const units = parseInt(document.getElementById('calc-units').value, 10);
            const compType = document.getElementById('calc-comp-type').value;
            const hasAmalgam = document.getElementById('calc-amalgam').checked;
            const sterilBrand = document.getElementById('calc-steril-brand').value;
            appState.calcUnits = units;

            document.getElementById('calc-unit-val').textContent = units + ' Ünit';

            let compName = "MGF 50/25 PRIME M (4 Ünitlik)";
            let compCode = "PR-OF300-040-M";
            let compLpm = "225 l/dk @ 5 bar";
            let compNoise = "66 dB(A)";
            let compPrice = 3250;
            let compQty = 1;

            if (units <= 1) {
                compName = compType === 'CS-M' ? "MGF MINI BOX 24/7 PRIME M" : "MGF 30/7 PRIME M";
                compCode = "PR-OF100-024-M";
                compLpm = "85 l/dk @ 5 bar";
                compNoise = compType === 'CS-M' ? "50 dB(A)" : "65 dB(A)";
                compPrice = compType === 'CS-M' ? 2150 : 1650;
            } else if (units <= 3) {
                compName = compType === 'CS-M' ? "MGF CS 30/15 PRIME M (Kabinli)" : "MGF 50/15 PRIME M";
                compCode = "PR-OF200-040-M";
                compLpm = "152 l/dk @ 5 bar";
                compNoise = compType === 'CS-M' ? "53 dB(A)" : "66 dB(A)";
                compPrice = compType === 'CS-M' ? 3100 : 2350;
            } else if (units <= 6) {
                compName = compType === 'CS-M' ? "MGF CS 100/30 TANDEM PRIME M" : "MGF 100/30 TANDEM PRIME M";
                compCode = "PR-OF400-090-MT";
                compLpm = "305 l/dk @ 5 bar";
                compNoise = compType === 'CS-M' ? "56 dB(A)" : "69 dB(A)";
                compPrice = compType === 'CS-M' ? 5600 : 7000;
            } else {
                compName = "2x MGF 50/25 PRIME M (Çift Yedekli 8 Ünitlik)";
                compCode = "2x PR-OF300-040-M";
                compLpm = "2x 225 l/dk = 450 l/dk";
                compNoise = "66 dB(A)";
                compPrice = 3250;
                compQty = 2;
            }

            document.getElementById('out-comp-title').textContent = compName;
            document.getElementById('out-comp-code').textContent = compCode;
            document.getElementById('out-air-lpm').textContent = compLpm;
            document.getElementById('out-comp-noise').textContent = compNoise;
            document.getElementById('out-comp-price').textContent = `${compQty} Adet x ${compPrice.toLocaleString('tr-TR')} €`;

            appState.currentCalcComp = {
                name: `${compName} DENTAL KOMPRESÖR (${compCode}) (İTALYA)`,
                qty: compQty,
                unitPrice: compPrice
            };

            let vacName = "MGF HYBRID 2 (3-4 Ünitlik)";
            let vacCode = "AS-100-EX" + (hasAmalgam ? "-AS" : "");
            let vacLpm = "1.500 l/dk";
            let vacPrice = 2950 + (hasAmalgam ? 850 : 0);
            let vacQty = 1;

            if (appState.suctionType === 'hybrid') {
                if (units <= 2) {
                    vacName = "MGF HYBRID 1";
                    vacCode = "AS-094-EX" + (hasAmalgam ? "-AS" : "");
                    vacLpm = "1.100 - 1.300 l/dk";
                    vacPrice = 2250 + (hasAmalgam ? 850 : 0);
                } else if (units <= 4) {
                    vacName = "MGF HYBRID 2";
                    vacCode = "AS-100-EX" + (hasAmalgam ? "-AS" : "");
                    vacLpm = "1.500 l/dk";
                    vacPrice = 2950 + (hasAmalgam ? 850 : 0);
                } else if (units <= 6) {
                    vacName = "MGF HYBRID 5 (İnverterli)";
                    vacCode = "AS-150-EX" + (hasAmalgam ? "-AS" : "");
                    vacLpm = "2.500 l/dk";
                    vacPrice = 4150 + (hasAmalgam ? 850 : 0);
                } else {
                    vacName = "2x MGF HYBRID 2 (Yedekli Çift Hat)";
                    vacCode = "2x AS-100-EX" + (hasAmalgam ? "-AS" : "");
                    vacLpm = "3.000 l/dk";
                    vacPrice = 2950 + (hasAmalgam ? 850 : 0);
                    vacQty = 2;
                }
            } else {
                vacName = "MGF DRY SILENT 4 (Kuru)";
                vacCode = "AS-200-S";
                vacLpm = "3.650 l/dk";
                vacPrice = 2400;
            }

            document.getElementById('out-vac-title').textContent = vacName;
            document.getElementById('out-vac-code').textContent = vacCode;
            document.getElementById('out-vac-lpm').textContent = vacLpm;
            document.getElementById('out-vac-price').textContent = `${vacQty} Adet x ${vacPrice.toLocaleString('tr-TR')} €`;

            appState.currentCalcVac = {
                name: `${vacName} DENTAL ASPİRATÖR (${vacCode}) (İTALYA)`,
                qty: vacQty,
                unitPrice: vacPrice
            };

            if (sterilBrand === 'YESON') {
                document.getElementById('out-steril-cap').textContent = "Yeson Daslav S 23L B-Class Set";
                document.getElementById('out-steril-price').textContent = "2.000 €";
                appState.currentCalcSteril = { name: "YESON DASLAV S 23 Lt B-CLASS OTOKLAV (KAPAMA + DİSTİLE SU DAHİL) (ÇİN)", qty: 1, unitPrice: 2000 };
            } else if (sterilBrand === 'SW_PLATINUM') {
                const vol = units >= 5 ? 28 : 22;
                const pr = units >= 5 ? 5490 : 4350;
                document.getElementById('out-steril-cap').textContent = `Stern Weber SW ${vol} Platinum Set (Millseal Dahil)`;
                document.getElementById('out-steril-price').textContent = `${pr.toLocaleString('tr-TR')} €`;
                appState.currentCalcSteril = { name: `STERN WEBER SW ${vol} PLATINUM B-CLASS OTOKLAV + MILLSEAL KAPAMA (İTALYA)`, qty: 1, unitPrice: pr };
            } else {
                const vol = units >= 5 ? 28 : 22;
                const pr = units >= 5 ? 4350 : 3950;
                document.getElementById('out-steril-cap').textContent = `Stern Weber SW ${vol} 3'lü Set`;
                document.getElementById('out-steril-price').textContent = `${pr.toLocaleString('tr-TR')} €`;
                appState.currentCalcSteril = { name: `STERN WEBER SW ${vol} B-CLASS OTOKLAV 3'LÜ SET (İTALYA)`, qty: 1, unitPrice: pr };
            }
        }

        function setSuctionType(type) {
            appState.suctionType = type;
            const bHy = document.getElementById('suction-hybrid');
            const bDr = document.getElementById('suction-dry');
            if (type === 'hybrid') {
                bHy.className = 'py-2 px-3 rounded-xl border border-sky-500 bg-sky-500/15 text-xs font-semibold text-white';
                bDr.className = 'py-2 px-3 rounded-xl border border-white/10 bg-gray-800 text-xs font-medium text-gray-400';
            } else {
                bDr.className = 'py-2 px-3 rounded-xl border border-sky-500 bg-sky-500/15 text-xs font-semibold text-white';
                bHy.className = 'py-2 px-3 rounded-xl border border-white/10 bg-gray-800 text-xs font-medium text-gray-400';
            }
            updateEngineeringCalc();
        }

        function addCalculatedCompToProposal() {
            addItemToProposal('KOMPRESÖR', appState.currentCalcComp.name, appState.currentCalcComp.qty, appState.currentCalcComp.unitPrice);
        }
        function addCalculatedVacToProposal() {
            addItemToProposal('ASPİRATÖR', appState.currentCalcVac.name, appState.currentCalcVac.qty, appState.currentCalcVac.unitPrice);
        }
        function addCalculatedSterilToProposal() {
            addItemToProposal('STERİLİZASYON', appState.currentCalcSteril.name, appState.currentCalcSteril.qty, appState.currentCalcSteril.unitPrice);
        }

        function addItemToProposal(cat, name, qty, price) {
            appState.proposalItems.push({ cat, name, qty: parseInt(qty, 10), price: parseFloat(price) });
            renderProposalTable();
            showToast(`${name.substring(0, 32)}... teklife eklendi.`);
        }
        function removeProposalItem(idx) {
            appState.proposalItems.splice(idx, 1);
            renderProposalTable();
        }
        function updateProposalQty(idx, val) {
            appState.proposalItems[idx].qty = Math.max(1, parseInt(val || 1, 10));
            renderProposalTable();
        }
        function updateProposalPrice(idx, val) {
            appState.proposalItems[idx].price = Math.max(0, parseFloat(val || 0));
            renderProposalTable();
        }
        function clearProposalItems() {
            appState.proposalItems = [];
            renderProposalTable();
            showToast("Teklif tablosu temizlendi.");
        }
        function addCustomRow() {
            const cat = document.getElementById('custom-item-cat').value.trim() || 'EKİPMAN';
            const name = document.getElementById('custom-item-name').value.trim();
            const qty = parseInt(document.getElementById('custom-item-qty').value || 1, 10);
            const price = parseFloat(document.getElementById('custom-item-price').value || 0);
            if (!name) {
                showToast("Ürün adı yazın.");
                return;
            }
            addItemToProposal(cat.toUpperCase(), name.toUpperCase(), qty, price);
            document.getElementById('custom-item-name').value = '';
            document.getElementById('custom-item-price').value = '';
        }

        async function saveProposalToCrm() {
            const tok = localStorage.getItem('token');
            if (!tok) {
                showToast("CRM veritabanına kaydetmek için önce ana panelden giriş yapın.");
                return;
            }
            const customer = document.getElementById('prop-customer').value.trim();
            if (!customer) {
                showToast("Lütfen önce UNVAN (Müşteri / Hekim Adı) alanını doldurun.");
                return;
            }
            if (appState.proposalItems.length === 0) {
                showToast("Teklif tablosunda henüz ürün yok.");
                return;
            }
            let total = 0;
            const mainDevices = [];
            appState.proposalItems.forEach(it => {
                total += (it.qty * it.price);
                if (!it.name.trim().startsWith('↳')) {
                    mainDevices.push(`${it.qty}x ${it.name.substring(0, 35)}`);
                }
            });
            const agreed = document.getElementById('prop-agreed-price').value.trim();
            const city = document.getElementById('prop-city').value.trim();
            const notesText = `KlinikMatrix Teklifi (${city || 'Belirtilmedi'}) - Toplam: ${total.toLocaleString('tr-TR')} €${agreed ? ' | Anlaşılan: ' + agreed : ''}`;

            try {
                const res = await fetch('/api/interactions', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + tok
                    },
                    body: JSON.stringify({
                        date: new Date().toISOString().split('T')[0],
                        customer_name: customer,
                        devices: mainDevices.join(', ').substring(0, 120) || 'Klinik Paketi',
                        notes: notesText,
                        staff_name: 'HAKAN BEHRAMOĞLU',
                        offer_url: ''
                    })
                });
                if (res.ok) {
                    showToast("Teklif özeti CRM Müşteri Görüşmelerine kaydedildi!");
                } else {
                    showToast("Kayıt sırasında bir hata oluştu.");
                }
            } catch (e) {
                showToast("Bağlantı hatası oluştu.");
            }
        }

        function renderProposalTable() {
            const tbody = document.getElementById('proposal-tbody');
            tbody.innerHTML = '';
            let grandTotal = 0;

            if (appState.proposalItems.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" class="py-8 text-center text-gray-500 text-xs">Teklif tablosu boş. Ünit Föyü veya diğer sekmelerden ürün ekleyin.</td></tr>`;
            }

            appState.proposalItems.forEach((it, idx) => {
                const sub = it.qty * it.price;
                grandTotal += sub;
                const tr = document.createElement('tr');
                tr.className = 'hover:bg-white/5 transition-colors';
                tr.innerHTML = `
                    <td class="py-2.5 px-4 font-mono text-xs font-bold text-sky-400 whitespace-nowrap">${it.cat}</td>
                    <td class="py-2.5 px-4 text-gray-200 text-xs leading-relaxed">${it.name}</td>
                    <td class="py-2.5 px-4 text-center">
                        <input type="number" value="${it.qty}" min="1" onchange="updateProposalQty(${idx}, this.value)" class="w-12 bg-gray-900 border border-white/15 rounded py-1 text-center text-white font-bold text-xs">
                    </td>
                    <td class="py-2.5 px-4 text-right">
                        <input type="number" value="${it.price}" step="10" onchange="updateProposalPrice(${idx}, this.value)" class="w-20 bg-gray-900 border border-white/15 rounded py-1 px-2 text-right text-gray-200 font-mono text-xs">
                    </td>
                    <td class="py-2.5 px-4 text-right font-mono font-bold text-white whitespace-nowrap">${sub.toLocaleString('tr-TR', { minimumFractionDigits: 2 })} €</td>
                    <td class="py-2.5 px-2 text-center no-print">
                        <button onclick="removeProposalItem(${idx})" class="text-gray-500 hover:text-rose-400 p-1">✕</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });

            const fmt = grandTotal.toLocaleString('tr-TR', { minimumFractionDigits: 2 }) + ' €';
            document.getElementById('proposal-total-cell').textContent = fmt;
            document.getElementById('header-total-badge').textContent = grandTotal.toLocaleString('tr-TR') + ' €';
            document.getElementById('tab-proposal-count').textContent = appState.proposalItems.length;
        }

        function getMannasLogoDataUrl() {
            const canvas = document.createElement('canvas');
            canvas.width = 620;
            canvas.height = 230;
            const ctx = canvas.getContext('2d');

            ctx.clearRect(0, 0, canvas.width, canvas.height);

            const grad = ctx.createLinearGradient(20, 200, 200, 20);
            grad.addColorStop(0, '#f97316');
            grad.addColorStop(0.5, '#ea580c');
            grad.addColorStop(1, '#f97316');

            ctx.beginPath();
            ctx.strokeStyle = grad;
            ctx.lineWidth = 26;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            ctx.moveTo(192, 152);
            ctx.bezierCurveTo(144, 216, 24, 192, 24, 92);
            ctx.bezierCurveTo(24, 20, 88, 8, 124, 48);
            ctx.bezierCurveTo(150, 76, 166, 76, 192, 48);
            ctx.bezierCurveTo(228, 8, 280, 24, 296, 76);
            ctx.stroke();

            ctx.font = '900 70px "Inter", "Arial Black", sans-serif';
            ctx.fillStyle = '#ea580c';
            ctx.textBaseline = 'alphabetic';
            ctx.fillText('MANNAS', 228, 154);

            ctx.font = '700 36px "Inter", Arial, sans-serif';
            ctx.fillStyle = '#f97316';
            ctx.letterSpacing = '6px';
            ctx.fillText('DENTAL', 232, 204);

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

            let total = 0;
            let rowsHtml = '';

            if (appState.proposalItems.length === 0) {
                rowsHtml = `<tr><td colspan="5" style="padding: 16px; text-align: center; color: #6b7280; font-size: 11px; border: 1px solid #cbd5e1;">Teklif tablosu boş.</td></tr>`;
            } else {
                appState.proposalItems.forEach(it => {
                    const sub = it.qty * it.price;
                    total += sub;
                    rowsHtml += `
                        <tr>
                            <td style="padding: 7px 9px; border: 1px solid #cbd5e1; font-weight: 700; font-size: 10px; color: #0c4a6e; white-space: nowrap;">${it.cat}</td>
                            <td style="padding: 7px 9px; border: 1px solid #cbd5e1; font-size: 10px; color: #111827; line-height: 1.3;">${it.name}</td>
                            <td style="padding: 7px 9px; border: 1px solid #cbd5e1; text-align: center; font-weight: 700; font-size: 10.5px; color: #111827;">${it.qty}</td>
                            <td style="padding: 7px 9px; border: 1px solid #cbd5e1; text-align: right; font-size: 10.5px; color: #111827; white-space: nowrap;">${it.price.toLocaleString('tr-TR', { minimumFractionDigits: 2 })} €</td>
                            <td style="padding: 7px 9px; border: 1px solid #cbd5e1; text-align: right; font-weight: 700; font-size: 10.5px; color: #111827; white-space: nowrap;">${sub.toLocaleString('tr-TR', { minimumFractionDigits: 2 })} €</td>
                        </tr>
                    `;
                });
            }

            const logoPng = getMannasLogoDataUrl();

            return `
                <div style="font-family: 'Inter', Arial, sans-serif; color: #111827; background: #ffffff;">
                    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid #ea580c; padding-bottom: 10px; margin-bottom: 12px;">
                        <div style="display: flex; align-items: center; gap: 12px;">
                            <img src="${logoPng}" style="width: 155px; height: auto;" alt="Mannas Dental">
                            <div>
                                <div style="font-size: 13.5px; font-weight: 800; color: #0f172a;">MANNAS DİŞ DEPOSU TİCARET ve SANAYİ LİMİTED ŞİRKETİ</div>
                                <div style="font-size: 9.5px; color: #4b5563; margin-top: 1px;">STERN WEBER • MYRAY • MGF • TÜRKİYE DİSTRİBÜTÖRÜ</div>
                                <div style="font-size: 9px; color: #64748b;">Oğuzhan Cad. No:39 Fındıkzade-Fatih / İSTANBUL • Tel: 0212 635 77 26 pbx</div>
                            </div>
                        </div>
                        <div style="text-align: right;">
                            <div style="background: #ea580c; color: #ffffff; font-weight: 800; font-size: 12px; padding: 4px 10px; border-radius: 6px; display: inline-block;">${subject}</div>
                            <div style="font-size: 10.5px; font-weight: 700; color: #1f2937; margin-top: 4px;">TARİH: ${dateVal}</div>
                        </div>
                    </div>

                    <table style="width: 100%; border-collapse: collapse; margin-bottom: 12px; font-size: 10.5px;">
                        <tr>
                            <td style="padding: 5px 8px; border: 1px solid #cbd5e1; background: #f8fafc; font-weight: 700; width: 18%;">UNVAN:</td>
                            <td style="padding: 5px 8px; border: 1px solid #cbd5e1; font-weight: 700; width: 32%;">${customer}</td>
                            <td style="padding: 5px 8px; border: 1px solid #cbd5e1; background: #f8fafc; font-weight: 700; width: 18%;">TC / VERGİ NO:</td>
                            <td style="padding: 5px 8px; border: 1px solid #cbd5e1; width: 32%;">${tax}</td>
                        </tr>
                        <tr>
                            <td style="padding: 5px 8px; border: 1px solid #cbd5e1; background: #f8fafc; font-weight: 700;">ADRES / ŞEHİR:</td>
                            <td style="padding: 5px 8px; border: 1px solid #cbd5e1;">${city}</td>
                            <td style="padding: 5px 8px; border: 1px solid #cbd5e1; background: #f8fafc; font-weight: 700;">CEP TEL:</td>
                            <td style="padding: 5px 8px; border: 1px solid #cbd5e1;">${phone}</td>
                        </tr>
                    </table>

                    <table style="width: 100%; border-collapse: collapse; margin-bottom: 12px;">
                        <thead>
                            <tr style="background: #0c4a6e; color: #ffffff; font-size: 10px; text-transform: uppercase;">
                                <th style="padding: 7px 9px; border: 1px solid #0c4a6e; text-align: left; width: 14%;">ÜRÜNLER</th>
                                <th style="padding: 7px 9px; border: 1px solid #0c4a6e; text-align: left; width: 52%;">ÜRÜN ADI</th>
                                <th style="padding: 7px 9px; border: 1px solid #0c4a6e; text-align: center; width: 8%;">ADET</th>
                                <th style="padding: 7px 9px; border: 1px solid #0c4a6e; text-align: right; width: 13%;">BİRİM FİYATI</th>
                                <th style="padding: 7px 9px; border: 1px solid #0c4a6e; text-align: right; width: 13%;">TUTARI</th>
                            </tr>
                        </thead>
                        <tbody>${rowsHtml}</tbody>
                        <tfoot>
                            <tr style="background: #f1f5f9;">
                                <td colspan="2" style="padding: 8px 9px; border: 1px solid #cbd5e1; font-weight: 700; font-size: 10px; color: #b45309;">
                                    FİYATLARIMIZA KDV DAHİL DEĞİLDİR
                                </td>
                                <td colspan="2" style="padding: 8px 9px; border: 1px solid #cbd5e1; text-align: right; font-weight: 800; font-size: 11px;">
                                    TOPLAM:
                                </td>
                                <td style="padding: 8px 9px; border: 1px solid #cbd5e1; text-align: right; font-weight: 800; font-size: 12px; color: #0284c7; white-space: nowrap;">
                                    ${total.toLocaleString('tr-TR', { minimumFractionDigits: 2 })} €
                                </td>
                            </tr>
                        </tfoot>
                    </table>

                    <table style="width: 100%; border-collapse: collapse; margin-bottom: 12px; font-size: 10px;">
                        <tr>
                            <td style="padding: 5px 8px; border: 1px solid #cbd5e1; background: #f8fafc; font-weight: 800; width: 34%;">✔ TOPLAM ANLAŞILAN FİYAT:</td>
                            <td style="padding: 5px 8px; border: 1px solid #cbd5e1; font-weight: 800; color: #047857;">${agreed}</td>
                        </tr>
                        <tr>
                            <td style="padding: 5px 8px; border: 1px solid #cbd5e1; background: #f8fafc; font-weight: 800;">✔ KDV TUTARI:</td>
                            <td style="padding: 5px 8px; border: 1px solid #cbd5e1;">${vat}</td>
                        </tr>
                        <tr>
                            <td style="padding: 5px 8px; border: 1px solid #cbd5e1; background: #f8fafc; font-weight: 800;">✔ TOPLAM PEŞİN VERİLECEK:</td>
                            <td style="padding: 5px 8px; border: 1px solid #cbd5e1;">${down}</td>
                        </tr>
                        <tr>
                            <td style="padding: 5px 8px; border: 1px solid #cbd5e1; background: #f8fafc; font-weight: 800;">✔ VADE SAYISI VE RAKAMI:</td>
                            <td style="padding: 5px 8px; border: 1px solid #cbd5e1;">${inst}</td>
                        </tr>
                        <tr>
                            <td style="padding: 5px 8px; border: 1px solid #cbd5e1; background: #f8fafc; font-weight: 800;">✔ İLK SENET ÖDEME TARİHİ:</td>
                            <td style="padding: 5px 8px; border: 1px solid #cbd5e1;">${firstDate}</td>
                        </tr>
                    </table>

                    <div style="border: 1px solid #cbd5e1; background: #f8fafc; padding: 8px 10px; border-radius: 6px; margin-bottom: 12px; font-size: 9.5px; font-weight: 700; color: #1e293b;">
                        NOT: TESLİMAT ÜRÜNLER HAZIR STOKTADIR YER HAZIR BİLGİSİ GELMESİNE MÜTEAKİBEN 2 HAFTA İÇERİSİNDE PROGRAMA ALINACAKTIR.
                    </div>

                    <div style="display: flex; justify-content: space-between; align-items: flex-end; border-top: 2px solid #e2e8f0; padding-top: 10px; font-size: 9px; color: #475569;">
                        <div>
                            <div style="font-weight: 800; color: #0f172a; font-size: 10px;">MANNAS DİŞ DEPOSU TİCARET ve SANAYİ LİMİTED ŞİRKETİ</div>
                            <div>Oğuzhan Cad. No:39 Fındıkzade-Fatih İSTANBUL • Beyazıt VD: 612001724 • Mersis: 0612001722400016</div>
                            <div>Tel: 0212 635 77 26 pbx • www.mannas.com.tr • satis@mannas.com.tr</div>
                        </div>
                        <div style="text-align: right; border: 1px solid #bae6fd; background: #f0f9ff; padding: 6px 12px; border-radius: 6px;">
                            <div style="font-weight: 800; font-size: 11px; color: #0c4a6e;">HAKAN BEHRAMOĞLU</div>
                            <div style="font-weight: 700; font-size: 10px; color: #0284c7;">İŞ GELİŞTİRME UZMANI</div>
                            <div>0090 (546) 291 82 43 • hakan.behramoglu@mannas.com.tr</div>
                        </div>
                    </div>
                </div>
            `;
        }

        function openOfficialPrintModal() {
            const paper = document.getElementById('a4-printable-paper');
            paper.innerHTML = buildOfficialA4Html();
            document.getElementById('a4-preview-modal').classList.remove('hidden');
        }
        function closeOfficialPrintModal() {
            document.getElementById('a4-preview-modal').classList.add('hidden');
        }

        function downloadDirectPdf() {
            const paper = document.getElementById('a4-printable-paper');
            paper.innerHTML = buildOfficialA4Html();
            const modal = document.getElementById('a4-preview-modal');
            const wasHidden = modal.classList.contains('hidden');
            if (wasHidden) modal.classList.remove('hidden');

            const customerRaw = document.getElementById('prop-customer').value.trim() || 'Musteri';
            const safeName = customerRaw.replace(/[^a-zA-Z0-9ğüşıöçĞÜŞİÖÇ\\s_-]/g, '').replace(/\\s+/g, '_');
            const fileName = `KlinikMatrix_Teklif_${safeName}.pdf`;

            showToast('PDF hazırlanıyor...');

            if (typeof html2pdf !== 'undefined') {
                const opt = {
                    margin: [8, 8, 8, 8],
                    filename: fileName,
                    image: { type: 'jpeg', quality: 0.98 },
                    html2canvas: { scale: 2, useCORS: true, backgroundColor: '#ffffff' },
                    jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
                };
                html2pdf().set(opt).from(paper).save().then(() => {
                    showToast('PDF teklif dosyası indirildi!');
                }).catch(() => {
                    triggerPopupPrint();
                });
            } else {
                triggerPopupPrint();
            }
        }

        function triggerPopupPrint() {
            const htmlContent = buildOfficialA4Html();
            const win = window.open('', '_blank', 'width=900,height=1000');
            if (win) {
                win.document.open();
                win.document.write(`
                    <!DOCTYPE html><html><head><meta charset="UTF-8"><title>Teklif Yazdır</title>
                    <style>@page { size: A4 portrait; margin: 8mm; } body { margin: 0; background: #fff; }</style>
                    </head><body>${htmlContent}<script>window.onload=function(){setTimeout(function(){window.print();},300);};<\\/script></body></html>
                `);
                win.document.close();
            } else {
                window.print();
            }
        }

        function copyOfficialProposal() {
            const customer = document.getElementById('prop-customer').value || '-';
            const dateVal = document.getElementById('prop-date').value || new Date().toLocaleDateString('tr-TR');
            let total = 0;
            let txt = `MANNAS DİŞ DEPOSU - FİYAT TEKLİFİ\\nUNVAN: ${customer} | TARİH: ${dateVal}\\n----------------------------------\\n`;
            appState.proposalItems.forEach((it, i) => {
                const sub = it.qty * it.price;
                total += sub;
                txt += `${i + 1}. [${it.cat}] ${it.name} (${it.qty} x ${it.price.toLocaleString('tr-TR')} € = ${sub.toLocaleString('tr-TR')} €)\\n`;
            });
            txt += `----------------------------------\\nTOPLAM: ${total.toLocaleString('tr-TR', { minimumFractionDigits: 2 })} € (KDV Hariç)\\n`;
            txt += `Hakan BEHRAMOĞLU (0546 291 82 43)\\n`;

            const ta = document.createElement('textarea');
            ta.value = txt;
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
            showToast("Teklif metni panoya kopyalandı!");
        }

        function resetToBlankTemplate() {
            document.getElementById('prop-customer').value = '';
            document.getElementById('prop-city').value = '';
            document.getElementById('prop-phone').value = '';
            document.getElementById('prop-tax').value = '';
            document.getElementById('prop-agreed-price').value = '';
            document.getElementById('prop-vat').value = '';
            document.getElementById('prop-downpayment').value = '';
            document.getElementById('prop-installments').value = '';
            document.getElementById('prop-first-date').value = '';
            appState.proposalItems = [];
            renderProposalTable();
            showToast("Yeni boş teklif şablonu hazır.");
        }

        function showToast(msg) {
            const box = document.getElementById('toast-box');
            document.getElementById('toast-text').textContent = msg;
            box.classList.remove('hidden');
            setTimeout(() => { box.classList.add('hidden'); }, 3500);
        }

        window.onload = function() {
            populateTdbOptionsDropdown();
            renderColorSwatches();
            selectUnitModel('S200');
            updateEngineeringCalc();
            resetToBlankTemplate();
        };
    </script>
</body>
</html>"""

@app.get("/konfigurator", response_class=HTMLResponse)
def get_konfigurator():
    return KLINIK_MATRIX_STUDIO_HTML

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
                    <button onclick="switchTab('studio')" id="nav-studio" class="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-slate-800 hover:text-white transition">
                        <i class="fa-solid fa-wand-magic-sparkles w-5 text-orange-400"></i> Konfigüratör & Teklif
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
                <div class="grid grid-cols-3 gap-2.5 md:hidden">
                    <button onclick="switchTab('studio')" class="bg-orange-500 active:bg-orange-600 text-white py-3 px-3 rounded-xl font-bold text-xs shadow-sm flex items-center justify-center gap-1.5">
                        <i class="fa-solid fa-wand-magic-sparkles text-sm"></i> Konfigüratör
                    </button>
                    <button onclick="toggleModal('modal-add-sale')" class="bg-blue-600 active:bg-blue-700 text-white py-3 px-3 rounded-xl font-bold text-xs shadow-sm flex items-center justify-center gap-1.5">
                        <i class="fa-solid fa-plus-circle text-sm"></i> Satış Ekle
                    </button>
                    <button onclick="toggleModal('modal-add-interaction')" class="bg-purple-600 active:bg-purple-700 text-white py-3 px-3 rounded-xl font-bold text-xs shadow-sm flex items-center justify-center gap-1.5">
                        <i class="fa-solid fa-comment-medical text-sm"></i> Not Ekle
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

            <!-- SECTION: KONFİGÜRATÖR & RESMİ TEKLİF STÜDYOSU -->
            <div id="section-studio" class="hidden space-y-3">
                <div class="flex flex-wrap items-center justify-between gap-2 bg-slate-900 text-white px-4 py-3 rounded-2xl shadow-sm">
                    <div class="flex items-center gap-2.5">
                        <i class="fa-solid fa-wand-magic-sparkles text-orange-400 text-lg"></i>
                        <div>
                            <h2 class="text-sm sm:text-base font-bold leading-tight">KlinikMatrix Konfigürasyon & Resmi Teklif Stüdyosu</h2>
                            <p class="text-[11px] text-slate-400">Stern Weber • MyRay • MGF • Silverfox Canlı Föy ve V.03 PDF Teklif Motoru</p>
                        </div>
                    </div>
                    <a href="/konfigurator" target="_blank" class="bg-sky-500 hover:bg-sky-400 text-white text-xs font-bold px-3.5 py-2 rounded-xl transition flex items-center gap-1.5 shadow">
                        <i class="fa-solid fa-up-right-from-square"></i> Tam Ekran Aç
                    </a>
                </div>
                <div class="w-full rounded-3xl overflow-hidden border border-slate-800 shadow-2xl bg-[#090D16]" style="height: calc(100vh - 150px); min-height: 680px;">
                    <iframe id="studio-iframe" src="/konfigurator" class="w-full h-full border-0"></iframe>
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
        <button onclick="switchTab('studio')" id="bnav-studio" class="flex flex-col items-center gap-1 text-slate-400 w-full py-1">
            <i class="fa-solid fa-wand-magic-sparkles text-base"></i>
            <span class="text-[10px]">Stüdyo</span>
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
            ['dashboard', 'studio', 'sales', 'products', 'interactions', 'staff'].forEach(t => {
                const sec = document.getElementById("section-" + t);
                if (sec) sec.classList.add("hidden");
                
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