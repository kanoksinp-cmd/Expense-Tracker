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
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def create_tables():
    conn = get_connection()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, password TEXT)')
    # ตารางที่รองรับระบบกลุ่มและประวัติผู้แก้ไข
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
st.set_page_config(page_title="ระบบบันทึกรายรับ-รายจ่ายกลุ่ม", page_icon="💰", layout="wide")

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
                        st.success("สมัครสมาชิกสำเร็จ! กรุณาไปที่แท็บเข้าสู่ระบบ")
                    except sqlite3.IntegrityError:
                        st.error("ชื่อผู้ใช้นี้มีคนใช้แล้ว")
                    finally:
                        conn.close()

    else:
        # --- เมนูหลัก ---
        st.sidebar.title(f"👤 {st.session_state.username}")
        if st.sidebar.button("ออกจากระบบ"):
            st.session_state.logged_in = False
            st.rerun()

        menu = st.sidebar.radio("เมนูหลัก", ["สรุปภาพรวมทั้งหมด", "บันทึกรายการใหม่"])

        if menu == "บันทึกรายการใหม่":
            st.header("📝 เพิ่มรายการใหม่")
            with st.form("transaction_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                t_date = col1.date_input("วันที่", datetime.now())
                t_type = col1.selectbox("ประเภท", ["รายรับ", "รายจ่าย"])
                t_cat = col2.selectbox("หมวดหมู่", ["อาหาร", "เดินทาง", "ค่าใช้จ่ายทั่วไป", "เงินเดือน", "ช้อปปิ้ง", "อื่นๆ"])
                t_amount = col2.number_input("จำนวนเงิน", min_value=0.0, step=10.0)
                
                t_bill = st.file_uploader("อัปโหลดสลิป (ถ้ามี)", type=['jpg', 'png', 'jpeg'])
                
                if st.form_submit_button("บันทึกข้อมูล"):
                    bill_path = save_bill(t_bill, st.session_state.username)
                    conn = get_connection()
                    c = conn.cursor()
                    c.execute('''INSERT INTO transactions(date, type, category, amount, bill_path, created_by, updated_by) 
                                 VALUES (?,?,?,?,?,?,?)''', 
                              (t_date.strftime("%Y-%m-%d"), t_type, t_cat, t_amount, bill_path, st.session_state.username, st.session_state.username))
                    conn.commit()
                    conn.close()
                    st.success(f"บันทึกข้อมูลเรียบร้อยโดยคุณ {st.session_state.username}")

        elif menu == "สรุปภาพรวมทั้งหมด":
            st.header("📊 รายการทั้งหมดของกลุ่ม")
            conn = get_connection()
            df = pd.read_sql_query('SELECT * FROM transactions', conn)
            conn.close()

            if not df.empty:
                # --- ส่วนการแก้ไขข้อมูล ---
                if st.session_state.editing_id:
                    try:
                        edit_row = df[df['id'] == st.session_state.editing_id].iloc[0]
                        with st.expander("✏️ แก้ไขรายการ", expanded=True):
                            ec1, ec2 = st.columns(2)
                            new_date = ec1.date_input("วันที่", datetime.strptime(edit_row['date'], "%Y-%m-%d"))
                            new_type = ec1.selectbox("ประเภท", ["รายรับ", "รายจ่าย"], index=["รายรับ", "รายจ่าย"].index(edit_row['type']))
                            new_cat = ec2.selectbox("หมวดหมู่", ["อาหาร", "เดินทาง", "ค่าใช้จ่ายทั่วไป", "เงินเดือน", "ช้อปปิ้ง", "อื่นๆ"], 
                                                   index=["อาหาร", "เดินทาง", "ค่าใช้จ่ายทั่วไป", "เงินเดือน", "ช้อปปิ้ง", "อื่นๆ"].index(edit_row['category']))
                            new_amt = ec2.number_input("จำนวนเงิน", value=float(edit_row['amount']))
                            
                            b1, b2, _ = st.columns([1,1,4])
                            if b1.button("บันทึกการแก้ไข"):
                                update_transaction(st.session_state.editing_id, new_date.strftime("%Y-%m-%d"), new_type, new_cat, new_amt, st.session_state.username)
                                st.session_state.editing_id = None
                                st.rerun()
                            if b2.button("ยกเลิก"):
                                st.session_state.editing_id = None
                                st.rerun()
                    except IndexError:
                        st.session_state.editing_id = None

                # --- ตารางแสดงผล (แก้ไข Error จากภาพ image_0cc455.png) ---
                h1, h2, h3, h4, h5, h6, h7 = st.columns([0.5, 1.2, 1.5, 1.2, 1.2, 1.2, 1])
                with h1: st.markdown("**ID**")
                with h2: st.markdown("**วันที่**")
                with h3: st.markdown("**ประเภท (หมวด)**")
                with h4: st.markdown("**จำนวนเงิน**")
                with h5: st.markdown("**บันทึกโดย**")
                with h6: st.markdown("**แก้ไขล่าสุด**")
                with h7: st.markdown("**จัดการ**")
                st.divider()

                for _, row in df.sort_values('date', ascending=False).iterrows():
                    c1, c2, c3, c4, c5, c6, c7 = st.columns([0.5, 1.2, 1.5, 1.2, 1.2, 1.2, 1])
                    c1.write(f"#{row['id']}")
                    c2.write(row['date'])
                    c3.write(f"{row['type']} ({row['category']})")
                    c4.write(f"฿{row['amount']:,.2f}")
                    c5.caption(row['created_by'])
                    
                    # ไฮไลต์ถ้าเป็นคนแก้ไขล่าสุด
                    edit_color = "blue" if row['updated_by'] == st.session_state.username else "gray"
                    c6.markdown(f":{edit_color}[{row['updated_by']}]")
                    
                    b_edit, b_del = c7.columns(2)
                    if b_edit.button("📝", key=f"e_{row['id']}"):
                        st.session_state.editing_id = row['id']
                        st.rerun()
                    if b_del.button("🗑️", key=f"d_{row['id']}"):
                        delete_transaction(row['id'])
                        st.rerun()
                    st.divider()

                # สรุปตัวเลข
                inc = df[df['type'] == 'รายรับ']['amount'].sum()
                exp = df[df['type'] == 'รายจ่าย']['amount'].sum()
                st.sidebar.markdown(f"### สรุปยอดกลุ่ม")
                st.sidebar.success(f"รายรับ: ฿{inc:,.2f}")
                st.sidebar.error(f"รายจ่าย: ฿{exp:,.2f}")
                st.sidebar.info(f"คงเหลือ: ฿{inc-exp:,.2f}")
            else:
                st.info("ยังไม่มีข้อมูลบันทึกในระบบ")

if __name__ == '__main__':
    main()
