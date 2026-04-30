import streamlit as st
import pandas as pd
import sqlite3
import os
import hashlib
from datetime import datetime

# --- การตั้งค่าพื้นฐานและฐานข้อมูล ---
DB_FILE = 'expense_tracker.db'
BILL_DIR = "bills"

# สร้างโฟลเดอร์เก็บรูปบิลถ้ายังไม่มี
if not os.path.exists(BILL_DIR):
    os.makedirs(BILL_DIR)

# ฟังก์ชันจัดการรหัสผ่าน (Hashing)
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return hashed_text
    return False

# ฟังก์ชันเชื่อมต่อฐานข้อมูล
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

# --- ฟังก์ชันเสริม ---
def save_bill(uploaded_file, username):
    if uploaded_file is not None:
        file_ext = uploaded_file.name.split('.')[-1]
        filename = f"{username}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{file_ext}"
        file_path = os.path.join(BILL_DIR, filename)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return file_path
    return None

# --- ตั้งค่าหน้าเว็บ Streamlit ---
st.set_page_config(page_title="ระบบบันทึกรายรับ-รายจ่าย", page_icon="💰", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# --- ส่วนควบคุมการเข้าใช้งาน ---
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
                    st.success(f"ยินดีต้อนรับคุณ {user}!")
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
                        st.success("สมัครสมาชิกสำเร็จ! กรุณาไปที่แท็บเข้าสู่ระบบ")
                    except sqlite3.IntegrityError:
                        st.error("ชื่อผู้ใช้นี้มีคนใช้แล้ว")
                    finally:
                        conn.close()
                else:
                    st.warning("กรุณากรอกข้อมูลให้ครบถ้วน")

    else:
        # --- หน้าตาโปรแกรมหลัก (เมื่อ Login แล้ว) ---
        st.sidebar.title(f"👤 {st.session_state.username}")
        if st.sidebar.button("ออกจากระบบ"):
            st.session_state.logged_in = False
            st.rerun()

        menu = st.sidebar.radio("เมนูหลัก", ["สรุปภาพรวม", "บันทึกรายการ"])

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
                    st.success("บันทึกรายการเรียบร้อย!")

        elif menu == "สรุปภาพรวม":
            st.header("📊 สรุปภาวะทางการเงิน")
            conn = get_connection()
            query = 'SELECT * FROM transactions WHERE username = ?'
            df = pd.read_sql_query(query, conn, params=(st.session_state.username,))
            conn.close()

            if not df.empty:
                # ส่วนแสดงตัวเลขสรุป
                income = df[df['type'] == 'รายรับ']['amount'].sum()
                expense = df[df['type'] == 'รายจ่าย']['amount'].sum()
                balance = income - expense
                
                m1, m2, m3 = st.columns(3)
                m1.metric("รายรับทั้งหมด", f"฿{income:,.2f}")
                m2.metric("รายจ่ายทั้งหมด", f"฿{expense:,.2f}")
                m3.metric("คงเหลือ", f"฿{balance:,.2f}")

                # ส่วนแสดงกราฟและตาราง
                st.divider()
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.subheader("ประวัติรายการล่าสุด")
                    st.dataframe(df[['date', 'type', 'category', 'amount']].sort_values('date', ascending=False), use_container_width=True)
                
                with c2:
                    st.subheader("สัดส่วนรายจ่าย")
                    expense_df = df[df['type'] == 'รายจ่าย']
                    if not expense_df.empty:
                        pie_data = expense_df.groupby('category')['amount'].sum()
                        st.pie_chart(pie_data)
                    else:
                        st.info("ยังไม่มีข้อมูลรายจ่าย")

                # ส่วนดูรูปภาพสลิป
                st.divider()
                st.subheader("🔍 ตรวจสอบหลักฐาน (สลิป)")
                receipt_list = df[df['bill_path'].notnull()]
                if not receipt_list.empty:
                    selected_id = st.selectbox("เลือก ID รายการเพื่อดูสลิป", receipt_list['id'])
                    path = receipt_list[receipt_list['id'] == selected_id]['bill_path'].values[0]
                    if os.path.exists(path):
                        st.image(path, caption=f"สลิปของรายการที่ {selected_id}", width=400)
                else:
                    st.info("ยังไม่มีการอัปโหลดสลิป")
            else:
                st.info("ยังไม่มีข้อมูลในระบบ เริ่มบันทึกรายการได้เลย!")

if __name__ == '__main__':
    main()
