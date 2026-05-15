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
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, profile_pic TEXT, last_active TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, budget REAL, created_by TEXT, created_at TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS trip_members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, username TEXT, status TEXT DEFAULT "accepted")')
        c.execute('''CREATE TABLE IF NOT EXISTS transactions 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, category TEXT, amount REAL, 
                      note TEXT, bill_path TEXT, created_by TEXT, trip_id INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS notifications 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, receiver TEXT, message TEXT, is_read INTEGER DEFAULT 0, created_at TEXT)''')
        
        # [CRITICAL FIX] บังคับตรวจสอบและอัปเดตคอลัมน์ status สำหรับตารางเดิม
        try:
            c.execute('SELECT status FROM trip_members LIMIT 1')
        except sqlite3.OperationalError:
            try:
                c.execute('ALTER TABLE trip_members ADD COLUMN status TEXT DEFAULT "accepted"')
                conn.commit()
            except:
                pass
            
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

def check_and_show_popups(username):
    with get_connection() as conn:
        unread_notis = conn.cursor().execute(
            'SELECT id, message FROM notifications WHERE receiver=? AND is_read=0', (username,)
        ).fetchall()
        
        if unread_notis:
            for noti_id, msg in unread_notis:
                st.toast(msg, icon="🔔")
                conn.cursor().execute('UPDATE notifications SET is_read=1 WHERE id=?', (noti_id,))
            conn.commit()

# --- 3. UI หน้า Login / Register ---
st.set_page_config(page_title="Trip Expense Master", layout="wide")

if 'username' not in st.session_state:
    st.session_state.username = None
if 'editing_tx_id' not in st.session_state:
    st.session_state.editing_tx_id = None
if 'current_trip_name' not in st.session_state:
    st.session_state.current_trip_name = None

if not st.session_state.username:
    st.title("💰 Trip Expense Tracker")
    tab_l, tab_r = st.tabs(["เข้าสู่ระบบ", "สมัครสมาชิก"])
    with tab_l:
        u = st.text_input("Username", key="login_u")
        p = st.text_input("Password", type='password', key="login_p")
        if st.button("Login", use_container_width=True):
            with get_connection() as conn:
                res = conn.cursor().execute('SELECT password FROM users WHERE username=?', (u,)).fetchone()
            if res and res[0] == make_hashes(p):
                st.session_state.username = u
                update_online_status(u)
                st.rerun()
            else: st.error("ชื่อหรือรหัสผ่านไม่ถูกต้อง")
    with tab_r:
        su = st.text_input("ชื่อผู้ใช้", key="reg_u")
        sp = st.text_input("รหัสผ่าน", type='password', key="reg_p")
        if st.button("Register", use_container_width=True):
            with get_connection() as conn:
                try:
                    conn.cursor().execute('INSERT INTO users(username, password) VALUES (?,?)', (su, make_hashes(sp)))
                    conn.commit()
                    st.success("สมัครสำเร็จ! กรุณาเข้าสู่ระบบ")
                except: st.error("ชื่อนี้มีผู้ใช้งานแล้ว")

# --- 4. UI ระบบหลัง Login ---
else:
    user_now = st.session_state.username
    update_online_status(user_now)
    check_and_show_popups(user_now)
    
    with get_connection() as conn:
        my_trips = pd.read_sql_query('''
            SELECT * FROM trips 
            WHERE id IN (SELECT trip_id FROM trip_members WHERE username = ? AND status = 'accepted')
        ''', conn, params=(user_now,))
        
        pending_trips = pd.read_sql_query('''
            SELECT t.*, tm.id as member_row_id FROM trips t
            JOIN trip_members tm ON t.id = tm.trip_id
            WHERE tm.username = ? AND tm.status = 'pending'
        ''', conn, params=(user_now,))
        
        notis = pd.read_sql_query('SELECT * FROM notifications WHERE receiver=? ORDER BY id DESC LIMIT 5', conn, params=(user_now,))

    # Sidebar
    st.sidebar.title(f"👤 {user_now}")
    
    total_alerts = len(notis[notis['is_read'] == 0]) + len(pending_trips)
    noti_text = f"🔔 แจ้งเตือน ({total_alerts})" if total_alerts > 0 else "🔔 แจ้งเตือน"
    
    menu = st.sidebar.radio("เมนู", [noti_text, "🧳 ทริปของฉัน", "➕ สร้างทริปใหม่"])
    
    if st.sidebar.button("Log out"):
        st.session_state.username = None
        st.session_state.current_trip_name = None
        st.rerun()

    # --- หน้าแจ้งเตือน & ระบบตอบรับคำเชิญเข้าทริป ---
    if "🔔" in menu:
        st.header("🔔 การแจ้งเตือนและคำเชิญทริป")
        
        if not pending_trips.empty:
            st.subheader("✉️ คำเชิญเข้าร่วมทริปใหม่")
            for _, p_trip in pending_trips.iterrows():
                # [FIXED KEY] ใช้ p_trip['member_row_id'] มาเป็น Key เพื่อให้ปุ่มมีตัวตนเฉพาะตัว ไม่ซ้ำกันในระบบ
                row_id = p_trip['member_row_id']
                
                with st.container(border=True):
                    c_text, c_accept, c_reject = st.columns([6, 1.5, 1.5])
                    c_text.markdown(f"**{p_trip['created_by']}** ได้เชิญคุณเข้าร่วมทริป **'{p_trip['name']}'** (งบประมาณ: ฿{p_trip['budget']:,.2f})")
                    
                    if c_accept.button("✅ ตอบรับคำเชิญ", key=f"btn_accept_{row_id}", use_container_width=True):
                        with get_connection() as conn:
                            conn.cursor().execute('UPDATE trip_members SET status="accepted" WHERE id=?', (row_id,))
                            send_notification(p_trip['created_by'], f"🤝 {user_now} ได้ตอบรับเข้าร่วมทริป '{p_trip['name']}' แล้ว!", conn=conn)
                            conn.commit()
                        st.session_state.current_trip_name = p_trip['name'] # เปลี่ยนหน้าไปทริปนี้ให้ทันที
                        st.success(f"เข้าร่วมทริป {p_trip['name']} สำเร็จ!")
                        st.rerun()
                        
                    if c_reject.button("❌ ปฏิเสธ", key=f"btn_reject_{row_id}", use_container_width=True):
                        with get_connection() as conn:
                            conn.cursor().execute('DELETE FROM trip_members WHERE id=?', (row_id,))
                            send_notification(p_trip['created_by'], f"👎 {user_now} ปฏิเสธการเข้าร่วมทริป '{p_trip['name']}'", conn=conn)
                            conn.commit()
                        st.info("ปฏิเสธคำเชิญเรียบร้อยแล้ว")
                        st.rerun()
            st.divider()

        st.subheader("💬 ประวัติการแจ้งเตือนล่าสุด")
        if notis.empty and pending_trips.empty: 
            st.info("ไม่มีข้อความ")
        else:
            for _, n in notis.iterrows():
                st.markdown(f"**[{n['created_at']}]** {n['message']}")
            if st.button("อ่านทั้งหมด", key="clear_all_notis"):
                with get_connection() as conn:
                    conn.cursor().execute('UPDATE notifications SET is_read=1 WHERE receiver=?', (user_now,))
                    conn.commit()
                st.rerun()

    # --- หน้าจัดการทริป ---
    elif menu == "🧳 ทริปของฉัน":
        if my_trips.empty: 
            st.info("ℹ️ คุณยังไม่มีทริปในขณะนี้ (หากเพื่อนเพิ่งเชิญเข้าทริป กรุณาไปที่เมนู '🔔 แจ้งเตือน' เพื่อกดยอมรับคำเชิญก่อนเข้าใช้งาน)")
        else:
            trip_options = my_trips['name'].tolist()
            
            if st.session_state.current_trip_name not in trip_options:
                st.session_state.current_trip_name = trip_options[0]
                
            sel_trip = st.selectbox(
                "เลือกทริป", 
                trip_options, 
                index=trip_options.index(st.session_state.current_trip_name),
                key="trip_select_box"
            )
            st.session_state.current_trip_name = sel_trip
            
            if sel_trip:
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
                            uploaded_file = st.file_uploader("📷 แนบรูปใบเสร็จ (ถ้ามี)", type=["jpg", "jpeg", "png"])
                            
                            if st.form_submit_button("บันทึกข้อมูล"):
                                if amt <= 0:
                                    st.error("กรุณาระบุจำนวนเงินที่มากกว่า 0")
                                else:
                                    with get_connection() as conn:
                                        cur = conn.cursor()
                                        cur.execute('''INSERT INTO transactions(date,type,category,amount,note,trip_id,created_by) 
                                                       VALUES (?,?,?,?,?,?,?)''',
                                                    (datetime.now().strftime("%Y-%m-%d"), ttype, cat, amt, note, t_id, user_now))
                                        tx_id = cur.lastrowid
                                        
                                        if uploaded_file is not None:
                                            file_ext = uploaded_file.name.split(".")[-1]
                                            bill_path = f"{BILL_DIR}/receipt_{tx_id}.{file_ext}"
                                            with open(bill_path, "wb") as f:
                                                f.write(uploaded_file.getbuffer())
                                            cur.execute('UPDATE transactions SET bill_path=? WHERE id=?', (bill_path, tx_id))
                                        
                                        m_list = cur.execute('SELECT username FROM trip_members WHERE trip_id=? AND username!=? AND status="accepted"', (t_id, user_now)).fetchall()
                                        for m in m_list:
                                            send_notification(m[0], f"💰 {user_now} เพิ่ม {ttype} {cat} ฿{amt:,.2f} ในทริป {sel_trip}", conn=conn)
                                        conn.commit()
                                    st.success("บันทึกรายจ่ายสำเร็จ!")
                                    st.rerun()

                    with tab2:
                        with get_connection() as conn:
                            df = pd.read_sql_query('SELECT * FROM transactions WHERE trip_id=?', conn, params=(t_id,))
                            member_count = conn.cursor().execute('SELECT COUNT(*) FROM trip_members WHERE trip_id=? AND status="accepted"', (t_id,)).fetchone()[0]
                        
                        st.subheader(f"📊 สรุปยอด {sel_trip}")
                        
                        if df.empty:
                            st.info("ยังไม่มีข้อมูลค่าใช้จ่ายในทริปนี้")
                        else:
                            total_expense = df[df['type'] == 'รายจ่าย']['amount'].sum()
                            total_income = df[df['type'] == 'รายรับ']['amount'].sum()
                            
                            c1, c2, c3, c4 = st.columns(4)
                            c1.metric("งบประมาณทริป", f"฿{t_row['budget']:,.2f}")
                            c2.metric("รายจ่ายรวม", f"฿{total_expense:,.2f}", delta=f"-{total_expense}" if total_expense > 0 else None, delta_color="inverse")
                            c3.metric("คงเหลือในงบ", f"฿{(t_row['budget'] - total_expense):,.2f}")
                            
                            per_person = total_expense / member_count if member_count > 0 else 0
                            c4.metric("หารเฉลี่ยต่อคน", f"฿{per_person:,.2f}", f"สมาชิกที่กดรับแล้ว {member_count} คน")
                            
                            st.divider()
                            
                            if st.session_state.editing_tx_id is not None:
                                with get_connection() as conn:
                                    tx_data = conn.cursor().execute('SELECT * FROM transactions WHERE id=?', (st.session_state.editing_tx_id,)).fetchone()
                                if tx_data:
                                    with st.expander("📝 ฟอร์มแก้ไขรายการ", expanded=True):
                                        with st.form("edit_form"):
                                            edit_type = st.selectbox("แก้ไขประเภท", ["รายจ่าย", "รายรับ"], index=0 if tx_data[2] == "รายจ่าย" else 1)
                                            edit_amt = st.number_input("แก้ไขจำนวนเงิน (บาท)", min_value=0.0, value=float(tx_data[4]))
                                            edit_cat = st.selectbox("แก้ไขหมวดหมู่", ["อาหาร", "เดินทาง", "ที่พัก", "ช้อปปิ้ง", "อื่นๆ"])
                                            edit_note = st.text_area("แก้ไขโน้ต", value=tx_data[5])
                                            if st.form_submit_button("💾 บันทึกการเปลี่ยนแปลง"):
                                                with get_connection() as conn:
                                                    conn.cursor().execute('UPDATE transactions SET type=?, category=?, amount=?, note=? WHERE id=?', (edit_type, edit_cat, edit_amt, edit_note, st.session_state.editing_tx_id))
                                                    conn.commit()
                                                st.session_state.editing_tx_id = None
                                                st.rerun()
                            
                            exp_df = df[df['type'] == 'รายจ่าย']
                            if not exp_df.empty:
                                fig = px.pie(exp_df, values='amount', names='category', hole=0.4)
                                st.plotly_chart(fig, use_container_width=True)

                            st.subheader("📋 รายการธุรกรรมทั้งหมด")
                            for _, row in df.iterrows():
                                col_info, col_edit, col_del = st.columns([6, 1, 1])
                                col_info.markdown(f"**[{row['date']}]** **{row['created_by']}** บันทึก **{row['type']}** **฿{row['amount']:,.2f}** ({row['category']}) - *{row['note']}*")
                                if row['created_by'] == user_now and col_edit.button("✏️ แก้ไข", key=f"btn_edit_{row['id']}"):
                                    st.session_state.editing_tx_id = row['id']
                                    st.rerun()
                                if (row['created_by'] == user_now or is_creator) and col_del.button("🗑️ ลบ", key=f"btn_del_{row['id']}"):
                                    with get_connection() as conn:
                                        conn.cursor().execute('DELETE FROM transactions WHERE id=?', (row['id'],))
                                        conn.commit()
                                    st.rerun()

                    with tab3:
                        st.subheader("👥 สมาชิกและสถานะการตอบรับ")
                        with get_connection() as conn:
                            members = pd.read_sql_query('''
                                SELECT u.username, u.last_active, tm.status FROM trip_members tm
                                JOIN users u ON tm.username = u.username WHERE tm.trip_id = ?
                            ''', conn, params=(t_id,))
                        
                        for _, m_row in members.iterrows():
                            status_icon = get_status_icon(m_row['last_active'])
                            invite_status = "⏱️ (กำลังรอการตอบรับ)" if m_row['status'] == 'pending' else "✅ (เข้าร่วมแล้ว)"
                            
                            c1, c2 = st.columns([4, 1])
                            c1.write(f"{status_icon} **{m_row['username']}** {invite_status} {'(ผู้สร้างทริป)' if m_row['username'] == t_row['created_by'] else ''}")
                            
                            if is_creator and m_row['username'] != user_now:
                                if c2.button("ลบออก", key=f"kick_{m_row['username']}"):
                                    with get_connection() as conn:
                                        conn.cursor().execute('DELETE FROM trip_members WHERE trip_id=? AND username=?', (t_id, m_row['username']))
                                        send_notification(m_row['username'], f"❌ คุณถูกลบออกจากทริป {sel_trip}", conn=conn)
                                        conn.commit()
                                    st.success("ลบสมาชิกสำเร็จ!")
                                    st.rerun()
                        
                        if is_creator:
                            st.divider()
                            st.subheader("✉️ เชิญเพื่อนเข้าทริป")
                            search_user = st.text_input("พิมพ์ชื่อผู้ใช้ที่ต้องการเชิญ", key="invite_user_input")
                            if search_user:
                                with get_connection() as conn:
                                    cur = conn.cursor()
                                    user_exists = cur.execute('SELECT COUNT(*) FROM users WHERE username=?', (search_user,)).fetchone()[0]
                                    is_already_member = cur.execute('SELECT COUNT(*) FROM trip_members WHERE trip_id=? AND username=?', (t_id, search_user)).fetchone()[0]
                                    
                                    if user_exists == 0:
                                        st.warning("⚠️ ไม่พบชื่อผู้ใช้งานนี้ในระบบ")
                                    elif is_already_member > 0:
                                        st.info("ℹ️ ผู้ใช้งานนี้อยู่ในทริปนี้แล้ว (หรือกำลังรอการตอบรับอยู่)")
                                    else:
                                        if st.button(f"ส่งคำเชิญให้ {search_user}", key="btn_send_invite"):
                                            cur.execute('INSERT INTO trip_members(trip_id, username, status) VALUES (?,?,"pending")', (t_id, search_user))
                                            send_notification(search_user, f"✉️ {user_now} เชิญคุณเข้าร่วมทริป '{sel_trip}' (กรุณากดตอบรับเพื่อเริ่มใช้งาน)", conn=conn)
                                            conn.commit()
                                            st.success(f"ส่งคำเชิญให้ {search_user} เรียบร้อยแล้ว ตัวแอพจะขึ้นป๊อปอัปฝั่งเพื่อนทันที!")
                                            st.rerun()

    elif menu == "➕ สร้างทริปใหม่":
        st.header("➕ สร้างทริปใหม่")
        with st.form("new_trip"):
            name = st.text_input("ชื่อทริป")
            bud = st.number_input("งบประมาณรวม (บาท)", min_value=0.0, step=500.0)
            if st.form_submit_button("สร้าง"):
                if name:
                    with get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute('INSERT INTO trips(name, budget, created_by, created_at) VALUES (?,?,?,?)', (name, bud, user_now, datetime.now().strftime("%Y-%m-%d")))
                        new_id = cur.lastrowid
                        cur.execute('INSERT INTO trip_members(trip_id, username, status) VALUES (?,?,"accepted")', (new_id, user_now))
                        conn.commit()
                    st.success("สร้างทริปสำเร็จ!")
                    st.rerun()
                else:
                    st.error("กรุณากรอกชื่อทริป")
