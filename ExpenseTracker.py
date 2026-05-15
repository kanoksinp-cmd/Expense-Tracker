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
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, profile_pic TEXT, last_active TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, budget REAL, description TEXT, created_by TEXT, created_at TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, category TEXT, amount REAL, 
                  note TEXT, bill_path TEXT, created_by TEXT, updated_by TEXT, trip_id INTEGER)''')
    
    # Migration (เช็กคอลัมน์กรณีมี DB เก่า)
    try:
        c.execute('SELECT profile_pic FROM users LIMIT 1')
    except sqlite3.OperationalError:
        c.execute('ALTER TABLE users ADD COLUMN profile_pic TEXT')
        c.execute('ALTER TABLE users ADD COLUMN last_active TEXT')
        
    for col, c_type in [('note', 'TEXT'), ('created_by', 'TEXT'), ('updated_by', 'TEXT'), ('trip_id', 'INTEGER')]:
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

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

def main():
    if not st.session_state.logged_in:
        st.title("💰 Expense Tracker")
        tab_login, tab_signup = st.tabs(["🔒 เข้าสู่ระบบ", "📝 สมัครสมาชิก"])
        
        with tab_login:
            l_user = st.text_input("ชื่อผู้ใช้งาน", key="l_user")
            l_pw = st.text_input("รหัสผ่าน", type='password', key="l_pw")
            if st.button("Login", use_container_width=True):
                conn = get_connection()
                res = conn.cursor().execute('SELECT password FROM users WHERE username = ?', (l_user,)).fetchone()
                conn.close()
                if res and check_hashes(l_pw, res[0]):
                    st.session_state.logged_in = True
                    st.session_state.username = l_user
                    update_user_active(l_user)
                    st.rerun()
                else:
                    st.error("ข้อมูลไม่ถูกต้อง")
                    
        with tab_signup:
            s_user = st.text_input("ตั้งชื่อผู้ใช้งาน", key="s_user")
            s_pw = st.text_input("ตั้งรหัสผ่าน", type='password', key="s_pw")
            if st.button("Register", use_container_width=True):
                if s_user and s_pw:
                    conn = get_connection()
                    try:
                        conn.cursor().execute('INSERT INTO users(username, password) VALUES (?,?)', (s_user, make_hashes(s_pw)))
                        conn.commit()
                        st.success("สมัครสำเร็จ! โปรดไปหน้า Login")
                    except sqlite3.IntegrityError:
                        st.error("ชื่อนี้มีคนใช้แล้ว")
                    finally:
                        conn.close()
    else:
        # --- หลัง LOGIN แล้ว ---
        update_user_active(st.session_state.username)
        conn = get_connection()
        user_df = pd.read_sql_query('SELECT * FROM users', conn)
        trips_df = pd.read_sql_query('SELECT * FROM trips', conn)
        conn.close()

        # Sidebar
        st.sidebar.title("👤 เมนูผู้ใช้")
        u_info = user_df[user_df['username'] == st.session_state.username].iloc[0]
        p_pic = u_info['profile_pic']
        
        if p_pic and isinstance(p_pic, str) and os.path.exists(p_pic):
            st.sidebar.image(p_pic, width=100)
        else:
            st.sidebar.markdown("🧑‍💻 *ยังไม่มีรูปโปรไฟล์*")
        
        st.sidebar.subheader(st.session_state.username)
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()

        menu = st.sidebar.radio("เมนู", ["🏠 ภาพรวม", "🧳 จัดการทริป", "⚙️ ตั้งค่าโปรไฟล์"])

        if menu == "🧳 จัดการทริป":
            st.header("🧳 จัดการทริปกลุ่ม")
            with st.form("c_trip"):
                tn = st.text_input("ชื่อทริป/โปรเจกต์")
                tb = st.number_input("งบประมาณ (บาท)", min_value=0.0)
                if st.form_submit_button("สร้างทริปใหม่"):
                    if tn:
                        conn = get_connection()
                        now = datetime.now().strftime("%Y-%m-%d %H:%M")
                        conn.cursor().execute('INSERT INTO trips(name, budget, created_by, created_at) VALUES (?,?,?,?)', (tn, tb, st.session_state.username, now))
                        conn.commit()
                        conn.close()
                        st.success(f"สร้างทริป {tn} สำเร็จ")
                        st.rerun()
            
            st.divider()
            if not trips_df.empty:
                for _, t in trips_df.iterrows():
                    with st.expander(f"📌 {t['name']} (งบ: ฿{t['budget']:,.2f})"):
                        st.write(f"สร้างโดย: {t['created_by']} เมื่อ {t['created_at']}")

        elif menu == "⚙️ ตั้งค่าโปรไฟล์":
            st.header("⚙️ ตั้งค่าโปรไฟล์")
            img = st.file_uploader("เปลี่ยนรูปโปรไฟล์", type=['jpg', 'png'])
            if st.button("บันทึกรูป"):
                if img:
                    save_profile_pic(img, st.session_state.username)
                    st.success("อัปเดตรูปแล้ว!")
                    st.rerun()
            
            st.divider()
            st.subheader("👥 สมาชิกในกลุ่ม")
            for _, u in user_df.iterrows():
                c1, c2 = st.columns([1, 5])
                pic = u['profile_pic']
                if pic and isinstance(pic, str) and os.path.exists(pic):
                    c1.image(pic, width=50)
                else: c1.write("👤")
                c2.write(f"**{u['username']}** | {get_user_status(u['last_active'])}")

        elif menu == "🏠 ภาพรวม":
            st.header("📊 ภาพรวมระบบ")
            st.info("ระบบพร้อมใช้งานแล้ว คุณสามารถเริ่มจัดการทริปหรือดูสถานะเพื่อนในกลุ่มได้เลย!")

if __name__ == '__main__':
    main()
