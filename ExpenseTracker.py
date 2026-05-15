import streamlit as st
import pandas as pd
import sqlite3
import hashlib
from datetime import datetime, timedelta
import plotly.express as px

# --- 1. Database Setup ---
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

# --- 2. Helper Functions ---
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

# --- 3. App UI ---
st.set_page_config(page_title="Trip Expense Shared", layout="wide")

if 'username' not in st.session_state: st.session_state.username = None
if 'current_trip_name' not in st.session_state: st.session_state.current_trip_name = None

# Login/Register
if not st.session_state.username:
    st.title("💰 Trip Expense Master")
    t1, t2 = st.tabs(["Login", "Register"])
    with t1:
        u = st.text_input("Username")
        p = st.text_input("Password", type='password')
        if st.button("เข้าสู่ระบบ", use_container_width=True):
            with get_connection() as conn:
                res = conn.cursor().execute('SELECT password FROM users WHERE username=?', (u,)).fetchone()
            if res and res[0] == hashlib.sha256(str.encode(p)).hexdigest():
                st.session_state.username = u
                st.rerun()
            else: st.error("ข้อมูลไม่ถูกต้อง")
    with t2:
        su = st.text_input("New Username")
        sp = st.text_input("New Password", type='password')
        if st.button("สมัครสมาชิก", use_container_width=True):
            with get_connection() as conn:
                try:
                    conn.cursor().execute('INSERT INTO users(username, password) VALUES (?,?)', (su, hashlib.sha256(str.encode(sp)).hexdigest()))
                    conn.commit()
                    st.success("สมัครแล้ว เข้าใช้งานได้เลย")
                except: st.error("ชื่อซ้ำ")

else:
    user_now = st.session_state.username
    update_online_status(user_now)

    # ดึงข้อมูลทริปที่ผู้ใช้เป็นสมาชิกอยู่
    with get_connection() as conn:
        my_trips_df = pd.read_sql_query('''
            SELECT t.* FROM trips t
            JOIN trip_members tm ON t.id = tm.trip_id
            WHERE LOWER(tm.username) = LOWER(?)
        ''', conn, params=(user_now,))

    # Sidebar
    st.sidebar.title(f"👤 {user_now}")
    menu = st.sidebar.radio("เมนู", ["🧳 ทริปของฉัน", "➕ สร้างทริปใหม่"])
    if st.sidebar.button("Logout"):
        st.session_state.username = None
        st.rerun()

    # --- หน้าหลัก: ทริปของฉัน (ทุกคนเห็นเหมือนกัน) ---
    if menu == "🧳 ทริปของฉัน":
        if my_trips_df.empty:
            st.info("คุณยังไม่มีทริป (หากเพิ่งโดนดึงเข้า ให้ลองรีเฟรชหน้าจอ)")
        else:
            trip_names = my_trips_df['name'].tolist()
            if st.session_state.current_trip_name not in trip_names:
                st.session_state.current_trip_name = trip_names[0]
            
            sel_trip = st.selectbox("เลือกทริป", trip_names, index=trip_names.index(st.session_state.current_trip_name))
            st.session_state.current_trip_name = sel_trip
            
            # ดึงข้อมูลทริปปัจจุบัน
            t_info = my_trips_df[my_trips_df['name'] == sel_trip].iloc[0]
            t_id = t_info['id']
            is_owner = (t_info['created_by'] == user_now)

            st.header(f"🚢 ทริป: {sel_trip}")
            
            # ทุกคนเห็น 3 Tab เหมือนกัน
            tab1, tab2, tab3 = st.tabs(["📝 บันทึกรายจ่าย", "📊 สรุปกองกลาง", "👥 สมาชิกกลุ่ม"])

            with tab1: # เพื่อนทุกคนสามารถบันทึกได้
                st.subheader("เพิ่มรายการใช้จ่ายใหม่")
                with st.form("exp_form", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    amt = c1.number_input("จำนวนเงิน", min_value=0.0)
                    cat = c2.selectbox("หมวดหมู่", ["อาหาร", "เดินทาง", "ที่พัก", "ช้อปปิ้ง", "อื่นๆ"])
                    note = st.text_input("โน้ตเพิ่มเติม (เช่น ใครจ่าย, จ่ายค่าอะไร)")
                    if st.form_submit_button("บันทึกข้อมูล"):
                        with get_connection() as conn:
                            conn.cursor().execute('INSERT INTO transactions(date, category, amount, note, created_by, trip_id) VALUES (?,?,?,?,?,?)',
                                                 (datetime.now().strftime("%Y-%m-%d"), cat, amt, note, user_now, t_id))
                            conn.commit()
                        st.success("บันทึกรายจ่ายสำเร็จ!")
                        st.rerun()

            with tab2: # ทุกคนเห็นสรุปเดียวกัน
                with get_connection() as conn:
                    tx_df = pd.read_sql_query('SELECT * FROM transactions WHERE trip_id=?', conn, params=(t_id,))
                
                if not tx_df.empty:
                    st.subheader(f"💰 ยอดรวมรายจ่ายทริป: ฿{tx_df['amount'].sum():,.2f}")
                    st.write(f"งบประมาณคงเหลือ: ฿{t_info['budget'] - tx_df['amount'].sum():,.2f}")
                    
                    fig = px.pie(tx_df, values='amount', names='category', title="สัดส่วนการใช้จ่าย")
                    st.plotly_chart(fig, use_container_width=True)
                    
                    st.write("### รายการทั้งหมด")
                    st.dataframe(tx_df[['date', 'category', 'amount', 'created_by', 'note']], use_container_width=True)
                else:
                    st.info("ยังไม่มีข้อมูลรายจ่ายในทริปนี้")

            with tab3: # ดูสมาชิก และการจัดการ
                st.subheader("👥 เพื่อนร่วมทริป")
                with get_connection() as conn:
                    members = pd.read_sql_query('''
                        SELECT u.username, u.last_active FROM trip_members tm
                        JOIN users u ON tm.username = u.username WHERE tm.trip_id = ?
                    ''', conn, params=(t_id,))
                
                for _, m in members.iterrows():
                    icon = get_status_icon(m['last_active'])
                    role = "(ผู้สร้างทริป)" if m['username'] == t_info['created_by'] else ""
                    st.write(f"{icon} **{m['username']}** {role}")
                
                # เฉพาะเจ้าของทริปที่ดึงเพื่อนเพิ่มได้
                if is_owner:
                    st.divider()
                    st.subheader("➕ จัดการสมาชิก (เฉพาะผู้สร้าง)")
                    target = st.text_input("พิมพ์ชื่อเพื่อนเพื่อดึงเข้าทริปทันที")
                    if st.button("ดึงเพื่อนเข้ากลุ่ม"):
                        with get_connection() as conn:
                            user_check = conn.cursor().execute('SELECT username FROM users WHERE LOWER(username) = LOWER(?)', (target,)).fetchone()
                            if user_check:
                                # ดึงเข้าทันที (accepted)
                                conn.cursor().execute('INSERT OR IGNORE INTO trip_members(trip_id, username) VALUES (?,?)', (t_id, user_check[0]))
                                conn.commit()
                                send_notification(user_check[0], f"🚀 คุณถูกดึงเข้าทริป '{sel_trip}' แล้ว!")
                                st.success(f"ดึง {user_check[0]} สำเร็จ!")
                                st.rerun()
                            else: st.error("ไม่พบชื่อผู้ใช้นี้")

    elif menu == "➕ สร้างทริปใหม่":
        st.header("➕ เริ่มทริปใหม่")
        with st.form("new_trip"):
            name = st.text_input("ชื่อทริป")
            bud = st.number_input("งบประมาณรวม", min_value=0.0)
            if st.form_submit_button("ตกลงสร้าง"):
                if name:
                    with get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute('INSERT INTO trips(name, budget, created_by) VALUES (?,?,?)', (name, bud, user_now))
                        new_id = cur.lastrowid
                        cur.execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (new_id, user_now))
                        conn.commit()
                    st.session_state.current_trip_name = name
                    st.session_state.menu_selection = "🧳 ทริปของฉัน"
                    st.rerun()
