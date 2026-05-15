import streamlit as st
import pandas as pd
import sqlite3
import os
import hashlib
from datetime import datetime, timedelta
import plotly.express as px

# --- 1. ตั้งค่าฐานข้อมูลและระบบ Auto-Migration ---
DB_FILE = 'expense_tracker.db'
BILL_DIR = "bills"
PROFILE_DIR = "profiles"

for folder in [BILL_DIR, PROFILE_DIR]:
    if not os.path.exists(folder):
        os.makedirs(folder)

def get_connection():
    # เพิ่ม timeout เพื่อลดโอกาสเกิด Database is locked
    return sqlite3.connect(DB_FILE, check_same_thread=False, timeout=20)

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
    
    # Migration: ตรวจสอบคอลัมน์ที่อาจตกหล่น
    cols = [('users', 'last_active', 'TEXT'), ('transactions', 'created_by', 'TEXT'), ('transactions', 'bill_path', 'TEXT')]
    for table, col, col_type in cols:
        try:
            c.execute(f'SELECT {col} FROM {table} LIMIT 1')
        except sqlite3.OperationalError:
            c.execute(f'ALTER TABLE {table} ADD COLUMN {col} {col_type}')
            
    conn.commit()
    conn.close()

init_db()

# --- 2. ฟังก์ชันเสริม ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def update_online_status(username):
    if username:
        conn = get_connection()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.cursor().execute('UPDATE users SET last_active=? WHERE username=?', (now, username))
        conn.commit()
        conn.close()

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
    if not conn:
        local_conn.commit()
        local_conn.close()

# --- 3. UI หน้า Login / Register ---
st.set_page_config(page_title="Trip Expense Master", layout="wide")

if 'username' not in st.session_state:
    st.session_state.username = None
if 'editing_tx_id' not in st.session_state:
    st.session_state.editing_tx_id = None

if not st.session_state.username:
    st.title("💰 Trip Expense Tracker")
    tab_l, tab_r = st.tabs(["เข้าสู่ระบบ", "สมัครสมาชิก"])
    with tab_l:
        u = st.text_input("Username", key="login_u")
        p = st.text_input("Password", type='password', key="login_p")
        if st.button("Login", use_container_width=True):
            conn = get_connection()
            res = conn.cursor().execute('SELECT password FROM users WHERE username=?', (u,)).fetchone()
            conn.close()
            if res and res[0] == make_hashes(p):
                st.session_state.username = u
                update_online_status(u)
                st.cache_data.clear() # ล้าง Cache เมื่อ Login
                st.rerun()
            else: st.error("ชื่อหรือรหัสผ่านไม่ถูกต้อง")
    with tab_r:
        su = st.text_input("ชื่อผู้ใช้", key="reg_u")
        sp = st.text_input("รหัสผ่าน", type='password', key="reg_p")
        if st.button("Register", use_container_width=True):
            conn = get_connection()
            try:
                conn.cursor().execute('INSERT INTO users(username, password) VALUES (?,?)', (su, make_hashes(sp)))
                conn.commit(); st.success("สมัครสำเร็จ! กรุณาเข้าสู่ระบบ")
            except: st.error("ชื่อนี้มีผู้ใช้งานแล้ว")
            finally: conn.close()

# --- 4. UI ระบบหลัง Login ---
else:
    user_now = st.session_state.username
    update_online_status(user_now)
    
    # ดึงข้อมูลทริปโดยใช้ INNER JOIN เพื่อความแม่นยำว่าสมาชิกต้องอยู่ในทริปนั้นจริง
    conn = get_connection()
    my_trips = pd.read_sql_query('''
        SELECT t.* FROM trips t
        INNER JOIN trip_members tm ON t.id = tm.trip_id
        WHERE tm.username = ?
    ''', conn, params=(user_now,))
    
    notis = pd.read_sql_query('SELECT * FROM notifications WHERE receiver=? ORDER BY id DESC LIMIT 10', conn, params=(user_now,))
    conn.close()

    # Sidebar
    st.sidebar.title(f"👤 {user_now}")
    unread_count = len(notis[notis['is_read'] == 0])
    noti_text = f"🔔 แจ้งเตือน ({unread_count})" if unread_count > 0 else "🔔 แจ้งเตือน"
    menu = st.sidebar.radio("เมนู", [noti_text, "🧳 ทริปของฉัน", "➕ สร้างทริปใหม่"])
    
    if st.sidebar.button("Log out"):
        st.session_state.username = None
        st.cache_data.clear()
        st.rerun()

    # --- หน้าแจ้งเตือน ---
    if "🔔" in menu:
        st.header("🔔 แจ้งเตือนล่าสุด")
        if notis.empty: st.info("ไม่มีข้อความ")
        else:
            for _, n in notis.iterrows():
                style = "**" if n['is_read'] == 0 else ""
                st.markdown(f"{style}[{n['created_at']}] {n['message']}{style}")
            if st.button("ทำเครื่องหมายว่าอ่านแล้ว"):
                conn = get_connection(); conn.cursor().execute('UPDATE notifications SET is_read=1 WHERE receiver=?', (user_now,)); conn.commit(); conn.close(); st.rerun()

    # --- หน้าจัดการทริป ---
    elif menu == "🧳 ทริปของฉัน":
        if my_trips.empty: 
            st.info("ℹ️ ไม่พบข้อมูลทริปของคุณในขณะนี้")
            if st.button("🔄 รีเฟรชข้อมูล"):
                st.cache_data.clear()
                st.rerun()
        else:
            trip_options = my_trips['name'].tolist()
            sel_trip = st.selectbox("เลือกทริป", trip_options, index=0)
            
            t_rows = my_trips[my_trips['name'] == sel_trip]
            if not t_rows.empty:
                t_row = t_rows.iloc[0]
                t_id = t_row['id']
                is_creator = (t_row['created_by'] == user_now)

                tab1, tab2, tab3 = st.tabs(["📝 รายจ่าย", "📊 สรุปและวิเคราะห์", "👥 สมาชิก"])

                with tab1:
                    st.subheader("บันทึกรายรับ-รายจ่าย")
                    with st.form("exp_form", clear_on_submit=True):
                        ttype = st.selectbox("ประเภท", ["รายจ่าย", "รายรับ"])
                        amt = st.number_input("จำนวนเงิน (บาท)", min_value=0.0, step=100.0)
                        cat = st.selectbox("หมวดหมู่", ["อาหาร", "เดินทาง", "ที่พัก", "ช้อปปิ้ง", "อื่นๆ"])
                        note = st.text_area("โน้ต/รายละเอียด")
                        uploaded_file = st.file_uploader("📷 แนบรูปใบเสร็จ", type=["jpg", "jpeg", "png"])
                        
                        if st.form_submit_button("บันทึก"):
                            if amt > 0:
                                conn = get_connection(); cur = conn.cursor()
                                cur.execute('INSERT INTO transactions(date,type,category,amount,note,trip_id,created_by) VALUES (?,?,?,?,?,?,?)',
                                            (datetime.now().strftime("%Y-%m-%d"), ttype, cat, amt, note, t_id, user_now))
                                tx_id = cur.lastrowid
                                if uploaded_file:
                                    path = f"{BILL_DIR}/receipt_{tx_id}.png"
                                    with open(path, "wb") as f: f.write(uploaded_file.getbuffer())
                                    cur.execute('UPDATE transactions SET bill_path=? WHERE id=?', (path, tx_id))
                                
                                m_list = cur.execute('SELECT username FROM trip_members WHERE trip_id=? AND username!=?', (t_id, user_now)).fetchall()
                                for m in m_list:
                                    send_notification(m[0], f"💰 {user_now} เพิ่ม {ttype} {cat} ฿{amt:,.2f} ใน {sel_trip}", conn=conn)
                                conn.commit(); conn.close(); st.success("สำเร็จ!"); st.rerun()

                with tab2:
                    conn = get_connection()
                    df = pd.read_sql_query('SELECT * FROM transactions WHERE trip_id=?', conn, params=(t_id,))
                    m_count = conn.cursor().execute('SELECT COUNT(*) FROM trip_members WHERE trip_id=?', (t_id,)).fetchone()[0]
                    conn.close()
                    
                    if df.empty: st.info("ยังไม่มีข้อมูล")
                    else:
                        exp = df[df['type'] == 'รายจ่าย']['amount'].sum()
                        c1, c2, c3 = st.columns(3)
                        c1.metric("งบประมาณ", f"฿{t_row['budget']:,.2f}")
                        c2.metric("จ่ายรวม", f"฿{exp:,.2f}")
                        c3.metric("เฉลี่ยต่อคน", f"฿{exp/m_count:,.2f}" if m_count > 0 else "0")
                        
                        fig = px.pie(df[df['type']=='รายจ่าย'], values='amount', names='category', hole=0.4)
                        st.plotly_chart(fig, use_container_width=True)
                        
                        st.subheader("📋 รายการธุรกรรม")
                        for _, row in df.iterrows():
                            c_txt, c_del = st.columns([7, 1])
                            c_txt.write(f"**{row['date']}** | {row['created_by']} จ่าย {row['category']} **฿{row['amount']:,.2f}** ({row['note']})")
                            if row['created_by'] == user_now or is_creator:
                                if c_del.button("🗑️", key=f"del_{row['id']}"):
                                    conn = get_connection(); conn.cursor().execute('DELETE FROM transactions WHERE id=?', (row['id'],)); conn.commit(); conn.close(); st.rerun()
                        
                        bill_df = df[df['bill_path'].notna()]
                        if not bill_df.empty:
                            st.divider()
                            st.subheader("🖼️ ดูใบเสร็จ")
                            sel_bill = st.selectbox("เลือกรายการ", bill_df['id'].tolist())
                            path = bill_df[bill_df['id']==sel_bill]['bill_path'].values[0]
                            if os.path.exists(path): st.image(path, width=300)

                with tab3:
                    st.subheader("👥 สมาชิก")
                    conn = get_connection()
                    members = pd.read_sql_query('''
                        SELECT u.username, u.last_active FROM trip_members tm
                        JOIN users u ON tm.username = u.username WHERE tm.trip_id = ?
                    ''', conn, params=(t_id,))
                    
                    for _, m in members.iterrows():
                        st.write(f"{get_status_icon(m['last_active'])} **{m['username']}** {'(แอดมิน)' if m['username']==t_row['created_by'] else ''}")
                    
                    if is_creator:
                        st.divider()
                        invite_u = st.text_input("ระบุชื่อผู้ใช้ที่ต้องการเชิญ")
                        if st.button("เชิญเข้าทริป"):
                            cur = conn.cursor()
                            exists = cur.execute('SELECT COUNT(*) FROM users WHERE username=?', (invite_u,)).fetchone()[0]
                            if exists:
                                cur.execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (t_id, invite_u))
                                send_notification(invite_u, f"✉️ คุณถูกเชิญเข้าทริป {sel_trip}", conn=conn)
                                conn.commit(); st.success(f"เชิญ {invite_u} แล้ว!"); st.rerun()
                            else: st.error("ไม่พบชื่อผู้ใช้")
                    conn.close()

    elif menu == "➕ สร้างทริปใหม่":
        st.header("➕ สร้างทริปใหม่")
        with st.form("new_trip"):
            name = st.text_input("ชื่อทริป")
            bud = st.number_input("งบประมาณ (บาท)", min_value=0.0)
            if st.form_submit_button("สร้างทริป"):
                if name:
                    conn = get_connection(); cur = conn.cursor()
                    cur.execute('INSERT INTO trips(name, budget, created_by, created_at) VALUES (?,?,?,?)', (name, bud, user_now, datetime.now().strftime("%Y-%m-%d")))
                    t_id = cur.lastrowid
                    cur.execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (t_id, user_now))
                    conn.commit(); conn.close()
                    st.cache_data.clear()
                    st.success("สร้างสำเร็จ!"); st.rerun()
