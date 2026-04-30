import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime

# --- การตั้งค่าฐานข้อมูล ---
conn = sqlite3.connect('expense_tracker.db', check_same_thread=False)
c = conn.cursor()

def create_tables():
    # ตารางผู้ใช้งาน
    c.execute('CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, password TEXT)')
    # ตารางบันทึกรายรับรายจ่าย
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  username TEXT, 
                  date TEXT, 
                  type TEXT, 
                  category TEXT, 
                  amount REAL, 
                  bill_path TEXT)''')
    conn.commit()

create_tables()

# --- ฟังก์ชันจัดการไฟล์ ---
if not os.path.exists("bills"):
    os.makedirs("bills")

def save_bill(uploaded_file, username):
    if uploaded_file is not None:
        file_path = f"bills/{username}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uploaded_file.name}"
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return file_path
    return None

# --- ส่วนของ UI ---
st.title("💰 โปรแกรมบันทึกรายรับ-รายจ่าย")

# ระบบ Login แบบง่าย
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    menu = ["Login", "Register"]
    choice = st.sidebar.selectbox("เมนูจัดการผู้ใช้", menu)

    if choice == "Register":
        new_user = st.text_input("Username")
        new_pw = st.text_input("Password", type='password')
        if st.button("สมัครสมาชิก"):
            try:
                c.execute('INSERT INTO users(username, password) VALUES (?,?)', (new_user, new_pw))
                conn.commit()
                st.success("สมัครสมาชิกสำเร็จ! กรุณา Login")
            except:
                st.error("Username นี้มีผู้ใช้แล้ว")

    elif choice == "Login":
        user = st.text_input("Username")
        pw = st.text_input("Password", type='password')
        if st.button("เข้าสู่ระบบ"):
            c.execute('SELECT * FROM users WHERE username = ? AND password = ?', (user, pw))
            if c.fetchone():
                st.session_state.logged_in = True
                st.session_state.username = user
                st.rerun()
            else:
                st.error("Username หรือ Password ไม่ถูกต้อง")

else:
    # --- หน้าหลักหลังจาก Login ---
    st.sidebar.write(f"สวัสดีคุณ: **{st.session_state.username}**")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    tab1, tab2 = st.tabs(["📝 บันทึกรายการ", "📊 ประวัติและสรุปผล"])

    with tab1:
        st.header("เพิ่มรายการใหม่")
        col1, col2 = st.columns(2)
        with col1:
            t_date = st.date_input("วันที่", datetime.now())
            t_type = st.selectbox("ประเภท", ["รายรับ", "รายจ่าย"])
            t_amount = st.number_input("จำนวนเงิน", min_value=0.0, step=1.0)
        with col2:
            t_cat = st.text_input("หมวดหมู่ (เช่น อาหาร, เงินเดือน)")
            t_bill = st.file_uploader("อัปโหลดบิล/ใบเสร็จ", type=['jpg', 'png', 'pdf'])

        if st.button("บันทึกข้อมูล"):
            bill_path = save_bill(t_bill, st.session_state.username)
            c.execute('''INSERT INTO transactions(username, date, type, category, amount, bill_path) 
                         VALUES (?,?,?,?,?,?)''', 
                      (st.session_state.username, t_date.strftime("%Y-%m-%d"), t_type, t_cat, t_amount, bill_path))
            conn.commit()
            st.success("บันทึกรายการเรียบร้อย!")

    with tab2:
        st.header("ประวัติการทำรายการ")
        query = 'SELECT date, type, category, amount, bill_path FROM transactions WHERE username = ? ORDER BY date DESC'
        df = pd.read_sql_query(query, conn, params=(st.session_state.username,))
        
        if not df.empty:
            st.dataframe(df.drop(columns=['bill_path']), use_container_width=True)
            
            # ส่วนแสดงรูปภาพบิล
            st.subheader("🔍 ดูรูปภาพบิล")
            row_idx = st.number_input("เลือกแถวที่ต้องการดูบิล (0, 1, 2...)", min_value=0, max_value=len(df)-1, step=1)
            selected_bill = df.iloc[row_idx]['bill_path']
            
            if selected_bill and os.path.exists(selected_bill):
                st.image(selected_bill, caption="หลักฐานการจ่ายเงิน")
            else:
                st.info("รายการนี้ไม่มีการอัปโหลดบิลไว้")
        else:
            st.info("ยังไม่มีข้อมูลบันทึก")
