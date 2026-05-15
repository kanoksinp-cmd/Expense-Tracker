import streamlit as st
import pandas as pd
import sqlite3
import os
import hashlib
from datetime import datetime, timedelta
import plotly.express as px

# --- 1. ตั้งค่าฐานข้อมูลและ Migration ---
DB_FILE = 'expense_tracker.db'
BILL_DIR = "bills"

if not os.path.exists(BILL_DIR):
    os.makedirs(BILL_DIR)

def get_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, profile_pic TEXT, last_active TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, budget REAL, created_by TEXT, created_at TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS trip_members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, username TEXT, status TEXT DEFAULT "accepted")')
        c.execute('CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, category TEXT, amount REAL, note TEXT, bill_path TEXT, created_by TEXT, trip_id INTEGER)')
        c.execute('CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, receiver TEXT, message TEXT, is_read INTEGER DEFAULT 0, created_at TEXT)')
        
        # ตรวจสอบคอลัมน์ status
        try:
            c.execute('SELECT status FROM trip_members LIMIT 1')
        except sqlite3.OperationalError:
            c.execute('ALTER TABLE trip_members ADD COLUMN status TEXT DEFAULT "accepted"')
        conn.commit()

init_db()

# --- 2. ฟังก์ชันเสริมและ Callbacks ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def send_notification(receiver, msg, conn=None):
    local_conn = conn if conn else get_connection()
    now = datetime.now().strftime("%H:%M")
    local_conn.cursor().execute('INSERT INTO notifications(receiver, message, created_at) VALUES (?,?,?)', (receiver, msg, now))
    if not conn:
        local_conn.commit()

def accept_trip_callback(row_id, trip_name, creator, username):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('UPDATE trip_members SET status="accepted" WHERE id=?', (row_id,))
        send_notification(creator, f"🤝 {username} ตอบรับเข้าร่วมทริป '{trip_name}' แล้ว!", conn=conn)
        conn.commit()
    st.session_state.menu_selection = "🧳 ทริปของฉัน"
    st.session_state.current_trip_name = trip_name
    st.toast(f"เข้าสู่ทริป {trip_name} แล้ว!", icon="✅")

def reject_trip_callback(row_id, trip_name, creator, username):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('DELETE FROM trip_members WHERE id=?', (row_id,))
        send_notification(creator, f"👎 {username} ปฏิเสธทริป '{trip_name}'", conn=conn)
        conn.commit()
    st.toast("ปฏิเสธคำเชิญแล้ว")

# --- 3. ส่วนประกอบ UI ---
st.set_page_config(page_title="Trip Expense Master", layout="wide")

if 'username' not in st.session_state: st.session_state.username = None
if 'menu_selection' not in st.session_state: st.session_state.menu_selection = "🔔 แจ้งเตือน"
if 'current_trip_name' not in st.session_state: st.session_state.current_trip_name = None

# ระบบ Login
if not st.session_state.username:
    st.title("💰 Trip Expense Tracker")
    tab_l, tab_r = st.tabs(["เข้าสู่ระบบ", "สมัครสมาชิก"])
    with tab_l:
        u = st.text_input("Username", key="l_u")
        p = st.text_input("Password", type='password', key="l_p")
        if st.button("Login"):
            with get_connection() as conn:
                res = conn.cursor().execute('SELECT password FROM users WHERE username=?', (u,)).fetchone()
            if res and res[0] == make_hashes(p):
                st.session_state.username = u
                st.rerun()
            else: st.error("ผิดพลาด")
    with tab_r:
        su = st.text_input("ชื่อผู้ใช้", key="r_u")
        sp = st.text_input("รหัสผ่าน", type='password', key="r_p")
        if st.button("Register"):
            with get_connection() as conn:
                try:
                    conn.cursor().execute('INSERT INTO users(username, password) VALUES (?,?)', (su, make_hashes(sp)))
                    conn.commit()
                    st.success("สำเร็จ!")
                except: st.error("ชื่อนี้มีแล้ว")

else:
    user_now = st.session_state.username
    
    # ดึงข้อมูลคำเชิญที่รอการตอบรับ (Pending) **จุดที่แก้ให้ปุ่มขึ้น**
    with get_connection() as conn:
        pending_trips = pd.read_sql_query('''
            SELECT tm.id as member_row_id, t.name, t.created_by, t.budget 
            FROM trip_members tm
            JOIN trips t ON tm.trip_id = t.id
            WHERE tm.username = ? AND tm.status = 'pending'
        ''', conn, params=(user_now,))
        
        notis = pd.read_sql_query('SELECT * FROM notifications WHERE receiver=? ORDER BY id DESC LIMIT 10', conn, params=(user_now,))
        
        my_trips = pd.read_sql_query('''
            SELECT * FROM trips WHERE id IN (SELECT trip_id FROM trip_members WHERE username=? AND status='accepted')
        ''', conn, params=(user_now,))

    # Sidebar
    st.sidebar.title(f"👤 {user_now}")
    total_alerts = len(pending_trips)
    noti_label = f"🔔 แจ้งเตือน ({total_alerts})" if total_alerts > 0 else "🔔 แจ้งเตือน"
    
    menu_list = [noti_label, "🧳 ทริปของฉัน", "➕ สร้างทริปใหม่"]
    
    # แก้ไขปัญหา index ไม่ตรงเมื่อ label เปลี่ยน
    current_idx = 0
    if st.session_state.menu_selection == "🧳 ทริปของฉัน": current_idx = 1
    elif st.session_state.menu_selection == "➕ สร้างทริปใหม่": current_idx = 2

    menu = st.sidebar.radio("เมนู", menu_list, index=current_idx)
    st.session_state.menu_selection = menu.split(" (")[0] # เก็บแค่ชื่อเมนูหลัก

    if st.sidebar.button("Log out"):
        st.session_state.username = None
        st.rerun()

    # --- หน้าแจ้งเตือน ---
    if "🔔" in menu:
        st.header("🔔 การแจ้งเตือนและคำเชิญทริป")
        
        # ส่วนที่ 1: กล่องคำเชิญ (ต้องมีปุ่มกดยอมรับ)
        if not pending_trips.empty:
            st.subheader("✉️ คำเชิญใหม่")
            for _, p in pending_trips.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([5, 2, 1.5])
                    c1.markdown(f"**{p['created_by']}** เชิญคุณเข้าร่วมทริป **'{p['name']}'**\n(งบประมาณ: ฿{p['budget']:,.2f})")
                    c2.button("✅ ตอบรับและเข้าทริป", key=f"acc_{p['member_row_id']}", 
                              on_click=accept_trip_callback, args=(p['member_row_id'], p['name'], p['created_by'], user_now))
                    c3.button("❌ ปฏิเสธ", key=f"rej_{p['member_row_id']}", 
                              on_click=reject_trip_callback, args=(p['member_row_id'], p['name'], p['created_by'], user_now))
            st.divider()

        # ส่วนที่ 2: ประวัติ (แบบในรูปของคุณ)
        st.subheader("💬 ประวัติการแจ้งเตือนล่าสุด")
        if notis.empty:
            st.info("ไม่มีประวัติการแจ้งเตือน")
        else:
            for _, n in notis.iterrows():
                st.write(f"[{n['created_at']}] {n['message']}")

    # --- หน้าทริปของฉัน ---
    elif "🧳" in menu:
        if my_trips.empty:
            st.warning("คุณยังไม่มีทริป กรุณาสร้างทริปใหม่หรือรอเพื่อนเชิญ")
        else:
            trip_names = my_trips['name'].tolist()
            if st.session_state.current_trip_name not in trip_names:
                st.session_state.current_trip_name = trip_names[0]
            
            sel_trip = st.selectbox("เลือกทริป", trip_names, index=trip_names.index(st.session_state.current_trip_name))
            st.session_state.current_trip_name = sel_trip
            
            t_row = my_trips[my_trips['name'] == sel_trip].iloc[0]
            t_id = t_row['id']
            
            tab1, tab2, tab3 = st.tabs(["📝 รายจ่าย", "📊 สรุป", "👥 สมาชิก"])
            
            with tab1:
                with st.form("exp_form", clear_on_submit=True):
                    amt = st.number_input("จำนวนเงิน", min_value=0.0)
                    cat = st.selectbox("หมวดหมู่", ["อาหาร", "เดินทาง", "ที่พัก", "อื่นๆ"])
                    note = st.text_input("โน้ต")
                    if st.form_submit_button("บันทึก"):
                        with get_connection() as conn:
                            conn.cursor().execute('INSERT INTO transactions(date, type, category, amount, note, created_by, trip_id) VALUES (?,?,?,?,?,?,?)',
                                                 (datetime.now().strftime("%Y-%m-%d"), "รายจ่าย", cat, amt, note, user_now, t_id))
                            conn.commit()
                        st.success("บันทึกแล้ว")
                        st.rerun()

            with tab2:
                with get_connection() as conn:
                    df = pd.read_sql_query('SELECT * FROM transactions WHERE trip_id=?', conn, params=(t_id,))
                if not df.empty:
                    st.metric("ยอดรวมรายจ่าย", f"฿{df['amount'].sum():,.2f}")
                    st.dataframe(df[['date', 'category', 'amount', 'created_by', 'note']], use_container_width=True)
                    fig = px.pie(df, values='amount', names='category', title="สัดส่วนรายจ่าย")
                    st.plotly_chart(fig)
                else:
                    st.info("ยังไม่มีข้อมูล")

            with tab3:
                with get_connection() as conn:
                    m_df = pd.read_sql_query('SELECT username, status FROM trip_members WHERE trip_id=?', conn, params=(t_id,))
                st.write("สมาชิกในกลุ่ม:")
                for _, m in m_df.iterrows():
                    st.write(f"- {m['username']} ({'✅ เข้าร่วมแล้ว' if m['status']=='accepted' else '⏱️ รอการตอบรับ'})")
                
                if t_row['created_by'] == user_now:
                    st.divider()
                    target_user = st.text_input("เชิญเพื่อน (ระบุ Username)")
                    if st.button("ส่งคำเชิญ"):
                        with get_connection() as conn:
                            check = conn.cursor().execute('SELECT * FROM users WHERE username=?', (target_user,)).fetchone()
                            if check:
                                conn.cursor().execute('INSERT INTO trip_members(trip_id, username, status) VALUES (?,?,?)', (t_id, target_user, 'pending'))
                                send_notification(target_user, f"✉️ {user_now} เชิญคุณเข้าร่วมทริป '{sel_trip}' (กรุณากดตอบรับเพื่อเริ่มใช้งาน)", conn=conn)
                                conn.commit()
                                st.success(f"ส่งคำเชิญให้ {target_user} แล้ว")
                            else: st.error("ไม่พบผู้ใช้งานนี้")

    # --- หน้าสร้างทริป ---
    elif "➕" in menu:
        st.header("➕ สร้างทริปใหม่")
        with st.form("new_trip"):
            name = st.text_input("ชื่อทริป")
            bud = st.number_input("งบประมาณ", min_value=0.0)
            if st.form_submit_button("สร้าง"):
                with get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute('INSERT INTO trips(name, budget, created_by, created_at) VALUES (?,?,?,?)', (name, bud, user_now, datetime.now().strftime("%Y-%m-%d")))
                    new_id = cur.lastrowid
                    cur.execute('INSERT INTO trip_members(trip_id, username, status) VALUES (?,?,?)', (new_id, user_now, 'accepted'))
                    conn.commit()
                st.success("สร้างทริปสำเร็จ!")
                st.session_state.menu_selection = "🧳 ทริปของฉัน"
                st.rerun()
