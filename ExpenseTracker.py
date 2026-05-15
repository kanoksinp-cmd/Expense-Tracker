import streamlit as st
import pandas as pd
import sqlite3
import os
import hashlib
from datetime import datetime, timedelta

# --- การตั้งค่าพื้นฐาน ---
DB_FILE = 'expense_tracker.db'
BILL_DIR = "bills"
PROFILE_DIR = "profiles"

if not os.path.exists(BILL_DIR):
    os.makedirs(BILL_DIR)
if not os.path.exists(PROFILE_DIR):
    os.makedirs(PROFILE_DIR)

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return hashed_text
    return False

def get_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def create_tables():
    conn = get_connection()
    c = conn.cursor()
    
    # 1. ตารางผู้ใช้งาน
    c.execute('''CREATE TABLE IF NOT EXISTS users(
                    username TEXT PRIMARY KEY, 
                    password TEXT,
                    profile_pic TEXT,
                    last_active TEXT)''')
                    
    # 2. ตารางทริป
    c.execute('''CREATE TABLE IF NOT EXISTS trips(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    budget REAL DEFAULT 0.0,
                    description TEXT,
                    created_by TEXT,
                    created_at TEXT)''')
                    
    # 3. ตารางธุรกรรม
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  date TEXT, 
                  type TEXT, 
                  category TEXT, 
                  amount REAL, 
                  note TEXT, 
                  bill_path TEXT,
                  created_by TEXT,
                  updated_by TEXT,
                  trip_id INTEGER)''')
    
    # --- Migration สำหรับฐานข้อมูลเดิม ---
    try:
        c.execute('SELECT profile_pic FROM users LIMIT 1')
    except sqlite3.OperationalError:
        c.execute('ALTER TABLE users ADD COLUMN profile_pic TEXT')
        c.execute('ALTER TABLE users ADD COLUMN last_active TEXT')

    columns_to_add = [
        ('note', 'TEXT'),
        ('created_by', 'TEXT DEFAULT "System"'),
        ('updated_by', 'TEXT DEFAULT "System"'),
        ('trip_id', 'INTEGER DEFAULT NULL')
    ]
    for col_name, col_type in columns_to_add:
        try:
            c.execute(f'SELECT {col_name} FROM transactions LIMIT 1')
        except sqlite3.OperationalError:
            c.execute(f'ALTER TABLE transactions ADD COLUMN {col_name} {col_type}')
    
    conn.commit()
    conn.close()

create_tables()

# --- ฟังก์ชันจัดการข้อมูล ---
def save_bill(uploaded_file, username):
    if uploaded_file is not None:
        file_ext = uploaded_file.name.split('.')[-1]
        filename = f"{username}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{file_ext}"
        file_path = os.path.join(BILL_DIR, filename)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return file_path
    return None

def save_profile_pic(uploaded_file, username):
    if uploaded_file is not None:
        file_ext = uploaded_file.name.split('.')[-1]
        filename = f"profile_{username}.{file_ext}"
        file_path = os.path.join(PROFILE_DIR, filename)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        conn = get_connection()
        c = conn.cursor()
        c.execute('UPDATE users SET profile_pic=? WHERE username=?', (file_path, username))
        conn.commit()
        conn.close()
        return file_path
    return None

def update_user_active(username):
    conn = get_connection()
    c = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('UPDATE users SET last_active=? WHERE username=?', (now_str, username))
    conn.commit()
    conn.close()

def get_user_status(last_active_str):
    if not last_active_str:
        return "⚫ ออฟไลน์"
    try:
        last_active = datetime.strptime(last_active_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() - last_active < timedelta(minutes=3):
            return "🟢 ออนไลน์"
        else:
            return "⚫ ออฟไลน์"
    except:
        return "⚫ ออฟไลน์"

def update_transaction(t_id, date, t_type, cat, amount, note, username, trip_id, bill_path=None):
    conn = get_connection()
    c = conn.cursor()
    t_id_val = None if trip_id == 0 else trip_id
    if bill_path:
        c.execute('''UPDATE transactions SET date=?, type=?, category=?, amount=?, note=?, updated_by=?, trip_id=?, bill_path=? WHERE id=?''', 
                  (date, t_type, cat, amount, note, username, t_id_val, bill_path, t_id))
    else:
        c.execute('''UPDATE transactions SET date=?, type=?, category=?, amount=?, note=?, updated_by=?, trip_id=? WHERE id=?''', 
                  (date, t_type, cat, amount, note, username, t_id_val, t_id))
    conn.commit()
    conn.close()

def delete_transaction(t_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM transactions WHERE id=?', (t_id,))
    conn.commit()
    conn.close()

# --- UI Setup ---
st.set_page_config(page_title="Group Expense Tracker", page_icon="💰", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'editing_id' not in st.session_state:
    st.session_state.editing_id = None
if 'view_bill_id' not in st.session_state:
    st.session_state.view_bill_id = None

def main():
    if not st.session_state.logged_in:
        st.title("🔒 Group Login")
        auth_mode = st.tabs(["เข้าสู่ระบบ", "สมัครสมาชิก"])
        with auth_mode[0]:
            user = st.text_input("Username", key="l_user")
            pw = st.text_input("Password", type='password', key="l_pw")
            if st.button("Login"):
                conn = get_connection()
                c = conn.cursor()
                c.execute('SELECT password FROM users WHERE username = ?', (user,))
                res = c.fetchone()
                if res and check_hashes(pw, res[0]):
                    st.session_state.logged_in = True
                    st.session_state.username = user
                    update_user_active(user)
                    st.rerun()
                else: st.error("ข้อมูลไม่ถูกต้อง")
        with auth_mode[1]:
            new_u = st.text_input("ชื่อผู้ใช้ใหม่")
            new_p = st.text_input("รหัสผ่านใหม่", type='password')
            if st.button("สมัครสมาชิก"):
                if new_u and new_p:
                    conn = get_connection()
                    try:
                        conn.cursor().execute('INSERT INTO users(username, password) VALUES (?,?)', (new_u, make_hashes(new_p)))
                        conn.commit()
                        st.success("สมัครสำเร็จ!")
                    except: st.error("ชื่อนี้ถูกใช้ไปแล้ว")
                    finally: conn.close()
    else:
        update_user_active(st.session_state.username)
        conn = get_connection()
        user_df = pd.read_sql_query('SELECT * FROM users', conn)
        trips_df = pd.read_sql_query('SELECT * FROM trips', conn)
        conn.close()
        
        current_user_info = user_df[user_df['username'] == st.session_state.username].iloc[0]
        p_pic = current_user_info['profile_pic']

        trip_options = {0: "📌 ไม่ระบุทริปส่วนกลาง"}
        for _, t_row in trips_df.iterrows():
            trip_options[t_row['id']] = t_row['name']

        # --- Sidebar ---
        st.sidebar.title("👤 โปรไฟล์ของคุณ")
        # แก้ไข BUG TypeError: ตรวจสอบ p_pic ว่าเป็น String และมีไฟล์อยู่จริงหรือไม่
        if p_pic is not None and isinstance(p_pic, str) and os.path.exists(p_pic):
            st.sidebar.image(p_pic, width=100)
        else:
            st.sidebar.markdown("🧑‍💻 *ยังไม่มีรูปโปรไฟล์*")
            
        st.sidebar.subheader(f"{st.session_state.username}")
        st.sidebar.caption("🟢 กำลังใช้งาน")
        
        if st.sidebar.button("ออกจากระบบ"):
            st.session_state.logged_in = False
            st.rerun()

        st.sidebar.divider()
        menu = st.sidebar.radio("เมนู", ["สรุปภาพรวมทั้งหมด", "บันทึกรายการใหม่", "🧳 จัดการทริปกลุ่ม", "ตั้งค่าโปรไฟล์"])

        # --- เมนู: จัดการทริปกลุ่ม ---
        if menu == "🧳 จัดการทริปกลุ่ม":
            st.header("🧳 บริหารจัดการทริปกลุ่ม")
            t_tab1, t_tab2 = st.tabs(["📊 ทริปปัจจุบัน", "➕ สร้างทริปใหม่"])
            with t_tab2:
                with st.form("create_trip_form", clear_on_submit=True):
                    trip_name = st.text_input("ชื่อทริป")
                    trip_budget = st.number_input("งบประมาณ (บาท)", min_value=0.0)
                    trip_desc = st.text_area("รายละเอียด")
                    if st.form_submit_button("➕ สร้างทริป"):
                        if trip_name:
                            conn = get_connection(); conn.cursor().execute('''INSERT INTO trips(name, budget, description, created_by, created_at) VALUES (?,?,?,?,?)''', (trip_name, trip_budget, trip_desc, st.session_state.username, datetime.now().strftime("%Y-%m-%d %H:%M"))); conn.commit(); conn.close()
                            st.success(f"
