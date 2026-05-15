import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image

# 1. ตั้งค่าหน้าจอ
st.set_page_config(page_title="Trip Expense Splitter Pro", layout="wide")

# 2. ฟังก์ชันจัดการฐานข้อมูล
DB_FILE = "trip_database.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # ตาราง User กลาง
    cursor.execute('CREATE TABLE IF NOT EXISTS all_users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)')
    # ตารางทริป
    cursor.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)')
    # ตารางสมาชิกในแต่ละทริป
    cursor.execute('CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, name TEXT, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    # ตารางค่าใช้จ่าย
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, description TEXT, 
            amount REAL, payer_name TEXT, split_members TEXT, image_blob BLOB,
            FOREIGN KEY(trip_id) REFERENCES trips(id)
        )
    ''')
    # ตารางบันทึกการเคลียร์เงิน
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, 
            debtor TEXT, creditor TEXT, amount REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(trip_id) REFERENCES trips(id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- 3. Sidebar: ศูนย์ควบคุมของ Leader ---
st.sidebar.header("⚙️ ระบบจัดการข้อมูล")

# 3.1 ลงทะเบียน User ใหม่
with st.sidebar.expander("👤 ลงทะเบียน User (ทำครั้งเดียว)"):
    reg_name = st.text_input("ระบุชื่อผู้ใช้งาน:").strip()
    if st.button("ลงทะเบียน"):
        if reg_name:
            try:
                conn = get_db_connection()
                conn.execute("INSERT INTO all_users (name) VALUES (?)", (reg_name,))
                conn.commit()
                conn.close()
                st.toast(f"ลงทะเบียนคุณ {reg_name} สำเร็จ!", icon='✅') # MsgBox
                st.rerun()
            except sqlite3.IntegrityError:
                st.sidebar.error("ชื่อนี้มีในระบบแล้ว")
        else:
            st.sidebar.warning("กรุณากรอกชื่อ")

# 3.2 สร้างทริปใหม่
st.sidebar.markdown("---")
new_trip_name = st.sidebar.text_input("➕ สร้างทริปใหม่:").strip()
if st.sidebar.button("บันทึกทริป"):
    if new_trip_name:
        try:
            conn = get_db_connection()
            conn.execute("INSERT INTO trips (name) VALUES (?)", (new_trip_name,))
            conn.commit()
            conn.close()
            st.toast(f"สร้างทริป {new_trip_name} เรียบร้อย!", icon='🗺️') # MsgBox
            st.rerun()
        except: st.sidebar.error("ชื่อทริปซ้ำ")

# 3.3 เลือกทริป
conn = get_db_connection()
trips_df = pd.read_sql_query("SELECT * FROM trips", conn)
trip_list = trips_df["name"].tolist() if not trips_df.empty else []

if not trip_list:
    st.title("✈️ ระบบจัดการทริป")
    st.info("กรุณาลงทะเบียน User และสร้างทริปที่เมนูซ้ายมือ")
    conn.close()
    st.stop()

current_trip = st.sidebar.selectbox("🗺️ เลือกทริปที่ต้องการจัดการ:", trip_list)
trip_id = conn.execute("SELECT id FROM trips WHERE name = ?", (current_trip,)).fetchone()["id"]

# 3.4 ดึง User เข้าทริป
st.sidebar.markdown("---")
st.sidebar.subheader(f"👥 สมาชิกใน {current_trip}")
all_users = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
existing_members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
available_users = [u for u in all_users if u not in existing_members]

selected_u = st.sidebar.selectbox("เลือกรายชื่อเพื่อดึงเข้าทริป:", ["-- เลือก --"] + available_users)
if st.sidebar.button("ดึงเพื่อนเข้าทริป"):
    if selected_u != "-- เลือก --":
        conn.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, selected_u))
        conn.commit()
        st.toast(f"เพิ่ม {selected_u} เข้าทริปแล้ว", icon='👥') # MsgBox
        st.rerun()
conn.close()

# --- 4. ส่วนแสดงผลหลัก ---
if not existing_members:
    st.warning("⚠️ กรุณาเลือกสมาชิกเข้าทริปก่อนเริ่มบันทึกบิล")
    st.stop()

st.title(f"📍 ทริป: {current_trip}")
tab1, tab2, tab3 = st.tabs(["📝 บันทึกบิล", "📊 ประวัติและแก้ไข", "💰 สรุปเคลียร์เงิน"])

# --- TAB 1: บันทึกบิลใหม่ ---
with tab1:
    with st.form("add_bill", clear_on_submit=True):
        st.header("➕ เพิ่มบิลค่าใช้จ่าย")
        desc = st.text_input("รายการ:")
        amt = st.number_input("จำนวนเงิน (บาท):", min_value=0.0, step=50.0)
        payer = st.selectbox("คนสำรองจ่าย:", existing_members)
        st.write("คนหาร:")
        split_to = [m for m in existing_members if st.checkbox(m, value=True, key=f"add_{m}")]
        file = st.file_uploader("สลิป:", type=['jpg','png','jpeg'])
        
        if st.form_submit_button("💾 บันทึกรายการ"):
            if desc and amt > 0 and split_to:
                blob = file.read() if file else None
                conn = get_db_connection()
                conn.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?,?,?,?,?,?)",
                             (trip_id, desc, amt, payer, ",".join(split_to), blob))
                conn.commit()
                conn.close()
                st.success(f"บันทึก '{desc}' สำเร็จ!") # MsgBox
                st.toast("ข้อมูลถูกบันทึกลงฐานข้อมูลแล้ว", icon='💾')
                st.rerun()
            else:
                st.error("กรุณากรอกข้อมูลให้ครบ")

# --- TAB 2: ประวัติและการแก้ไข ---
with tab2:
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()

    if not expenses:
        st.info("ยังไม่มีข้อมูลบิล")
    else:
        for row in expenses:
            with st.expander(f"📌 {row['description']} | {row['amount']:,.2f} บาท (โดย {row['payer_name']})"):
                c_view, c_edit = st.columns(2)
                with c_view:
                    if row['image_blob']:
                        st.image(row['image_blob'], width=250)
                    else: st.caption("ไม่มีรูปภาพ")
                
                with c_edit:
                    with st.form(f"edit_{row['id']}"):
                        u_desc = st.text_input("ชื่อรายการ:", value=row['description'])
                        u_amt = st.number_input("จำนวนเงิน:", value=row['amount'])
                        u_payer = st.selectbox("คนจ่าย:", existing_members, index=existing_members.index(row['payer_name']))
                        if st.form_submit_button("💾 อัปเดตการแก้ไข"):
                            conn = get_db_connection()
                            conn.execute("UPDATE expenses SET description=?, amount=?, payer_name=? WHERE id=?", (u_desc, u_amt, u_payer, row['id']))
                            conn.commit()
                            conn.close()
                            st.toast("อัปเดตข้อมูลสำเร็จ!", icon='📝') # MsgBox
                            st.rerun()
                    
                    if st.button(f"🗑️ ลบบิลนี้", key=f"del_{row['id']}"):
                        conn = get_db_connection()
                        conn.execute("DELETE FROM expenses WHERE id=?", (row['id'],))
                        conn.commit()
                        conn.close()
                        st.toast("ลบรายการเรียบร้อย", icon='🗑️') # MsgBox
                        st.rerun()

# --- TAB 3: สรุปและเคลียร์เงิน (รวบยอดจากทุกบิล) ---
with tab3:
    st.header("🤝 สรุปยอดโอนเงินรวบยอด")
    conn = get_db_connection()
    expenses_rows = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()

    if not expenses_rows:
        st.info("ยังไม่มีบิลให้คำนวณ")
    else:
        # คำนวณยอดสุทธิสะสม
        net_balances = {m: 0.0 for m in existing_members}
        for row in expenses_rows:
            p, a, s_str = row['payer_name'], row['amount'], row['split_members']
            s_list = s_str.split(",")
            net_balances[p] += a
            share = a / len(s_list)
            for m in s_list:
                net_balances[m] -= share
        
        # แสดงสถานะ
        c1, c2 = st.columns(2)
        with c1:
            st.write("**🟢 คนที่ต้องได้รับเงินคืน:**")
            for m, b in net_balances.items():
                if b > 0.01: st.write(f"{m}: `{b:,.2f}` บาท")
        with c2:
            st.write("**🔴 คนที่ต้องจ่ายเพิ่ม:**")
            for m, b in net_balances.items():
                if b < -0.01: st.write(f"{m}: `{abs(b):,.2f}` บาท")

        # จับคู่โอนเงิน
        debtors = [[m, b] for m, b in net_balances.items() if b < -0.01]
        creditors = [[m, b] for m, b in net_balances.items() if b > 0.01]
        
        st.write("---")
        st.subheader("🚀 แผนโอนเงินที่สั้นที่สุด")
        final_tx = []
        while debtors and creditors:
            amt = min(abs(debtors[0][1]), creditors[0][1])
            tx_msg = f"💳 **{debtors[0][0]}** โอนเงินให้ **{creditors[0][0]}** ยอด **{amt:,.2f}** บาท"
            st.info(tx_msg)
            final_tx.append((debtors[0][0], creditors[0][0], amt))
            debtors[0][1] += amt
            creditors[0][1] -= amt
            if abs(debtors[0][1]) < 0.01: debtors.pop(0)
            if abs(creditors[0][1]) < 0.01: creditors.pop(0)

        if st.button("🎯 บันทึกสรุปยอดปิดทริปลงประวัติ", type="primary"):
            conn = get_db_connection()
            conn.execute("DELETE FROM settlements WHERE trip_id = ?", (trip_id,))
            for t in final_tx:
                conn.execute("INSERT INTO settlements (trip_id, debtor, creditor, amount) VALUES (?,?,?,?)", (trip_id, t[0], t[1], t[2]))
            conn.commit()
            conn.close()
            st.success("บันทึกประวัติการเคลียร์เงินก้อนสุดท้ายแล้ว!") # MsgBox
            st.toast("ล็อกยอดสำเร็จ!", icon='🎯')
            st.rerun()

        # แสดงประวัติที่บันทึกไว้
        st.write("---")
        st.subheader("📋 ประวัติการเคลียร์เงินที่บันทึกไว้")
        conn = get_db_connection()
        saved = conn.execute("SELECT * FROM settlements WHERE trip_id = ?", (trip_id,)).fetchall()
        conn.close()
        if saved:
            st.table(pd.DataFrame([{"จาก": s[2], "ถึง": s[3], "จำนวน": f"{s[4]:,.2f}"} for s in saved]))
        else: st.caption("ยังไม่มีบันทึก")
