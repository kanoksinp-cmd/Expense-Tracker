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

if not os.path.exists(BILL_DIR):
    os.makedirs(BILL_DIR)
if not os.path.exists(PROFILE_DIR):
    os.makedirs(PROFILE_DIR)

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
    
    # 1. ตารางผู้ใช้งาน
    c.execute('''CREATE TABLE IF NOT EXISTS users(
                    username TEXT PRIMARY KEY, 
                    password TEXT,
                    profile_pic TEXT,
                    last_active TEXT)''')
                    
    # 2. ตารางทริป (เพิ่มใหม่)
    c.execute('''CREATE TABLE IF NOT EXISTS trips(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    budget REAL DEFAULT 0.0,
                    description TEXT,
                    created_by TEXT,
                    created_at TEXT)''')
                    
    # 3. ตารางธุรกรรม (เพิ่มคอลัมน์ trip_id)
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  date TEXT, 
                  type TEXT, 
                  category TEXT, 
                  amount REAL, 
                  note TEXT, 
                  bill_path TEXT,
                  created_by TEXT,
                  updated_by TEXT,
                  trip_id INTEGER)''')
    
    # --- Migration Logic สำหรับฐานข้อมูลเดิม ---
    # ตรวจสอบคอลัมน์ตาราง users
    try:
        c.execute('SELECT profile_pic FROM users LIMIT 1')
    except sqlite3.OperationalError:
        c.execute('ALTER TABLE users ADD COLUMN profile_pic TEXT')
        c.execute('ALTER TABLE users ADD COLUMN last_active TEXT')

    # ตรวจสอบคอลัมน์ตาราง transactions (รวมถึง trip_id)
    columns_to_add = [
        ('note', 'TEXT'),
        ('created_by', 'TEXT DEFAULT "System"'),
        ('updated_by', 'TEXT DEFAULT "System"'),
        ('trip_id', 'INTEGER DEFAULT NULL')
    ]
    for col_name, col_type in columns_to_add:
        try:
            c.execute(f'SELECT {col_name} FROM transactions LIMIT 1')
        except sqlite3.OperationalError:
            c.execute(f'ALTER TABLE transactions ADD COLUMN {col_name} {col_type}')
    
    conn.commit()
    conn.close()

create_tables()

# --- ฟังก์ชันจัดการข้อมูล ---
def save_bill(uploaded_file, username):
    if uploaded_file is not None:
        file_ext = uploaded_file.name.split('.')[-1]
        filename = f"{username}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{file_ext}"
        file_path = os.path.join(BILL_DIR, filename)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return file_path
    return None

def save_profile_pic(uploaded_file, username):
    if uploaded_file is not None:
        file_ext = uploaded_file.name.split('.')[-1]
        filename = f"profile_{username}.{file_ext}"
        file_path = os.path.join(PROFILE_DIR, filename)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        conn = get_connection()
        c = conn.cursor()
        c.execute('UPDATE users SET profile_pic=? WHERE username=?', (file_path, username))
        conn.commit()
        conn.close()
        return file_path
    return None

def update_user_active(username):
    conn = get_connection()
    c = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('UPDATE users SET last_active=? WHERE username=?', (now_str, username))
    conn.commit()
    conn.close()

def get_user_status(last_active_str):
    if not last_active_str:
        return "⚫ ออฟไลน์"
    try:
        last_active = datetime.strptime(last_active_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() - last_active < timedelta(minutes=3):
            return "🟢 ออนไลน์"
        else:
            return "⚫ ออฟไลน์"
    except:
        return "⚫ ออฟไลน์"

def update_transaction(t_id, date, t_type, cat, amount, note, username, trip_id, bill_path=None):
    conn = get_connection()
    c = conn.cursor()
    # แปลงทริปทั่วไปให้เป็น None หากเลือก "ไม่ระบุทริป"
    t_id_val = None if trip_id == 0 else trip_id
    
    if bill_path:
        c.execute('''UPDATE transactions 
                     SET date=?, type=?, category=?, amount=?, note=?, updated_by=?, trip_id=?, bill_path=? 
                     WHERE id=?''', (date, t_type, cat, amount, note, username, t_id_val, bill_path, t_id))
    else:
        c.execute('''UPDATE transactions 
                     SET date=?, type=?, category=?, amount=?, note=?, updated_by=?, trip_id=? 
                     WHERE id=?''', (date, t_type, cat, amount, note, username, t_id_val, t_id))
    conn.commit()
    conn.close()

def delete_transaction(t_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM transactions WHERE id=?', (t_id,))
    conn.commit()
    conn.close()

# --- UI Setup ---
st.set_page_config(page_title="Group Expense Tracker", page_icon="💰", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'editing_id' not in st.session_state:
    st.session_state.editing_id = None
if 'view_bill_id' not in st.session_state:
    st.session_state.view_bill_id = None

def main():
    if not st.session_state.logged_in:
        st.title("🔒 Group Login")
        auth_mode = st.tabs(["เข้าสู่ระบบ", "สมัครสมาชิก"])
        with auth_mode[0]:
            user = st.text_input("Username", key="l_user")
            pw = st.text_input("Password", type='password', key="l_pw")
            if st.button("Login"):
                conn = get_connection()
                c = conn.cursor()
                c.execute('SELECT password FROM users WHERE username = ?', (user,))
                res = c.fetchone()
                if res and check_hashes(pw, res[0]):
                    st.session_state.logged_in = True
                    st.session_state.username = user
                    update_user_active(user)
                    st.rerun()
                else: st.error("ข้อมูลไม่ถูกต้อง")
        with auth_mode[1]:
            new_u = st.text_input("ชื่อผู้ใช้ใหม่")
            new_p = st.text_input("รหัสผ่านใหม่", type='password')
            if st.button("สมัครสมาชิก"):
                if new_u and new_p:
                    conn = get_connection()
                    try:
                        conn.cursor().execute('INSERT INTO users(username, password) VALUES (?,?)', (new_u, make_hashes(new_p)))
                        conn.commit()
                        st.success("สมัครสำเร็จ!")
                    except: st.error("ชื่อนี้ถูกใช้ไปแล้ว")
                    finally: conn.close()
    else:
        update_user_active(st.session_state.username)

        # ดึงข้อมูลผู้ใช้และทริปทั้งหมดเพื่อไปใช้งานในหน้าระบบ
        conn = get_connection()
        user_df = pd.read_sql_query('SELECT * FROM users', conn)
        trips_df = pd.read_sql_query('SELECT * FROM trips', conn)
        conn.close()
        
        current_user_info = user_df[user_df['username'] == st.session_state.username].iloc[0]
        p_pic = current_user_info['profile_pic']

        # ทำดิกชันนารีจับคู่เพื่อแปลงเลข ID ทริป เป็นชื่อทริป
        trip_options = {0: "📌 ไม่ระบุทริปส่วนกลาง"}
        for _, t_row in trips_df.iterrows():
            trip_options[t_row['id']] = t_row['name']

        # --- Sidebar ---
        st.sidebar.title("👤 โปรไฟล์ของคุณ")
        if p_pic and os.path.exists(p_pic):
            st.sidebar.image(p_pic, width=100)
        else:
            st.sidebar.markdown("🧑‍💻 *ยังไม่มีรูปโปรไฟล์*")
            
        st.sidebar.subheader(f"{st.session_state.username}")
        st.sidebar.caption("🟢 กำลังใช้งาน")
        
        if st.sidebar.button("ออกจากระบบ"):
            st.session_state.logged_in = False
            st.rerun()

        st.sidebar.divider()
        menu = st.sidebar.radio("เมนู", ["สรุปภาพรวมทั้งหมด", "บันทึกรายการใหม่", "🧳 จัดการทริปกลุ่ม", "ตั้งค่าโปรไฟล์"])

        # --- เมนู: 🧳 จัดการทริปกลุ่ม (เพิ่มใหม่) ---
        if menu == "🧳 จัดการทริปกลุ่ม":
            st.header("🧳 บริหารจัดการทริปกลุ่ม")
            
            t_tab1, t_tab2 = st.tabs(["📊 ทริปปัจจุบัน", "➕ สร้างทริปใหม่"])
            
            with t_tab2:
                st.subheader("สร้างทริป/โครงการใหม่")
                with st.form("create_trip_form", clear_on_submit=True):
                    trip_name = st.text_input("ชื่อทริป (เช่น ทริปภูเก็ต 2026, ค่าส่วนกลางประจำปี)")
                    trip_budget = st.number_input("งบประมาณตั้งต้น (บาท)", min_value=0.0, value=0.0)
                    trip_desc = st.text_area("รายละเอียด / คำอธิบายทริป")
                    
                    if st.form_submit_button("➕ สร้างทริป"):
                        if trip_name:
                            conn = get_connection()
                            conn.cursor().execute('''INSERT INTO trips(name, budget, description, created_by, created_at) 
                                                     VALUES (?,?,?,?,?)''',
                                                  (trip_name, trip_budget, trip_desc, st.session_state.username, datetime.now().strftime("%Y-%m-%d %H:%M")))
                            conn.commit()
                            conn.close()
                            st.success(f"สร้างทริป '{trip_name}' สำเร็จ!")
                            st.rerun()
                        else:
                            st.error("กรุณากรอกชื่อทริป")
            
            with t_tab1:
                st.subheader("รายการทริปทั้งหมด")
                if trips_df.empty:
                    st.info("ยังไม่มีการสร้างทริปในกลุ่มนี้")
                else:
                    conn = get_connection()
                    all_trans = pd.read_sql_query('SELECT * FROM transactions', conn)
                    conn.close()
                    
                    for _, t_row in trips_df.iterrows():
                        with st.expander(f"🗺️ {t_row['name']} (งบประมาณ: ฿{t_row['budget']:,.2f})"):
                            st.write(f"**รายละเอียด:** {t_row['description'] if t_row['description'] else '-'}")
                            st.caption(f"สร้างโดย: {t_row['created_by']} เมื่อ {t_row['created_at']}")
                            
                            # คำนวณรายจ่ายเฉพาะทริปนี้
                            if not all_trans.empty:
                                t_expenses = all_trans[(all_trans['trip_id'] == t_row['id']) & (all_trans['type'] == 'รายจ่าย')]['amount'].sum()
                                t_income = all_trans[(all_trans['trip_id'] == t_row['id']) & (all_trans['type'] == 'รายรับ')]['amount'].sum()
                            else:
                                t_expenses, t_income = 0.0, 0.0
                                
                            meta_col1, meta_col2, meta_col3 = st.columns(3)
                            meta_col1.metric("ยอดรับเงินเข้าทริป", f"฿{t_income:,.2f}")
                            meta_col2.metric("ยอดใช้จ่ายในทริป", f"฿{t_expenses:,.2f}")
                            
                            # คำนวณเปอร์เซ็นต์การใช้งบ
                            if t_row['budget'] > 0:
                                percent = (t_expenses / t_row['budget'])
                                st.progress(min(percent, 1.0), text=f"ใช้ไปแล้ว {percent*100:.1f}% ของงบประมาณ")
                                if t_expenses > t_row['budget']:
                                    st.warning("⚠️ ยอดใช้จ่ายเกินงบประมาณที่ตั้งไว้!")
                            else:
                                st.info("ทริปนี้ไม่ได้กำหนดงบประมาณตั้งต้นไว้")

        # --- เมนู: ตั้งค่าโปรไฟล์ ---
        elif menu == "ตั้งค่าโปรไฟล์":
            st.header("⚙️ ตั้งค่าข้อมูลส่วนตัว")
            st.subheader(f"ผู้ใช้งาน: {st.session_state.username}")
            
            new_pic = st.file_uploader("อัปโหลด/เปลี่ยนรูปโปรไฟล์", type=['jpg', 'png', 'jpeg'])
            if st.button("บันทึกรูปโปรไฟล์"):
                if new_pic:
                    save_profile_pic(new_pic, st.session_state.username)
                    st.success("เปลี่ยนรูปโปรไฟล์สำเร็จแล้ว!")
                    st.rerun()
                else: st.warning("กรุณาเลือกไฟล์รูปภาพก่อนกดบันทึก")

            st.divider()
            st.subheader("👥 สมาชิกในกลุ่มทั้งหมด")
            for _, u_row in user_df.iterrows():
                u_status = get_user_status(u_row['last_active'])
                col_u1, col_u2 = st.columns([0.5, 4])
                if u_row['profile_pic'] and os.path.exists(u_row['profile_pic']):
                    col_u1.image(u_row['profile_pic'], width=40)
                else: col_u1.write("👤")
                col_u2.markdown(f"**{u_row['username']}** | สถานะ: {u_status}")

        # --- เมนู: บันทึกรายการใหม่ ---
        elif menu == "บันทึกรายการใหม่":
            st.header("📝 เพิ่มรายการใหม่")
            with st.form("add_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                t_date = col1.date_input("วันที่", datetime.now())
                t_type = col1.selectbox("ประเภท", ["รายรับ", "รายจ่าย"])
                t_cat = col2.selectbox("หมวดหมู่", ["อาหาร", "เดินทาง", "ส่วนกลาง", "อื่นๆ"])
                t_amount = col2.number_input("จำนวนเงิน", min_value=0.0)
                
                # ฟังก์ชันผูกรายการเข้ากับทริป
                chosen_trip_id = st.selectbox(
                    "ผูกเข้ากับทริป/โครงการ (เลือกได้หากเป็นรายจ่ายของทริป)", 
                    options=list(trip_options.keys()), 
                    format_func=lambda x: trip_options[x]
                )
                
                t_note = st.text_area("รายละเอียดเพิ่มเติม (เช่น ร้านค้า, หมายเหตุ)")
                t_bill = st.file_uploader("อัปโหลดสลิป/รูปบิล", type=['jpg', 'png', 'jpeg'])
                
                if st.form_submit_button("บันทึกข้อมูล"):
                    bill_path = save_bill(t_bill, st.session_state.username)
                    db_trip_id = None if chosen_trip_id == 0 else chosen_trip_id
                    
                    conn = get_connection()
                    conn.cursor().execute('''INSERT INTO transactions(date, type, category, amount, note, bill_path, created_by, updated_by, trip_id) 
                                             VALUES (?,?,?,?,?,?,?,?,?)''', 
                                          (t_date.strftime("%Y-%m-%d"), t_type, t_cat, t_amount, t_note, bill_path, st.session_state.username, st.session_state.username, db_trip_id))
                    conn.commit()
                    conn.close()
                    st.success("บันทึกสำเร็จ!")

        # --- เมนู: สรุปภาพรวม ---
        elif menu == "สรุปภาพรวมทั้งหมด":
            st.header("📊 รายการบันทึกทั้งหมด")
            
            # ดรอปดาวน์สำหรับกรองข้อมูลดูเป็นรายทริปบนหน้าแดชบอร์ดหลัก
            filter_trip = st.selectbox("🔍 ตัวกรอง: เลือกดูข้อมูลตามทริป", options=list(trip_options.keys()), format_func=lambda x: trip_options[x])
            
            conn = get_connection()
            if filter_trip == 0:
                df = pd.read_sql_query('SELECT * FROM transactions', conn)
            else:
                df = pd.read_sql_query('SELECT * FROM transactions WHERE trip_id = ?', conn, params=(filter_trip,))
            conn.close()

            if not df.empty:
                t_in = df[df['type'] == 'รายรับ']['amount'].sum()
                t_out = df[df['type'] == 'รายจ่าย']['amount'].sum()
                
                m1, m2, m3 = st.columns(3)
                m1.metric("ยอดรับรวม", f"฿{t_in:,.2f}")
                m2.metric("ยอดจ่ายรวม", f"฿{t_out:,.2f}")
                m3.metric("คงเหลือสุทธิ (ในตัวกรองนี้)", f"฿{t_in - t_out:,.2f}")
                st.divider()

                # ส่วนแก้ไขรายการ
                if st.session_state.editing_id:
                    edit_row = df[df['id'] == st.session_state.editing_id].iloc[0]
                    with st.expander(f"🛠️ แก้ไขรายการ #{st.session_state.editing_id}", expanded=True):
                        ec1, ec2 = st.columns(2)
                        n_date = ec1.date_input("วันที่", datetime.strptime(edit_row['date'], "%Y-%m-%d"))
                        n_amt = ec2.number_input("จำนวนเงิน", value=float(edit_row['amount']))
                        
                        # เลือกแก้ทริปย้อนหลังได้ในหน้านี้
                        current_trip_index = int(edit_row['trip_id']) if pd.notna(edit_row['trip_id']) else 0
                        n_trip = st.selectbox("เปลี่ยนทริป", options=list(trip_options.keys()), index=list(trip_options.keys()).index(current_trip_index), format_func=lambda x: trip_options[x])
                        
                        n_note = st.text_area("รายละเอียด", value=edit_row['note'] if edit_row['note'] else "")
                        n_bill = st.file_uploader("เปลี่ยนรูปบิล", type=['jpg', 'png', 'jpeg'])
                        
                        eb1, eb2, _ = st.columns([1,1,4])
                        if eb1.button("✅ ยืนยัน"):
                            new_path = save_bill(n_bill, st.session_state.username) if n_bill else None
                            update_transaction(st.session_state.editing_id, n_date.strftime("%Y-%m-%d"), edit_row['type'], edit_row['category'], n_amt, n_note, st.session_state.username, n_trip, new_path)
                            st.session_state.editing_id = None
                            st.rerun()
                        if eb2.button("❌ ยกเลิก"):
                            st.session_state.editing_id = None
                            st.rerun()

                # --- ตารางแสดงผลแบบแนวนอน ---
                cols_width = [0.6, 1, 1.2, 1, 2, 1.2, 0.7, 1.2, 0.8]
                h = st.columns(cols_width)
                headers = ["ID", "วันที่", "ประเภท", "จำนวน", "รายละเอียด", "ทริป", "บิล", "บันทึกโดย", "จัดการ"]
                for col, head in zip(h, headers):
                    col.markdown(f"**{head}**")

                for _, row in df.sort_values('id', ascending=False).iterrows():
                    r_id = row['id']
                    c = st.columns(cols_width)
                    c[0].write(f"#{r_id}")
                    c[1].write(row['date'])
                    c[2].write(f"{row['type']}\n({row['category']})")
                    
                    color = "green" if row['type'] == "รายรับ" else "red"
                    c[3].markdown(f":{color}[฿{row['amount']:,.2f}]")
                    c[4].write(row['note'] if row['note'] else "-")
                    
                    # คอลัมน์แสดงว่าผูกกับทริปไหน (เพิ่มใหม่)
                    t_id_raw = row['trip_id']
                    c[5].write(trip_options.get(int(t_id_raw) if pd.notna(t_id_raw) else 0, "-"))

                    path = row['bill_path']
                    if path and isinstance(path, str) and os.path.exists(path):
                        btn_txt = "❌ หุบ" if st.session_state.view_bill_id == r_id else "🖼️ ดู"
                        if c[6].button(btn_txt, key=f"v_{r_id}"):
                            st.session_state.view_bill_id = r_id if st.session_state.view_bill_id != r_id else None
                            st.rerun()
                    else: c[6].write("-")

                    creator_info = user_df[user_df['username'] == row['created_by']]
                    c_status = get_user_status(creator_info.iloc[0]['last_active']) if not creator_info.empty else "⚫ ออฟไลน์"

                    c[7].markdown(f"**{row['created_by']}** ({c_status})", unsafe_allow_html=True)
                    
                    m_edit, m_del = c[8].columns(2)
                    if m_edit.button("📝", key=f"e_{r_id}"):
                        st.session_state.editing_id = r_id
                        st.rerun()
                    if m_del.button("🗑️", key=f"d_{r_id}"):
                        delete_transaction(r_id)
                        st.rerun()
                    
                    if st.session_state.view_bill_id == r_id:
                        st.image(path, width=400)
                    st.divider()
            else:
                st.info("ยังไม่มีข้อมูลบันทึกในทริปหรือตัวกรองที่เลือก")

if __name__ == '__main__':
    main()
