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

# --- ฟังก์ชันจัดการไฟล์ ---
def save_uploaded_file(uploaded_file, folder, prefix):
    if uploaded_file:
        ext = uploaded_file.name.split('.')[-1]
        filename = f"{prefix}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}"
        file_path = os.path.join(folder, filename)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
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
                else: st.error("ข้อมูลไม่ถูกต้อง")
                    
        with tab_signup:
            s_user = st.text_input("ตั้งชื่อผู้ใช้งาน", key="s_user")
            s_pw = st.text_input("ตั้งรหัสผ่าน", type='password', key="s_pw")
            if st.button("Register", use_container_width=True):
                if s_user and s_pw:
                    conn = get_connection()
                    try:
                        conn.cursor().execute('INSERT INTO users(username, password) VALUES (?,?)', (s_user, make_hashes(s_pw)))
                        conn.commit()
                        st.success("สมัครสำเร็จ!")
                    except sqlite3.IntegrityError: st.error("ชื่อนี้มีคนใช้แล้ว")
                    finally: conn.close()
    else:
        update_user_active(st.session_state.username)
        conn = get_connection()
        user_df = pd.read_sql_query('SELECT * FROM users', conn)
        trips_df = pd.read_sql_query('SELECT * FROM trips', conn)
        
        # ดึงข้อมูล Transaction
        df_trans = pd.read_sql_query('SELECT * FROM transactions', conn)
        conn.close()

        # Sidebar
        st.sidebar.title("👤 เมนูผู้ใช้")
        u_info = user_df[user_df['username'] == st.session_state.username].iloc[0]
        p_pic = u_info['profile_pic']
        
        if p_pic and isinstance(p_pic, str) and os.path.exists(p_pic):
            st.sidebar.image(p_pic, width=100)
        else: st.sidebar.markdown("🧑‍💻 *ยังไม่มีรูปโปรไฟล์*")
        
        st.sidebar.subheader(st.session_state.username)
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()

        menu = st.sidebar.radio("เมนู", ["📊 ภาพรวม & บันทึก", "🧳 จัดการทริป", "⚙️ ตั้งค่าโปรไฟล์"])

        # --- เมนู: ภาพรวม & บันทึกค่าใช้จ่าย ---
        if menu == "📊 ภาพรวม & บันทึก":
            st.header("📊 ภาพรวม & บันทึกค่าใช้จ่าย")
            
            # ฟอร์มบันทึกใหม่
            with st.expander("📝 เพิ่มรายการบันทึกใหม่", expanded=False):
                with st.form("add_transaction", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    t_date = col1.date_input("วันที่", datetime.now())
                    t_type = col1.selectbox("ประเภท", ["รายจ่าย", "รายรับ"])
                    t_amt = col2.number_input("จำนวนเงิน", min_value=0.0)
                    t_cat = col2.selectbox("หมวดหมู่", ["อาหาร", "เดินทาง", "ที่พัก", "ช้อปปิ้ง", "อื่นๆ"])
                    
                    trip_options = {0: "📌 ไม่ระบุทริป (ส่วนตัว/ทั่วไป)"}
                    for _, t in trips_df.iterrows(): trip_options[t['id']] = t['name']
                    t_trip = st.selectbox("ผูกกับทริป", options=list(trip_options.keys()), format_func=lambda x: trip_options[x])
                    
                    t_note = st.text_area("บันทึกเพิ่มเติม")
                    t_bill = st.file_uploader("อัปโหลดสลิป (ถ้ามี)", type=['jpg', 'png', 'jpeg'])
                    
                    if st.form_submit_button("บันทึกรายการ"):
                        b_path = save_uploaded_file(t_bill, BILL_DIR, "bill")
                        tid = None if t_trip == 0 else t_trip
                        conn = get_connection()
                        conn.cursor().execute('''INSERT INTO transactions(date, type, category, amount, note, bill_path, created_by, updated_by, trip_id) 
                                                 VALUES (?,?,?,?,?,?,?,?,?)''', 
                                              (t_date.strftime("%Y-%m-%d"), t_type, t_cat, t_amt, t_note, b_path, st.session_state.username, st.session_state.username, tid))
                        conn.commit()
                        conn.close()
                        st.success("บันทึกสำเร็จ!")
                        st.rerun()

            st.divider()
            if not df_trans.empty:
                st.subheader("รายการล่าสุด")
                # แสดงตารางแบบง่าย
                display_df = df_trans.copy()
                display_df = display_df.sort_values(by='id', ascending=False)
                st.dataframe(display_df[['date', 'type', 'category', 'amount', 'note', 'created_by']], use_container_width=True)
            else:
                st.info("ยังไม่มีรายการบันทึก")

        # --- เมนู: จัดการทริป ---
        elif menu == "🧳 จัดการทริป":
            st.header("🧳 จัดการทริปกลุ่ม")
            with st.form("c_trip"):
                tn = st.text_input("ชื่อทริป/โปรเจกต์")
                tb = st.number_input("งบประมาณ (บาท)", min_value=0.0)
                if st.form_submit_button("สร้างทริปใหม่"):
                    if tn:
                        conn = get_connection()
                        now = datetime.now().strftime("%Y-%m-%d %H:%M")
                        conn.cursor().execute('INSERT INTO trips(name, budget, created_by, created_at) VALUES (?,?,?,?)', (tn, tb, st.session_state.username, now))
                        conn.commit(); conn.close()
                        st.success(f"สร้างทริป {tn} สำเร็จ"); st.rerun()
            
            st.divider()
            for _, t in trips_df.iterrows():
                with st.expander(f"📌 {t['name']} (งบ: ฿{t['budget']:,.2f})"):
                    st.write(f"สร้างโดย: {t['created_by']} เมื่อ {t['created_at']}")

        # --- เมนู: ตั้งค่าโปรไฟล์ ---
        elif menu == "⚙️ ตั้งค่าโปรไฟล์":
            st.header("⚙️ ตั้งค่าโปรไฟล์")
            img = st.file_uploader("เปลี่ยนรูปโปรไฟล์", type=['jpg', 'png'])
            if st.button("บันทึกรูป") and img:
                p_path = save_uploaded_file(img, PROFILE_DIR, f"profile_{st.session_state.username}")
                conn = get_connection()
                conn.cursor().execute('UPDATE users SET profile_pic=? WHERE username=?', (p_path, st.session_state.username))
                conn.commit(); conn.close()
                st.success("อัปเดตรูปแล้ว!"); st.rerun()
            
            st.divider()
            st.subheader("👥 สมาชิกในกลุ่ม")
            for _, u in user_df.iterrows():
                c1, c2 = st.columns([1, 5])
                pic = u['profile_pic']
                if pic and isinstance(pic, str) and os.path.exists(pic): c1.image(pic, width=50)
                else: c1.write("👤")
                c2.write(f"**{u['username']}** | {get_user_status(u['last_active'])}")

if __name__ == '__main__':
    main()
