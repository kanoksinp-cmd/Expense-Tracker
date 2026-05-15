import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image

st.set_page_config(page_title="Trip Expense Splitter Ultimate", layout="wide")

# --- 1. จัดการฐานข้อมูล (เพิ่มสถานะ is_deleted) ---
DB_FILE = "trip_database.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS all_users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)')
    # เพิ่มคอลัมน์ is_deleted ในตาราง trips (0 = ปกติ, 1 = อยู่ในถังขยะ)
    cursor.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, is_deleted INTEGER DEFAULT 0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, name TEXT, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, description TEXT, amount REAL, payer_name TEXT, split_members TEXT, image_blob BLOB, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS settlements (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, debtor TEXT, creditor TEXT, amount REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    conn.commit()
    conn.close()

init_db()

# --- 2. Sidebar: ศูนย์ควบคุม ---
st.sidebar.header("⚙️ ระบบจัดการข้อมูล")

# 2.1 ลงทะเบียน User
with st.sidebar.expander("👤 ลงทะเบียน User"):
    reg_name = st.text_input("ชื่อผู้ใช้งาน:").strip()
    if st.button("ลงทะเบียน"):
        if reg_name:
            try:
                conn = get_db_connection()
                conn.execute("INSERT INTO all_users (name) VALUES (?)", (reg_name,))
                conn.commit()
                conn.close()
                st.toast(f"ลงทะเบียนคุณ {reg_name} สำเร็จ!", icon='✅')
                st.rerun()
            except: st.sidebar.error("ชื่อนี้มีในระบบแล้ว")

# 2.2 สร้างทริป
st.sidebar.markdown("---")
new_t = st.sidebar.text_input("➕ สร้างทริปใหม่:").strip()
if st.sidebar.button("บันทึกทริป"):
    if new_t:
        try:
            conn = get_db_connection()
            conn.execute("INSERT INTO trips (name, is_deleted) VALUES (?, 0)", (new_t,))
            conn.commit()
            conn.close()
            st.toast(f"สร้างทริป {new_t} สำเร็จ!", icon='🗺️')
            st.rerun()
        except: st.sidebar.error("ชื่อทริปซ้ำ")

# 2.3 เลือกทริป (เฉพาะที่ยังไม่ถูกลบ)
conn = get_db_connection()
trips_df = pd.read_sql_query("SELECT * FROM trips WHERE is_deleted = 0", conn)
trip_list = trips_df["name"].tolist() if not trips_df.empty else []

# 2.4 ถังขยะ (Trash Bin)
with st.sidebar.expander("🗑️ ถังขยะ (ทริปที่ลบแล้ว)"):
    trash_df = pd.read_sql_query("SELECT * FROM trips WHERE is_deleted = 1", conn)
    if trash_df.empty:
        st.write("ถังขยะว่างเปล่า")
    else:
        for _, row in trash_df.iterrows():
            st.write(f"📁 {row['name']}")
            c1, c2 = st.columns(2)
            if c1.button("กู้คืน", key=f"res_{row['id']}"):
                conn.execute("UPDATE trips SET is_deleted = 0 WHERE id = ?", (row['id'],))
                conn.commit()
                st.toast(f"กู้คืนทริป {row['name']} แล้ว", icon='♻️')
                st.rerun()
            if c2.button("ลบทิ้งถาวร", key=f"pdel_{row['id']}"):
                conn.execute("DELETE FROM trips WHERE id = ?", (row['id'],))
                conn.execute("DELETE FROM expenses WHERE trip_id = ?", (row['id'],))
                conn.execute("DELETE FROM members WHERE trip_id = ?", (row['id'],))
                conn.commit()
                st.toast("ลบข้อมูลถาวรแล้ว", icon='🔥')
                st.rerun()

if not trip_list:
    st.title("✈️ ระบบจัดการทริป")
    st.info("กรุณาสร้างทริปที่เมนูซ้ายมือ")
    conn.close()
    st.stop()

current_trip = st.sidebar.selectbox("🗺️ เลือกทริปที่ต้องการจัดการ:", trip_list)
trip_id = conn.execute("SELECT id FROM trips WHERE name = ?", (current_trip,)).fetchone()["id"]

# 2.5 ลบทริป (ย้ายไปถังขยะ)
if st.sidebar.button("🗑️ ย้ายทริปนี้ไปถังขยะ"):
    conn.execute("UPDATE trips SET is_deleted = 1 WHERE id = ?", (trip_id,))
    conn.commit()
    st.toast("ย้ายไปที่ถังขยะแล้ว", icon='🗑️')
    st.rerun()

# 2.6 จัดการสมาชิก
all_users = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
existing_members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
available_users = [u for u in all_users if u not in existing_members]

selected_u = st.sidebar.selectbox("ดึงเพื่อนเข้าทริป:", ["-- เลือก --"] + available_users)
if st.sidebar.button("ดึงเข้าทริป"):
    if selected_u != "-- เลือก --":
        conn.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, selected_u))
        conn.commit()
        st.toast(f"เพิ่ม {selected_u} แล้ว")
        st.rerun()
conn.close()

# --- 3. ส่วนแสดงผลหลัก ---
if not existing_members:
    st.title(f"📍 ทริป: {current_trip}")
    st.warning("⚠️ กรุณาเลือกสมาชิกเข้าทริปก่อน")
    st.stop()

st.title(f"📍 ทริป: {current_trip}")
tab1, tab2, tab3 = st.tabs(["📝 บันทึกบิล", "📊 ประวัติและรูปภาพ", "💰 สรุปเคลียร์เงิน"])

# --- TAB 1: บันทึกบิล ---
with tab1:
    with st.form("add_bill", clear_on_submit=True):
        desc = st.text_input("รายการ:")
        amt = st.number_input("จำนวนเงิน:", min_value=0.0)
        payer = st.selectbox("คนจ่าย:", existing_members)
        st.write("คนหาร:")
        split_to = [m for m in existing_members if st.checkbox(m, value=True, key=f"a_{m}")]
        file = st.file_uploader("แนบสลิป (ถ้ามี):", type=['jpg','png','jpeg'])
        if st.form_submit_button("💾 บันทึก"):
            if desc and amt > 0:
                blob = file.read() if file else None
                conn = get_db_connection()
                conn.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?,?,?,?,?,?)",
                             (trip_id, desc, amt, payer, ",".join(split_to), blob))
                conn.commit()
                conn.close()
                st.toast("บันทึกสำเร็จ!", icon='✅')
                st.rerun()

# --- TAB 2: ประวัติและรูปภาพ (เพิ่มฟังก์ชันโหลดรูปทีหลัง) ---
with tab2:
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()
    
    for row in expenses:
        with st.expander(f"📌 {row['description']} - {row['amount']:,.2f} บาท"):
            c1, c2 = st.columns(2)
            with c1:
                if row['image_blob']:
                    st.image(row['image_blob'], caption="รูปสลิปปัจจุบัน", use_column_width=True)
                else:
                    st.info("🈚 ยังไม่มีรูปภาพสลิป")
            
            with c2:
                # ส่วนอัปโหลดรูปทีหลัง
                new_file = st.file_uploader("➕ อัปโหลด/เปลี่ยนรูปสลิป:", type=['jpg','png','jpeg'], key=f"up_{row['id']}")
                if st.button("💾 บันทึกรูปภาพ", key=f"btn_up_{row['id']}"):
                    if new_file:
                        conn = get_db_connection()
                        conn.execute("UPDATE expenses SET image_blob = ? WHERE id = ?", (new_file.read(), row['id']))
                        conn.commit()
                        conn.close()
                        st.toast("อัปเดตรูปภาพเรียบร้อย!", icon='📸')
                        st.rerun()
                
                st.markdown("---")
                if st.button("🗑️ ลบบิลนี้", key=f"del_{row['id']}"):
                    conn = get_db_connection()
                    conn.execute("DELETE FROM expenses WHERE id = ?", (row['id'],))
                    conn.commit()
                    conn.close()
                    st.toast("ลบรายการแล้ว")
                    st.rerun()

# --- TAB 3: สรุปเคลียร์เงิน (Logic เดิม) ---
with tab3:
    st.subheader("🤝 สรุปยอดโอนเงินรวบยอด")
    conn = get_db_connection()
    ex_rows = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()
    
    if not ex_rows:
        st.info("ไม่มีข้อมูล")
    else:
        net = {m: 0.0 for m in existing_members}
        for r in ex_rows:
            net[r['payer_name']] += r['amount']
            sl = r['split_members'].split(",")
            share = r['amount'] / len(sl)
            for m in sl: net[m] -= share
        
        # แสดงผลและบันทึกปิดทริป (เหมือนโค้ดก่อนหน้า)
        for m, b in net.items():
            if b > 0.01: st.success(f"{m} ได้คืน: {b:,.2f} บาท")
            if b < -0.01: st.error(f"{m} ต้องจ่าย: {abs(b):,.2f} บาท")
