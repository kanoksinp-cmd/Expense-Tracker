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

# --- ฟังก์ชันจัดการข้อมูล ---
def save_profile_pic(uploaded_file, username):
    if uploaded_file:
        ext = uploaded_file.name.split('.')[-1]
        file_path = os.path.join(PROFILE_DIR, f"profile_{username}.{ext}")
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        conn = get_connection()
        conn.cursor().execute('UPDATE users SET profile_pic=? WHERE username=?', (file_path, username))
        conn.commit()
        conn.close()
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

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'editing_id' not in st.session_state:
    st.session_state.editing_id = None

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
                else: st.error("ชื่อผู้ใช้หรือรหัสผ่านผิด")
                    
        with tab_signup:
            s_user = st.text_input("ตั้งชื่อผู้ใช้งาน", key="s_user")
            s_pw = st.text_input("ตั้งรหัสผ่าน", type='password', key="s_pw")
            if st.button("ลงทะเบียนใหม่", use_container_width=True):
                if s_user and s_pw:
                    conn = get_connection()
                    try:
                        conn.cursor().execute('INSERT INTO users(username, password) VALUES (?,?)', (s_user, make_hashes(s_pw)))
                        conn.commit()
                        st.success("สมัครสำเร็จ! กรุณาสลับไปหน้า Login")
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
        else: st.sidebar.markdown("🧑‍💻 *ยังไม่มีรูป*")
        st.sidebar.subheader(user_now)
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()

        menu = st.sidebar.radio("เมนูหลัก", ["🧳 ทริปของฉัน", "➕ สร้างทริปใหม่", "⚙️ ตั้งค่าโปรไฟล์"])

        if menu == "🧳 ทริปของฉัน":
            st.header("🧳 รายการทริปของคุณ")
            if my_trips_df.empty:
                st.info("คุณยังไม่มีทริป")
            else:
                sel_trip_name = st.selectbox("เลือกทริปที่ต้องการจัดการ", my_trips_df['name'].tolist())
                t_id = my_trips_df[my_trips_df['name'] == sel_trip_name].iloc[0]['id']

                tab1, tab2, tab3 = st.tabs(["📝 บันทึก/แก้ไขรายการ", "📊 ประวัติรายการ", "👥 สมาชิกทริป"])

                with tab1:
                    # ส่วนการแก้ไขข้อมูล
                    if st.session_state.editing_id:
                        st.subheader("✏️ แก้ไขรายการ")
                        conn = get_connection()
                        edit_data = conn.cursor().execute('SELECT * FROM transactions WHERE id=?', (st.session_state.editing_id,)).fetchone()
                        conn.close()
                        if edit_data:
                            with st.form("edit_form"):
                                e_date = st.date_input("วันที่", datetime.strptime(edit_data[1], "%Y-%m-%d"))
                                e_type = st.selectbox("ประเภท", ["รายจ่าย", "รายรับ"], index=0 if edit_data[2]=="รายจ่าย" else 1)
                                e_amt = st.number_input("จำนวนเงิน", value=float(edit_data[4]))
                                e_cat = st.selectbox("หมวดหมู่", ["อาหาร", "ที่พัก", "เดินทาง", "อื่นๆ"], index=0)
                                e_note = st.text_area("หมายเหตุ", value=edit_data[5])
                                if st.form_submit_button("บันทึกการแก้ไข"):
                                    conn = get_connection()
                                    conn.cursor().execute('UPDATE transactions SET date=?, type=?, category=?, amount=?, note=? WHERE id=?', 
                                                          (e_date.strftime("%Y-%m-%d"), e_type, e_cat, e_amt, e_note, st.session_state.editing_id))
                                    conn.commit(); conn.close()
                                    st.session_state.editing_id = None
                                    st.success("แก้ไขแล้ว!"); st.rerun()
                            if st.button("ยกเลิกการแก้ไข"):
                                st.session_state.editing_id = None
                                st.rerun()
                    else:
                        st.subheader("➕ เพิ่มรายการใหม่")
                        with st.form("add_form", clear_on_submit=True):
                            c1, c2 = st.columns(2)
                            date = c1.date_input("วันที่")
                            ttype = c1.selectbox("ประเภท", ["รายจ่าย", "รายรับ"])
                            amt = c2.number_input("จำนวนเงิน", min_value=0.0)
                            cat = c2.selectbox("หมวดหมู่", ["อาหาร", "ที่พัก", "เดินทาง", "อื่นๆ"])
                            note = st.text_area("หมายเหตุ")
                            if st.form_submit_button("บันทึก"):
                                conn = get_connection()
                                conn.cursor().execute('INSERT INTO transactions(date, type, category, amount, note, created_by, trip_id) VALUES (?,?,?,?,?,?,?)', 
                                                      (date.strftime("%Y-%m-%d"), ttype, cat, amt, note, user_now, t_id))
                                conn.commit(); conn.close()
                                st.success("บันทึกสำเร็จ!"); st.rerun()

                with tab2:
                    st.subheader("📊 รายการทั้งหมด")
                    conn = get_connection()
                    df_trans = pd.read_sql_query('SELECT * FROM transactions WHERE trip_id = ? ORDER BY date DESC', conn, params=(t_id,))
                    conn.close()
                    
                    if not df_trans.empty:
                        for _, row in df_trans.iterrows():
                            with st.container():
                                col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
                                col1.write(f"**{row['date']}** | {row['category']}")
                                color = "red" if row['type'] == "รายจ่าย" else "green"
                                col2.markdown(f":{color}[{row['type']} ฿{row['amount']:,.2f}]")
                                if col3.button("✏️", key=f"edit_{row['id']}"):
                                    st.session_state.editing_id = row['id']
                                    st.rerun()
                                if col4.button("🗑️", key=f"del_{row['id']}"):
                                    conn = get_connection()
                                    conn.cursor().execute('DELETE FROM transactions WHERE id=?', (row['id'],))
                                    conn.commit(); conn.close()
                                    st.success("ลบรายการแล้ว"); st.rerun()
                                st.caption(f"โน้ต: {row['note']} (โดย {row['created_by']})")
                                st.divider()
                    else: st.info("ยังไม่มีข้อมูล")

                with tab3:
                    st.subheader("👥 จัดการสมาชิก")
                    conn = get_connection()
                    members = pd.read_sql_query('SELECT username FROM trip_members WHERE trip_id = ?', conn, params=(t_id,))
                    st.write(f"สมาชิก: {', '.join(members['username'].tolist())}")
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
                tb = st.number_input("งบประมาณ", min_value=0.0)
                if st.form_submit_button("สร้าง"):
                    if tn:
                        conn = get_connection(); cur = conn.cursor()
                        cur.execute('INSERT INTO trips(name, budget, created_by, created_at) VALUES (?,?,?,?)', (tn, tb, user_now, datetime.now().strftime("%Y-%m-%d %H:%M")))
                        cur.execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (cur.lastrowid, user_now))
                        conn.commit(); conn.close(); st.success("สำเร็จ!"); st.rerun()

        elif menu == "⚙️ ตั้งค่าโปรไฟล์":
            st.header("⚙️ ตั้งค่าโปรไฟล์")
            img = st.file_uploader("เปลี่ยนรูป", type=['jpg', 'png'])
            if st.button("บันทึก") and img:
                save_profile_pic(img, user_now); st.rerun()
            st.divider()
            for _, u in user_df.iterrows():
                st.write(f"**{u['username']}** | {get_user_status(u['last_active'])}")

if __name__ == '__main__':
    main()
