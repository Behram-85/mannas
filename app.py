import os
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse
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
    # Render veya Neon kimi zaman "postgres://" verir, psycopg2 "postgresql://" bekler
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    import sqlite3

SECRET_KEY = "mannas-super-secret-jwt-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crm_database.db")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/token")
app = FastAPI(title="Dental CRM & Satış Takip Portalı")

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
        # PostgreSQL için ? yerine %s dönüştürmesi
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
        notes TEXT
    )''', commit=True)

    # Varsayılan Admin
    user = execute_query("SELECT id FROM users WHERE username = ?", ("admin",), fetch_one=True)
    if not user:
        execute_query("INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                      ("admin", hash_password("admin123"), "Sistem Yöneticisi", "Admin"), commit=True)
    else:
        execute_query("UPDATE users SET password_hash = ? WHERE username = 'admin'",
                      (hash_password("admin123"),), commit=True)

    # Tohum veriler: Personel
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

    # Tohum veriler: Ürünler
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
            ("MY RAY", "SEFALOMETRİ SENSÖR ve ATACHMAN", 8000.0, 4),
            ("MY RAY", "XVS SENSÖR RVG SIZE 1", 2450.0, 10),
            ("MY RAY", "XVS SENSÖR RVG SIZE 2", 2850.0, 2)
            
        ]
        for item in seed_products:
            execute_query("INSERT INTO products (brand, model, price, stock) VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING", item, commit=True)

    # Tohum veriler: Satışlar
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
        if username is None:
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
    execute_query("INSERT INTO interactions (date, customer_name, devices, notes) VALUES (?, ?, ?, ?)",
                  (item.date, item.customer_name, item.devices, item.notes), commit=True)
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def index():
    return """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dental Satış & CRM Yönetim Paneli</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>.sidebar-active { background-color: #1e293b; border-left: 4px solid #3b82f6; }</style>
</head>
<body class="bg-slate-50 text-slate-900 min-h-screen flex flex-col font-sans">
    <div id="login-modal" class="fixed inset-0 bg-slate-900/80 backdrop-blur-sm z-50 flex items-center justify-center">
        <div class="bg-white p-8 rounded-2xl shadow-2xl w-full max-w-md border border-slate-100">
            <div class="text-center mb-6">
                <div class="inline-flex items-center justify-center w-14 h-14 bg-blue-100 text-blue-600 rounded-2xl mb-3">
                    <i class="fa-solid fa-tooth text-2xl"></i>
                </div>
                <h2 class="text-2xl font-bold tracking-tight text-slate-800">Dental CRM Portalı</h2>
                <p class="text-sm text-slate-500 mt-1">Lütfen hesabınıza giriş yapın</p>
            </div>
            <div id="login-error" class="hidden mb-4 p-3 bg-red-50 border border-red-200 text-red-600 text-xs rounded-lg font-medium"></div>
            <form id="login-form" onsubmit="handleLogin(event)" class="space-y-4">
                <div>
                    <label class="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1">Kullanıcı Adı</label>
                    <input type="text" id="username" value="admin" required class="w-full px-4 py-2.5 rounded-lg border border-slate-300 focus:ring-2 focus:ring-blue-500 focus:outline-none text-sm">
                </div>
                <div>
                    <label class="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1">Şifre</label>
                    <input type="password" id="password" value="admin123" required class="w-full px-4 py-2.5 rounded-lg border border-slate-300 focus:ring-2 focus:ring-blue-500 focus:outline-none text-sm">
                </div>
                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2.5 rounded-lg text-sm shadow-md transition duration-200">Giriş Yap</button>
            </form>
        </div>
    </div>

    <div id="app" class="flex-1 flex flex-row hidden min-h-screen">
        <aside class="w-64 bg-slate-900 text-slate-300 flex flex-col justify-between flex-shrink-0">
            <div>
                <div class="px-6 py-6 border-b border-slate-800 flex items-center gap-3">
                    <i class="fa-solid fa-tooth text-blue-500 text-2xl"></i>
                    <div>
                        <div class="font-bold text-white text-base leading-tight">DENTAL PORTAL</div>
                        <div class="text-[11px] text-slate-400 font-medium">Satış & Stok Yönetimi</div>
                    </div>
                </div>
                <nav class="p-4 space-y-1 text-sm font-medium">
                    <button onclick="switchTab('dashboard')" id="nav-dashboard" class="w-full flex items-center gap-3 px-4 py-3 rounded-lg hover:bg-slate-800 sidebar-active text-white transition">
                        <i class="fa-solid fa-chart-pie w-5 text-blue-400"></i> Gösterge Paneli
                    </button>
                    <button onclick="switchTab('sales')" id="nav-sales" class="w-full flex items-center gap-3 px-4 py-3 rounded-lg hover:bg-slate-800 hover:text-white transition">
                        <i class="fa-solid fa-receipt w-5 text-emerald-400"></i> Satışlar
                    </button>
                    <button onclick="switchTab('products')" id="nav-products" class="w-full flex items-center gap-3 px-4 py-3 rounded-lg hover:bg-slate-800 hover:text-white transition">
                        <i class="fa-solid fa-boxes-stacked w-5 text-amber-400"></i> Ürünler & Stok
                    </button>
                    <button onclick="switchTab('interactions')" id="nav-interactions" class="w-full flex items-center gap-3 px-4 py-3 rounded-lg hover:bg-slate-800 hover:text-white transition">
                        <i class="fa-solid fa-comments w-5 text-purple-400"></i> Görüşmeler
                    </button>
                    <button onclick="switchTab('staff')" id="nav-staff" class="w-full flex items-center gap-3 px-4 py-3 rounded-lg hover:bg-slate-800 hover:text-white transition">
                        <i class="fa-solid fa-id-card-clip w-5 text-sky-400"></i> Ekip / Personel
                    </button>
                </nav>
            </div>
            <div class="p-4 border-t border-slate-800 text-xs">
                <div class="flex items-center justify-between mb-3 px-2">
                    <span id="user-display" class="font-medium text-slate-300">Yönetici</span>
                    <span class="bg-blue-900/60 text-blue-300 px-2 py-0.5 rounded text-[10px] font-semibold uppercase">Admin</span>
                </div>
                <button onclick="logout()" class="w-full py-2 px-3 bg-red-950/40 hover:bg-red-900/60 text-red-300 border border-red-900/50 rounded-lg flex items-center justify-center gap-2 transition">
                    <i class="fa-solid fa-right-from-bracket"></i> Çıkış Yap
                </button>
            </div>
        </aside>

        <main class="flex-1 p-8 overflow-y-auto">
            <div id="section-dashboard" class="space-y-6">
                <div class="flex items-center justify-between">
                    <h1 class="text-2xl font-bold text-slate-800">Genel Durum Paneli</h1>
                    <span class="text-xs text-slate-500 bg-white border px-3 py-1.5 rounded-lg shadow-sm font-medium">Bulut Veritabanı Aktif</span>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-4 gap-5">
                    <div class="bg-white p-5 rounded-2xl shadow-sm border border-slate-200/80">
                        <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Toplam Ciro</span>
                        <div class="text-2xl font-extrabold text-slate-800 mt-2" id="kpi-revenue">€ 0,00</div>
                        <div class="text-xs text-emerald-600 mt-1 font-medium"><i class="fa-solid fa-arrow-trend-up"></i> Güncel ciro</div>
                    </div>
                    <div class="bg-white p-5 rounded-2xl shadow-sm border border-slate-200/80">
                        <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Satılan Cihaz Adedi</span>
                        <div class="text-2xl font-extrabold text-slate-800 mt-2" id="kpi-units">0</div>
                        <div class="text-xs text-slate-500 mt-1 font-medium">İşlem sayısı: <span id="kpi-count">0</span></div>
                    </div>
                    <div class="bg-white p-5 rounded-2xl shadow-sm border border-slate-200/80">
                        <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Depodaki Stok Adedi</span>
                        <div class="text-2xl font-extrabold text-amber-600 mt-2" id="kpi-stock">0</div>
                        <div class="text-xs text-slate-500 mt-1 font-medium"><span id="kpi-sku">0</span> farklı ürün modeli</div>
                    </div>
                    <div class="bg-white p-5 rounded-2xl shadow-sm border border-slate-200/80">
                        <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Aktif Satış Personeli</span>
                        <div class="text-2xl font-extrabold text-blue-600 mt-2" id="kpi-staff">5</div>
                        <div class="text-xs text-slate-500 mt-1 font-medium">Kadroda yer alan yetkililer</div>
                    </div>
                </div>

                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200/80">
                        <h3 class="font-bold text-slate-800 mb-4 text-sm">Personele Göre Ciro Dağılımı (€)</h3>
                        <canvas id="staffChart" height="240"></canvas>
                    </div>
                    <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200/80">
                        <h3 class="font-bold text-slate-800 mb-4 text-sm">Markalara Göre Satış Hacmi (€)</h3>
                        <canvas id="brandChart" height="240"></canvas>
                    </div>
                </div>
            </div>

            <div id="section-sales" class="hidden space-y-6">
                <div class="flex items-center justify-between">
                    <div>
                        <h1 class="text-2xl font-bold text-slate-800">Gerçekleşen Satışlar</h1>
                        <p class="text-xs text-slate-500 mt-0.5">Sisteme girilen tüm faturalı satış kayıtları</p>
                    </div>
                    <button onclick="toggleModal('modal-add-sale')" class="bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold px-4 py-2.5 rounded-lg shadow transition flex items-center gap-2">
                        <i class="fa-solid fa-plus"></i> Yeni Satış Ekle
                    </button>
                </div>
                <div class="bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-hidden">
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
                                <th class="p-4">Toplam Tutar</th>
                                <th class="p-4 text-center">İşlem</th>
                            </tr>
                        </thead>
                        <tbody id="sales-table-body" class="divide-y divide-slate-100 font-medium text-slate-700"></tbody>
                    </table>
                </div>
            </div>

            <div id="section-products" class="hidden space-y-6">
                <div class="flex items-center justify-between">
                    <div>
                        <h1 class="text-2xl font-bold text-slate-800">Ürün & Stok Yönetimi</h1>
                        <p class="text-xs text-slate-500 mt-0.5">Katalog fiyatları ve anlık stok adetleri</p>
                    </div>
                </div>
                <div class="bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-hidden">
                    <table class="w-full text-left text-xs">
                        <thead class="bg-slate-50 text-slate-500 font-semibold border-b uppercase text-[10px]">
                            <tr>
                                <th class="p-4">Marka</th>
                                <th class="p-4">Model Tanımı</th>
                                <th class="p-4">Liste Fiyatı (€)</th>
                                <th class="p-4">Depo Stok</th>
                                <th class="p-4">Durum</th>
                                <th class="p-4 text-center">İşlem</th>
                            </tr>
                        </thead>
                        <tbody id="products-table-body" class="divide-y divide-slate-100 font-medium text-slate-700"></tbody>
                    </table>
                </div>
            </div>

            <div id="section-interactions" class="hidden space-y-6">
                <div class="flex items-center justify-between">
                    <div>
                        <h1 class="text-2xl font-bold text-slate-800">Müşteri Görüşme Takibi</h1>
                        <p class="text-xs text-slate-500 mt-0.5">Müşteriler ile yapılan görüşme ve talepler</p>
                    </div>
                    <button onclick="toggleModal('modal-add-interaction')" class="bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold px-4 py-2.5 rounded-lg shadow transition flex items-center gap-2">
                        <i class="fa-solid fa-plus"></i> Görüşme Ekle
                    </button>
                </div>
                <div class="bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-hidden">
                    <table class="w-full text-left text-xs">
                        <thead class="bg-slate-50 text-slate-500 font-semibold border-b uppercase text-[10px]">
                            <tr>
                                <th class="p-4">Tarih</th>
                                <th class="p-4">Müşteri Adı</th>
                                <th class="p-4">Görüşülen Cihazlar</th>
                                <th class="p-4">Açıklama / Detaylar</th>
                            </tr>
                        </thead>
                        <tbody id="interactions-table-body" class="divide-y divide-slate-100 font-medium text-slate-700"></tbody>
                    </table>
                </div>
            </div>

            <div id="section-staff" class="hidden space-y-6">
                <h1 class="text-2xl font-bold text-slate-800">Personel Listesi</h1>
                <div class="bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-hidden">
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

    <div id="modal-add-sale" class="fixed inset-0 bg-slate-900/60 backdrop-blur-xs z-50 flex items-center justify-center hidden">
        <div class="bg-white p-6 rounded-2xl shadow-2xl w-full max-w-lg border">
            <h3 class="text-lg font-bold text-slate-800 mb-4">Yeni Satış Kaydı</h3>
            <form id="sale-form" onsubmit="submitSale(event)" class="space-y-3 text-xs">
                <div>
                    <label class="font-semibold text-slate-600">Tarih</label>
                    <input type="date" id="sale-date" required class="w-full p-2 border rounded-lg mt-1">
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Satış Yetkilisi</label>
                    <select id="sale-staff" required class="w-full p-2 border rounded-lg mt-1"></select>
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Müşteri / Kurum Adı</label>
                    <input type="text" id="sale-customer" required class="w-full p-2 border rounded-lg mt-1" placeholder="Örn: Dent Klinik">
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Müşteri Konumu (Şehir)</label>
                    <input type="text" id="sale-location" required class="w-full p-2 border rounded-lg mt-1" placeholder="Örn: İstanbul">
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Ürün Seçiniz</label>
                    <select id="sale-product" onchange="onProductSelect()" required class="w-full p-2 border rounded-lg mt-1"></select>
                </div>
                <div class="grid grid-cols-2 gap-3">
                    <div>
                        <label class="font-semibold text-slate-600">Birim Fiyat (€)</label>
                        <input type="number" step="0.01" id="sale-price" required class="w-full p-2 border rounded-lg mt-1">
                    </div>
                    <div>
                        <label class="font-semibold text-slate-600">Adet</label>
                        <input type="number" min="1" id="sale-qty" value="1" required class="w-full p-2 border rounded-lg mt-1">
                    </div>
                </div>
                <div class="flex justify-end gap-2 pt-4">
                    <button type="button" onclick="toggleModal('modal-add-sale')" class="px-4 py-2 border rounded-lg font-medium text-slate-600">İptal</button>
                    <button type="submit" class="px-5 py-2 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700">Kaydet</button>
                </div>
            </form>
        </div>
    </div>

    <div id="modal-add-interaction" class="fixed inset-0 bg-slate-900/60 backdrop-blur-xs z-50 flex items-center justify-center hidden">
        <div class="bg-white p-6 rounded-2xl shadow-2xl w-full max-w-lg border">
            <h3 class="text-lg font-bold text-slate-800 mb-4">Yeni Görüşme Notu</h3>
            <form id="interaction-form" onsubmit="submitInteraction(event)" class="space-y-3 text-xs">
                <div>
                    <label class="font-semibold text-slate-600">Tarih</label>
                    <input type="date" id="inter-date" required class="w-full p-2 border rounded-lg mt-1">
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Müşteri Adı</label>
                    <input type="text" id="inter-customer" required class="w-full p-2 border rounded-lg mt-1" placeholder="Dr. Adı veya Klinik">
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Görüşülen Cihazlar</label>
                    <input type="text" id="inter-devices" required class="w-full p-2 border rounded-lg mt-1" placeholder="Örn: S300, X5">
                </div>
                <div>
                    <label class="font-semibold text-slate-600">Açıklama / Detaylar</label>
                    <textarea id="inter-notes" rows="3" required class="w-full p-2 border rounded-lg mt-1" placeholder="Görüşme detayları..."></textarea>
                </div>
                <div class="flex justify-end gap-2 pt-4">
                    <button type="button" onclick="toggleModal('modal-add-interaction')" class="px-4 py-2 border rounded-lg font-medium text-slate-600">İptal</button>
                    <button type="submit" class="px-5 py-2 bg-purple-600 text-white rounded-lg font-semibold hover:bg-purple-700">Kaydet</button>
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
            document.getElementById("app").classList.remove("hidden");
            document.getElementById("user-display").textContent = localStorage.getItem("user_name") || "Yönetici";
            await Promise.all([loadStaff(), loadProducts(), loadDashboard(), loadSales(), loadInteractions()]);
        }

        function switchTab(tab) {
            ['dashboard', 'sales', 'products', 'interactions', 'staff'].forEach(t => {
                document.getElementById("section-" + t).classList.add("hidden");
                const nav = document.getElementById("nav-" + t);
                nav.classList.remove("sidebar-active", "text-white");
                nav.classList.add("hover:bg-slate-800");
            });
            document.getElementById("section-" + tab).classList.remove("hidden");
            const activeNav = document.getElementById("nav-" + tab);
            activeNav.classList.add("sidebar-active", "text-white");
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
                    datasets: [{ data: brandValues, backgroundColor: ['#0284c7', '#10b981', '#f59e0b', '#6366f1'] }]
                },
                options: { responsive: true }
            });
        }

        async function loadProducts() {
            const res = await authFetch("/api/products");
            rawProducts = await res.json();
            const tbody = document.getElementById("products-table-body");
            tbody.innerHTML = "";
            const select = document.getElementById("sale-product");
            select.innerHTML = "<option value=''>Seçiniz...</option>";

            rawProducts.forEach(p => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td class="p-4 font-bold text-slate-800">${p.brand}</td>
                    <td class="p-4">${p.model}</td>
                    <td class="p-4">${fmtEUR(p.price)}</td>
                    <td class="p-4"><span class="font-bold ${p.stock <= 2 ? 'text-rose-600' : 'text-slate-800'}">${p.stock}</span></td>
                    <td class="p-4">
                        ${p.stock > 0 
                            ? '<span class="bg-emerald-50 text-emerald-700 px-2 py-1 rounded text-[10px] font-semibold">Mevcut</span>' 
                            : '<span class="bg-rose-50 text-rose-700 px-2 py-1 rounded text-[10px] font-semibold">Tükendi</span>'}
                    </td>
                    <td class="p-4 text-center">
                        <button onclick="quickStockUpdate(${p.id}, ${p.price}, ${p.stock})" class="text-slate-400 hover:text-blue-600"><i class="fa-solid fa-pen-to-square"></i></button>
                    </td>
                `;
                tbody.appendChild(tr);

                const opt = document.createElement("option");
                opt.value = p.id;
                opt.textContent = `${p.brand} - ${p.model} (Stok: ${p.stock})`;
                select.appendChild(opt);
            });
        }

        function onProductSelect() {
            const id = document.getElementById("sale-product").value;
            const p = rawProducts.find(x => x.id == id);
            if (p) {
                document.getElementById("sale-price").value = p.price;
            }
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
            tbody.innerHTML = "";
            sales.forEach(s => {
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
                        <button onclick="deleteSale(${s.id})" class="text-slate-300 hover:text-red-600 transition"><i class="fa-solid fa-trash"></i></button>
                    </td>
                `;
                tbody.appendChild(tr);
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
            tbody.innerHTML = "";
            const select = document.getElementById("sale-staff");
            select.innerHTML = "";

            rawStaff.forEach(s => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td class="p-4 font-bold text-slate-800">${s.name}</td>
                    <td class="p-4"><span class="bg-slate-100 text-slate-700 px-2 py-0.5 rounded text-[11px]">${s.department}</span></td>
                    <td class="p-4 text-slate-500">${s.title}</td>
                `;
                tbody.appendChild(tr);

                const opt = document.createElement("option");
                opt.value = s.name;
                opt.textContent = s.name;
                select.appendChild(opt);
            });
            document.getElementById("kpi-staff").textContent = rawStaff.length;
        }

        async function loadInteractions() {
            const res = await authFetch("/api/interactions");
            const data = await res.json();
            const tbody = document.getElementById("interactions-table-body");
            tbody.innerHTML = "";
            if (data.length === 0) {
                tbody.innerHTML = `<tr><td colspan="4" class="p-4 text-center text-slate-400">Kayıtlı görüşme bulunmamaktadır.</td></tr>`;
                return;
            }
            data.forEach(i => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td class="p-4 text-slate-500">${i.date}</td>
                    <td class="p-4 font-bold text-slate-800">${i.customer_name}</td>
                    <td class="p-4 font-medium text-purple-700">${i.devices}</td>
                    <td class="p-4 text-slate-600">${i.notes}</td>
                `;
                tbody.appendChild(tr);
            });
        }

        async function submitInteraction(e) {
            e.preventDefault();
            const payload = {
                date: document.getElementById("inter-date").value,
                customer_name: document.getElementById("inter-customer").value,
                devices: document.getElementById("inter-devices").value,
                notes: document.getElementById("inter-notes").value
            };

            await authFetch("/api/interactions", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            toggleModal('modal-add-interaction');
            document.getElementById("interaction-form").reset();
            await loadInteractions();
        }
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
