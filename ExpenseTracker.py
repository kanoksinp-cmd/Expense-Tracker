import streamlit as st
import pandas as pd
import sqlite3
import os
import hashlib
from datetime import datetime

# --- การตั้งค่าพื้นฐาน ---
DB_FILE = 'expense_tracker.db'
BILL_DIR = "bills"

if not os.path.exists(BILL_DIR):
    os.makedirs(BILL_DIR)

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
    c.execute('CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, password TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  date TEXT, 
                  type TEXT, 
                  category TEXT, 
                  amount REAL, 
                  bill_path TEXT,
                  created_by TEXT,
                  updated_by TEXT)''')
    
    # Migration Logic: ป้องกัน Error แบบในรูป image_0cc07a.png
    try:
        c.execute('SELECT created_by FROM transactions LIMIT 1')
    except sqlite3.OperationalError:
        c.execute('ALTER TABLE transactions ADD COLUMN created_by TEXT DEFAULT "System"')
        c.execute('ALTER TABLE transactions ADD COLUMN updated_by TEXT DEFAULT "System"')
    
    conn.commit()
    conn.close()

create_tables()

# --- ฟังก์ชันเสริมจัดการข้อมูล ---
def save_bill(uploaded_file, username):
    if uploaded_file is not None:
        file_ext = uploaded_file.name.split('.')[-1]
        filename = f"{username}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{file_ext}"
        file_path = os.path.join(BILL_DIR, filename)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return file_path
    return None

def update_transaction(t_id, date, t_type, cat, amount, username, bill_path=None):
    conn = get_connection()
    c = conn.cursor()
    if bill_path:
        # กรณีมีการเปลี่ยนรูปบิลใหม่
        c.execute('''UPDATE transactions 
                     SET date=?, type=?, category=?, amount=?, updated_by=?, bill_path=? 
                     WHERE id=?''', (date, t_type, cat, amount, username, bill_path, t_id))
    else:
        # กรณีไม่เปลี่ยนรูปบิล (ใช้รูปเดิม)
        c.execute('''UPDATE transactions 
                     SET date=?, type=?, category=?, amount=?, updated_by=? 
                     WHERE id=?''', (date, t_type, cat, amount, username, t_id))
    conn.commit()
    conn.close()

def delete_transaction(t_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM transactions WHERE id=?', (t_id,))
    conn.commit()
    conn.close()

# --- ส่วนหน้าตาโปรแกรม (Streamlit UI) ---
st.set_page_config(page_title="Group Expense Tracker", page_icon="💰", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'editing_id' not in st.session_state:
    st.session_state.editing_id = None

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
                    st.rerun()
                else: st.error("ข้อมูลไม่ถูกต้อง")
        with auth_mode[1]:
            new_u = st.text_input("ชื่อผู้ใช้ใหม่")
            new_p = st.text_input("รหัสผ่านใหม่", type='password')
            if st.button("สมัครสมาชิก"):
                if new_u and new_p:
                    conn = get_connection()
                    try:
                        conn.cursor().execute('INSERT INTO users VALUES (?,?)', (new_u, make_hashes(new_p)))
                        conn.commit()
                        st.success("สมัครสำเร็จ!")
                    except: st.error("ชื่อนี้ถูกใช้ไปแล้ว")
                    finally: conn.close()
    else:
        # --- Sidebar ---
        st.sidebar.title(f"👤 {st.session_state.username}")
        if st.sidebar.button("ออกจากระบบ"):
            st.session_state.logged_in = False
            st.rerun()

        menu = st.sidebar.radio("เมนู", ["สรุปภาพรวมทั้งหมด", "บันทึกรายการใหม่"])

        # --- เมนู: บันทึกรายการใหม่ ---
        if menu == "บันทึกรายการใหม่":
            st.header("📝 เพิ่มรายการใหม่")
            with st.form("add_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                t_date = col1.date_input("วันที่", datetime.now())
                t_type = col1.selectbox("ประเภท", ["รายรับ", "รายจ่าย"])
                t_cat = col2.selectbox("หมวดหมู่", ["อาหาร", "เดินทาง", "ส่วนกลาง", "เงินเดือน", "ช้อปปิ้ง", "อื่นๆ"])
                t_amount = col2.number_input("จำนวนเงิน", min_value=0.0)
                t_bill = st.file_uploader("อัปโหลดสลิป/รูปบิล (ถ้ามี)", type=['jpg', 'png', 'jpeg'])
                
                if st.form_submit_button("บันทึกข้อมูล"):
                    bill_path = save_bill(t_bill, st.session_state.username)
                    conn = get_connection()
                    conn.cursor().execute('''INSERT INTO transactions(date, type, category, amount, bill_path, created_by, updated_by) 
                                             VALUES (?,?,?,?,?,?,?)''', 
                                          (t_date.strftime("%Y-%m-%d"), t_type, t_cat, t_amount, bill_path, st.session_state.username, st.session_state.username))
                    conn.commit()
                    st.success("บันทึกสำเร็จ!")

        # --- เมนู: สรุปภาพรวม ---
        elif menu == "สรุปภาพรวมทั้งหมด":
            st.header("📊 รายการทั้งหมด")
            conn = get_connection()
            df = pd.read_sql_query('SELECT * FROM transactions', conn)
            conn.close()

            if not df.empty:
                # --- ส่วนแก้ไขรายการ (เพิ่มความสามารถในการเปลี่ยนรูปบิล) ---
                if st.session_state.editing_id:
                    edit_row = df[df['id'] == st.session_state.editing_id].iloc[0]
                    with st.expander(f"🛠️ แก้ไขรายการ ID #{st.session_state.editing_id}", expanded=True):
                        ec1, ec2 = st.columns(2)
                        new_date = ec1.date_input("แก้ไขวันที่", datetime.strptime(edit_row['date'], "%Y-%m-%d"))
                        new_type = ec1.selectbox("แก้ไขประเภท", ["รายรับ", "รายจ่าย"], index=["รายรับ", "รายจ่าย"].index(edit_row['type']))
                        new_cat = ec2.selectbox("แก้ไขหมวดหมู่", ["อาหาร", "เดินทาง", "ส่วนกลาง", "เงินเดือน", "ช้อปปิ้ง", "อื่นๆ"], 
                                               index=["อาหาร", "เดินทาง", "ส่วนกลาง", "เงินเดือน", "ช้อปปิ้ง", "อื่นๆ"].index(edit_row['category']))
                        new_amt = ec2.number_input("แก้ไขจำนวนเงิน", value=float(edit_row['amount']))
                        
                        st.markdown("---")
                        st.write("🖼️ **จัดการรูปบิล**")
                        if edit_row['bill_path']:
                            st.image(edit_row['bill_path'], width=200, caption="รูปบิลปัจจุบัน")
                        new_bill = st.file_uploader("อัปโหลดรูปบิลใหม่เพื่อเปลี่ยน (ทิ้งว่างไว้ถ้าไม่ต้องการเปลี่ยน)", type=['jpg', 'png', 'jpeg'], key="edit_bill_upload")
                        
                        eb1, eb2, _ = st.columns([1,1,4])
                        if eb1.button("✅ ยืนยันการแก้ไข"):
                            # ตรวจสอบว่ามีการอัปโหลดรูปใหม่ไหม
                            updated_bill_path = save_bill(new_bill, st.session_state.username) if new_bill else None
                            update_transaction(st.session_state.editing_id, new_date.strftime("%Y-%m-%d"), new_type, new_cat, new_amt, st.session_state.username, updated_bill_path)
                            st.session_state.editing_id = None
                            st.success("แก้ไขข้อมูลเรียบร้อย!")
                            st.rerun()
                        if eb2.button("❌ ยกเลิก"):
                            st.session_state.editing_id = None
                            st.rerun()

                # --- การแสดงผลตาราง ---
                st.divider()
                cols_width = [0.5, 1.2, 1.5, 1.2, 1, 1.2, 1.2, 1]
                h = st.columns(cols_width)
                headers = ["ID", "วันที่", "ประเภท (หมวด)", "จำนวน", "บิล", "บันทึกโดย", "แก้ไขล่าสุด", "จัดการ"]
                for i, head in enumerate(headers):
                    h[i].markdown(f"**{head}**")

                for _, row in df.sort_values('id', ascending=False).iterrows():
                    c = st.columns(cols_width)
                    c[0].write(f"#{row['id']}")
                    c[1].write(row['date'])
                    c[2].write(f"{row['type']} ({row['category']})")
                    c[3].write(f"฿{row['amount']:,.2f}")
                    
                    # คอลัมน์แสดงรูปบิล
                    if row['bill_path'] and os.path.exists(row['bill_path']):
                        if c[4].button("🖼️ ดู", key=f"v_{row['id']}"):
                            st.image(row['bill_path'], caption=f"บิลรายการ #{row['id']}", width=400)
                    else:
                        c[4].write("-")

                    c[5].caption(row['created_by'])
                    u_color = "blue" if row['updated_by'] == st.session_state.username else "gray"
                    c[6].markdown(f":{u_color}[{row['updated_by']}]")
                    
                    e_btn, d_btn = c[7].columns(2)
                    if e_btn.button("📝", key=f"e_{row['id']}"):
                        st.session_state.editing_id = row['id']
                        st.rerun()
                    if d_btn.button("🗑️", key=f"d_{row['id']}"):
                        delete_transaction(row['id'])
                        st.rerun()
                    st.divider()
            else:
                st.info("ยังไม่มีข้อมูลบันทึกไว้")

if __name__ == '__main__':
    main()
