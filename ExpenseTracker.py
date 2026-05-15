import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image

# ตั้งค่าหน้าเว็บ
st.set_page_config(page_title="Trip Expense Master Pro", layout="wide")

# --- 1. จัดการฐานข้อมูล ---
DB_FILE = "trip_database.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # User กลาง
    cursor.execute('CREATE TABLE IF NOT EXISTS all_users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)')
    # ทริป (เพิ่ม is_deleted)
    cursor.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, is_deleted INTEGER DEFAULT 0)')
    # สมาชิกทริป
    cursor.execute('CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, name TEXT)')
    # ค่าใช้จ่าย
    cursor.execute('CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, description TEXT, amount REAL, payer_name TEXT, split_members TEXT, image_blob BLOB)')
    # ประวัติเคลียร์เงิน
    cursor.execute('CREATE TABLE IF NOT EXISTS settlements (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, debtor TEXT, creditor TEXT, amount REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
    conn.commit()
    conn.close()

init_db()

# --- 2. Sidebar: ศูนย์ควบคุม ---
st.sidebar.header("⚙️ ระบบจัดการข้อมูล")

# 2.1 ลงทะเบียน User ใหม่
with st.sidebar.expander("👤 ลงทะเบียน User (Global)"):
    reg_name = st.text_input("ระบุชื่อผู้ใช้งาน:").strip()
    if st.button("ลงทะเบียน"):
        if reg_name:
            try:
                conn = get_db_connection()
                conn.execute("INSERT INTO all_users (name) VALUES (?)", (reg_name,))
                conn.commit()
                conn.close()
                st.toast(f"ลงทะเบียนคุณ {reg_name} สำเร็จ!", icon='✅')
                st.rerun()
            except: st.sidebar.error("ชื่อนี้มีในระบบแล้ว")

# 2.2 สร้างทริป
st.sidebar.markdown("---")
new_t = st.sidebar.text_input("➕ สร้างทริปใหม่:").strip()
if st.sidebar.button("บันทึกทริป"):
    if new_t:
        try:
            conn = get_db_connection()
            conn.execute("INSERT INTO trips (name, is_deleted) VALUES (?, 0)", (new_t,))
            conn.commit()
            conn.close()
            st.toast(f"สร้างทริป {new_t} สำเร็จ!", icon='🗺️')
            st.rerun()
        except: st.sidebar.error("ชื่อทริปซ้ำ")

# 2.3 ระบบถังขยะ (Trash Bin)
with st.sidebar.expander("🗑️ ถังขยะ (รายการที่ลบ)"):
    conn = get_db_connection()
    trash_df = pd.read_sql_query("SELECT * FROM trips WHERE is_deleted = 1", conn)
    if trash_df.empty:
        st.write("ถังขยะว่างเปล่า")
    else:
        for _, row in trash_df.iterrows():
            st.write(f"📁 {row['name']}")
            c1, c2 = st.columns(2)
            if c1.button("กู้คืน", key=f"res_{row['id']}"):
                conn.execute("UPDATE trips SET is_deleted = 0 WHERE id = ?", (row['id'],))
                conn.commit()
                st.toast(f"กู้คืนทริป {row['name']} แล้ว", icon='♻️')
                st.rerun()
            if c2.button("ลบทิ้งถาวร", key=f"pdel_{row['id']}"):
                conn.execute("DELETE FROM trips WHERE id = ?", (row['id'],))
                conn.execute("DELETE FROM expenses WHERE trip_id = ?", (row['id'],))
                conn.execute("DELETE FROM members WHERE trip_id = ?", (row['id'],))
                conn.execute("DELETE FROM settlements WHERE trip_id = ?", (row['id'],))
                conn.commit()
                st.toast("ลบข้อมูลออกจากฐานข้อมูลถาวรแล้ว", icon='🔥')
                st.rerun()
    conn.close()

# 2.4 เลือกทริปใช้งาน
conn = get_db_connection()
trips_df = pd.read_sql_query("SELECT * FROM trips WHERE is_deleted = 0", conn)
trip_list = trips_df["name"].tolist() if not trips_df.empty else []

if not trip_list:
    st.title("✈️ ระบบจัดการทริป")
    st.info("เริ่มต้นโดยการสร้างทริปที่เมนูซ้ายมือ")
    conn.close()
    st.stop()

st.sidebar.markdown("---")
current_trip = st.sidebar.selectbox("🗺️ เลือกทริปที่จะจัดการ:", trip_list)
trip_id = conn.execute("SELECT id FROM trips WHERE name = ?", (current_trip,)).fetchone()["id"]

# ปุ่มย้ายไปถังขยะ
if st.sidebar.button("🗑️ ย้ายทริปนี้ไปที่ถังขยะ"):
    conn.execute("UPDATE trips SET is_deleted = 1 WHERE id = ?", (trip_id,))
    conn.commit()
    st.toast("ย้ายทริปไปที่ถังขยะแล้ว สามารถกู้คืนได้", icon='🗑️')
    st.rerun()

# 2.5 จัดการสมาชิก
st.sidebar.markdown("---")
all_u = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
cur_m = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
avail_u = [u for u in all_u if u not in cur_m]

sel_u = st.sidebar.selectbox("ดึงเพื่อนเข้าทริปนี้:", ["-- เลือกรายชื่อ --"] + avail_u)
if st.sidebar.button("ดึงเพื่อนเข้าทริป"):
    if sel_u != "-- เลือกรายชื่อ --":
        conn.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, sel_u))
        conn.commit()
        st.toast(f"เพิ่มคุณ {sel_u} เข้าทริปสำเร็จ", icon='👥')
        st.rerun()
conn.close()

# --- 3. หน้าหลัก ---
if not cur_m:
    st.title(f"📍 ทริป: {current_trip}")
    st.warning("⚠️ กรุณาดึงสมาชิกเข้าทริปที่เมนูด้านซ้ายก่อน")
    st.stop()

st.title(f"📍 ทริป: {current_trip}")
t1, t2, t3 = st.tabs(["📝 บันทึกบิล", "📊 ประวัติบิล & รูปภาพ", "💰 สรุปการโอนเงิน"])

# --- TAB 1: บันทึกบิล ---
with t1:
    with st.form("add_bill", clear_on_submit=True):
        f_desc = st.text_input("รายการ:")
        f_amt = st.number_input("จำนวนเงิน (บาท):", min_value=0.0)
        f_payer = st.selectbox("ใครสำรองจ่าย:", cur_m)
        st.write("คนช่วยหาร:")
        f_split = [m for m in cur_m if st.checkbox(m, value=True, key=f"split_{m}")]
        f_img = st.file_uploader("สลิป (ไม่บังคับ):", type=['jpg','png','jpeg'])
        if st.form_submit_button("💾 บันทึก"):
            if f_desc and f_amt > 0 and f_split:
                conn = get_db_connection()
                conn.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?,?,?,?,?,?)",
                             (trip_id, f_desc, f_amt, f_payer, ",".join(f_split), f_img.read() if f_img else None))
                conn.commit()
                conn.close()
                st.success(f"บันทึก '{f_desc}' เรียบร้อย!")
                st.toast("บันทึกสำเร็จ", icon='✅')
                st.rerun()

# --- TAB 2: ประวัติและการจัดการรูปภาพ ---
with t2:
    conn = get_db_connection()
    bills = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()
    
    if not bills:
        st.info("ยังไม่มีรายการค่าใช้จ่าย")
    else:
        for row in bills:
            with st.expander(f"📌 {row['description']} | {row['amount']:,.2f} บาท"):
                c1, c2 = st.columns(2)
                with c1:
                    if row['image_blob']:
                        st.image(row['image_blob'], caption="สลิปปัจจุบัน", width=250)
                    else:
                        st.caption("🈚 บิลนี้ยังไม่มีรูปภาพ")
                
                with c2:
                    st.write("**อัปเดตรูปภาพ/แก้ไขข้อมูล**")
                    new_img = st.file_uploader("อัปโหลดรูปภาพใหม่:", type=['jpg','png','jpeg'], key=f"img_{row['id']}")
                    if st.button("📸 บันทึกรูปภาพใหม่", key=f"btn_img_{row['id']}"):
                        if new_img:
                            conn = get_db_connection()
                            conn.execute("UPDATE expenses SET image_blob = ? WHERE id = ?", (new_img.read(), row['id']))
                            conn.commit()
                            conn.close()
                            st.toast("อัปเดตรูปภาพสำเร็จ!", icon='📸')
                            st.rerun()
                    
                    if st.button("🗑️ ลบบิลนี้", key=f"del_b_{row['id']}"):
                        conn = get_db_connection()
                        conn.execute("DELETE FROM expenses WHERE id = ?", (row['id'],))
                        conn.commit()
                        conn.close()
                        st.toast("ลบบิลเรียบร้อย", icon='🗑️')
                        st.rerun()

# --- TAB 3: สรุปยอดเคลียร์เงิน ---
with t3:
    st.header("🤝 สรุปยอดโอนเงินรวบยอด")
    conn = get_db_connection()
    ex_rows = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()
    
    if not ex_rows:
        st.info("กรุณาบันทึกบิลก่อน")
    else:
        # คำนวณ Net Balance
        net = {m: 0.0 for m in cur_m}
        for r in ex_rows:
            net[r['payer_name']] += r['amount']
            sl = r['split_members'].split(",")
            share = r['amount'] / len(sl)
            for m in sl: net[m] -= share
            
        c_p, c_n = st.columns(2)
        with c_p:
            st.write("**🟢 คนที่จะได้รับเงินคืน:**")
            for m, b in net.items():
                if b > 0.01: st.write(f"{m}: `{b:,.2f}` บาท")
        with c_n:
            st.write("**🔴 คนที่จะต้องจ่ายเพิ่ม:**")
            for m, b in net.items():
                if b < -0.01: st.write(f"{m}: `{abs(b):,.2f}` บาท")
        
        # อัลกอริทึมจับคู่โอน
        debtors = [[m, b] for m, b in net.items() if b < -0.01]
        creditors = [[m, b] for m, b in net.items() if b > 0.01]
        
        st.write("---")
        st.subheader("🚀 แผนการโอนเงิน (รวบยอดทุกบิล)")
        final_tx = []
        while debtors and creditors:
            amt = min(abs(debtors[0][1]), creditors[0][1])
            st.info(f"💳 **{debtors[0][0]}** โอนเงินให้ **{creditors[0][0]}** เป็นยอด **{amt:,.2f}** บาท")
            final_tx.append((debtors[0][0], creditors[0][0], amt))
            debtors[0][1] += amt
            creditors[0][1] -= amt
            if abs(debtors[0][1]) < 0.01: debtors.pop(0)
            if abs(creditors[0][1]) < 0.01: creditors.pop(0)

        if st.button("🎯 บันทึกสรุปยอดปิดทริป", type="primary"):
            conn = get_db_connection()
            conn.execute("DELETE FROM settlements WHERE trip_id = ?", (trip_id,))
            for tx in final_tx:
                conn.execute("INSERT INTO settlements (trip_id, debtor, creditor, amount) VALUES (?,?,?,?)", (trip_id, tx[0], tx[1], tx[2]))
            conn.commit()
            conn.close()
            st.success("บันทึกประวัติการเคลียร์เงินแล้ว!")
            st.toast("ล็อกยอดสำเร็จ", icon='🎯')
            st.rerun()
