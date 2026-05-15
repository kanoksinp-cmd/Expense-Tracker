import streamlit as st
import pandas as pd
import sqlite3
import hashlib
from datetime import datetime
import plotly.express as px

# --- 1. จัดการฐานข้อมูล ---
DB_FILE = 'expense_tracker.db'

def get_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, budget REAL, created_by TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS trip_members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, username TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, category TEXT, amount REAL, note TEXT, created_by TEXT, trip_id INTEGER)')
        conn.commit()

init_db()

# --- 2. ระบบ Login / Register ---
st.set_page_config(page_title="Trip Shared Expense", layout="wide")

if 'username' not in st.session_state: st.session_state.username = None
if 'current_trip_name' not in st.session_state: st.session_state.current_trip_name = None

if not st.session_state.username:
    st.title("💰 Trip Expense Master")
    tab_login, tab_reg = st.tabs(["เข้าสู่ระบบ", "สมัครสมาชิก"])
    with tab_login:
        u = st.text_input("Username")
        p = st.text_input("Password", type='password')
        if st.button("Login", use_container_width=True):
            with get_connection() as conn:
                res = conn.cursor().execute('SELECT password FROM users WHERE username=?', (u,)).fetchone()
            if res and res[0] == hashlib.sha256(str.encode(p)).hexdigest():
                st.session_state.username = u
                st.rerun()
            else: st.error("ชื่อหรือรหัสผ่านไม่ถูกต้อง")
    with tab_reg:
        su = st.text_input("New Username")
        sp = st.text_input("New Password", type='password')
        if st.button("Sign Up", use_container_width=True):
            with get_connection() as conn:
                try:
                    conn.cursor().execute('INSERT INTO users(username, password) VALUES (?,?)', (su, hashlib.sha256(str.encode(sp)).hexdigest()))
                    conn.commit()
                    st.success("สมัครสมาชิกสำเร็จ!")
                except: st.error("ชื่อนี้มีผู้ใช้งานแล้ว")

else:
    user_now = st.session_state.username

    # ดึงทริปทั้งหมดที่มีชื่อเราอยู่ (เพื่อให้เพื่อนเห็นทริปที่ร่วมอยู่ด้วย)
    with get_connection() as conn:
        my_trips_df = pd.read_sql_query('''
            SELECT DISTINCT t.* FROM trips t
            JOIN trip_members tm ON t.id = tm.trip_id
            WHERE LOWER(tm.username) = LOWER(?)
        ''', conn, params=(user_now,))

    # Sidebar
    st.sidebar.title(f"👤 {user_now}")
    menu = st.sidebar.radio("เมนูหลัก", ["🧳 ทริปของฉัน", "➕ สร้างทริปใหม่"])
    if st.sidebar.button("Logout"):
        st.session_state.username = None
        st.rerun()

    # --- หน้าหลัก: ทริปของฉัน ---
    if menu == "🧳 ทริปของฉัน":
        if my_trips_df.empty:
            st.info("คุณยังไม่มีทริปในตอนนี้ (ลองให้เพื่อนดึงเข้าทริป หรือสร้างทริปใหม่)")
            if st.button("🔄 รีเฟรช"): st.rerun()
        else:
            # ส่วนการเลือกทริป (ทุกคนที่อยู่ในทริปจะเห็นชื่อทริปปรากฏที่นี่เหมือนกัน)
            trip_list = my_trips_df['name'].tolist()
            if st.session_state.current_trip_name not in trip_list:
                st.session_state.current_trip_name = trip_list[0]
            
            sel_trip = st.selectbox("🎯 เลือกทริปที่ต้องการใช้งานร่วมกัน", trip_list, 
                                    index=trip_list.index(st.session_state.current_trip_name))
            st.session_state.current_trip_name = sel_trip
            
            t_data = my_trips_df[my_trips_df['name'] == sel_trip].iloc[0]
            t_id = t_data['id']
            is_owner = (t_data['created_by'] == user_now)

            # หัวข้อทริปและสถานะ
            st.title(f"🚢 ทริป: {sel_trip}")
            if is_owner:
                st.caption("🛡️ คุณคือผู้สร้างทริปนี้ (มีสิทธิ์ลบทริปและสมาชิก)")
            else:
                st.caption(f"👥 สมาชิกทริป (ผู้สร้าง: {t_data['created_by']})")

            tab1, tab2, tab3 = st.tabs(["📝 บันทึกรายจ่าย", "📊 สรุปกองกลาง", "👥 สมาชิกทริป"])

            with tab1: # ทุกคนบันทึกร่วมกันได้
                st.subheader("เพิ่มรายการใช้จ่ายลงกองกลาง")
                with st.form("shared_exp", clear_on_submit=True):
                    amt = st.number_input("จำนวนเงิน (บาท)", min_value=0.0)
                    cat = st.selectbox("หมวดหมู่", ["อาหาร", "เดินทาง", "ที่พัก", "ช้อปปิ้ง", "อื่นๆ"])
                    note = st.text_input("รายละเอียดเพิ่มเติม (เช่น จ่ายค่าอะไร หรือใครออกไปก่อน)")
                    if st.form_submit_button("บันทึกข้อมูล"):
                        with get_connection() as conn:
                            conn.cursor().execute('INSERT INTO transactions(date, category, amount, note, created_by, trip_id) VALUES (?,?,?,?,?,?)',
                                                 (datetime.now().strftime("%Y-%m-%d"), cat, amt, note, user_now, t_id))
                            conn.commit()
                        st.success("บันทึกสำเร็จ! ข้อมูลจะอัปเดตให้เพื่อนๆ เห็นทันที")
                        st.rerun()

            with tab2: # เห็นยอดรวมอัปเดตพร้อมกันแบบ Real-time
                with get_connection() as conn:
                    tx_df = pd.read_sql_query('SELECT * FROM transactions WHERE trip_id=?', conn, params=(t_id,))
                
                if not tx_df.empty:
                    c1, c2, c3 = st.columns(3)
                    total_spent = tx_df['amount'].sum()
                    c1.metric("ยอดจ่ายรวม", f"฿{total_spent:,.2f}")
                    c2.metric("งบประมาณ", f"฿{t_data['budget']:,.2f}")
                    c3.metric("คงเหลือ", f"฿{t_data['budget'] - total_spent:,.2f}")
                    
                    fig = px.pie(tx_df, values='amount', names='category', hole=0.4, title="สัดส่วนรายจ่ายรายหมวด")
                    st.plotly_chart(fig, use_container_width=True)
                    
                    st.write("📋 ประวัติการใช้จ่ายของทุกคนในกลุ่ม")
                    st.dataframe(tx_df[['date', 'category', 'amount', 'created_by', 'note']], use_container_width=True)
                else:
                    st.info("ยังไม่มีข้อมูลรายจ่ายในทริปนี้ เริ่มบันทึกคนแรกได้เลย!")

            with tab3: # ดูรายชื่อเพื่อน และจัดการสมาชิก
                st.subheader("👥 สมาชิกในกลุ่มนี้")
                with get_connection() as conn:
                    m_list = pd.read_sql_query('''
                        SELECT u.username FROM trip_members tm
                        JOIN users u ON tm.username = u.username WHERE tm.trip_id = ?
                    ''', conn, params=(t_id,))
                
                for _, m in m_list.iterrows():
                    col_m1, col_m2 = st.columns([4, 1])
                    col_m1.write(f"✅ **{m['username']}** {'(ผู้สร้าง)' if m['username'] == t_data['created_by'] else ''}")
                    if is_owner and m['username'] != user_now:
                        if col_m2.button("ลบออก", key=f"kick_{m['username']}"):
                            with get_connection() as conn:
                                conn.cursor().execute('DELETE FROM trip_members WHERE trip_id=? AND username=?', (t_id, m['username']))
                                conn.commit()
                            st.rerun()
                
                if is_owner:
                    st.divider()
                    st.subheader("➕ ดึงเพื่อนเข้าทริป")
                    target = st.text_input("ระบุ Username ของเพื่อน")
                    if st.button("ดึงเพื่อนเข้ากลุ่มทันที"):
                        with get_connection() as conn:
                            # ค้นหา user (Case-insensitive)
                            find_u = conn.cursor().execute('SELECT username FROM users WHERE LOWER(username) = LOWER(?)', (target,)).fetchone()
                            if find_u:
                                conn.cursor().execute('INSERT OR IGNORE INTO trip_members(trip_id, username) VALUES (?,?)', (t_id, find_u[0]))
                                conn.commit()
                                st.success(f"ดึง {find_u[0]} เข้าทริปเรียบร้อย!")
                                st.rerun()
                            else: st.error("ไม่พบชื่อผู้ใช้นี้")
                    
                    st.divider()
                    if st.button("🗑️ ลบทริปนี้ถาวร (สำหรับผู้สร้าง)", type="primary"):
                        with get_connection() as conn:
                            conn.cursor().execute('DELETE FROM trips WHERE id=?', (t_id,))
                            conn.cursor().execute('DELETE FROM trip_members WHERE trip_id=?', (t_id,))
                            conn.cursor().execute('DELETE FROM transactions WHERE trip_id=?', (t_id,))
                            conn.commit()
                        st.session_state.current_trip_name = None
                        st.rerun()

    # --- หน้า 2: สร้างทริป ---
    elif menu == "➕ สร้างทริปใหม่":
        st.header("➕ เริ่มต้นทริปใหม่")
        with st.form("new_trip"):
            t_name = st.text_input("ชื่อทริป (เช่น ทริปญี่ปุ่น 2024)")
            t_bud = st.number_input("งบประมาณกองกลาง", min_value=0.0)
            if st.form_submit_button("ตกลงสร้างทริป"):
                if t_name:
                    with get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute('INSERT INTO trips(name, budget, created_by) VALUES (?,?,?)', (t_name, t_bud, user_now))
                        new_id = cur.lastrowid
                        cur.execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (new_id, user_now))
                        conn.commit()
                    st.session_state.current_trip_name = t_name
                    st.success(f"สร้างทริป '{t_name}' สำเร็จ! ไปที่เมนู 'ทริปของฉัน' เพื่อดึงเพื่อนได้เลย")
                    st.rerun()
