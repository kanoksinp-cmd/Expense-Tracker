import streamlit as st
import pandas as pd
import sqlite3
import os
import hashlib
from datetime import datetime, timedelta

# --- 1. ตั้งค่าฐานข้อมูลและ Migration ---
DB_FILE = 'expense_tracker.db'
BILL_DIR = "bills"
PROFILE_DIR = "profiles"

for folder in [BILL_DIR, PROFILE_DIR]:
    if not os.path.exists(folder):
        os.makedirs(folder)

def get_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, profile_pic TEXT, last_active TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, budget REAL, created_by TEXT, created_at TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS trip_members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, username TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, category TEXT, amount REAL, 
                  note TEXT, bill_path TEXT, created_by TEXT, trip_id INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notifications 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, receiver TEXT, message TEXT, is_read INTEGER DEFAULT 0, created_at TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- 2. ฟังก์ชันเสริมการทำงาน ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def update_active_status(username):
    """ อัปเดตเวลาใช้งานล่าสุดของผู้ใช้ """
    if username:
        conn = get_connection()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.cursor().execute('UPDATE users SET last_active=? WHERE username=?', (now, username))
        conn.commit()
        conn.close()

def get_online_status(last_active_str):
    """ ตรวจสอบว่าเป็นออนไลน์หรือไม่ (ถ้าใช้งานภายใน 5 นาทีที่ผ่านมา) """
    if not last_active_str: return "⚪ ออฟไลน์"
    last_active = datetime.strptime(last_active_str, "%Y-%m-%d %H:%M:%S")
    if datetime.now() - last_active < timedelta(minutes=5):
        return "🟢 ออนไลน์"
    return "⚪ ออฟไลน์"

def send_notify(receiver, msg):
    conn = get_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn.cursor().execute('INSERT INTO notifications(receiver, message, created_at) VALUES (?,?,?)', (receiver, msg, now))
    conn.commit()
    conn.close()

# --- 3. ส่วน UI หลัก ---
st.set_page_config(page_title="Trip Expense Master", layout="wide")

if 'username' not in st.session_state:
    st.session_state.username = None

# หน้า Login / Register
if not st.session_state.username:
    st.title("💰 Trip Expense Tracker")
    t1, t2 = st.tabs(["Login", "Register"])
    with t1:
        u = st.text_input("Username", key="l_u")
        p = st.text_input("Password", type='password', key="l_p")
        if st.button("เข้าสู่ระบบ"):
            conn = get_connection()
            res = conn.cursor().execute('SELECT password FROM users WHERE username=?', (u,)).fetchone()
            conn.close()
            if res and res[0] == make_hashes(p):
                st.session_state.username = u
                update_active_status(u)
                st.rerun()
            else: st.error("ชื่อหรือรหัสผ่านผิด")
    with t2:
        su = st.text_input("Username", key="r_u")
        sp = st.text_input("Password", type='password', key="r_p")
        if st.button("สมัครสมาชิก"):
            conn = get_connection()
            try:
                conn.cursor().execute('INSERT INTO users(username, password) VALUES (?,?)', (su, make_hashes(sp)))
                conn.commit()
                st.success("สมัครสำเร็จ! กรุณา Login")
            except: st.error("ชื่อนี้ถูกใช้ไปแล้ว")
            finally: conn.close()

# หน้าแอปพลิเคชันหลัง Login
else:
    user_now = st.session_state.username
    update_active_status(user_now)
    
    # ดึงข้อมูลจากฐานข้อมูล
    conn = get_connection()
    my_trips = pd.read_sql_query('''
        SELECT DISTINCT t.* FROM trips t 
        LEFT JOIN trip_members m ON t.id = m.trip_id 
        WHERE t.created_by = ? OR m.username = ?
    ''', conn, params=(user_now, user_now))
    notis = pd.read_sql_query('SELECT * FROM notifications WHERE receiver=? ORDER BY id DESC LIMIT 5', conn, params=(user_now,))
    conn.close()

    # Sidebar
    st.sidebar.title(f"👤 {user_now}")
    unread = len(notis[notis['is_read'] == 0])
    menu = st.sidebar.radio("เมนู", [f"🔔 แจ้งเตือน ({unread})", "🧳 ทริปของฉัน", "➕ สร้างทริป", "⚙️ โปรไฟล์"])
    
    if st.sidebar.button("Logout"):
        st.session_state.username = None
        st.rerun()

    # --- เมนู: แจ้งเตือน ---
    if "🔔" in menu:
        st.header("🔔 การแจ้งเตือน")
        if notis.empty: st.info("ไม่มีข้อความใหม่")
        else:
            for _, n in notis.iterrows():
                st.markdown(f"**[{n['created_at']}]** {n['message']}")
            if st.button("ล้างสถานะการอ่าน"):
                conn = get_connection(); conn.cursor().execute('UPDATE notifications SET is_read=1 WHERE receiver=?', (user_now,)); conn.commit(); conn.close(); st.rerun()

    # --- เมนู: ทริปของฉัน ---
    elif menu == "🧳 ทริปของฉัน":
        if my_trips.empty: st.info("คุณยังไม่มีทริป")
        else:
            sel_trip_name = st.selectbox("เลือกทริป", my_trips['name'].tolist())
            t_data = my_trips[my_trips['name'] == sel_trip_name].iloc[0]
            t_id = t_data['id']
            is_creator = (t_data['created_by'] == user_now)

            tab1, tab2, tab3 = st.tabs(["📝 บันทึกเงิน", "📊 สรุปยอด", "👥 สมาชิก & สถานะ"])

            with tab1:
                with st.form("add_form"):
                    ttype = st.selectbox("ประเภท", ["รายจ่าย", "รายรับ"])
                    amt = st.number_input("จำนวนเงิน", min_value=0.0)
                    cat = st.selectbox("หมวดหมู่", ["อาหาร", "เดินทาง", "ที่พัก", "อื่นๆ"])
                    note = st.text_area("โน้ต")
                    if st.form_submit_button("บันทึก"):
                        conn = get_connection()
                        conn.cursor().execute('INSERT INTO transactions(date,type,category,amount,note,trip_id) VALUES (?,?,?,?,?,?)',
                                              (datetime.now().strftime("%Y-%m-%d"), ttype, cat, amt, note, t_id))
                        # แจ้งเตือนเพื่อนในทริป
                        m_list = conn.cursor().execute('SELECT username FROM trip_members WHERE trip_id=? AND username!=?', (t_id, user_now)).fetchall()
                        for m in m_list: send_notify(m[0], f"💰 {user_now} เพิ่มรายการ {amt} ในทริป {sel_trip_name}")
                        conn.commit(); conn.close(); st.success("บันทึกสำเร็จ!"); st.rerun()

            with tab2:
                conn = get_connection()
                df = pd.read_sql_query('SELECT * FROM transactions WHERE trip_id=?', conn, params=(t_id,))
                conn.close()
                st.subheader(f"📊 สรุป {sel_trip_name}")
                exp = df[df['type']=='รายจ่าย']['amount'].sum()
                st.metric("ใช้จ่ายไปแล้ว", f"฿{exp:,.2f}")
                st.dataframe(df[['date', 'type', 'category', 'amount', 'note']], use_container_width=True)

            with tab3:
                st.subheader("👥 สมาชิกในทริป")
                conn = get_connection()
                # ดึงรายชื่อสมาชิกพร้อมสถานะล่าสุด
                members_status = pd.read_sql_query('''
                    SELECT u.username, u.last_active FROM trip_members m
                    JOIN users u ON m.username = u.username
                    WHERE m.trip_id = ?
                ''', conn, params=(t_id,))
                
                for _, row in members_status.iterrows():
                    status = get_online_status(row['last_active'])
                    c1, c2 = st.columns([4, 1])
                    c1.write(f"• {row['username']} {status}")
                    if is_creator and row['username'] != user_now:
                        if c2.button("ลบ", key=f"k_{row['username']}"):
                            conn.cursor().execute('DELETE FROM trip_members WHERE trip_id=? AND username=?', (t_id, row['username']))
                            send_notify(row['username'], f"❌ คุณถูกเชิญออกจากทริป {sel_trip_name}")
                            conn.commit(); conn.close(); st.rerun()
                
                if is_creator:
                    st.divider()
                    st.subheader("📩 เชิญเพื่อนเข้าทริป")
                    all_u = pd.read_sql_query('SELECT username FROM users', conn)['username'].tolist()
                    invite_list = [u for u in all_u if u not in members_status['username'].tolist()]
                    friend = st.selectbox("เลือกเพื่อน", invite_list)
                    if st.button("ส่งคำเชิญ"):
                        # จุดแก้ไขสำคัญ: ต้องบันทึกเข้า trip_members ทันที
                        conn.cursor().execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (t_id, friend))
                        conn.commit() # บันทึกเพื่อนลงทริปก่อน
                        send_notify(friend, f"✉️ {user_now} เชิญคุณเข้าร่วมทริป '{sel_trip_name}'")
                        conn.close()
                        st.success(f"เชิญ {friend} เรียบร้อยแล้ว!")
                        st.rerun()

    elif menu == "➕ สร้างทริป":
        st.header("➕ สร้างทริปใหม่")
        with st.form("new_t"):
            name = st.text_input("ชื่อทริป")
            bud = st.number_input("งบประมาณ", min_value=0.0)
            if st.form_submit_button("สร้าง"):
                conn = get_connection(); cur = conn.cursor()
                cur.execute('INSERT INTO trips(name, budget, created_by, created_at) VALUES (?,?,?,?)', (name, bud, user_now, datetime.now().strftime("%Y-%m-%d")))
                t_id_new = cur.lastrowid
                # ผู้สร้างต้องเป็นสมาชิกคนแรกโดยอัตโนมัติ
                cur.execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (t_id_new, user_now))
                conn.commit(); conn.close(); st.success("สร้างทริปสำเร็จ!"); st.rerun()

if __name__ == '__main__':
    main()
