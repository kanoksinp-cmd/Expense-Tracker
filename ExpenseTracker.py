import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image

# 1. ตั้งค่าหน้าจอ
st.set_page_config(page_title="Trip Expense Splitter Pro", layout="wide")

# 2. ฟังก์ชันจัดการฐานข้อมูล (เพิ่มคอลัมน์ status)
DB_FILE = "trip_database.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS all_users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)')
    
    # เพิ่มคอลัมน์ status: 0 = ปกติ, 1 = อยู่ในถังขยะ
    try:
        cursor.execute('ALTER TABLE trips ADD COLUMN status INTEGER DEFAULT 0')
    except:
        pass # ถ้ามีคอลัมน์อยู่แล้วจะไม่ทำอะไร
    
    cursor.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, status INTEGER DEFAULT 0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, name TEXT, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, description TEXT, 
            amount REAL, payer_name TEXT, split_members TEXT, image_blob BLOB,
            FOREIGN KEY(trip_id) REFERENCES trips(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, 
            debtor TEXT, creditor TEXT, amount REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(trip_id) REFERENCES trips(id)
        )
    ''')
    conn.commit()
    conn.close()

def compress_image(uploaded_file):
    if uploaded_file is None: return None
    img = Image.open(uploaded_file)
    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
    img.thumbnail((800, 800))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=70)
    return buffer.getvalue()

init_db()

# --- 3. Sidebar ---
st.sidebar.header("⚙️ ระบบจัดการข้อมูล")

# 3.1 ลงทะเบียน User (เหมือนเดิม)
with st.sidebar.expander("👤 ลงทะเบียน User"):
    reg_name = st.sidebar.text_input("ชื่อผู้ใช้งาน:", key="reg_input").strip()
    if st.sidebar.button("ลงทะเบียน"):
        if reg_name:
            try:
                conn = get_db_connection()
                conn.execute("INSERT INTO all_users (name) VALUES (?)", (reg_name,))
                conn.commit()
                conn.close()
                st.rerun()
            except: st.sidebar.error("มีชื่อนี้แล้ว")

# 3.2 สร้างทริป (เหมือนเดิม)
new_trip_name = st.sidebar.text_input("➕ สร้างทริปใหม่:").strip()
if st.sidebar.button("บันทึกทริป"):
    if new_trip_name:
        try:
            conn = get_db_connection()
            conn.execute("INSERT INTO trips (name, status) VALUES (?, 0)", (new_trip_name,))
            conn.commit()
            conn.close()
            st.rerun()
        except: st.sidebar.error("ชื่อทริปซ้ำ")

# 3.3 เลือกทริป (เฉพาะที่ status = 0)
conn = get_db_connection()
trips_df = pd.read_sql_query("SELECT * FROM trips WHERE status = 0", conn)
trip_list = trips_df["name"].tolist() if not trips_df.empty else []

# --- 🗑️ ส่วนของถังขยะ (Recycle Bin) ---
st.sidebar.markdown("---")
with st.sidebar.expander("🗑️ ถังขยะ (ทริปที่ถูกลบ)"):
    deleted_trips = conn.execute("SELECT * FROM trips WHERE status = 1").fetchall()
    if not deleted_trips:
        st.write("ไม่มีทริปในถังขยะ")
    else:
        for dt in deleted_trips:
            col_name, col_back, col_del = st.columns([2, 1, 1])
            col_name.write(dt['name'])
            if col_back.button("🔄", key=f"restore_{dt['id']}", help="กู้คืน"):
                conn.execute("UPDATE trips SET status = 0 WHERE id = ?", (dt['id'],))
                conn.commit()
                st.rerun()
            if col_del.button("❌", key=f"pdel_{dt['id']}", help="ลบถาวร"):
                # ลบจริงทุกตาราง
                conn.execute("DELETE FROM settlements WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM expenses WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM members WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM trips WHERE id = ?", (dt['id'],))
                conn.commit()
                st.rerun()

if not trip_list:
    st.title("✈️ ระบบจัดการทริป")
    st.info("กรุณาสร้างทริปใหม่ หรือกู้คืนทริปจากถังขยะ")
    conn.close()
    st.stop()

st.sidebar.markdown("---")
current_trip = st.sidebar.selectbox("🗺️ เลือกทริปปัจจุบัน:", trip_list)
trip_id = conn.execute("SELECT id FROM trips WHERE name = ?", (current_trip,)).fetchone()["id"]

# ปุ่มย้ายไปถังขยะ (Soft Delete)
if st.sidebar.button("🗑️ ย้ายทริปนี้ไปถังขยะ"):
    conn.execute("UPDATE trips SET status = 1 WHERE id = ?", (trip_id,))
    conn.commit()
    st.rerun()

# 3.4 เพิ่มสมาชิก (เหมือนเดิม)
st.sidebar.subheader(f"👥 สมาชิกใน {current_trip}")
all_users = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
existing_members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
available_users = [u for u in all_users if u not in existing_members]

selected_u = st.sidebar.selectbox("ดึงเพื่อนเข้าทริป:", ["-- เลือก --"] + available_users)
if st.sidebar.button("ดึงเข้าทริป"):
    if selected_u != "-- เลือก --":
        conn.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, selected_u))
        conn.commit()
        st.rerun()
conn.close()

# --- ส่วน Tabs 1, 2, 3 (เหมือนเดิมจากโค้ดล่าสุด) ---
# ... (ก๊อปปี้ส่วน tab1, tab2, tab3 จากโค้ดก่อนหน้ามาวางต่อได้เลย)
