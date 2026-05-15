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
    # 1. ตารางผู้ใช้งาน
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, profile_pic TEXT, last_active TEXT)')
    # 2. ตารางทริป
    c.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, budget REAL, created_by TEXT, created_at TEXT)')
    # 3. ตารางสมาชิกในทริป (สำหรับเชิญเพื่อน)
    c.execute('CREATE TABLE IF NOT EXISTS trip_members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, username TEXT)')
    # 4. ตารางธุรกรรม
    c.execute('''CREATE TABLE IF NOT EXISTS transactions 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, category TEXT, amount REAL, 
                  note TEXT, bill_path TEXT, created_by TEXT, updated_by TEXT, trip_id INTEGER)''')
    
    # Migration สำหรับฐานข้อมูลเดิม
    try:
        c.execute('SELECT profile_pic FROM users LIMIT 1')
    except sqlite3.OperationalError:
        c.execute('ALTER TABLE users ADD COLUMN profile_pic TEXT')
        c.execute('ALTER TABLE users ADD COLUMN last_active TEXT')
        
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
st.set_page_config(page_title="Trip Expense Tracker", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

def main():
    if not st.session_state.logged_in:
        st.title("💰 Trip Expense Manager")
        tab_login, tab_signup = st.tabs(["🔒 เข้าสู่ระบบ", "📝 สมัครสมาชิก"])
        
        with tab_login:
            l_user = st.text_input("ชื่อผู้ใช้งาน", key="l_user")
            l_pw = st.text_input("รหัสผ่าน", type='password', key="l_pw")
            if st.button("เข้าสู่ระบบ", use_container_width=True):
                conn = get_connection()
                res = conn.cursor().execute('SELECT password FROM users WHERE username = ?', (l_user,)).fetchone()
                conn.close()
                if res and check_hashes(l_pw, res[0]):
                    st.session_state.logged_in = True
                    st.session_state.username = l_user
                    update_user_active(l_user)
                    st.rerun()
                else: st.error("ชื่อผู้ใช้หรือรหัสผ่านผิด")
                    
        with tab_signup:
            s_user = st.text_input("ตั้งชื่อผู้ใช้งาน", key="s_user")
            s_pw = st.text_input("ตั้งรหัสผ่าน", type='password', key="s_pw")
            if st.button("ลงทะเบียนใหม่", use_container_width=True):
                if s_user and s_pw:
                    conn = get_connection()
                    try:
                        conn.cursor().execute('INSERT INTO users(username, password) VALUES (?,?)', (s_user, make_hashes(s_pw)))
                        conn.commit()
                        st.success("สมัครสมาชิกสำเร็จ! กรุณาสลับไปหน้า Login")
                    except sqlite3.IntegrityError: st.error("ชื่อนี้มีคนใช้แล้ว")
                    finally: conn.close()
                else: st.warning("กรุณากรอกข้อมูลให้ครบ")
    else:
        # --- LOGIN สำเร็จ ---
        update_user_active(st.session_state.username)
        user_now = st.session_state.username
        
        conn = get_connection()
        user_df = pd.read_sql_query('SELECT * FROM users', conn)
        # ดึงทริปที่ตนเองเป็นเจ้าของหรือเป็นสมาชิก
        my_trips_df = pd.read_sql_query('''
            SELECT DISTINCT t.* FROM trips t
            LEFT JOIN trip_members m ON t.id = m.trip_id
            WHERE t.created_by = ? OR m.username = ?
        ''', conn, params=(user_now, user_now))
        conn.close()

        # Sidebar
        st.sidebar.title("👤 โปรไฟล์")
        u_info = user_df[user_df['username'] == user_now].iloc[0]
        p_pic = u_info['profile_pic']
        
        if p_pic and isinstance(p_pic, str) and os.path.exists(p_pic):
            st.sidebar.image(p_pic, width=100)
        else: st.sidebar.markdown("🧑‍💻 *ยังไม่มีรูปโปรไฟล์*")
            
        st.sidebar.subheader(user_now)
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()

        menu = st.sidebar.radio("เมนูหลัก", ["🧳 ทริปของฉัน", "➕ สร้างทริปใหม่", "⚙️ ตั้งค่าโปรไฟล์"])

        # --- เมนู: ทริปของฉัน ---
        if menu == "🧳 ทริปของฉัน":
            st.header("🧳 รายการทริปของคุณ")
            if my_trips_df.empty:
                st.info("คุณยังไม่มีทริป เริ่มสร้างทริปใหม่ได้ที่เมนูสร้างทริป")
            else:
                sel_trip_name = st.selectbox("เลือกทริปที่ต้องการจัดการ", my_trips_df['name'].tolist())
                t_info = my_trips_df[my_trips_df['name'] == sel_trip_name].iloc[0]
                t_id = t_info['id']

                t_tab1, t_tab2, t_tab3 = st.tabs(["📝 บันทึกค่าใช้จ่าย", "📊 ประวัติรายการ", "👥 สมาชิก & เชิญเพื่อน"])

                with t_tab1:
                    with st.form("add_exp_form", clear_on_submit=True):
                        c1, c2 = st.columns(2)
                        date = c1.date_input("วันที่บันทึก")
                        ttype = c1.selectbox("ประเภท", ["รายจ่าย", "รายรับ"])
                        amt = c2.number_input("จำนวนเงิน (บาท)", min_value=0.0)
                        cat = c2.selectbox("หมวดหมู่", ["อาหาร", "ที่พัก", "เดินทาง", "ช้อปปิ้ง", "อื่นๆ"])
                        note = st.text_area("หมายเหตุ/รายละเอียด")
                        if st.form_submit_button("บันทึกรายการลงทริป"):
                            conn = get_connection()
                            conn.cursor().execute('INSERT INTO transactions(date, type, category, amount, note, created_by, trip_id) VALUES (?,?,?,?,?,?,?)', 
                                                  (date.strftime("%Y-%m-%d"), ttype, cat, amt, note, user_now, t_id))
                            conn.commit(); conn.close()
                            st.success("บันทึกข้อมูลเรียบร้อยแล้ว!"); st.rerun()

                with t_tab2:
                    conn = get_connection()
                    df_trans = pd.read_sql_query('SELECT date, type, category, amount, note, created_by FROM transactions WHERE trip_id = ? ORDER BY date DESC', conn, params=(t_id,))
                    conn.close()
                    if not df_trans.empty:
                        st.dataframe(df_trans, use_container_width=True)
                        total_exp = df_trans[df_trans['type'] == 'รายจ่าย']['amount'].sum()
                        st.metric("ยอดใช้จ่ายรวมในทริปนี้", f"฿{total_exp:,.2f}")
                    else: st.info("ยังไม่มีรายการบันทึกในทริปนี้")

                with t_tab3:
                    conn = get_connection()
                    members = pd.read_sql_query('SELECT username FROM trip_members WHERE trip_id = ?', conn, params=(t_id,))
                    st.subheader(f"👥 สมาชิกในทริป ({len(members)} คน)")
                    st.write(", ".join(members['username'].tolist()))
                    
                    st.divider()
                    st.subheader("📩 เชิญเพื่อนเข้าทริปนี้")
                    all_u = user_df['username'].tolist()
                    invite_list = [u for u in all_u if u not in members['username'].tolist()]
                    if invite_list:
                        friend = st.selectbox("เลือกชื่อเพื่อนที่มีในระบบ", invite_list)
                        if st.button("➕ เพิ่มเพื่อนเข้าทริป"):
                            conn.cursor().execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (t_id, friend))
                            conn.commit(); conn.close()
                            st.success(f"เพิ่ม {friend} เข้าทริปสำเร็จ!"); st.rerun()
                    else: st.write("สมาชิกครบทุกคนแล้ว")

        # --- เมนู: สร้างทริปใหม่ ---
        elif menu == "➕ สร้างทริปใหม่":
            st.header("➕ สร้างทริปใหม่")
            with st.form("create_trip"):
                tn = st.text_input("ชื่อทริป (เช่น เที่ยวญี่ปุ่น 2024)")
                tb = st.number_input("งบประมาณที่ตั้งไว้", min_value=0.0)
                if st.form_submit_button("สร้างทริป"):
                    if tn:
                        conn = get_connection(); cursor = conn.cursor()
                        cursor.execute('INSERT INTO trips(name, budget, created_by, created_at) VALUES (?,?,?,?)', 
                                      (tn, tb, user_now, datetime.now().strftime("%Y-%m-%d %H:%M")))
                        new_id = cursor.lastrowid
                        cursor.execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (new_id, user_now))
                        conn.commit(); conn.close()
                        st.success(f"สร้างทริป {tn} สำเร็จ!"); st.rerun()

        # --- เมนู: ตั้งค่าโปรไฟล์ ---
        elif menu == "⚙️ ตั้งค่าโปรไฟล์":
            st.header("⚙️ ตั้งค่าโปรไฟล์ & ดูสถานะสมาชิก")
            img = st.file_uploader("เปลี่ยนรูปโปรไฟล์ของคุณ", type=['jpg', 'png', 'jpeg'])
            if st.button("บันทึกรูปภาพ"):
                if img:
                    save_profile_pic(img, user_now)
                    st.success("อัปเดตรูปโปรไฟล์สำเร็จ!"); st.rerun()
            
            st.divider()
            st.subheader("👥 สมาชิกทั้งหมดในระบบ")
            for _, u in user_df.iterrows():
                c1, c2 = st.columns([1, 6])
                pic = u['profile_pic']
                if pic and isinstance(pic, str) and os.path.exists(pic):
                    c1.image(pic, width=50)
                else: c1.write("👤")
                c2.write(f"**{u['username']}** | สถานะ: {get_user_status(u['last_active'])}")

if __name__ == '__main__':
    main()
