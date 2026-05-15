import streamlit as st
import pandas as pd
import sqlite3
import hashlib
from datetime import datetime, timedelta
import plotly.express as px

# --- 1. ตั้งค่าฐานข้อมูล ---
DB_FILE = 'expense_tracker.db'

def get_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, last_active TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, budget REAL, created_by TEXT, created_at TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS trip_members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, username TEXT, status TEXT DEFAULT "accepted")')
        c.execute('CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, category TEXT, amount REAL, note TEXT, created_by TEXT, trip_id INTEGER)')
        c.execute('CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, receiver TEXT, message TEXT, is_read INTEGER DEFAULT 0, created_at TEXT)')
        conn.commit()

init_db()

# --- 2. ฟังก์ชันช่วยจัดการ (Helper Functions) ---
def update_online_status(username):
    if username:
        with get_connection() as conn:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.cursor().execute('UPDATE users SET last_active=? WHERE username=?', (now, username))
            conn.commit()

def send_notification(receiver, msg):
    with get_connection() as conn:
        now = datetime.now().strftime("%H:%M")
        conn.cursor().execute('INSERT INTO notifications(receiver, message, created_at) VALUES (?,?,?)', (receiver, msg, now))
        conn.commit()

def get_status_icon(last_active_str):
    if not last_active_str: return "⚪"
    try:
        last_dt = datetime.strptime(last_active_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() - last_dt < timedelta(minutes=5): return "🟢"
    except: pass
    return "⚪"

# --- 3. ระบบหน้าจอหลัก ---
st.set_page_config(page_title="Trip Expense Master", layout="wide")

if 'username' not in st.session_state: st.session_state.username = None
if 'current_trip_name' not in st.session_state: st.session_state.current_trip_name = None

# ส่วนของ Login / Register
if not st.session_state.username:
    st.title("💰 Trip Expense Master")
    tab_login, tab_reg = st.tabs(["เข้าสู่ระบบ", "สมัครสมาชิก"])
    
    with tab_login:
        u = st.text_input("Username", key="login_u")
        p = st.text_input("Password", type='password', key="login_p")
        if st.button("Login", use_container_width=True):
            with get_connection() as conn:
                res = conn.cursor().execute('SELECT password FROM users WHERE username=?', (u,)).fetchone()
            if res and res[0] == hashlib.sha256(str.encode(p)).hexdigest():
                st.session_state.username = u
                update_online_status(u)
                st.rerun()
            else: st.error("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
            
    with tab_reg:
        su = st.text_input("Username", key="reg_u")
        sp = st.text_input("Password", type='password', key="reg_p")
        if st.button("สมัครสมาชิก", use_container_width=True):
            with get_connection() as conn:
                try:
                    conn.cursor().execute('INSERT INTO users(username, password) VALUES (?,?)', (su, hashlib.sha256(str.encode(sp)).hexdigest()))
                    conn.commit()
                    st.success("สมัครสมาชิกสำเร็จ! กรุณาไปที่หน้าเข้าสู่ระบบ")
                except: st.error("ชื่อนี้มีผู้ใช้งานแล้ว")

else:
    user_now = st.session_state.username
    update_online_status(user_now)

    # ดึงข้อมูลทริปทั้งหมดที่เราเป็นสมาชิก (ใช้ Case-Insensitive)
    with get_connection() as conn:
        my_trips_df = pd.read_sql_query('''
            SELECT t.* FROM trips t
            JOIN trip_members tm ON t.id = tm.trip_id
            WHERE LOWER(tm.username) = LOWER(?)
        ''', conn, params=(user_now,))
        
        unread_notis = pd.read_sql_query('SELECT * FROM notifications WHERE receiver=? AND is_read=0', conn, params=(user_now,))

    # แสดง Notification แบบ Toast
    if not unread_notis.empty:
        for _, n in unread_notis.iterrows():
            st.toast(n['message'], icon="📢")
        with get_connection() as conn:
            conn.cursor().execute('UPDATE notifications SET is_read=1 WHERE receiver=?', (user_now,))
            conn.commit()

    # Sidebar เมนู
    st.sidebar.header(f"👤 {user_now}")
    menu = st.sidebar.radio("เมนูหลัก", ["🧳 ทริปของฉัน", "➕ สร้างทริปใหม่", "🔔 แจ้งเตือน"])
    if st.sidebar.button("ออกจากระบบ"):
        st.session_state.username = None
        st.rerun()

    # --- หน้า 1: ทริปของฉัน ---
    if menu == "🧳 ทริปของฉัน":
        if my_trips_df.empty:
            st.info("คุณยังไม่มีทริปในตอนนี้")
            if st.button("🔄 รีเฟรชเช็คทริปใหม่"): st.rerun()
        else:
            trip_list = my_trips_df['name'].tolist()
            if st.session_state.current_trip_name not in trip_list:
                st.session_state.current_trip_name = trip_list[0]
            
            sel_trip = st.selectbox("เลือกทริปที่ต้องการจัดการ", trip_list, 
                                    index=trip_list.index(st.session_state.current_trip_name))
            st.session_state.current_trip_name = sel_trip
            
            t_data = my_trips_df[my_trips_df['name'] == sel_trip].iloc[0]
            t_id = t_data['id']
            is_owner = (t_data['created_by'] == user_now)

            tab1, tab2, tab3 = st.tabs(["📝 บันทึกรายจ่าย", "📊 สรุปยอด", "👥 สมาชิกและการจัดการ"])

            with tab1:
                with st.form("expense_form", clear_on_submit=True):
                    amt = st.number_input("จำนวนเงิน (บาท)", min_value=0.0)
                    cat = st.selectbox("หมวดหมู่", ["อาหาร", "เดินทาง", "ที่พัก", "ช้อปปิ้ง", "อื่นๆ"])
                    note = st.text_input("หมายเหตุ")
                    if st.form_submit_button("บันทึก"):
                        with get_connection() as conn:
                            conn.cursor().execute('INSERT INTO transactions(date, category, amount, note, created_by, trip_id) VALUES (?,?,?,?,?,?)',
                                                 (datetime.now().strftime("%Y-%m-%d"), cat, amt, note, user_now, t_id))
                            conn.commit()
                        st.success("บันทึกรายจ่ายแล้ว!")
                        st.rerun()

            with tab2:
                with get_connection() as conn:
                    tx_df = pd.read_sql_query('SELECT * FROM transactions WHERE trip_id=?', conn, params=(t_id,))
                if not tx_df.empty:
                    st.subheader(f"รวมยอดจ่ายทั้งหมด: ฿{tx_df['amount'].sum():,.2f}")
                    fig = px.pie(tx_df, values='amount', names='category', hole=0.3)
                    st.plotly_chart(fig, use_container_width=True)
                    st.dataframe(tx_df[['date', 'category', 'amount', 'created_by', 'note']], use_container_width=True)
                else: st.info("ยังไม่มีรายการใช้จ่าย")

            with tab3:
                st.subheader("👥 สมาชิกในกลุ่ม")
                with get_connection() as conn:
                    m_list = pd.read_sql_query('''
                        SELECT u.username, u.last_active FROM trip_members tm
                        JOIN users u ON tm.username = u.username WHERE tm.trip_id = ?
                    ''', conn, params=(t_id,))
                
                for _, m in m_list.iterrows():
                    c1, c2 = st.columns([4, 1])
                    c1.write(f"{get_status_icon(m['last_active'])} **{m['username']}** {'(หัวหน้าทริป)' if m['username'] == t_data['created_by'] else ''}")
                    if is_owner and m['username'] != user_now:
                        if c2.button("ลบสมาชิก", key=f"kick_{m['username']}"):
                            with get_connection() as conn:
                                conn.cursor().execute('DELETE FROM trip_members WHERE trip_id=? AND username=?', (t_id, m['username']))
                                conn.commit()
                            send_notification(m['username'], f"❌ คุณถูกลบออกจากทริป '{sel_trip}'")
                            st.rerun()

                if is_owner:
                    st.divider()
                    st.subheader("➕ ดึงเพื่อนเข้าทริป (ไม่ต้องรอรับ)")
                    
                    # ค้นหาคนออนไลน์
                    five_mins = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
                    with get_connection() as conn:
                        on_users = pd.read_sql_query('''
                            SELECT username FROM users WHERE last_active >= ? AND username != ?
                            AND username NOT IN (SELECT username FROM trip_members WHERE trip_id = ?)
                        ''', conn, params=(five_mins, user_now, t_id))
                    
                    if not on_users.empty:
                        st.write("เพื่อนที่กำลังออนไลน์:")
                        cols = st.columns(3)
                        for i, row in on_users.iterrows():
                            if cols[i%3].button(f"➕ {row['username']}", key=f"inv_{row['username']}"):
                                with get_connection() as conn:
                                    conn.cursor().execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (t_id, row['username']))
                                    conn.commit()
                                    send_notification(row['username'], f"🚀 คุณถูกดึงเข้าทริป '{sel_trip}' แล้ว!")
                                st.rerun()
                    
                    target = st.text_input("ค้นหา Username เพื่อนเพื่อดึงเข้ากลุ่ม")
                    if st.button("ดึงเข้ากลุ่มทันที"):
                        with get_connection() as conn:
                            found = conn.cursor().execute('SELECT username FROM users WHERE LOWER(username) = LOWER(?)', (target,)).fetchone()
                            if found:
                                conn.cursor().execute('INSERT OR IGNORE INTO trip_members(trip_id, username) VALUES (?,?)', (t_id, found[0]))
                                conn.commit()
                                send_notification(found[0], f"🚀 คุณถูกดึงเข้าทริป '{sel_trip}'")
                                st.success(f"ดึง {found[0]} เข้าทริปแล้ว!")
                                st.rerun()
                            else: st.error("ไม่พบชื่อผู้ใช้นี้")

    # --- หน้า 2: สร้างทริป ---
    elif menu == "➕ สร้างทริปใหม่":
        st.header("➕ สร้างทริปใหม่")
        with st.form("create_trip"):
            t_name = st.text_input("ชื่อทริป")
            t_bud = st.number_input("งบประมาณ (บาท)", min_value=0.0)
            if st.form_submit_button("ตกลงสร้างทริป"):
                if t_name:
                    with get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute('INSERT INTO trips(name, budget, created_by) VALUES (?,?,?)', (t_name, t_bud, user_now))
                        new_id = cur.lastrowid
                        cur.execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (new_id, user_now))
                        conn.commit()
                    st.session_state.current_trip_name = t_name
                    st.session_state.menu_selection = "🧳 ทริปของฉัน"
                    st.rerun()
                else: st.error("กรุณาใส่ชื่อทริป")

    # --- หน้า 3: แจ้งเตือน ---
    elif menu == "🔔 แจ้งเตือน":
        st.header("🔔 ประวัติการแจ้งเตือน")
        with get_connection() as conn:
            all_notis = pd.read_sql_query('SELECT * FROM notifications WHERE receiver=? ORDER BY id DESC LIMIT 20', conn, params=(user_now,))
        if all_notis.empty: st.info("ไม่มีการแจ้งเตือน")
        else:
            for _, n in all_notis.iterrows():
                st.write(f"[{n['created_at']}] {n['message']}")
