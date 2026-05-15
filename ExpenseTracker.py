import streamlit as st
import pandas as pd
import sqlite3
import os
import hashlib
from datetime import datetime, timedelta

# --- 1. ตั้งค่าฐานข้อมูลและระบบ Migration ---
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
    # สร้างตารางหลัก
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, profile_pic TEXT, last_active TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, budget REAL, created_by TEXT, created_at TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS trip_members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, username TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, category TEXT, amount REAL, 
                  note TEXT, bill_path TEXT, created_by TEXT, trip_id INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notifications 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, receiver TEXT, message TEXT, is_read INTEGER DEFAULT 0, created_at TEXT)''')
    
    # อัปเกรดฐานข้อมูลอัตโนมัติ (Migration)
    try:
        c.execute('SELECT last_active FROM users LIMIT 1')
    except sqlite3.OperationalError:
        c.execute('ALTER TABLE users ADD COLUMN last_active TEXT')
    
    conn.commit()
    conn.close()

init_db()

# --- 2. ฟังก์ชันเสริมการทำงาน ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def update_active_status(username):
    """ อัปเดต Heartbeat เพื่อบอกว่าผู้ใช้กำลังออนไลน์ """
    if username:
        conn = get_connection()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.cursor().execute('UPDATE users SET last_active=? WHERE username=?', (now, username))
        conn.commit()
        conn.close()

def get_status_dot(last_active_str):
    if not last_active_str: return "⚪ ออฟไลน์"
    last_active = datetime.strptime(last_active_str, "%Y-%m-%d %H:%M:%S")
    if datetime.now() - last_active < timedelta(minutes=3):
        return "🟢 ออนไลน์"
    return "⚪ ออฟไลน์"

def send_notify(receiver, msg):
    conn = get_connection()
    now = datetime.now().strftime("%H:%M")
    conn.cursor().execute('INSERT INTO notifications(receiver, message, created_at) VALUES (?,?,?)', (receiver, msg, now))
    conn.commit()
    conn.close()

def save_file(uploaded_file, folder, prefix):
    if uploaded_file:
        ext = uploaded_file.name.split('.')[-1]
        path = os.path.join(folder, f"{prefix}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}")
        with open(path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return path
    return None

# --- 3. ส่วน UI ---
st.set_page_config(page_title="Trip Expense Master", layout="wide")

if 'username' not in st.session_state:
    st.session_state.username = None

if not st.session_state.username:
    st.title("💰 Trip Expense Manager")
    t1, t2 = st.tabs(["Login", "Register"])
    with t1:
        u = st.text_input("Username", key="l_u")
        p = st.text_input("Password", type='password', key="l_p")
        if st.button("เข้าสู่ระบบ", use_container_width=True):
            conn = get_connection()
            res = conn.cursor().execute('SELECT password FROM users WHERE username=?', (u,)).fetchone()
            conn.close()
            if res and res[0] == make_hashes(p):
                st.session_state.username = u
                update_active_status(u)
                st.rerun()
            else: st.error("ข้อมูลไม่ถูกต้อง")
    with t2:
        su = st.text_input("ชื่อผู้ใช้ใหม่", key="r_u")
        sp = st.text_input("รหัสผ่านใหม่", type='password', key="r_p")
        if st.button("ลงทะเบียน", use_container_width=True):
            conn = get_connection()
            try:
                conn.cursor().execute('INSERT INTO users(username, password) VALUES (?,?)', (su, make_hashes(sp)))
                conn.commit(); st.success("สมัครสำเร็จ!")
            except: st.error("ชื่อนี้มีในระบบแล้ว")
            finally: conn.close()
else:
    # หน้าหลักแอป
    user_now = st.session_state.username
    update_active_status(user_now)
    
    conn = get_connection()
    u_info = pd.read_sql_query('SELECT * FROM users WHERE username=?', conn, params=(user_now,)).iloc[0]
    my_trips = pd.read_sql_query('''
        SELECT DISTINCT t.* FROM trips t 
        LEFT JOIN trip_members m ON t.id = m.trip_id 
        WHERE t.created_by = ? OR m.username = ?
    ''', conn, params=(user_now, user_now))
    notis = pd.read_sql_query('SELECT * FROM notifications WHERE receiver=? ORDER BY id DESC LIMIT 10', conn, params=(user_now,))
    conn.close()

    # Sidebar
    st.sidebar.title(f"👤 {user_now}")
    if u_info['profile_pic'] and os.path.exists(str(u_info['profile_pic'])):
        st.sidebar.image(u_info['profile_pic'], width=100)
    
    unread = len(notis[notis['is_read'] == 0])
    noti_label = f"🔔 แจ้งเตือน ({unread})" if unread > 0 else "🔔 แจ้งเตือน"
    menu = st.sidebar.radio("เมนู", [noti_label, "🧳 ทริปของฉัน", "➕ สร้างทริป", "⚙️ โปรไฟล์"])
    
    if st.sidebar.button("Logout"):
        st.session_state.username = None
        st.rerun()

    # --- เมนู: แจ้งเตือน ---
    if "🔔" in menu:
        st.header("🔔 การแจ้งเตือน")
        if notis.empty: st.info("ไม่มีข้อความ")
        else:
            for _, n in notis.iterrows():
                st.markdown(f"**[{n['created_at']}]** {n['message']}")
            if st.button("อ่านแล้วทั้งหมด"):
                conn = get_connection(); conn.cursor().execute('UPDATE notifications SET is_read=1 WHERE receiver=?', (user_now,)); conn.commit(); conn.close(); st.rerun()

    # --- เมนู: ทริปของฉัน ---
    elif menu == "🧳 ทริปของฉัน":
        if my_trips.empty: st.info("คุณยังไม่มีทริป")
        else:
            sel_trip = st.selectbox("เลือกทริป", my_trips['name'].tolist())
            t_row = my_trips[my_trips['name'] == sel_trip].iloc[0]
            t_id = t_row['id']
            is_admin = (t_row['created_by'] == user_now)

            tab1, tab2, tab3 = st.tabs(["📝 รายจ่าย", "📊 สรุปยอด", "👥 สมาชิก & สถานะ"])

            with tab1:
                with st.form("add_exp"):
                    c1, c2 = st.columns(2)
                    ttype = c1.selectbox("ประเภท", ["รายจ่าย", "รายรับ"])
                    amt = c2.number_input("จำนวนเงิน", min_value=0.0)
                    cat = st.selectbox("หมวดหมู่", ["อาหาร", "เดินทาง", "ที่พัก", "ช้อปปิ้ง", "อื่นๆ"])
                    note = st.text_area("หมายเหตุ")
                    bill = st.file_uploader("แนบสลิป", type=['jpg','png'])
                    if st.form_submit_button("บันทึก"):
                        b_path = save_file(bill, BILL_DIR, "bill")
                        conn = get_connection()
                        conn.cursor().execute('INSERT INTO transactions(date,type,category,amount,note,bill_path,trip_id,created_by) VALUES (?,?,?,?,?,?,?,?)',
                                              (datetime.now().strftime("%Y-%m-%d"), ttype, cat, amt, note, b_path, t_id, user_now))
                        # แจ้งเตือนเพื่อนทุกคนในทริป
                        m_list = conn.cursor().execute('SELECT username FROM trip_members WHERE trip_id=? AND username!=?', (t_id, user_now)).fetchall()
                        for m in m_list: send_notify(m[0], f"💰 {user_now} อัปเดต {ttype} ฿{amt:,.2f} ใน {sel_trip}")
                        conn.commit(); conn.close(); st.success("บันทึกแล้ว!"); st.rerun()

            with tab2:
                conn = get_connection()
                df = pd.read_sql_query('SELECT * FROM transactions WHERE trip_id=?', conn, params=(t_id,))
                conn.close()
                exp = df[df['type']=='รายจ่าย']['amount'].sum()
                st.subheader(f"💰 งบประมาณคงเหลือ: ฿{t_row['budget'] - exp:,.2f}")
                st.divider()
                for _, r in df.iterrows():
                    with st.expander(f"{r['date']} - {r['category']} (฿{r['amount']:,.2f})"):
                        c_a, c_b = st.columns([2,1])
                        c_a.write(f"โดย: {r['created_by']}\n\nโน้ต: {r['note']}")
                        if r['bill_path']: c_b.image(r['bill_path'])
                        if st.button("🗑️ ลบรายการ", key=f"del_{r['id']}"):
                            conn = get_connection(); conn.cursor().execute('DELETE FROM transactions WHERE id=?', (r['id'],)); conn.commit(); conn.close(); st.rerun()

            with tab3:
                st.subheader("👥 สมาชิกและสถานะออนไลน์")
                conn = get_connection()
                m_status = pd.read_sql_query('''
                    SELECT u.username, u.last_active, u.profile_pic FROM trip_members tm
                    JOIN users u ON tm.username = u.username
                    WHERE tm.trip_id = ?
                ''', conn, params=(t_id,))
                
                for _, row in m_status.iterrows():
                    dot = get_status_dot(row['last_active'])
                    c_m1, c_m2 = st.columns([4,1])
                    c_m1.write(f"{dot} **{row['username']}**")
                    if is_admin and row['username'] != user_now:
                        if c_m2.button("เตะออก", key=f"k_{row['username']}"):
                            conn.cursor().execute('DELETE FROM trip_members WHERE trip_id=? AND username=?', (t_id, row['username']))
                            send_notify(row['username'], f"❌ คุณถูกนำออกจากทริป {sel_trip}")
                            conn.commit(); conn.close(); st.rerun()
                
                if is_admin:
                    st.divider()
                    st.subheader("✉️ เชิญเพื่อน")
                    all_u = pd.read_sql_query('SELECT username FROM users', conn)['username'].tolist()
                    invite_list = [u for u in all_u if u not in m_status['username'].tolist()]
                    friend = st.selectbox("เลือกเพื่อนที่จะเชิญ", invite_list)
                    if st.button("ส่งคำเชิญ"):
                        conn.cursor().execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (t_id, friend))
                        conn.commit()
                        send_notify(friend, f"✉️ {user_now} เชิญคุณเข้าร่วมทริป '{sel_trip}'")
                        conn.close()
                        st.success(f"เชิญ {friend} สำเร็จ!"); st.rerun()

    elif menu == "➕ สร้างทริป":
        st.header("➕ สร้างทริปใหม่")
        with st.form("create_t"):
            name = st.text_input("ชื่อทริป")
            bud = st.number_input("งบประมาณรวม", min_value=0.0)
            if st.form_submit_button("สร้าง"):
                conn = get_connection(); cur = conn.cursor()
                cur.execute('INSERT INTO trips(name, budget, created_by, created_at) VALUES (?,?,?,?)', (name, bud, user_now, datetime.now().strftime("%Y-%m-%d")))
                cur.execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (cur.lastrowid, user_now))
                conn.commit(); conn.close(); st.success("สร้างทริปสำเร็จ!"); st.rerun()

    elif menu == "⚙️ โปรไฟล์":
        st.header("⚙️ ตั้งค่าโปรไฟล์")
        img = st.file_uploader("เปลี่ยนรูปโปรไฟล์", type=['jpg','png'])
        if st.button("บันทึก") and img:
            p_path = save_file(img, PROFILE_DIR, f"p_{user_now}")
            conn = get_connection(); conn.cursor().execute('UPDATE users SET profile_pic=? WHERE username=?', (p_path, user_now)); conn.commit(); conn.close(); st.rerun()
