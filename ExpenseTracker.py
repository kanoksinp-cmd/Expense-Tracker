import streamlit as st
import pandas as pd
import sqlite3
import os
import hashlib
from datetime import datetime

# --- การตั้งค่าพื้นฐานและฐานข้อมูล ---
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
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    return conn

def create_tables():
    conn = get_connection()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, password TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  username TEXT, 
                  date TEXT, 
                  type TEXT, 
                  category TEXT, 
                  amount REAL, 
                  bill_path TEXT)''')
    conn.commit()
    conn.close()

create_tables()

def save_bill(uploaded_file, username):
    if uploaded_file is not None:
        file_ext = uploaded_file.name.split('.')[-1]
        filename = f"{username}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{file_ext}"
        file_path = os.path.join(BILL_DIR, filename)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return file_path
    return None

# --- ส่วนของการจัดการข้อมูล (CRUD) ---
def update_transaction(t_id, date, t_type, cat, amount):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''UPDATE transactions 
                 SET date=?, type=?, category=?, amount=? 
                 WHERE id=?''', (date, t_type, cat, amount, t_id))
    conn.commit()
    conn.close()

def delete_transaction(t_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM transactions WHERE id=?', (t_id,))
    conn.commit()
    conn.close()

# --- ตั้งค่าหน้าเว็บ ---
st.set_page_config(page_title="ระบบบันทึกรายรับ-รายจ่าย", page_icon="💰", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'editing_id' not in st.session_state:
    st.session_state.editing_id = None

def main():
    if not st.session_state.logged_in:
        st.title("🔒 กรุณาเข้าสู่ระบบ")
        auth_mode = st.tabs(["เข้าสู่ระบบ", "สมัครสมาชิก"])
        
        with auth_mode[0]:
            user = st.text_input("Username", key="login_user")
            pw = st.text_input("Password", type='password', key="login_pw")
            if st.button("Login"):
                conn = get_connection()
                c = conn.cursor()
                c.execute('SELECT password FROM users WHERE username = ?', (user,))
                result = c.fetchone()
                conn.close()
                if result and check_hashes(pw, result[0]):
                    st.session_state.logged_in = True
                    st.session_state.username = user
                    st.rerun()
                else:
                    st.error("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")

        with auth_mode[1]:
            new_user = st.text_input("ชื่อผู้ใช้ใหม่")
            new_pw = st.text_input("รหัสผ่านใหม่", type='password')
            if st.button("สร้างบัญชี"):
                if new_user and new_pw:
                    conn = get_connection()
                    c = conn.cursor()
                    try:
                        c.execute('INSERT INTO users(username, password) VALUES (?,?)', 
                                  (new_user, make_hashes(new_pw)))
                        conn.commit()
                        st.success("สมัครสำเร็จ!")
                    except sqlite3.IntegrityError:
                        st.error("ชื่อนี้มีคนใช้แล้ว")
                    finally:
                        conn.close()

    else:
        # --- หน้าหลักหลัง Login ---
        st.sidebar.title(f"👤 {st.session_state.username}")
        if st.sidebar.button("ออกจากระบบ"):
            st.session_state.logged_in = False
            st.rerun()

        menu = st.sidebar.radio("เมนูหลัก", ["สรุปภาพรวม", "บันทึกรายการ"])

        # --- เมนู: บันทึกรายการ ---
        if menu == "บันทึกรายการ":
            st.header("📝 เพิ่มรายการใหม่")
            with st.form("transaction_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    t_date = st.date_input("วันที่", datetime.now())
                    t_type = st.selectbox("ประเภท", ["รายรับ", "รายจ่าย"])
                with col2:
                    t_cat = st.selectbox("หมวดหมู่", ["อาหาร", "เดินทาง", "ค่าใช้จ่ายทั่วไป", "เงินเดือน", "ช้อปปิ้ง", "อื่นๆ"])
                    t_amount = st.number_input("จำนวนเงิน", min_value=0.0, step=10.0)
                
                t_bill = st.file_uploader("อัปโหลดสลิป/บิล (ถ้ามี)", type=['jpg', 'png', 'jpeg'])
                
                if st.form_submit_button("บันทึกข้อมูล"):
                    bill_path = save_bill(t_bill, st.session_state.username)
                    conn = get_connection()
                    c = conn.cursor()
                    c.execute('''INSERT INTO transactions(username, date, type, category, amount, bill_path) 
                                 VALUES (?,?,?,?,?,?)''', 
                              (st.session_state.username, t_date.strftime("%Y-%m-%d"), t_type, t_cat, t_amount, bill_path))
                    conn.commit()
                    conn.close()
                    st.success("บันทึกเรียบร้อย!")

        # --- เมนู: สรุปภาพรวม (เพิ่มส่วนแก้ไข) ---
        elif menu == "สรุปภาพรวม":
            st.header("📊 สรุปภาวะทางการเงิน")
            conn = get_connection()
            df = pd.read_sql_query('SELECT * FROM transactions WHERE username = ?', conn, params=(st.session_state.username,))
            conn.close()

            if not df.empty:
                # Metrics
                income = df[df['type'] == 'รายรับ']['amount'].sum()
                expense = df[df['type'] == 'รายจ่าย']['amount'].sum()
                st.columns(3)[0].metric("รายรับ", f"฿{income:,.2f}")
                st.columns(3)[1].metric("รายจ่าย", f"฿{expense:,.2f}")
                st.columns(3)[2].metric("คงเหลือ", f"฿{income-expense:,.2f}")

                st.divider()

                # --- ส่วนแก้ไขข้อมูล (จะปรากฏเมื่อกดปุ่ม Edit) ---
                if st.session_state.editing_id:
                    st.subheader("✏️ แก้ไขรายการ")
                    edit_row = df[df['id'] == st.session_state.editing_id].iloc[0]
                    
                    with st.expander("เปิดหน้าต่างแก้ไข", expanded=True):
                        ec1, ec2 = st.columns(2)
                        new_date = ec1.date_input("วันที่ใหม่", datetime.strptime(edit_row['date'], "%Y-%m-%d"))
                        new_type = ec1.selectbox("ประเภทใหม่", ["รายรับ", "รายจ่าย"], index=["รายรับ", "รายจ่าย"].index(edit_row['type']))
                        new_cat = ec2.selectbox("หมวดหมู่ใหม่", ["อาหาร", "เดินทาง", "ค่าใช้จ่ายทั่วไป", "เงินเดือน", "ช้อปปิ้ง", "อื่นๆ"], 
                                                index=["อาหาร", "เดินทาง", "ค่าใช้จ่ายทั่วไป", "เงินเดือน", "ช้อปปิ้ง", "อื่นๆ"].index(edit_row['category']))
                        new_amt = ec2.number_input("จำนวนเงินใหม่", value=float(edit_row['amount']))
                        
                        btn1, btn2, _ = st.columns([1,1,4])
                        if btn1.button("✅ บันทึกการแก้ไข"):
                            update_transaction(st.session_state.editing_id, new_date.strftime("%Y-%m-%d"), new_type, new_cat, new_amt)
                            st.session_state.editing_id = None
                            st.success("แก้ไขข้อมูลแล้ว!")
                            st.rerun()
                        if btn2.button("❌ ยกเลิก"):
                            st.session_state.editing_id = None
                            st.rerun()
                    st.divider()

                # --- ตารางรายการพร้อมปุ่ม Edit/Delete ---
                st.subheader("📜 ประวัติรายการ")
                # แสดงผลแบบวน Loop เพื่อสร้างปุ่มในแต่ละแถว
                for index, row in df.sort_values('date', ascending=False).iterrows():
                    cols = st.columns([1, 2, 2, 2, 2, 1, 1])
                    cols[0].write(f"#{row['id']}")
                    cols[1].write(row['date'])
                    cols[2].write(row['type'])
                    cols[3].write(row['category'])
                    cols[4].write(f"฿{row['amount']:,.2f}")
                    
                    if cols[5].button("📝", key=f"edit_{row['id']}"):
                        st.session_state.editing_id = row['id']
                        st.rerun()
                    
                    if cols[6].button("🗑️", key=f"del_{row['id']}"):
                        delete_transaction(row['id'])
                        st.warning(f"ลบรายการที่ {row['id']} แล้ว")
                        st.rerun()

            else:
                st.info("ยังไม่มีข้อมูล")

if __name__ == '__main__':
    main()
