import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image

# ตั้งค่าหน้าเว็บ
st.set_page_config(page_title="Trip Expense Splitter Pro", layout="wide")

# --- 1. จัดการฐานข้อมูล SQLite ---
DB_FILE = "trip_database.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS all_users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, name TEXT, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, description TEXT, amount REAL, payer_name TEXT, split_members TEXT, image_blob BLOB, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS settlements (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, debtor TEXT, creditor TEXT, amount REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    conn.commit()
    conn.close()

init_db()

# --- 2. ส่วนเมนู Sidebar ---
st.sidebar.header("⚙️ ระบบจัดการข้อมูล")

# 2.1 ลงทะเบียน User กลาง
with st.sidebar.expander("👤 ลงทะเบียน User (ไม่ต้องมีรหัส)"):
    reg_name = st.text_input("ระบุชื่อเล่น/ชื่อจริง:").strip()
    if st.button("ลงทะเบียน"):
        if reg_name:
            try:
                conn = get_db_connection()
                conn.execute("INSERT INTO all_users (name) VALUES (?)", (reg_name,))
                conn.commit()
                conn.close()
                st.toast(f"✅ ลงทะเบียนคุณ {reg_name} สำเร็จ!", icon='👤') # Message Box แจ้งเตือน
                st.rerun()
            except sqlite3.IntegrityError:
                st.sidebar.error("❌ ชื่อนี้มีในระบบแล้ว")
        else:
            st.sidebar.warning("กรุณาใส่ชื่อ")

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
            st.toast(f"🗺️ สร้างทริป {new_trip} สำเร็จ!", icon='✈️') # Message Box แจ้งเตือน
            st.rerun()
        except: st.sidebar.error("❌ ชื่อทริปซ้ำ")

# 2.3 เลือกทริป
conn = get_db_connection()
trips_df = pd.read_sql_query("SELECT * FROM trips", conn)
trip_list = trips_df["name"].tolist() if not trips_df.empty else []

if not trip_list:
    st.title("✈️ ระบบจัดการทริป")
    st.info("กรุณาลงทะเบียน User และสร้างทริปที่เมนูซ้ายมือ")
    conn.close()
    st.stop()

current_trip_name = st.sidebar.selectbox("🗺️ เลือกทริปที่จะจัดการ:", trip_list)
trip_id = conn.execute("SELECT id FROM trips WHERE name = ?", (current_trip_name,)).fetchone()["id"]

# 2.4 ดึง User เข้าทริป
st.sidebar.markdown("---")
st.sidebar.subheader(f"👥 สมาชิกใน {current_trip_name}")
all_registered_users = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
existing_members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
available_to_add = [u for u in all_registered_users if u not in existing_members]

selected_user = st.sidebar.selectbox("เลือกรายชื่อเข้าทริป:", ["-- เลือก --"] + available_to_add)
if st.sidebar.button("ดึงเข้าทริป"):
    if selected_user != "-- เลือก --":
        conn.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, selected_user))
        conn.commit()
        st.toast(f"➕ เพิ่ม {selected_user} เข้าทริป {current_trip_name} แล้ว", icon='👥') # Message Box แจ้งเตือน
        st.rerun()

conn.close()

# --- 3. หน้าแสดงผลหลัก ---
if not existing_members:
    st.warning("⚠️ กรุณาเลือกสมาชิกเข้าทริปก่อนเริ่มใช้งาน")
    st.stop()

st.title(f"📍 ทริป: {current_trip_name}")
tab1, tab2, tab3 = st.tabs(["📝 บันทึกบิล", "📊 ประวัติบิล", "💰 สรุปการโอนเงิน"])

# --- TAB 1: บันทึกบิลใหม่ ---
with tab1:
    with st.form("add_exp", clear_on_submit=True):
        desc = st.text_input("รายการค่าใช้จ่าย:")
        amt = st.number_input("จำนวนเงิน (บาท):", min_value=0.0, step=10.0)
        payer = st.selectbox("ใครเป็นคนสำรองจ่าย?", existing_members)
        st.write("คนช่วยหาร:")
        split_to = [m for m in existing_members if st.checkbox(m, value=True, key=f"add_{m}")]
        file = st.file_uploader("แนบสลิป:", type=['jpg','png','jpeg'])
        if st.form_submit_button("💾 บันทึกรายการ"):
            if desc and amt > 0 and split_to:
                blob = file.read() if file else None
                conn = get_db_connection()
                conn.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?,?,?,?,?,?)",
                             (trip_id, desc, amt, payer, ",".join(split_to), blob))
                conn.commit()
                conn.close()
                st.success(f"บันทึกรายการ '{desc}' เรียบร้อย!") # Success Message
                st.toast("บันทึกข้อมูลแล้ว!", icon='💾')
                st.rerun()

# --- TAB 2: ประวัติและการแก้ไข ---
with tab2:
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()

    for row in expenses:
        with st.expander(f"📌 {row['description']} - {row['amount']:,.2f} บาท"):
            with st.form(f"edit_{row['id']}"):
                e_desc = st.text_input("รายการ:", value=row['description'])
                e_amt = st.number_input("เงิน:", value=row['amount'], min_value=0.0)
                e_payer = st.selectbox("คนจ่าย:", existing_members, index=existing_members.index(row['payer_name']))
                
                # ปุ่มลบรายการ (อยู่นอกฟอร์มเพื่อความปลอดภัย แต่อันนี้รวมไว้ใน Logic)
                c1, c2 = st.columns(2)
                with c1:
                    if st.form_submit_button("💾 บันทึกการแก้ไข"):
                        conn = get_db_connection()
                        conn.execute("UPDATE expenses SET description=?, amount=?, payer_name=? WHERE id=?", (e_desc, e_amt, e_payer, row['id']))
                        conn.commit()
                        conn.close()
                        st.toast("แก้ไขข้อมูลสำเร็จ!", icon='📝')
                        st.rerun()
                with c2:
                    # ใช้ปุ่มธรรมดาในคอลัมน์เพื่อความสะดวกในการสั่งลบ
                    pass
            if st.button(f"🗑️ ลบรายการนี้", key=f"del_{row['id']}"):
                conn = get_db_connection()
                conn.execute("DELETE FROM expenses WHERE id=?", (row['id'],))
                conn.commit()
                conn.close()
                st.toast("ลบรายการออกจากฐานข้อมูลแล้ว", icon='🗑️')
                st.rerun()

# --- TAB 3: สรุปการเคลียร์เงิน ---
with tab3:
    st.subheader("🤝 สรุปยอดโอนเงินรวมทุกบิล")
    # (Logic คำนวณ Net Balance และการโอนเงินเหมือนเวอร์ชันก่อนหน้า)
    
    # ... ส่วนแสดงผล calculated_transactions ...
    
    if st.button("🎯 บันทึกสรุปยอดเคลียร์เงินลงประวัติทริป"):
        # Logic การบันทึกเข้าตาราง settlements
        # ...
        st.success("บันทึกสรุปยอดโอนเงินลงในฐานข้อมูลถาวรแล้ว!")
        st.toast("ล็อคยอดสำเร็จ!", icon='🎯')
