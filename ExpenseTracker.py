import streamlit as st
import pandas as pd
import sqlite3
import hashlib
from datetime import datetime, timedelta
import plotly.express as px

# --- 1. จัดการฐานข้อมูล ---
DB_FILE = 'expense_tracker.db'

def get_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, last_active TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, budget REAL, created_by TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS trip_members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, username TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, category TEXT, amount REAL, note TEXT, created_by TEXT, trip_id INTEGER)')
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

# --- 3. หน้าจอหลัก ---
st.set_page_config(page_title="Trip Expense Shared", layout="wide")

if 'username' not in st.session_state: st.session_state.username = None
if 'current_trip_name' not in st.session_state: st.session_state.current_trip_name = None

# ระบบ Login / Register
if not st.session_state.username:
    st.title("💰 Trip Expense Master (Shared)")
    t1, t2 = st.tabs(["เข้าสู่ระบบ", "สมัครสมาชิก"])
    with t1:
        u = st.text_input("Username")
        p = st.text_input("Password", type='password')
        if st.button("Login", use_container_width=True):
            with get_connection() as conn:
                res = conn.cursor().execute('SELECT password FROM users WHERE username=?', (u,)).fetchone()
            if res and res[0] == make_hashes(p):
                st.session_state.username = u
                st.rerun()
            else: st.error("ชื่อหรือรหัสผ่านไม่ถูกต้อง")
    with t2:
        su = st.text_input("New Username")
        sp = st.text_input("New Password", type='password')
        if st.button("สมัครสมาชิก", use_container_width=True):
            with get_connection() as conn:
                try:
                    conn.cursor().execute('INSERT INTO users(username, password) VALUES (?,?)', (su, make_hashes(sp)))
                    conn.commit()
                    st.success("สมัครสำเร็จ! กรุณาเข้าสู่ระบบ")
                except: st.error("ชื่อนี้มีในระบบแล้ว")

else:
    user_now = st.session_state.username
    update_online_status(user_now)

    # ดึงทริปที่ผู้ใช้คนนี้เกี่ยวข้องทั้งหมด (ทั้งสร้างเองและโดนเชิญ)
    with get_connection() as conn:
        my_trips_df = pd.read_sql_query('''
            SELECT DISTINCT t.* FROM trips t
            JOIN trip_members tm ON t.id = tm.trip_id
            WHERE LOWER(tm.username) = LOWER(?)
        ''', conn, params=(user_now,))

    # Sidebar
    st.sidebar.title(f"👤 {user_now}")
    menu = st.sidebar.radio("เมนูหลัก", ["🧳 ทริปของฉัน", "➕ สร้างทริปใหม่"])
    if st.sidebar.button("Log out"):
        st.session_state.username = None
        st.rerun()

    # --- หน้าหลัก: ทริปของฉัน ---
    if menu == "🧳 ทริปของฉัน":
        if my_trips_df.empty:
            st.info("คุณยังไม่มีทริป (หากเพื่อนดึงเข้ากลุ่มแล้ว ลองกดรีเฟรช)")
            if st.button("🔄 รีเฟรช"): st.rerun()
        else:
            trip_list = my_trips_df['name'].tolist()
            if st.session_state.current_trip_name not in trip_list:
                st.session_state.current_trip_name = trip_list[0]
            
            sel_trip = st.selectbox("เลือกทริปที่ต้องการใช้งาน", trip_list, 
                                    index=trip_list.index(st.session_state.current_trip_name))
            st.session_state.current_trip_name = sel_trip
            
            # ดึงข้อมูลทริปปัจจุบัน
            t_data = my_trips_df[my_trips_df['name'] == sel_trip].iloc[0]
            t_id = t_data['id']
            is_owner = (t_data['created_by'] == user_now)

            # --- เฉพาะเจ้าของทริปที่ลบทริปได้ ---
            if is_owner:
                with st.sidebar.expander("⚙️ ตั้งค่าโดยผู้สร้าง"):
                    if st.button("🗑️ ลบทริปนี้ถาวร", type="primary"):
                        with get_connection() as conn:
                            conn.cursor().execute('DELETE FROM trips WHERE id=?', (t_id,))
                            conn.cursor().execute('DELETE FROM trip_members WHERE trip_id=?', (t_id,))
                            conn.cursor().execute('DELETE FROM transactions WHERE trip_id=?', (t_id,))
                            conn.commit()
                        st.session_state.current_trip_name = None
                        st.rerun()

            st.title(f"🚢 {sel_trip}")
            tab1, tab2, tab3 = st.tabs(["📝 ลงบันทึกรายจ่าย", "📊 สรุปกองกลาง", "👥 จัดการสมาชิก"])

            with tab1: # เพื่อนทุกคนบันทึกร่วมกันได้ที่นี่
                st.subheader("เพิ่มรายการรายจ่ายใหม่")
                with st.form("exp_form", clear_on_submit=True):
                    amt = st.number_input("จำนวนเงิน (บาท)", min_value=0.0)
                    cat = st.selectbox("หมวดหมู่", ["อาหาร", "เดินทาง", "ที่พัก", "ช้อปปิ้ง", "อื่นๆ"])
                    note = st.text_input("รายละเอียด/ใครเป็นคนจ่าย")
                    if st.form_submit_button("บันทึกลงกองกลาง"):
                        with get_connection() as conn:
                            conn.cursor().execute('INSERT INTO transactions(date, category, amount, note, created_by, trip_id) VALUES (?,?,?,?,?,?)',
                                                 (datetime.now().strftime("%Y-%m-%d"), cat, amt, note, user_now, t_id))
                            conn.commit()
                        st.success("บันทึกรายจ่ายแล้ว!")
                        st.rerun()

            with tab2: # เห็นยอดรวมอัปเดตพร้อมกัน
                with get_connection() as conn:
                    tx_df = pd.read_sql_query('SELECT * FROM transactions WHERE trip_id=?', conn, params=(t_id,))
                
                if not tx_df.empty:
                    col1, col2 = st.columns(2)
                    col1.metric("ยอดจ่ายรวมทริป", f"฿{tx_df['amount'].sum():,.2f}")
                    col2.metric("งบประมาณที่ตั้ง", f"฿{t_data['budget']:,.2f}")
                    
                    fig = px.pie(tx_df, values='amount', names='category', hole=0.4, title="สัดส่วนรายจ่าย")
                    st.plotly_chart(fig, use_container_width=True)
                    
                    st.write("📋 ประวัติการบันทึก (ทุกคนเห็นเหมือนกัน)")
                    st.dataframe(tx_df[['date', 'category', 'amount', 'created_by', 'note']], use_container_width=True)
                else:
                    st.info("ยังไม่มีข้อมูลรายจ่าย")

            with tab3: # การจัดการสมาชิก
                st.subheader("👥 สมาชิกในทริปนี้")
                with get_connection() as conn:
                    members = pd.read_sql_query('''
                        SELECT u.username FROM trip_members tm
                        JOIN users u ON tm.username = u.username WHERE tm.trip_id = ?
                    ''', conn, params=(t_id,))
                
                for _, m in members.iterrows():
                    c1, c2 = st.columns([4, 1])
                    c1.write(f"✅ **{m['username']}** {'(ผู้สร้าง)' if m['username'] == t_data['created_by'] else ''}")
                    # เฉพาะผู้สร้างที่ลบคนอื่นได้
                    if is_owner and m['username'] != user_now:
                        if c2.button("ลบออก", key=f"kick_{m['username']}"):
                            with get_connection() as conn:
                                conn.cursor().execute('DELETE FROM trip_members WHERE trip_id=? AND username=?', (t_id, m['username']))
                                conn.commit()
                            st.rerun()
                
                # เฉพาะผู้สร้างที่ดึงเพื่อนได้
                if is_owner:
                    st.divider()
                    st.subheader("➕ ดึงเพื่อนเข้าทริปทันที")
                    target = st.text_input("พิมพ์ Username เพื่อนเพื่อดึงเข้า")
                    if st.button("ดึงเพื่อนร่วมทริป"):
                        with get_connection() as conn:
                            # เช็คชื่อแบบไม่สนตัวเล็กใหญ่
                            u_db = conn.cursor().execute('SELECT username FROM users WHERE LOWER(username) = LOWER(?)', (target,)).fetchone()
                            if u_db:
                                conn.cursor().execute('INSERT OR IGNORE INTO trip_members(trip_id, username) VALUES (?,?)', (t_id, u_db[0]))
                                conn.commit()
                                st.success(f"ดึง {u_db[0]} เข้ากลุ่มสำเร็จ!")
                                st.rerun()
                            else: st.error("ไม่พบชื่อผู้ใช้นี้")

    # --- หน้า 2: สร้างทริปใหม่ ---
    elif menu == "➕ สร้างทริปใหม่":
        st.header("➕ เริ่มทริปใหม่")
        with st.form("new_trip"):
            name = st.text_input("ชื่อทริป")
            bud = st.number_input("งบประมาณรวม", min_value=0.0)
            if st.form_submit_button("สร้างทริป"):
                if name:
                    with get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute('INSERT INTO trips(name, budget, created_by) VALUES (?,?,?)', (name, bud, user_now))
                        new_id = cur.lastrowid
                        cur.execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (new_id, user_now))
                        conn.commit()
                    st.session_state.current_trip_name = name
                    st.rerun()
                else: st.error("กรุณาระบุชื่อทริป")
