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
    
    # 3. ตารางสมาชิกในทริป (เพิ่มใหม่สำหรับระบบเชิญเพื่อน)
    c.execute('CREATE TABLE IF NOT EXISTS trip_members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, username TEXT)')
    
    # 4. ตารางธุรกรรม
    c.execute('''CREATE TABLE IF NOT EXISTS transactions 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, category TEXT, amount REAL, 
                  note TEXT, bill_path TEXT, created_by TEXT, updated_by TEXT, trip_id INTEGER)''')
    
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

# --- UI Setup ---
st.set_page_config(page_title="Trip Expense Tracker", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

def main():
    if not st.session_state.logged_in:
        st.title("💰 Trip Expense Tracker")
        tab_login, tab_signup = st.tabs(["🔒 เข้าสู่ระบบ", "📝 สมัครสมาชิก"])
        
        with tab_login:
            l_user = st.text_input("ชื่อผู้ใช้งาน", key="l_user")
            l_pw = st.text_input("รหัสผ่าน", type='password', key="l_pw")
            if st.button("Login"):
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
            if st.button("Register"):
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
        user_now = st.session_state.username
        
        # ดึงข้อมูลที่จำเป็น
        conn = get_connection()
        all_users = pd.read_sql_query('SELECT username FROM users', conn)['username'].tolist()
        
        # ดึงทริปที่ผู้ใช้คนนี้เป็นสมาชิก หรือเป็นเจ้าของ
        my_trips_df = pd.read_sql_query('''
            SELECT DISTINCT t.* FROM trips t
            LEFT JOIN trip_members m ON t.id = m.trip_id
            WHERE t.created_by = ? OR m.username = ?
        ''', conn, params=(user_now, user_now))
        
        st.sidebar.title(f"👤 {user_now}")
        menu = st.sidebar.radio("เมนู", ["🧳 ทริปของฉัน", "➕ สร้างทริปใหม่", "⚙️ ตั้งค่าโปรไฟล์"])
        
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()

        # --- เมนู: สร้างทริปใหม่ ---
        if menu == "➕ สร้างทริปใหม่":
            st.header("➕ สร้างทริปใหม่")
            with st.form("new_trip"):
                tn = st.text_input("ชื่อทริป")
                tb = st.number_input("งบประมาณรวม", min_value=0.0)
                if st.form_submit_button("ยืนยันสร้างทริป"):
                    if tn:
                        conn = get_connection()
                        now = datetime.now().strftime("%Y-%m-%d %H:%M")
                        cursor = conn.cursor()
                        cursor.execute('INSERT INTO trips(name, budget, created_by, created_at) VALUES (?,?,?,?)', 
                                      (tn, tb, user_now, now))
                        trip_id = cursor.lastrowid
                        # เพิ่มตัวเองเป็นสมาชิกคนแรก
                        cursor.execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (trip_id, user_now))
                        conn.commit()
                        st.success(f"สร้างทริป {tn} สำเร็จ!")
                        st.rerun()

        # --- เมนู: ทริปของฉัน (จัดการสมาชิกและบันทึกค่าใช้จ่าย) ---
        elif menu == "🧳 ทริปของฉัน":
            st.header("🧳 รายการทริปที่คุณเข้าร่วม")
            if my_trips_df.empty:
                st.info("คุณยังไม่มีทริป เริ่มสร้างทริปใหม่ได้ที่เมนูซ้ายมือ")
            else:
                selected_trip_name = st.selectbox("เลือกทริปที่ต้องการจัดการ", my_trips_df['name'].tolist())
                trip_info = my_trips_df[my_trips_df['name'] == selected_trip_name].iloc[0]
                t_id = trip_info['id']

                t_tab1, t_tab2, t_tab3 = st.tabs(["📝 บันทึกค่าใช้จ่าย", "👥 สมาชิก & เชิญเพื่อน", "📊 สรุปยอด"])

                with t_tab1:
                    st.subheader(f"บันทึกเงินใน: {selected_trip_name}")
                    with st.form("add_exp", clear_on_submit=True):
                        c1, c2 = st.columns(2)
                        date = c1.date_input("วันที่")
                        ttype = c1.selectbox("ประเภท", ["รายจ่าย", "รายรับ"])
                        amt = c2.number_input("จำนวนเงิน", min_value=0.0)
                        cat = c2.selectbox("หมวดหมู่", ["อาหาร", "ที่พัก", "เดินทาง", "อื่นๆ"])
                        note = st.text_area("หมายเหตุ")
                        if st.form_submit_button("บันทึกลงทริป"):
                            conn = get_connection()
                            conn.cursor().execute('''INSERT INTO transactions(date, type, category, amount, note, created_by, trip_id) 
                                                     VALUES (?,?,?,?,?,?,?)''', 
                                                  (date.strftime("%Y-%m-%d"), ttype, cat, amt, note, user_now, t_id))
                            conn.commit()
                            st.success("บันทึกเรียบร้อย!")
                            st.rerun()

                with t_tab2:
                    st.subheader("👥 สมาชิกในทริปนี้")
                    conn = get_connection()
                    members = pd.read_sql_query('SELECT username FROM trip_members WHERE trip_id = ?', conn, params=(t_id,))
                    st.write(", ".join(members['username'].tolist()))
                    
                    st.divider()
                    st.subheader("📩 เชิญเพื่อนเข้าทริป")
                    # กรองเอาเฉพาะเพื่อนที่ยังไม่ได้อยู่ในทริปนี้
                    available_friends = [u for u in all_users if u not in members['username'].tolist()]
                    friend_to_invite = st.selectbox("เลือกชื่อเพื่อน", available_friends)
                    if st.button("เพิ่มเพื่อนเข้าทริป"):
                        conn.cursor().execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (t_id, friend_to_invite))
                        conn.commit()
                        st.success(f"เพิ่ม {friend_to_invite} เข้าทริปแล้ว!")
                        st.rerun()

                with t_tab3:
                    st.subheader("📊 รายการทั้งหมดในทริป")
                    trans_df = pd.read_sql_query('SELECT date, type, amount, category, created_by, note FROM transactions WHERE trip_id = ? ORDER BY date DESC', conn, params=(t_id,))
                    if not trans_df.empty:
                        st.dataframe(trans_df, use_container_width=True)
                        total_out = trans_df[trans_df['type'] == 'รายจ่าย']['amount'].sum()
                        st.metric("ยอดใช้จ่ายรวมในทริปนี้", f"฿{total_out:,.2f}")
                    else:
                        st.info("ยังไม่มีรายการบันทึกในทริปนี้")

if __name__ == '__main__':
    main()
