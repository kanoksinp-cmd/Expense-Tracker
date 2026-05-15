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

# สร้างโฟลเดอร์ถ้ายังไม่มี
for folder in [BILL_DIR, PROFILE_DIR]:
    if not os.path.exists(folder):
        os.makedirs(folder)

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
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password TEXT, profile_pic TEXT, last_active TEXT)''')
    # 2. ตารางทริป
    c.execute('''CREATE TABLE IF NOT EXISTS trips
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, budget REAL, 
                  description TEXT, created_by TEXT, created_at TEXT)''')
    # 3. ตารางธุรกรรม
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, category TEXT, 
                  amount REAL, note TEXT, bill_path TEXT, created_by TEXT, updated_by TEXT, trip_id INTEGER)''')
    
    # Migration (ตรวจสอบคอลัมน์กรณีใช้ DB เก่า)
    try:
        c.execute('SELECT profile_pic FROM users LIMIT 1')
    except sqlite3.OperationalError:
        c.execute('ALTER TABLE users ADD COLUMN profile_pic TEXT')
        c.execute('ALTER TABLE users ADD COLUMN last_active TEXT')

    cols = [('note', 'TEXT'), ('created_by', 'TEXT'), ('updated_by', 'TEXT'), ('trip_id', 'INTEGER')]
    for col, c_type in cols:
        try:
            c.execute(f'SELECT {col} FROM transactions LIMIT 1')
        except sqlite3.OperationalError:
            c.execute(f'ALTER TABLE transactions ADD COLUMN {col} {c_type}')
            
    conn.commit()
    conn.close()

create_tables()

# --- ฟังก์ชันจัดการข้อมูล ---
def save_profile_pic(uploaded_file, username):
    if uploaded_file:
        ext = uploaded_file.name.split('.')[-1]
        file_path = os.path.join(PROFILE_DIR, f"profile_{username}.{ext}")
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        conn = get_connection()
        conn.cursor().execute('UPDATE users SET profile_pic=? WHERE username=?', (file_path, username))
        conn.commit()
        conn.close()
        return file_path
    return None

def update_user_active(username):
    conn = get_connection()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.cursor().execute('UPDATE users SET last_active=? WHERE username=?', (now_str, username))
    conn.commit()
    conn.close()

def get_user_status(last_active_str):
    if not last_active_str: return "⚫ ออฟไลน์"
    try:
        last_active = datetime.strptime(last_active_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() - last_active < timedelta(minutes=3):
            return "🟢 ออนไลน์"
        return "⚫ ออฟไลน์"
    except: return "⚫ ออฟไลน์"

# --- UI Setup ---
st.set_page_config(page_title="Group Expense Tracker", layout="wide")

if 'logged_in' not in st.session_state: st.session_state.logged_in = False

def main():
    if not st.session_state.logged_in:
        st.title("🔒 Login")
        user = st.text_input("Username")
        pw = st.text_input("Password", type='password')
        if st.button("Login"):
            conn = get_connection()
            res = conn.cursor().execute('SELECT password FROM users WHERE username = ?', (user,)).fetchone()
            if res and check_hashes(pw, res[0]):
                st.session_state.logged_in = True
                st.session_state.username = user
                update_user_active(user)
                st.rerun()
            else:
                st.error("ชื่อผู้ใช้หรือรหัสผ่านผิด")
    else:
        update_user_active(st.session_state.username)
        conn = get_connection()
        user_df = pd.read_sql_query('SELECT * FROM users', conn)
        trips_df = pd.read_sql_query('SELECT * FROM trips', conn)
        conn.close()

        # Sidebar
        st.sidebar.title("👤 Profile")
        u_info = user_df[user_df['username'] == st.session_state.username].iloc[0]
        p_pic = u_info['profile_pic']
        
        # แก้ไขจุดที่เคยเกิด TypeError
        if p_pic and isinstance(p_pic, str) and os.path.exists(p_pic):
            st.sidebar.image(p_pic, width=100)
        else:
            st.sidebar.write("🧑‍💻 ยังไม่มีรูปโปรไฟล์")
            
        st.sidebar.subheader(st.session_state.username)
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()

        menu = st.sidebar.radio("เมนู", ["📊 ภาพรวม", "🧳 จัดการทริป", "⚙️ ตั้งค่าโปรไฟล์"])

        if menu == "🧳 จัดการทริป":
            st.header("🧳 จัดการทริป")
            with st.form("create_trip"):
                tn = st.text_input("ชื่อทริป")
                tb = st.number_input("งบประมาณ", min_value=0.0)
                if st.form_submit_button("สร้างทริป"):
                    if tn:
                        conn = get_connection()
                        now = datetime.now().strftime("%Y-%m-%d %H:%M")
                        conn.cursor().execute('INSERT INTO trips(name, budget, created_by, created_at) VALUES (?,?,?,?)', 
                                              (tn, tb, st.session_state.username, now))
                        conn.commit()
                        st.success(f"สร้างทริป {tn} เรียบร้อย")
                        st.rerun()

        elif menu == "⚙️ ตั้งค่าโปรไฟล์":
            st.header("⚙️ ตั้งค่าโปรไฟล์")
            img = st.file_uploader("อัปโหลดรูปโปรไฟล์", type=['jpg', 'png'])
            if st.button("บันทึกรูป"):
                if img:
                    save_profile_pic(img, st.session_state.username)
                    st.success("อัปเดตรูปโปรไฟล์แล้ว")
                    st.rerun()
            
            st.divider()
            st.subheader("👥 สถานะสมาชิก")
            for _, u in user_df.iterrows():
                col1, col2 = st.columns([1, 4])
                pic = u['profile_pic']
                if pic and isinstance(pic, str) and os.path.exists(pic):
                    col1.image(pic, width=50)
                else:
                    col1.write("👤")
                col2.write(f"**{u['username']}** - {get_user_status(u['last_active'])}")

        elif menu == "📊 ภาพรวม":
            st.header("📊 ภาพรวมการใช้จ่าย")
            st.info("กรุณาเลือกเมนูบันทึกรายการเพื่อเพิ่มข้อมูล")

if __name__ == '__main__':
    main()
