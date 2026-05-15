import streamlit as st
import pandas as pd
import sqlite3
import os
import hashlib
from datetime import datetime, timedelta

# --- 1. ตั้งค่าฐานข้อมูลและระบบ Migration (แก้ปัญหา OperationalError) ---
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
    # สร้างตารางหลักหากยังไม่มี
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, profile_pic TEXT, last_active TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, budget REAL, created_by TEXT, created_at TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS trip_members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, username TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, category TEXT, amount REAL, 
                  note TEXT, bill_path TEXT, created_by TEXT, trip_id INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notifications 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, receiver TEXT, message TEXT, is_read INTEGER DEFAULT 0, created_at TEXT)''')
    
    # ตรวจสอบและเพิ่มคอลัมน์ที่อาจขาดหายไป (Migration)
    columns_to_add = [
        ('users', 'last_active', 'TEXT'),
        ('users', 'profile_pic', 'TEXT')
    ]
    for table, col, col_type in columns_to_add:
        try:
            c.execute(f'SELECT {col} FROM {table} LIMIT 1')
        except sqlite3.OperationalError:
            c.execute(f'ALTER TABLE {table} ADD COLUMN {col} {col_type}')
    
    conn.commit()
    conn.close()

init_db()

# --- 2. ฟังก์ชันเสริม (Helper Functions) ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def update_active_status(username):
    """ อัปเดตสถานะออนไลน์ของผู้ใช้ """
    if username:
        conn = get_connection()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.cursor().execute('UPDATE users SET last_active=? WHERE username=?', (now, username))
        conn.commit()
        conn.close()

def get_status_dot(last_active_str):
    if not last_active_str: return "⚪ ออฟไลน์"
    try:
        last_active = datetime.strptime(last_active_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() - last_active < timedelta(minutes=5):
            return "🟢 ออนไลน์"
    except: pass
    return "⚪ ออฟไลน์"

def send_notify(receiver, msg):
    """ ส่งการแจ้งเตือน (แก้ปัญหาการแจ้งเตือนไม่ขึ้น) """
    conn = get_connection()
    now = datetime.now().strftime("%H:%M")
    conn.cursor().execute('INSERT INTO notifications(receiver, message, created_at) VALUES (?,?,?)', (receiver, msg, now))
    conn.commit()
    conn.close()

# --- 3. ส่วนการแสดงผล (UI) ---
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
            else: st.error("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    with t2:
        su = st.text_input("ชื่อผู้ใช้ใหม่", key="r_u")
        sp = st.text_input("รหัสผ่านใหม่", type='password', key="r_p")
        if st.button("สมัครสมาชิก"):
            if su and sp:
                conn = get_connection()
                try:
                    conn.cursor().execute('INSERT INTO users(username, password) VALUES (?,?)', (su, make_hashes(sp)))
                    conn.commit(); st.success("สมัครสมาชิกสำเร็จ!")
                except: st.error("ชื่อผู้ใช้นี้ถูกใช้งานแล้ว")
                finally: conn.close()

else:
    user_now = st.session_state.username
    update_active_status(user_now)
    
    conn = get_connection()
    u_info = pd.read_sql_query('SELECT * FROM users WHERE username=?', conn, params=(user_now,)).iloc[0]
    my_trips = pd.read_sql_query('''
        SELECT DISTINCT t.* FROM trips t 
        LEFT JOIN trip_members tm ON t.id = tm.trip_id 
        WHERE t.created_by = ? OR tm.username = ?
    ''', conn, params=(user_now, user_now))
    notis = pd.read_sql_query('SELECT * FROM notifications WHERE receiver=? ORDER BY id DESC LIMIT 10', conn, params=(user_now,))
    conn.close()

    # Sidebar
    st.sidebar.title(f"👤 {user_now}")
    unread_count = len(notis[notis['is_read'] == 0])
    noti_label = f"🔔 แจ้งเตือน ({unread_count})" if unread_count > 0 else "🔔 แจ้งเตือน"
    menu = st.sidebar.radio("เมนูหลัก", [noti_label, "🧳 ทริปของฉัน", "➕ สร้างทริป", "⚙️ โปรไฟล์"])
    
    if st.sidebar.button("Logout"):
        st.session_state.username = None
        st.rerun()

    # --- หน้าแจ้งเตือน ---
    if "🔔" in menu:
        st.header("🔔 การแจ้งเตือน")
        if notis.empty: st.info("ไม่มีการแจ้งเตือนใหม่")
        else:
            for _, n in notis.iterrows():
                st.markdown(f"**[{n['created_at']}]** {n['message']}")
            if st.button("ทำเลิกว่าอ่านแล้วทั้งหมด"):
                conn = get_connection(); conn.cursor().execute('UPDATE notifications SET is_read=1 WHERE receiver=?', (user_now,)); conn.commit(); conn.close(); st.rerun()

    # --- หน้าจัดการทริป ---
    elif menu == "🧳 ทริปของฉัน":
        if my_trips.empty: st.info("คุณยังไม่ได้เข้าร่วมทริปใดๆ")
        else:
            sel_trip = st.selectbox("เลือกทริป", my_trips['name'].tolist())
            t_row = my_trips[my_trips['name'] == sel_trip].iloc[0]
            t_id = t_row['id']
            is_admin = (t_row['created_by'] == user_now)

            tab1, tab2, tab3 = st.tabs(["📝 รายจ่าย", "📊 สรุปยอด", "👥 สมาชิก & สถานะ"])

            with tab1:
                with st.form("add_exp_form", clear_on_submit=True):
                    ttype = st.selectbox("ประเภท", ["รายจ่าย", "รายรับ"])
                    amt = st.number_input("จำนวนเงิน", min_value=0.0)
                    cat = st.selectbox("หมวดหมู่", ["อาหาร", "เดินทาง", "ที่พัก", "อื่นๆ"])
                    note = st.text_area("บันทึกเพิ่มเติม")
                    if st.form_submit_button("บันทึกรายการ"):
                        conn = get_connection()
                        conn.cursor().execute('INSERT INTO transactions(date,type,category,amount,note,trip_id,created_by) VALUES (?,?,?,?,?,?,?)',
                                              (datetime.now().strftime("%Y-%m-%d"), ttype, cat, amt, note, t_id, user_now))
                        # แจ้งเตือนสมาชิกในทริป
                        m_list = conn.cursor().execute('SELECT username FROM trip_members WHERE trip_id=? AND username!=?', (t_id, user_now)).fetchall()
                        for m in m_list:
                            send_notify(m[0], f"💰 {user_now} เพิ่ม {ttype} ฿{amt:,.2f} ในทริป {sel_trip}")
                        conn.commit(); conn.close(); st.success("บันทึกสำเร็จ!"); st.rerun()

            with tab2:
                conn = get_connection()
                df = pd.read_sql_query('SELECT * FROM transactions WHERE trip_id=?', conn, params=(t_id,))
                conn.close()
                exp_total = df[df['type']=='รายจ่าย']['amount'].sum()
                st.subheader(f"💰 งบประมาณคงเหลือ: ฿{t_row['budget'] - exp_total:,.2f}")
                st.dataframe(df[['date', 'type', 'category', 'amount', 'note', 'created_by']], use_container_width=True)

            with tab3:
                st.subheader("👥 สมาชิกและสถานะออนไลน์")
                conn = get_connection()
                m_data = pd.read_sql_query('''
                    SELECT u.username, u.last_active FROM trip_members tm
                    JOIN users u ON tm.username = u.username
                    WHERE tm.trip_id = ?
                ''', conn, params=(t_id,))
                
                for _, row in m_data.iterrows():
                    status = get_status_dot(row['last_active'])
                    c1, c2 = st.columns([4, 1])
                    c1.write(f"{status} **{row['username']}**")
                    if is_admin and row['username'] != user_now:
                        if c2.button("ลบ", key=f"remove_{row['username']}"):
                            conn.cursor().execute('DELETE FROM trip_members WHERE trip_id=? AND username=?', (t_id, row['username']))
                            send_notify(row['username'], f"❌ คุณถูกนำออกจากทริป {sel_trip}")
                            conn.commit(); conn.close(); st.rerun()
                
                if is_admin:
                    st.divider()
                    st.subheader("✉️ เชิญเพื่อนเข้าทริป")
                    all_u = pd.read_sql_query('SELECT username FROM users', conn)['username'].tolist()
                    can_invite = [u for u in all_u if u not in m_data['username'].tolist()]
                    friend = st.selectbox("เลือกเพื่อน", can_invite)
                    if st.button("ส่งคำเชิญ"):
                        conn.cursor().execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (t_id, friend))
                        conn.commit()
                        send_notify(friend, f"✉️ {user_now} เชิญคุณเข้าร่วมทริป '{sel_trip}'")
                        conn.close()
                        st.success(f"เชิญ {friend} สำเร็จ!"); st.rerun()

    elif menu == "➕ สร้างทริป":
        st.header("➕ สร้างทริปใหม่")
        with st.form("create_trip_form"):
            name = st.text_input("ชื่อทริป")
            budget = st.number_input("งบประมาณรวม", min_value=0.0)
            if st.form_submit_button("สร้างทริป"):
                if name:
                    conn = get_connection(); cur = conn.cursor()
                    cur.execute('INSERT INTO trips(name, budget, created_by, created_at) VALUES (?,?,?,?)', (name, budget, user_now, datetime.now().strftime("%Y-%m-%d")))
                    new_t_id = cur.lastrowid
                    cur.execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (new_t_id, user_now))
                    conn.commit(); conn.close(); st.success("สร้างทริปสำเร็จ!"); st.rerun()

if __name__ == '__main__':
    main()
