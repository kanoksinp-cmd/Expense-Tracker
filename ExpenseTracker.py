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
    
    # Migration: ตรวจสอบคอลัมน์ที่อาจตกหล่นจากเวอร์ชันเก่า
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
    # ป้องกัน DB Locked โดยการเลือกใช้ Connection ที่ถูกส่งมาจากฟังก์ชันแม่ (ถ้ามี)
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
    
    conn = get_connection()
    # [FIXED] แก้ไข SQL Query ตรงนี้ให้ดึงทริปจากรายชื่อสมาชิกในตาราง trip_members โดยตรง 
    # ทำให้เพื่อนที่ถูกเชิญมองเห็นทริปร่วมกันได้ทันทีแบบ 100%
    my_trips = pd.read_sql_query('''
        SELECT * FROM trips 
        WHERE id IN (SELECT trip_id FROM trip_members WHERE username = ?)
    ''', conn, params=(user_now,))
    
    notis = pd.read_sql_query('SELECT * FROM notifications WHERE receiver=? ORDER BY id DESC LIMIT 5', conn, params=(user_now,))
    conn.close()

    # Sidebar
    st.sidebar.title(f"👤 {user_now}")
    unread_count = len(notis[notis['is_read'] == 0])
    noti_text = f"🔔 แจ้งเตือน ({unread_count})" if unread_count > 0 else "🔔 แจ้งเตือน"
    menu = st.sidebar.radio("เมนู", [noti_text, "🧳 ทริปของฉัน", "➕ สร้างทริปใหม่"])
    
    if st.sidebar.button("Log out"):
        st.session_state.username = None
        st.rerun()

    # --- หน้าแจ้งเตือน ---
    if "🔔" in menu:
        st.header("🔔 แจ้งเตือนล่าสุด")
        if notis.empty: st.info("ไม่มีข้อความ")
        else:
            for _, n in notis.iterrows():
                st.markdown(f"**[{n['created_at']}]** {n['message']}")
            if st.button("อ่านทั้งหมด"):
                conn = get_connection(); conn.cursor().execute('UPDATE notifications SET is_read=1 WHERE receiver=?', (user_now,)); conn.commit(); conn.close(); st.rerun()

    # --- หน้าจัดการทริป ---
    elif menu == "🧳 ทริปของฉัน":
        if my_trips.empty: st.info("ยังไม่มีทริป")
        else:
            sel_trip = st.selectbox("เลือกทริป", my_trips['name'].tolist())
            t_row = my_trips[my_trips['name'] == sel_trip].iloc[0]
            t_id = t_row['id']
            is_creator = (t_row['created_by'] == user_now)

            tab1, tab2, tab3 = st.tabs(["📝 รายจ่าย", "📊 สรุปและวิเคราะห์", "👥 สมาชิก"])

            # แท็บ 1: บันทึกข้อมูล
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
                            conn = get_connection()
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
                            
                            m_list = cur.execute('SELECT username FROM trip_members WHERE trip_id=? AND username!=?', (t_id, user_now)).fetchall()
                            for m in m_list:
                                send_notification(m[0], f"💰 {user_now} เพิ่ม {ttype} {cat} ฿{amt:,.2f} ในทริป {sel_trip}", conn=conn)
                            
                            conn.commit()
                            conn.close()
                            st.success("บันทึกรายจ่ายสำเร็จ!")
                            st.rerun()

            # แท็บ 2: สรุป วิเคราะห์ และแก้ไขรายการ
            with tab2:
                conn = get_connection()
                df = pd.read_sql_query('SELECT * FROM transactions WHERE trip_id=?', conn, params=(t_id,))
                member_count = conn.cursor().execute('SELECT COUNT(*) FROM trip_members WHERE trip_id=?', (t_id,)).fetchone()[0]
                conn.close()
                
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
                    c4.metric("หารเฉลี่ยต่อคน", f"฿{per_person:,.2f}", f"สมาชิก {member_count} คน")
                    
                    st.divider()
                    
                    # กล่องฟอร์มแก้ไขข้อมูล
                    if st.session_state.editing_tx_id is not None:
                        st.info("🛠️ กำลังแก้ไขรายการ")
                        conn = get_connection()
                        tx_data = conn.cursor().execute('SELECT * FROM transactions WHERE id=?', (st.session_state.editing_tx_id,)).fetchone()
                        conn.close()
                        
                        if tx_data:
                            with st.expander("📝 ฟอร์มแก้ไขรายการ บันทึกโดย " + tx_data[7], expanded=True):
                                with st.form("edit_form"):
                                    edit_type = st.selectbox("แก้ไขประเภท", ["รายจ่าย", "รายรับ"], index=0 if tx_data[2] == "รายจ่าย" else 1)
                                    edit_amt = st.number_input("แก้ไขจำนวนเงิน (บาท)", min_value=0.0, value=float(tx_data[4]))
                                    edit_cat = st.selectbox("แก้ไขหมวดหมู่", ["อาหาร", "เดินทาง", "ที่พัก", "ช้อปปิ้ง", "อื่นๆ"], index=["อาหาร", "เดินทาง", "ที่พัก", "ช้อปปิ้ง", "อื่นๆ"].index(tx_data[3]) if tx_data[3] in ["อาหาร", "เดินทาง", "ที่พัก", "ช้อปปิ้ง", "อื่นๆ"] else 4)
                                    edit_note = st.text_area("แก้ไขโน้ต", value=tx_data[5])
                                    edit_file = st.file_uploader("📷 เปลี่ยนรูปใบเสร็จใหม่ (ข้ามหากไม่ต้องการเปลี่ยน)", type=["jpg", "jpeg", "png"])
                                    
                                    c_btn1, c_btn2 = st.columns(2)
                                    if c_btn1.form_submit_button("💾 บันทึกการเปลี่ยนแปลง", use_container_width=True):
                                        conn = get_connection()
                                        cur = conn.cursor()
                                        
                                        current_bill_path = tx_data[6]
                                        if edit_file is not None:
                                            file_ext = edit_file.name.split(".")[-1]
                                            current_bill_path = f"{BILL_DIR}/receipt_{tx_data[0]}.{file_ext}"
                                            with open(current_bill_path, "wb") as f:
                                                f.write(edit_file.getbuffer())
                                                
                                        cur.execute('''UPDATE transactions 
                                                       SET type=?, category=?, amount=?, note=?, bill_path=? 
                                                       WHERE id=?''', (edit_type, edit_cat, edit_amt, edit_note, current_bill_path, st.session_state.editing_tx_id))
                                        conn.commit()
                                        conn.close()
                                        st.session_state.editing_tx_id = None
                                        st.success("อัปเดตรายการเรียบร้อยแล้ว!")
                                        st.rerun()
                                        
                                    if c_btn2.form_submit_button("❌ ยกเลิก", use_container_width=True):
                                        st.session_state.editing_tx_id = None
                                        st.rerun()
                        st.divider()

                    # แสดงกราฟรายจ่าย
                    exp_df = df[df['type'] == 'รายจ่าย']
                    if not exp_df.empty:
                        st.subheader("📈 สัดส่วนรายจ่ายตามหมวดหมู่")
                        fig = px.pie(exp_df, values='amount', names='category', hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu)
                        st.plotly_chart(fig, use_container_width=True)
                    
                    # ตารางรายการธุรกรรมพร้อมปุ่ม แก้ไข/ลบ
                    st.subheader("📋 รายการธุรกรรมทั้งหมด")
                    for _, row in df.iterrows():
                        with st.container():
                            col_info, col_edit, col_del = st.columns([6, 1, 1])
                            bill_indicator = "📎 มีใบเสร็จ" if row['bill_path'] else "❌ ไม่มีใบเสร็จ"
                            col_info.markdown(f"**[{row['date']}]** **{row['created_by']}** บันทึก **{row['type']}** หมวด **{row['category']}** ยอดเงิน **฿{row['amount']:,.2f}**  \n*โน้ต:* {row['note']} | *({bill_indicator})*")
                            
                            if row['created_by'] == user_now:
                                if col_edit.button("✏️ แก้ไข", key=f"btn_edit_{row['id']}"):
                                    st.session_state.editing_tx_id = row['id']
                                    st.rerun()
                            else:
                                col_edit.write("")
                                
                            if row['created_by'] == user_now or is_creator:
                                if col_del.button("🗑️ ลบ", key=f"btn_del_{row['id']}"):
                                    conn = get_connection()
                                    if row['bill_path'] and os.path.exists(row['bill_path']):
                                        try: os.remove(row['bill_path'])
                                        except: pass
                                    conn.cursor().execute('DELETE FROM transactions WHERE id=?', (row['id'],))
                                    conn.commit()
                                    conn.close()
                                    st.success("ลบรายการสำเร็จ!")
                                    st.rerun()
                            else:
                                col_del.write("")
                        st.write("---")

                    # ตรวจสอบรูปใบเสร็จ
                    df_with_bills = df[df['bill_path'].notna() & (df['bill_path'] != "")]
                    if not df_with_bills.empty:
                        st.subheader("🖼️ เปิดดูใบเสร็จที่แนบไว้")
                        selected_bill = st.selectbox("เลือกรายการที่ต้องการดูใบเสร็จ", df_with_bills.apply(lambda r: f"ID {r['id']}: {r['category']} - ฿{r['amount']}", axis=1))
                        if selected_bill:
                            tx_sel_id = selected_bill.split(":")[0].replace("ID ", "")
                            path_to_img = df_with_bills[df_with_bills['id'] == int(tx_sel_id)]['bill_path'].values[0]
                            if os.path.exists(path_to_img):
                                st.image(path_to_img, caption=selected_bill, width=400)

            # แท็บ 3: สมาชิกกลุ่มและการส่งการแจ้งเตือนแบบปลอดภัยจากปัญหา DB Locked
            with tab3:
                st.subheader("👥 สมาชิกและสถานะ")
                conn = get_connection()
                members = pd.read_sql_query('''
                    SELECT u.username, u.last_active FROM trip_members tm
                    JOIN users u ON tm.username = u.username WHERE tm.trip_id = ?
                ''', conn, params=(t_id,))
                
                for _, m_row in members.iterrows():
                    status = get_status_icon(m_row['last_active'])
                    c1, c2 = st.columns([4, 1])
                    c1.write(f"{status} **{m_row['username']}** {'(ผู้สร้างทริป)' if m_row['username'] == t_row['created_by'] else ''}")
                    
                    if is_creator and m_row['username'] != user_now:
                        if c2.button("ลบออก", key=f"kick_{m_row['username']}"):
                            cur = conn.cursor()
                            cur.execute('DELETE FROM trip_members WHERE trip_id=? AND username=?', (t_id, m_row['username']))
                            send_notification(m_row['username'], f"❌ คุณถูกลบออกจากทริป {sel_trip}", conn=conn)
                            conn.commit()
                            conn.close()
                            st.success("ลบสมาชิกสำเร็จ!")
                            st.rerun()
                
                if is_creator:
                    st.divider()
                    st.subheader("✉️ เชิญเพื่อนเข้าทริป")
                    search_user = st.text_input("พิมพ์ชื่อผู้ใช้ที่ต้องการเชิญ")
                    if search_user:
                        cur = conn.cursor()
                        user_exists = cur.execute('SELECT COUNT(*) FROM users WHERE username=?', (search_user,)).fetchone()[0]
                        is_already_member = cur.execute('SELECT COUNT(*) FROM trip_members WHERE trip_id=? AND username=?', (t_id, search_user)).fetchone()[0]
                        
                        if user_exists == 0:
                            st.warning("⚠️ ไม่พบชื่อผู้ใช้งานนี้ในระบบ")
                        elif is_already_member > 0:
                            st.info("ℹ️ ผู้ใช้งานนี้อยู่ในทริปนี้แล้ว")
                        else:
                            if st.button(f"ส่งคำเชิญให้ {search_user}"):
                                cur.execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (t_id, search_user))
                                send_notification(search_user, f"✉️ {user_now} เชิญคุณเข้าร่วมทริป '{sel_trip}'", conn=conn)
                                conn.commit()
                                conn.close()
                                st.success(f"เพิ่ม {search_user} เข้าทริปสำเร็จ!"); st.rerun()
                try:
                    conn.close()
                except:
                    pass

    elif menu == "➕ สร้างทริปใหม่":
        st.header("➕ สร้างทริปใหม่")
        with st.form("new_trip"):
            name = st.text_input("ชื่อทริป")
            bud = st.number_input("งบประมาณรวม (บาท)", min_value=0.0, step=500.0)
            if st.form_submit_button("สร้าง"):
                if name:
                    conn = get_connection(); cur = conn.cursor()
                    cur.execute('INSERT INTO trips(name, budget, created_by, created_at) VALUES (?,?,?,?)', (name, bud, user_now, datetime.now().strftime("%Y-%m-%d")))
                    new_id = cur.lastrowid
                    cur.execute('INSERT INTO trip_members(trip_id, username) VALUES (?,?)', (new_id, user_now))
                    conn.commit(); conn.close(); st.success("สร้างทริปสำเร็จ!"); st.rerun()
                else:
                    st.error("กรุณากรอกชื่อทริป")
