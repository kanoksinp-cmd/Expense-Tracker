import streamlit as st
import pandas as pd
import sqlite3
import os
import hashlib
from datetime import datetime, timedelta
import plotly.express as px

# --- 1. ตั้งค่าฐานข้อมูลและโฟลเดอร์ ---
DB_FILE = 'expense_tracker.db'
BILL_DIR = "bills"

if not os.path.exists(BILL_DIR):
    os.makedirs(BILL_DIR)

def get_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, last_active TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, budget REAL, created_by TEXT, created_at TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS trip_members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, username TEXT, status TEXT DEFAULT "accepted")')
        c.execute('CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, category TEXT, amount REAL, note TEXT, bill_path TEXT, created_by TEXT, trip_id INTEGER)')
        c.execute('CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, receiver TEXT, message TEXT, is_read INTEGER DEFAULT 0, created_at TEXT)')
        conn.commit()

init_db()

# --- 2. ฟังก์ชันเสริม ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def update_online_status(username):
    if username:
        with get_connection() as conn:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.cursor().execute('UPDATE users SET last_active=? WHERE username=?', (now, username))
            conn.commit()

def get_status_icon(last_active_str):
    if not last_active_str: return "⚪ ออฟไลน์"
    try:
        last_dt = datetime.strptime(last_active_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() - last_dt < timedelta(minutes=5):
            return "🟢 ออนไลน์"
    except: pass
    return "⚪ ออฟไลน์"

def send_notification(receiver, msg, conn=None):
    local_conn = conn if conn else get_connection()
    now = datetime.now().strftime("%H:%M")
    local_conn.cursor().execute('INSERT INTO notifications(receiver, message, created_at) VALUES (?,?,?)', (receiver, msg, now))
    if not conn: local_conn.commit()

# --- 3. UI ระบบ Login ---
st.set_page_config(page_title="Trip Expense Master", layout="wide")

if 'username' not in st.session_state: st.session_state.username = None
if 'menu_selection' not in st.session_state: st.session_state.menu_selection = "🧳 ทริปของฉัน"
if 'current_trip_name' not in st.session_state: st.session_state.current_trip_name = None

if not st.session_state.username:
    st.title("💰 Trip Expense Tracker")
    tab_l, tab_r = st.tabs(["เข้าสู่ระบบ", "สมัครสมาชิก"])
    with tab_l:
        u = st.text_input("Username", key="l_u")
        p = st.text_input("Password", type='password', key="l_p")
        if st.button("Login", use_container_width=True):
            with get_connection() as conn:
                res = conn.cursor().execute('SELECT password FROM users WHERE username=?', (u,)).fetchone()
            if res and res[0] == make_hashes(p):
                st.session_state.username = u
                update_online_status(u)
                st.rerun()
            else: st.error("ชื่อหรือรหัสผ่านไม่ถูกต้อง")
    with tab_r:
        su = st.text_input("ชื่อผู้ใช้", key="r_u")
        sp = st.text_input("รหัสผ่าน", type='password', key="r_p")
        if st.button("Register", use_container_width=True):
            with get_connection() as conn:
                try:
                    conn.cursor().execute('INSERT INTO users(username, password) VALUES (?,?)', (su, make_hashes(sp)))
                    conn.commit()
                    st.success("สมัครสมาชิกสำเร็จ!")
                except: st.error("ชื่อนี้มีผู้ใช้งานแล้ว")

else:
    user_now = st.session_state.username
    update_online_status(user_now)
    
    with get_connection() as conn:
        # ดึงเฉพาะทริปที่เข้าร่วมแล้ว (ซึ่งเวอร์ชันนี้จะเข้าร่วมทันทีที่โดนดึง)
        my_trips = pd.read_sql_query('''
            SELECT * FROM trips WHERE id IN (SELECT trip_id FROM trip_members WHERE username=? AND status='accepted')
        ''', conn, params=(user_now,))
        notis = pd.read_sql_query('SELECT * FROM notifications WHERE receiver=? ORDER BY id DESC LIMIT 10', conn, params=(user_now,))

    # Sidebar
    st.sidebar.title(f"👤 {user_now}")
    menu_list = ["🧳 ทริปของฉัน", "🔔 แจ้งเตือน", "➕ สร้างทริปใหม่"]
    menu = st.sidebar.radio("เมนู", menu_list, index=menu_list.index(st.session_state.menu_selection))
    st.session_state.menu_selection = menu

    if st.sidebar.button("Log out"):
        st.session_state.username = None
        st.rerun()

    # --- หน้าทริปของฉัน ---
    if menu == "🧳 ทริปของฉัน":
        if my_trips.empty:
            st.info("ยังไม่มีทริปในขณะนี้ สร้างทริปใหม่หรือรอเพื่อนดึงเข้ากลุ่มได้เลย")
        else:
            trip_names = my_trips['name'].tolist()
            if st.session_state.current_trip_name not in trip_names: st.session_state.current_trip_name = trip_names[0]
            sel_trip = st.selectbox("เลือกทริป", trip_names, index=trip_names.index(st.session_state.current_trip_name))
            st.session_state.current_trip_name = sel_trip
            
            t_row = my_trips[my_trips['name'] == sel_trip].iloc[0]
            t_id = t_row['id']
            
            tab1, tab2, tab3 = st.tabs(["📝 บันทึกรายจ่าย", "📊 สรุปภาพรวม", "👥 สมาชิกทริป"])
            
            with tab1: # รายจ่าย
                with st.form("exp_form", clear_on_submit=True):
                    amt = st.number_input("จำนวนเงิน (บาท)", min_value=0.0)
                    cat = st.selectbox("หมวดหมู่", ["อาหาร", "เดินทาง", "ที่พัก", "ช้อปปิ้ง", "อื่นๆ"])
                    note = st.text_input("รายละเอียด")
                    if st.form_submit_button("บันทึก"):
                        with get_connection() as conn:
                            conn.cursor().execute('INSERT INTO transactions(date, type, category, amount, note, created_by, trip_id) VALUES (?,?,?,?,?,?,?)',
                                                 (datetime.now().strftime("%Y-%m-%d"), "รายจ่าย", cat, amt, note, user_now, t_id))
                            conn.commit()
                        st.success("บันทึกสำเร็จ!")
                        st.rerun()

            with tab2: # สรุป
                with get_connection() as conn:
                    df = pd.read_sql_query('SELECT * FROM transactions WHERE trip_id=?', conn, params=(t_id,))
                if not df.empty:
                    st.metric("ยอดรวมรายจ่ายทริปนี้", f"฿{df['amount'].sum():,.2f}")
                    fig = px.pie(df, values='amount', names='category', hole=0.3)
                    st.plotly_chart(fig, use_container_width=True)
                    st.dataframe(df[['date', 'category', 'amount', 'created_by', 'note']], use_container_width=True)
                else: st.info("ยังไม่มีประวัติการจ่ายเงิน")

            with tab3: # สมาชิก & Auto-Join
                st.subheader("👥 สมาชิกที่อยู่ในทริปนี้")
                with get_connection() as conn:
                    m_df = pd.read_sql_query('''
                        SELECT u.username, u.last_active FROM trip_members tm
                        JOIN users u ON tm.username = u.username WHERE tm.trip_id = ?
                    ''', conn, params=(t_id,))
                
                for _, m in m_df.iterrows():
                    st.write(f"{get_status_icon(m['last_active'])} **{m['username']}**")
                
                if t_row['created_by'] == user_now:
                    st.divider()
                    st.subheader("⚡ ดึงเพื่อนที่ออนไลน์เข้าทริปทันที")
                    five_mins_ago = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
                    with get_connection() as conn:
                        online_f = pd.read_sql_query('''
                            SELECT username FROM users WHERE last_active >= ? AND username != ?
                            AND username NOT IN (SELECT username FROM trip_members WHERE trip_id = ?)
                        ''', conn, params=(five_mins_ago, user_now, t_id))
                    
                    if not online_f.empty:
                        cols = st.columns(3)
                        for idx, f in online_f.iterrows():
                            if cols[idx % 3].button(f"➕ ดึง {f['username']}", key=f"q_{f['username']}"):
                                with get_connection() as conn:
                                    conn.cursor().execute('INSERT INTO trip_members(trip_id, username, status) VALUES (?,?,?)', (t_id, f['username'], 'accepted'))
                                    send_notification(f['username'], f"🚀 {user_now} ดึงคุณเข้าทริป '{sel_trip}' แล้ว", conn=conn)
                                    conn.commit()
                                st.rerun()
                    else: st.info("ไม่มีเพื่อนออนไลน์ในขณะนี้")

                    st.divider()
                    target = st.text_input("🔍 พิมพ์ชื่อเพื่อดึงเข้าทริปทันที")
                    if st.button("ดึงเพื่อนเข้ากลุ่ม"):
                        with get_connection() as conn:
                            exists = conn.cursor().execute('SELECT * FROM users WHERE username=?', (target,)).fetchone()
                            is_in = conn.cursor().execute('SELECT * FROM trip_members WHERE trip_id=? AND username=?', (t_id, target)).fetchone()
                            if exists and not is_in:
                                conn.cursor().execute('INSERT INTO trip_members(trip_id, username, status) VALUES (?,?,?)', (t_id, target, 'accepted'))
                                send_notification(target, f"🚀 {user_now} ดึงคุณเข้าทริป '{sel_trip}'", conn=conn)
                                conn.commit()
                                st.success(f"ดึง {target} สำเร็จ")
                                st.rerun()
                            else: st.error("ไม่พบชื่อผู้ใช้หรืออยู่ในทริปอยู่แล้ว")

    # --- หน้าแจ้งเตือน ---
    elif menu == "🔔 แจ้งเตือน":
        st.header("🔔 ประวัติการแจ้งเตือน")
        if notis.empty: st.info("ไม่มีการแจ้งเตือนใหม่")
        else:
            for _, n in notis.iterrows():
                st.write(f"[{n['created_at']}] {n['message']}")

    # --- หน้าสร้างทริป ---
    elif menu == "➕ สร้างทริปใหม่":
        st.header("➕ สร้างทริปใหม่")
        with st.form("n_trip"):
            name = st.text_input("ชื่อทริป")
            bud = st.number_input("งบประมาณรวม", min_value=0.0)
            if st.form_submit_button("ยืนยันสร้างทริป"):
                if name:
                    with get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute('INSERT INTO trips(name, budget, created_by, created_at) VALUES (?,?,?,?)', (name, bud, user_now, datetime.now().strftime("%Y-%m-%d")))
                        new_id = cur.lastrowid
                        cur.execute('INSERT INTO trip_members(trip_id, username, status) VALUES (?,?,?)', (new_id, user_now, 'accepted'))
                        conn.commit()
                    st.session_state.menu_selection = "🧳 ทริปของฉัน"
                    st.session_state.current_trip_name = name
                    st.rerun()
