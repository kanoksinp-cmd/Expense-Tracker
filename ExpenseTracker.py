import streamlit as st
import pandas as pd
import sqlite3
import os
import hashlib
from datetime import datetime, timedelta

# --- การตั้งค่าพื้นฐาน ---
DB_FILE = 'expense_tracker.db'
BILL_DIR = "bills"
PROFILE_DIR = "profiles"

for folder in [BILL_DIR, PROFILE_DIR]:
    if not os.path.exists(folder):
        os.makedirs(folder)

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return hashed_text
    return False

def get_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def create_tables():
    conn = get_connection()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, profile_pic TEXT, last_active TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, budget REAL, created_by TEXT, created_at TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS trip_members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, username TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, category TEXT, amount REAL, 
                  note TEXT, bill_path TEXT, created_by TEXT, updated_by TEXT, trip_id INTEGER)''')
    conn.commit()
    conn.close()

create_tables()

# --- ฟังก์ชันจัดการไฟล์ ---
def save_uploaded_file(uploaded_file, folder, prefix):
    if uploaded_file:
        ext = uploaded_file.name.split('.')[-1]
        filename = f"{prefix}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}"
        file_path = os.path.join(folder, filename)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return file_path
    return None

def update_user_active(username):
    conn = get_connection()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.cursor().execute('UPDATE users SET last_active=? WHERE username=?', (now_str, username))
    conn.commit()
    conn.close()

def get_user_status(last_active_str):
    if not last_active_str: return "⚫ ออฟไลน์"
    try:
        last_active = datetime.strptime(last_active_str, "%Y-%m-%d %H:%M:%S")
        return "🟢 ออนไลน์" if datetime.now() - last_active < timedelta(minutes=3) else "⚫ ออฟไลน์"
    except: return "⚫ ออฟไลน์"

# --- UI Setup ---
st.set_page_config(page_title="Trip Expense Tracker", layout="wide")

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'editing_id' not in st.session_state: st.session_state.editing_id = None

def main():
    if not st.session_state.logged_in:
        st.title("💰 Trip Expense Manager")
        tab_login, tab_signup = st.tabs(["🔒 เข้าสู่ระบบ", "📝 สมัครสมาชิก"])
        with tab_login:
            l_user = st.text_input("ชื่อผู้ใช้งาน", key="l_user")
            l_pw = st.text_input("รหัสผ่าน", type='password', key="l_pw")
            if st.button("เข้าสู่ระบบ", use_container_width=True):
                conn = get_connection()
                res = conn.cursor().execute('SELECT password FROM users WHERE username = ?', (l_user,)).fetchone()
                conn.close()
                if res and check_hashes(l_pw, res[0]):
                    st.session_state.logged_in = True
                    st.session_state.username = l_user
                    update_user_active(l_user)
                    st.rerun()
                else: st.error("ข้อมูลไม่ถูกต้อง")
        with tab_signup:
            s_user = st.text_input("ตั้งชื่อผู้ใช้งาน", key="s_user")
            s_pw = st.text_input("ตั้งรหัสผ่าน", type='password', key="s_pw")
            if st.button("ลงทะเบียน", use_container_width=True):
                if s_user and s_pw:
                    conn = get_connection()
                    try:
                        conn.cursor().execute('INSERT INTO users(username, password) VALUES (?,?)', (s_user, make_hashes(s_pw)))
                        conn.commit()
                        st.success("สมัครสำเร็จ!")
                    except sqlite3.IntegrityError: st.error("ชื่อนี้มีคนใช้แล้ว")
                    finally: conn.close()
    else:
        update_user_active(st.session_state.username)
        user_now = st.session_state.username
        conn = get_connection()
        user_df = pd.read_sql_query('SELECT * FROM users', conn)
        my_trips_df = pd.read_sql_query('''
            SELECT DISTINCT t.* FROM trips t
            LEFT JOIN trip_members m ON t.id = m.trip_id
            WHERE t.created_by = ? OR m.username = ?
        ''', conn, params=(user_now, user_now))
        conn.close()

        # Sidebar
        st.sidebar.title("👤 โปรไฟล์")
        u_info = user_df[user_df['username'] == user_now].iloc[0]
        p_pic = u_info['profile_pic']
        if p_pic and isinstance(p_pic, str) and os.path.exists(p_pic):
            st.sidebar.image(p_pic, width=100)
        st.sidebar.subheader(user_now)
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()

        menu = st.sidebar.radio("เมนูหลัก", ["🧳 ทริปของฉัน", "➕ สร้างทริปใหม่", "⚙️ ตั้งค่าโปรไฟล์"])

        if menu == "🧳 ทริปของฉัน":
            if my_trips_df.empty:
                st.info("คุณยังไม่มีทริป")
            else:
                sel_trip_name = st.selectbox("เลือกทริปที่ต้องการจัดการ", my_trips_df['name'].tolist())
                t_row = my_trips_df[my_trips_df['name'] == sel_trip_name].iloc[0]
                t_id = t_row['id']
                t_budget = t_row['budget']

                tab1, tab2, tab3 = st.tabs(["📝 บันทึก/แก้ไข", "📊 สรุปยอด & ประวัติ", "👥 สมาชิก"])

                with tab1:
                    if st.session_state.editing_id:
                        st.subheader("✏️ แก้ไขรายการ")
                        # (ส่วนโค้ดแก้ไข... เหมือนเดิมแต่เพิ่มแนบสลิป)
                    else:
                        st.subheader("➕ เพิ่มรายการใหม่")
                        with st.form("add_form", clear_on_submit=True):
                            c1, c2 = st.columns(2)
                            date = c1.date_input("วันที่")
                            ttype = c1.selectbox("ประเภท", ["รายจ่าย", "รายรับ"])
                            amt = c2.number_input("จำนวนเงิน", min_value=0.0)
                            cat = c2.selectbox("หมวดหมู่", ["อาหาร", "ที่พัก", "เดินทาง", "ช้อปปิ้ง", "อื่นๆ"])
                            note = st.text_area("หมายเหตุ")
                            bill = st.file_uploader("แนบสลิป/บิล (รูปภาพ)", type=['jpg', 'png', 'jpeg'])
                            if st.form_submit_button("บันทึก"):
                                b_path = save_uploaded_file(bill, BILL_DIR, "bill")
                                conn = get_connection()
                                conn.cursor().execute('INSERT INTO transactions(date, type, category, amount, note, bill_path, created_by, trip_id) VALUES (?,?,?,?,?,?,?,?)', 
                                                      (date.strftime("%Y-%m-%d"), ttype, cat, amt, note, b_path, user_now, t_id))
                                conn.commit(); conn.close()
                                st.success("บันทึกสำเร็จ!"); st.rerun()

                with tab2:
                    conn = get_connection()
                    df_trans = pd.read_sql_query('SELECT * FROM transactions WHERE trip_id = ? ORDER BY date DESC', conn, params=(t_id,))
                    conn.close()
                    
                    # --- ส่วนสรุปยอดล่าสุด ---
                    st.subheader("💰 สรุปยอดล่าสุด")
                    exp = df_trans[df_trans['type'] == 'รายจ่าย']['amount'].sum()
                    inc = df_trans[df_trans['type'] == 'รายรับ']['amount'].sum()
                    bal = t_budget - exp + inc
                    
                    m1, m2, m3 = st.columns(3)
                    m1.metric("งบประมาณทริป", f"฿{t_budget:,.2f}")
                    m2.metric("ใช้จ่ายไปแล้ว", f"฿{exp:,.2f}", delta=f"-{exp}", delta_color="inverse")
                    m3.metric("คงเหลือ/เงินกองกลาง", f"฿{bal:,.2f}")
                    
                    st.divider()
                    st.subheader("📜 ประวัติรายการ")
                    for _, row in df_trans.iterrows():
                        with st.expander(f"{row['date']} | {row['category']} - ฿{row['amount']:,.2f} ({row['type']})"):
                            col_a, col_b = st.columns([2, 1])
                            with col_a:
                                st.write(f"**บันทึกโดย:** {row['created_by']}")
                                st.write(f"**หมายเหตุ:** {row['note']}")
                                if st.button("🗑️ ลบรายการ", key=f"del_{row['id']}"):
                                    conn = get_connection()
                                    conn.cursor().execute('DELETE FROM transactions WHERE id=?', (row['id'],))
                                    conn.commit(); conn.close(); st.rerun()
                            with col_b:
                                if row['bill_path'] and os.path.exists(row['bill_path']):
                                    st.image(row['bill_path'], caption="สลิปแนบ", use_container_width=True)
                                else: st.caption("ไม่มีสลิปแนบ")

                with tab3:
                    # (ส่วนจัดการสมาชิก... เหมือนเดิม)
                    st.subheader("👥 สมาชิกทริป")
                    conn = get_connection()
                    members = pd.read_sql_query('SELECT username FROM trip_members WHERE trip_id = ?', conn, params=(t_id,))
                    st.write(", ".join(members['username'].tolist()))
                    invite_list = [u for u in user_df['username'].tolist() if u not in members['username'].tolist()]
                    if invite_list:
                        friend = st.selectbox("เชิญเพื่อน", invite_list)
                        if st.button("เพิ่มเพื่อน"):
                            conn.cursor().execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (t_id, friend))
                            conn.commit(); conn.close(); st.rerun()

        elif menu == "➕ สร้างทริปใหม่":
            st.header("➕ สร้างทริปใหม่")
            with st.form("c_trip"):
                tn = st.text_input("ชื่อทริป")
                tb = st.number_input("งบประมาณเบื้องต้น", min_value=0.0)
                if st.form_submit_button("สร้าง"):
                    if tn:
                        conn = get_connection(); cur = conn.cursor()
                        cur.execute('INSERT INTO trips(name, budget, created_by, created_at) VALUES (?,?,?,?)', (tn, tb, user_now, datetime.now().strftime("%Y-%m-%d %H:%M")))
                        cur.execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (cur.lastrowid, user_now))
                        conn.commit(); conn.close(); st.success("สำเร็จ!"); st.rerun()

        elif menu == "⚙️ ตั้งค่าโปรไฟล์":
            # (ส่วนตั้งค่าโปรไฟล์... เหมือนเดิม)
            st.header("⚙️ ตั้งค่าโปรไฟล์")
            img = st.file_uploader("เปลี่ยนรูป", type=['jpg', 'png'])
            if st.button("บันทึก") and img:
                p_path = save_uploaded_file(img, PROFILE_DIR, f"profile_{user_now}")
                conn = get_connection()
                conn.cursor().execute('UPDATE users SET profile_pic=? WHERE username=?', (p_path, user_now))
                conn.commit(); conn.close(); st.rerun()
            st.divider()
            for _, u in user_df.iterrows():
                st.write(f"**{u['username']}** | {get_user_status(u['last_active'])}")

if __name__ == '__main__':
    main()
