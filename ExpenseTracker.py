import streamlit as st
import pandas as pd
import sqlite3
import os
import hashlib
from datetime import datetime, timedelta

# --- 1. การตั้งค่าพื้นฐานและโครงสร้างไฟล์ ---
DB_FILE = 'expense_tracker.db'
BILL_DIR = "bills"
PROFILE_DIR = "profiles"

for folder in [BILL_DIR, PROFILE_DIR]:
    if not os.path.exists(folder):
        os.makedirs(folder)

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return hashed_text if make_hashes(password) == hashed_text else False

def get_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

# --- 2. ระบบจัดการฐานข้อมูล (ป้องกัน OperationalError) ---
def init_db():
    conn = get_connection()
    c = conn.cursor()
    # สร้างตารางหลัก
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, profile_pic TEXT, last_active TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, budget REAL, created_by TEXT, created_at TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS trip_members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, username TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, category TEXT, amount REAL, 
                  note TEXT, bill_path TEXT, created_by TEXT, updated_by TEXT, trip_id INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notifications 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, receiver TEXT, message TEXT, is_read INTEGER DEFAULT 0, created_at TEXT)''')
    
    # ตรวจสอบและอัปเดตคอลัมน์ที่อาจขาดหาย (Migration)
    columns_to_check = [
        ('users', 'last_active', 'TEXT'),
        ('users', 'profile_pic', 'TEXT'),
        ('transactions', 'bill_path', 'TEXT')
    ]
    for table, col, col_type in columns_to_check:
        try:
            c.execute(f'SELECT {col} FROM {table} LIMIT 1')
        except sqlite3.OperationalError:
            c.execute(f'ALTER TABLE {table} ADD COLUMN {col} {col_type}')
            
    conn.commit()
    conn.close()

init_db()

# --- 3. ฟังก์ชันเสริม (Helper Functions) ---
def add_notify(receiver, message):
    try:
        conn = get_connection()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn.cursor().execute('INSERT INTO notifications(receiver, message, created_at) VALUES (?,?,?)', (receiver, message, now))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Notification Error: {e}")

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
    if username:
        conn = get_connection()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.cursor().execute('UPDATE users SET last_active=? WHERE username=?', (now_str, username))
        conn.commit()
        conn.close()

# --- 4. UI หน้าจอหลัก ---
st.set_page_config(page_title="Trip Expense master", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None

def main():
    if not st.session_state.logged_in:
        st.title("💰 Trip Expense Manager")
        t1, t2 = st.tabs(["🔒 Login", "📝 Sign Up"])
        with t1:
            u = st.text_input("Username", key="login_u")
            p = st.text_input("Password", type='password', key="login_p")
            if st.button("Login", use_container_width=True):
                conn = get_connection()
                res = conn.cursor().execute('SELECT password FROM users WHERE username=?', (u,)).fetchone()
                conn.close()
                if res and check_hashes(p, res[0]):
                    st.session_state.logged_in = True
                    st.session_state.username = u
                    update_user_active(u)
                    st.rerun()
                else: st.error("ข้อมูลไม่ถูกต้อง")
        with t2:
            su = st.text_input("Username", key="reg_u")
            sp = st.text_input("Password", type='password', key="reg_p")
            if st.button("Register", use_container_width=True):
                if su and sp:
                    conn = get_connection()
                    try:
                        conn.cursor().execute('INSERT INTO users(username, password) VALUES (?,?)', (su, make_hashes(sp)))
                        conn.commit()
                        st.success("สมัครสำเร็จ!")
                    except sqlite3.IntegrityError: st.error("ชื่อนี้มีคนใช้แล้ว")
                    finally: conn.close()
    else:
        # --- ระบบหลังจาก Login ---
        user_now = st.session_state.username
        update_user_active(user_now)
        
        conn = get_connection()
        user_info = pd.read_sql_query('SELECT * FROM users WHERE username=?', conn, params=(user_now,)).iloc[0]
        my_trips = pd.read_sql_query('''
            SELECT DISTINCT t.* FROM trips t
            LEFT JOIN trip_members m ON t.id = m.trip_id
            WHERE t.created_by = ? OR m.username = ?
        ''', conn, params=(user_now, user_now))
        notis = pd.read_sql_query('SELECT * FROM notifications WHERE receiver=? ORDER BY id DESC LIMIT 5', conn, params=(user_now,))
        conn.close()

        # Sidebar
        st.sidebar.title(f"👤 {user_now}")
        p_pic = user_info['profile_pic']
        if p_pic and isinstance(p_pic, str) and os.path.exists(p_pic):
            st.sidebar.image(p_pic, width=100)
            
        unread = len(notis[notis['is_read'] == 0])
        noti_label = f"🔔 แจ้งเตือน ({unread})" if unread > 0 else "🔔 แจ้งเตือน"
        menu = st.sidebar.radio("เมนูหลัก", [noti_label, "🧳 ทริปของฉัน", "➕ สร้างทริป", "⚙️ โปรไฟล์"])
        
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()

        # --- เมนู: แจ้งเตือน ---
        if menu == noti_label:
            st.header("🔔 การแจ้งเตือนล่าสุด")
            if notis.empty: st.info("ไม่มีข้อความ")
            else:
                for _, n in notis.iterrows():
                    st.markdown(f"**[{n['created_at']}]**: {n['message']}")
                if st.button("อ่านทั้งหมด"):
                    conn = get_connection(); conn.cursor().execute('UPDATE notifications SET is_read=1 WHERE receiver=?', (user_now,)); conn.commit(); conn.close(); st.rerun()

        # --- เมนู: ทริปของฉัน ---
        elif menu == "🧳 ทริปของฉัน":
            if my_trips.empty: st.info("คุณยังไม่มีทริป")
            else:
                sel_trip = st.selectbox("เลือกทริป", my_trips['name'].tolist())
                t_row = my_trips[my_trips['name'] == sel_trip].iloc[0]
                t_id = t_row['id']
                is_admin = (t_row['created_by'] == user_now)

                tab1, tab2, tab3 = st.tabs(["📝 บันทึกเงิน", "📊 สรุปยอด", "👥 สมาชิก"])

                with tab1:
                    with st.form("exp_form", clear_on_submit=True):
                        c1, c2 = st.columns(2)
                        date = c1.date_input("วันที่")
                        ttype = c1.selectbox("ประเภท", ["รายจ่าย", "รายรับ"])
                        amt = c2.number_input("จำนวนเงิน", min_value=0.0)
                        cat = c2.selectbox("หมวดหมู่", ["อาหาร", "เดินทาง", "ที่พัก", "อื่นๆ"])
                        note = st.text_area("โน้ต")
                        file = st.file_uploader("สลิป", type=['jpg','png'])
                        if st.form_submit_button("บันทึก"):
                            path = save_uploaded_file(file, BILL_DIR, "bill")
                            conn = get_connection()
                            conn.cursor().execute('INSERT INTO transactions(date,type,category,amount,note,bill_path,created_by,trip_id) VALUES (?,?,?,?,?,?,?,?)',
                                                  (date.strftime("%Y-%m-%d"), ttype, cat, amt, note, path, user_now, t_id))
                            # แจ้งเตือนสมาชิกคนอื่น
                            m_list = conn.cursor().execute('SELECT username FROM trip_members WHERE trip_id=? AND username!=?', (t_id, user_now)).fetchall()
                            for m in m_list: add_notify(m[0], f"📢 {user_now} อัปเดต {ttype} {amt:,.2f} ใน {sel_trip}")
                            conn.commit(); conn.close(); st.success("บันทึกสำเร็จ!"); st.rerun()

                with tab2:
                    conn = get_connection()
                    df = pd.read_sql_query('SELECT * FROM transactions WHERE trip_id=? ORDER BY id DESC', conn, params=(t_id,))
                    conn.close()
                    exp = df[df['type']=='รายจ่าย']['amount'].sum()
                    inc = df[df['type']=='รายรับ']['amount'].sum()
                    st.subheader(f"📊 สรุปยอด: {sel_trip}")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("งบประมาณ", f"฿{t_row['budget']:,.2f}")
                    m2.metric("จ่ายไป", f"฿{exp:,.2f}")
                    m3.metric("คงเหลือ", f"฿{t_row['budget'] - exp + inc:,.2f}")
                    st.divider()
                    for _, r in df.iterrows():
                        with st.expander(f"{r['date']} | {r['category']} - {r['amount']:,.2f}"):
                            ca, cb = st.columns([2,1])
                            ca.write(f"โดย: {r['created_by']}\n\nโน้ต: {r['note']}")
                            if r['bill_path']: cb.image(r['bill_path'])
                            if st.button("🗑️ ลบ", key=f"del_{r['id']}"):
                                conn = get_connection(); conn.cursor().execute('DELETE FROM transactions WHERE id=?', (r['id'],)); conn.commit(); conn.close(); st.rerun()

                with tab3:
                    st.subheader("👥 สมาชิก")
                    conn = get_connection()
                    m_df = pd.read_sql_query('SELECT username FROM trip_members WHERE trip_id=?', conn, params=(t_id,))
                    for m_name in m_df['username']:
                        c_m1, c_m2 = st.columns([4,1])
                        c_m1.write(f"• {m_name}")
                        if is_admin and m_name != user_now:
                            if c_m2.button("เตะ", key=f"kick_{m_name}"):
                                conn.cursor().execute('DELETE FROM trip_members WHERE trip_id=? AND username=?', (t_id, m_name))
                                add_notify(m_name, f"❌ คุณถูกลบออกจากทริป {sel_trip}")
                                conn.commit(); conn.close(); st.rerun()
                    if is_admin:
                        st.divider()
                        all_u = pd.read_sql_query('SELECT username FROM users', conn)['username'].tolist()
                        invite_list = [u for u in all_u if u not in m_df['username'].tolist()]
                        friend = st.selectbox("เชิญเพื่อน", invite_list)
                        if st.button("เชิญ"):
                            conn.cursor().execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (t_id, friend))
                            add_notify(friend, f"✉️ {user_now} เชิญคุณเข้าทริป {sel_trip}")
                            conn.commit(); conn.close(); st.rerun()

        elif menu == "➕ สร้างทริป":
            st.header("➕ สร้างทริปใหม่")
            with st.form("new_t"):
                name = st.text_input("ชื่อทริป")
                bud = st.number_input("งบรวม", min_value=0.0)
                if st.form_submit_button("สร้าง"):
                    if name:
                        conn = get_connection(); cur = conn.cursor()
                        cur.execute('INSERT INTO trips(name, budget, created_by, created_at) VALUES (?,?,?,?)', (name, bud, user_now, datetime.now().strftime("%Y-%m-%d")))
                        cur.execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (cur.lastrowid, user_now))
                        conn.commit(); conn.close(); st.success("สำเร็จ!"); st.rerun()

        elif menu == "⚙️ โปรไฟล์":
            st.header("⚙️ ตั้งค่าโปรไฟล์")
            img = st.file_uploader("เปลี่ยนรูป", type=['jpg','png'])
            if st.button("บันทึก") and img:
                p_path = save_uploaded_file(img, PROFILE_DIR, f"p_{user_now}")
                conn = get_connection(); conn.cursor().execute('UPDATE users SET profile_pic=? WHERE username=?', (p_path, user_now)); conn.commit(); conn.close(); st.rerun()

if __name__ == '__main__':
    main()
