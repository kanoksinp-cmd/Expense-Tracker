import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image

st.set_page_config(page_title="Trip Expense Persistent Pro", layout="wide")

# --- 1. จัดการฐานข้อมูล (เพิ่มตาราง all_users) ---
DB_FILE = "trip_database.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # 1. ตารางลงทะเบียน User กลาง (ใหม่!)
    cursor.execute('CREATE TABLE IF NOT EXISTS all_users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)')
    # 2. ตารางทริป
    cursor.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)')
    # 3. ตารางสมาชิกในทริป (ดึงจาก all_users)
    cursor.execute('CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, name TEXT, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    # 4. ตารางค่าใช้จ่าย
    cursor.execute('CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, description TEXT, amount REAL, payer_name TEXT, split_members TEXT, image_blob BLOB, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    # 5. ตารางเก็บผลเคลียร์เงิน
    cursor.execute('CREATE TABLE IF NOT EXISTS settlements (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, debtor TEXT, creditor TEXT, amount REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    conn.commit()
    conn.close()

init_db()

# --- 2. ส่วนเมนู Sidebar ---
st.sidebar.header("⚙️ ระบบจัดการข้อมูลหลัก")

# 2.1 หน้าลงทะเบียน User (ทำครั้งเดียวใช้ได้ทุกทริป)
with st.sidebar.expander("👤 ลงทะเบียน User ใหม่"):
    reg_name = st.text_input("ชื่อเล่น/ชื่อจริง (ไม่ต้องมีรหัส):").strip()
    if st.button("ลงทะเบียน"):
        if reg_name:
            try:
                conn = get_db_connection()
                conn.execute("INSERT INTO all_users (name) VALUES (?)", (reg_name,))
                conn.commit()
                conn.close()
                st.success(f"ลงทะเบียนคุณ {reg_name} แล้ว")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("ชื่อนี้มีในระบบแล้ว")
        else:
            st.warning("กรุณาใส่ชื่อ")

# 2.2 สร้างทริป
st.sidebar.markdown("---")
new_trip = st.sidebar.text_input("➕ สร้างทริปใหม่:").strip()
if st.sidebar.button("บันทึกทริป"):
    if new_trip:
        try:
            conn = get_db_connection()
            conn.execute("INSERT INTO trips (name) VALUES (?)", (new_trip,))
            conn.commit()
            conn.close()
            st.sidebar.success("สร้างทริปสำเร็จ!")
            st.rerun()
        except: st.sidebar.error("ชื่อทริปซ้ำ")

# 2.3 เลือกทริป
conn = get_db_connection()
trips_df = pd.read_sql_query("SELECT * FROM trips", conn)
trip_list = trips_df["name"].tolist() if not trips_df.empty else []

if not trip_list:
    st.title("✈️ ระบบจัดการทริป")
    st.info("เริ่มต้นโดยการลงทะเบียน User และสร้างทริปที่เมนูซ้ายมือครับ")
    conn.close()
    st.stop()

current_trip_name = st.sidebar.selectbox("🗺️ เลือกทริปที่จะจัดการ:", trip_list)
trip_id = conn.execute("SELECT id FROM trips WHERE name = ?", (current_trip_name,)).fetchone()["id"]

# 2.4 เพิ่มสมาชิกเข้าทริป (ดึงจาก User ที่ลงทะเบียนไว้)
st.sidebar.markdown("---")
st.sidebar.subheader(f"👥 สมาชิกใน {current_trip_name}")

# ดึงรายชื่อ User ทั้งหมดในระบบที่ยังไม่ได้อยู่ในทริปนี้
all_registered_users = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
existing_members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
available_to_add = [u for u in all_registered_users if u not in existing_members]

selected_user = st.sidebar.selectbox("เลือก User เพื่อดึงเข้าทริป:", ["-- เลือกรายชื่อ --"] + available_to_add)
if st.sidebar.button("ดึงเข้าทริป"):
    if selected_user != "-- เลือกรายชื่อ --":
        conn.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, selected_user))
        conn.commit()
        st.sidebar.success(f"เพิ่ม {selected_user} เข้าทริปแล้ว")
        st.rerun()

if existing_members:
    st.sidebar.write("**สมาชิกปัจจุบัน:** " + ", ".join(existing_members))
conn.close()

# --- 3. หน้าแสดงผล (Tabs) ---
if not existing_members:
    st.warning("⚠️ กรุณาเลือกสมาชิกเข้าทริปก่อนเริ่มบันทึกค่าใช้จ่าย")
    st.stop()

st.title(f"🗺️ ทริป: {current_trip_name}")
tab1, tab2, tab3 = st.tabs(["📝 บันทึกค่าใช้จ่าย", "📊 ประวัติบิล & แก้ไข", "💰 คำนวณสรุปโอนเงิน"])

# (เนื้อหาใน Tab 1, 2, 3 ใช้ Logic เดิมที่คำนวณ Net Balance และการโอนเงินที่สั้นที่สุด)
# ตัวแปรสมาชิกที่ใช้ในแอปจะใช้: existing_members

# --- TAB 1: บันทึกบิล ---
with tab1:
    with st.form("add_exp"):
        desc = st.text_input("รายการ:")
        amt = st.number_input("เงินรวม:", min_value=0.0)
        payer = st.selectbox("คนสำรองจ่าย:", existing_members)
        st.write("คนช่วยหาร:")
        split_to = [m for m in existing_members if st.checkbox(m, value=True, key=f"split_{m}")]
        file = st.file_uploader("สลิป:", type=['jpg','png','jpeg'])
        if st.form_submit_button("บันทึก"):
            if desc and amt > 0 and split_to:
                blob = file.read() if file else None
                conn = get_db_connection()
                conn.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?,?,?,?,?,?)",
                             (trip_id, desc, amt, payer, ",".join(split_to), blob))
                conn.commit()
                conn.close()
                st.success("บันทึกบิลแล้ว")
                st.rerun()

# --- TAB 2 & 3: (Logic คำนวณรวบยอด Net Balance ตามเดิมที่เคยส่งให้ก่อนหน้านี้) ---
# ... (ส่วน Tab 2 และ Tab 3 จะใช้ข้อมูลจาก existing_members ในการคำนวณเหมือนเดิมทุกประการ)
