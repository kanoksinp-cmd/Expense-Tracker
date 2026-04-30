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
    
    # เพิ่มคอลัมน์ created_by และ updated_by
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  date TEXT, 
                  type TEXT, 
                  category TEXT, 
                  amount REAL, 
                  bill_path TEXT,
                  created_by TEXT,
                  updated_by TEXT)''')
    conn.commit()
    conn.close()

create_tables()

# --- ฟังก์ชันจัดการข้อมูล (CRUD) ---
def update_transaction(t_id, date, t_type, cat, amount, username):
    conn = get_connection()
    c = conn.cursor()
    # บันทึกว่าใครเป็นคนแก้ไขล่าสุดใน updated_by
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

# --- UI และ Logic ---
st.set_page_config(page_title="ระบบบันทึกกลุ่ม", page_icon="👥", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'editing_id' not in st.session_state:
    st.session_state.editing_id = None

def main():
    if not st.session_state.logged_in:
        # --- ส่วน Login (เหมือนเดิม) ---
        st.title("🔒 Group Expense Login")
        auth_mode = st.tabs(["เข้าสู่ระบบ", "สมัครสมาชิก"])
        with auth_mode[0]:
            user = st.text_input("Username")
            pw = st.text_input("Password", type='password')
            if st.button("Login"):
                conn = get_connection()
                c = conn.cursor()
                c.execute('SELECT password FROM users WHERE username = ?', (user,))
                res = c.fetchone()
                if res and check_hashes(pw, res[0]):
                    st.session_state.logged_in = True
                    st.session_state.username = user
                    st.rerun()
                else: st.error("ผิดพลาด")
        with auth_mode[1]:
            # ส่วนสมัครสมาชิก... (เหมือนโค้ดเดิมของคุณ)
            pass
    else:
        # --- หน้าหลักหลัง Login ---
        st.sidebar.title(f"👤 ผู้ใช้: {st.session_state.username}")
        if st.sidebar.button("ออกจากระบบ"):
            st.session_state.logged_in = False
            st.rerun()

        menu = st.sidebar.radio("เมนู", ["สรุปภาพรวมทั้งหมด", "บันทึกรายการใหม่"])

        if menu == "บันทึกรายการใหม่":
            st.header("📝 เพิ่มรายการใหม่ (ในนามกลุ่ม)")
            with st.form("add_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                t_date = col1.date_input("วันที่", datetime.now())
                t_type = col1.selectbox("ประเภท", ["รายรับ", "รายจ่าย"])
                t_cat = col2.selectbox("หมวดหมู่", ["อาหาร", "ส่วนกลาง", "เดินทาง", "อื่นๆ"])
                t_amount = col2.number_input("จำนวนเงิน", min_value=0.0)
                
                if st.form_submit_button("บันทึก"):
                    conn = get_connection()
                    c = conn.cursor()
                    # บันทึกทั้ง created_by และ updated_by เป็นชื่อผู้ใช้ปัจจุบันในครั้งแรก
                    c.execute('''INSERT INTO transactions(date, type, category, amount, created_by, updated_by) 
                                 VALUES (?,?,?,?,?,?)''', 
                              (t_date.strftime("%Y-%m-%d"), t_type, t_cat, t_amount, st.session_state.username, st.session_state.username))
                    conn.commit()
                    st.success(f"บันทึกโดย {st.session_state.username} เรียบร้อย!")

        elif menu == "สรุปภาพรวมทั้งหมด":
            st.header("📊 รายการทั้งหมดของกลุ่ม")
            conn = get_connection()
            # ดึงข้อมูลทั้งหมดโดยไม่กรอง username เพื่อให้เห็นของทุกคน
            df = pd.read_sql_query('SELECT * FROM transactions', conn)
            conn.close()

            if not df.empty:
                # --- ส่วนแก้ไข ---
                if st.session_state.editing_id:
                    edit_row = df[df['id'] == st.session_state.editing_id].iloc[0]
                    with st.expander("🛠️ แก้ไขรายการนี้", expanded=True):
                        c1, c2 = st.columns(2)
                        new_date = c1.date_input("วันที่", datetime.strptime(edit_row['date'], "%Y-%m-%d"))
                        new_amt = c2.number_input("จำนวนเงิน", value=float(edit_row['amount']))
                        if st.button("ยืนยันการแก้ไข"):
                            update_transaction(st.session_state.editing_id, new_date.strftime("%Y-%m-%d"), 
                                               edit_row['type'], edit_row['category'], new_amt, st.session_state.username)
                            st.session_state.editing_id = None
                            st.rerun()

                # --- ตารางแสดงผล ---
                # หัวตาราง
                h1, h2, h3, h4, h5, h6, h7 = st.columns([1, 2, 2, 2, 2, 2, 1])
                h1.bold("ID")
                h2.bold("วันที่")
                h3.bold("ประเภท/หมวด")
                h4.bold("จำนวน")
                h5.bold("บันทึกโดย")
                h6.bold("แก้ไขล่าสุด")
                h7.bold("จัดการ")

                for _, row in df.sort_values('id', ascending=False).iterrows():
                    st.divider()
                    c1, c2, c3, c4, c5, c6, c7 = st.columns([1, 2, 2, 2, 2, 2, 1])
                    c1.write(f"#{row['id']}")
                    c2.write(row['date'])
                    c3.write(f"{row['type']}\n({row['category']})")
                    c4.subheader(f"฿{row['amount']:,.2f}")
                    c5.caption(f"👤 {row['created_by']}")
                    
                    # เน้นชื่อคนแก้ไขล่าสุด
                    color = "blue" if row['updated_by'] == st.session_state.username else "gray"
                    c6.markdown(f":{color}[👤 {row['updated_by']}]")
                    
                    btn_col1, btn_col2 = c7.columns(2)
                    if btn_col1.button("📝", key=f"ed_{row['id']}"):
                        st.session_state.editing_id = row['id']
                        st.rerun()
                    if btn_col2.button("🗑️", key=f"dl_{row['id']}"):
                        delete_transaction(row['id'])
                        st.rerun()
            else:
                st.info("ยังไม่มีข้อมูลในกลุ่มนี้")

if __name__ == '__main__':
    main()
