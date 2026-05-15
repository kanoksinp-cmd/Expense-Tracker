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
    # สร้างตารางพื้นฐาน
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, profile_pic TEXT, last_active TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, budget REAL, created_by TEXT, created_at TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS trip_members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, username TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, category TEXT, amount REAL, 
                  note TEXT, bill_path TEXT, created_by TEXT, updated_by TEXT, trip_id INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notifications 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, receiver TEXT, message TEXT, is_read INTEGER DEFAULT 0, created_at TEXT)''')
    
    # --- แก้ไข OperationalError: ตรวจสอบ Column ที่อาจขาดหายไป ---
    try:
        c.execute('SELECT last_active FROM users LIMIT 1')
    except sqlite3.OperationalError:
        c.execute('ALTER TABLE users ADD COLUMN last_active TEXT')
    
    conn.commit()
    conn.close()

create_tables()

# --- ฟังก์ชันจัดการระบบ ---
def add_notify(receiver, message):
    conn = get_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn.cursor().execute('INSERT INTO notifications(receiver, message, created_at) VALUES (?,?,?)', (receiver, message, now))
    conn.commit()
    conn.close()

def save_file(uploaded_file, folder, prefix):
    if uploaded_file:
        ext = uploaded_file.name.split('.')[-1]
        filename = f"{prefix}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}"
        file_path = os.path.join(folder, filename)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return file_path
    return None

def update_user_active(username):
    if username:
        conn = get_connection()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.cursor().execute('UPDATE users SET last_active=? WHERE username=?', (now_str, username))
        conn.commit()
        conn.close()

# --- UI Setup ---
st.set_page_config(page_title="Trip Expense Master", layout="wide")

if 'logged_in' not in st.session_state: 
    st.session_state.logged_in = False
    st.session_state.username = None

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
                        st.success("สมัครสำเร็จ! กรุณาเข้าสู่ระบบ")
                    except sqlite3.IntegrityError: st.error("ชื่อนี้มีคนใช้แล้ว")
                    finally: conn.close()
    else:
        # --- LOGIN แล้ว ---
        user_now = st.session_state.username
        update_user_active(user_now)
        
        conn = get_connection()
        user_info = pd.read_sql_query('SELECT * FROM users WHERE username = ?', conn, params=(user_now,)).iloc[0]
        my_trips = pd.read_sql_query('''
            SELECT DISTINCT t.* FROM trips t
            LEFT JOIN trip_members m ON t.id = m.trip_id
            WHERE t.created_by = ? OR m.username = ?
        ''', conn, params=(user_now, user_now))
        notis = pd.read_sql_query('SELECT * FROM notifications WHERE receiver = ? ORDER BY id DESC LIMIT 10', conn, params=(user_now,))
        conn.close()

        # Sidebar
        st.sidebar.title(f"👤 {user_now}")
        
        # --- แก้ TypeError: ตรวจสอบรูปโปรไฟล์ก่อนใช้ os.path.exists ---
        p_pic = user_info['profile_pic']
        if p_pic and isinstance(p_pic, str) and os.path.exists(p_pic):
            st.sidebar.image(p_pic, width=100)
        else:
            st.sidebar.caption("ยังไม่มีรูปโปรไฟล์")
            
        unread = len(notis[notis['is_read'] == 0])
        noti_btn = f"🔔 แจ้งเตือน ({unread})" if unread > 0 else "🔔 แจ้งเตือน"
        menu = st.sidebar.radio("เมนูหลัก", [noti_btn, "🧳 ทริปของฉัน", "➕ สร้างทริปใหม่", "⚙️ ตั้งค่าโปรไฟล์"])

        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.username = None
            st.rerun()

        # --- เมนู: แจ้งเตือน ---
        if menu == noti_btn:
            st.header("🔔 กล่องข้อความ")
            if notis.empty: st.info("ไม่มีแจ้งเตือน")
            else:
                if st.button("อ่านทั้งหมด"):
                    conn = get_connection(); conn.cursor().execute('UPDATE notifications SET is_read = 1 WHERE receiver = ?', (user_now,)); conn.commit(); conn.close(); st.rerun()
                for _, n in notis.iterrows():
                    bg = "#f0f2f6" if n['is_read'] == 0 else "transparent"
                    st.markdown(f'<div style="background:{bg}; padding:10px; border-radius:5px; margin-bottom:5px;">{n["message"]} <br><small>{n["created_at"]}</small></div>', unsafe_allow_html=True)

        # --- เมนู: ทริปของฉัน ---
        elif menu == "🧳 ทริปของฉัน":
            if my_trips.empty: st.info("คุณยังไม่มีทริป")
            else:
                sel_trip = st.selectbox("เลือกทริป", my_trips['name'].tolist())
                t_data = my_trips[my_trips['name'] == sel_trip].iloc[0]
                t_id = t_data['id']
                is_admin = (t_data['created_by'] == user_now)

                t1, t2, t3 = st.tabs(["📝 บันทึกรายจ่าย", "📊 สรุปยอด & สลิป", "👥 จัดการสมาชิก"])

                with t1:
                    with st.form("add_exp", clear_on_submit=True):
                        c1, c2 = st.columns(2)
                        date = c1.date_input("วันที่")
                        ttype = c1.selectbox("ประเภท", ["รายจ่าย", "รายรับ"])
                        amt = c2.number_input("จำนวนเงิน", min_value=0.0)
                        cat = c2.selectbox("หมวดหมู่", ["อาหาร", "ที่พัก", "เดินทาง", "อื่นๆ"])
                        note = st.text_area("หมายเหตุ")
                        file = st.file_uploader("แนบสลิป", type=['jpg','png','jpeg'])
                        if st.form_submit_button("บันทึก"):
                            path = save_file(file, BILL_DIR, "bill")
                            conn = get_connection()
                            conn.cursor().execute('INSERT INTO transactions(date,type,category,amount,note,bill_path,created_by,trip_id) VALUES (?,?,?,?,?,?,?,?)',
                                                  (date.strftime("%Y-%m-%d"), ttype, cat, amt, note, path, user_now, t_id))
                            # แจ้งเตือนเพื่อน
                            m_list = conn.cursor().execute('SELECT username FROM trip_members WHERE trip_id=? AND username!=?', (t_id, user_now)).fetchall()
                            for m in m_list: add_notify(m[0], f"💰 {user_now} เพิ่ม {ttype} {cat} ฿{amt:,.2f} ในทริป {sel_trip}")
                            conn.commit(); conn.close(); st.success("บันทึกแล้ว"); st.rerun()

                with t2:
                    conn = get_connection()
                    df = pd.read_sql_query('SELECT * FROM transactions WHERE trip_id = ? ORDER BY date DESC', conn, params=(t_id,))
                    conn.close()
                    exp = df[df['type'] == 'รายจ่าย']['amount'].sum()
                    inc = df[df['type'] == 'รายรับ']['amount'].sum()
                    st.subheader("💰 สถานะการเงินทริป")
                    c_1, c_2, c_3 = st.columns(3)
                    c_1.metric("งบประมาณ", f"฿{t_data['budget']:,.2f}")
                    c_2.metric("จ่ายจริง", f"฿{exp:,.2f}", delta=f"-{exp}", delta_color="inverse")
                    c_3.metric("คงเหลือ", f"฿{t_data['budget'] - exp + inc:,.2f}")
                    
                    st.divider()
                    for _, r in df.iterrows():
                        with st.expander(f"{r['date']} | {r['category']} - ฿{r['amount']:,.2f}"):
                            col_l, col_r = st.columns([2,1])
                            col_l.write(f"ผู้บันทึก: {r['created_by']}\n\nโน้ต: {r['note']}")
                            if r['bill_path']: col_r.image(r['bill_path'])
                            if st.button("🗑️ ลบ", key=f"del_{r['id']}"):
                                conn = get_connection(); conn.cursor().execute('DELETE FROM transactions WHERE id=?', (r['id'],)); conn.commit(); conn.close(); st.rerun()

                with t3:
                    st.subheader("👥 สมาชิก")
                    conn = get_connection()
                    members = pd.read_sql_query('SELECT username FROM trip_members WHERE trip_id = ?', conn, params=(t_id,))
                    for m in members['username']:
                        cm1, cm2 = st.columns([4,1])
                        cm1.write(f"• {m} {'(Admin)' if m == t_data['created_by'] else ''}")
                        if is_admin and m != user_now:
                            if cm2.button("เตะ", key=f"k_{m}"):
                                conn.cursor().execute('DELETE FROM trip_members WHERE trip_id=? AND username=?', (t_id, m))
                                add_notify(m, f"❌ คุณถูกเชิญออกจากทริป {sel_trip}")
                                conn.commit(); conn.close(); st.rerun()
                    
                    if is_admin:
                        st.divider()
                        all_users = pd.read_sql_query('SELECT username FROM users', conn)['username'].tolist()
                        invite_list = [u for u in all_users if u not in members['username'].tolist()]
                        friend = st.selectbox("เชิญเพื่อน", invite_list)
                        if st.button("เพิ่มเข้าทริป"):
                            conn.cursor().execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (t_id, friend))
                            add_notify(friend, f"✉️ {user_now} เชิญคุณเข้าทริป {sel_trip}")
                            conn.commit(); conn.close(); st.success("เชิญแล้ว"); st.rerun()

        elif menu == "➕ สร้างทริปใหม่":
            st.header("➕ สร้างทริปใหม่")
            with st.form("new_trip"):
                name = st.text_input("ชื่อทริป")
                budget = st.number_input("งบประมาณ", min_value=0.0)
                if st.form_submit_button("สร้างทริป"):
                    if name:
                        conn = get_connection(); cur = conn.cursor()
                        cur.execute('INSERT INTO trips(name, budget, created_by, created_at) VALUES (?,?,?,?)', (name, budget, user_now, datetime.now().strftime("%Y-%m-%d")))
                        cur.execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (cur.lastrowid, user_now))
                        conn.commit(); conn.close(); st.success("สร้างทริปสำเร็จ!"); st.rerun()

        elif menu == "⚙️ ตั้งค่าโปรไฟล์":
            st.header("⚙️ โปรไฟล์")
            new_img = st.file_uploader("เปลี่ยนรูปโปรไฟล์", type=['jpg','png'])
            if st.button("บันทึกรูป"):
                if new_img:
                    path = save_file(new_img, PROFILE_DIR, f"p_{user_now}")
                    conn = get_connection(); conn.cursor().execute('UPDATE users SET profile_pic=? WHERE username=?', (path, user_now)); conn.commit(); conn.close(); st.rerun()

if __name__ == '__main__':
    main()
