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
    cursor.execute('CREATE TABLE IF NOT EXISTS all_users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, status INTEGER DEFAULT 0)')
    
    # ตรวจสอบเผื่อ Schema เก่าไม่มี status
    try: cursor.execute('ALTER TABLE trips ADD COLUMN status INTEGER DEFAULT 0')
    except: pass

    cursor.execute('CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, name TEXT, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, description TEXT, 
            amount REAL, payer_name TEXT, split_members TEXT, image_blob BLOB,
            FOREIGN KEY(trip_id) REFERENCES trips(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, 
            debtor TEXT, creditor TEXT, amount REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(trip_id) REFERENCES trips(id)
        )
    ''')
    conn.commit()
    conn.close()

def compress_image(uploaded_file):
    if uploaded_file is None: return None
    img = Image.open(uploaded_file)
    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
    img.thumbnail((800, 800))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=70)
    return buffer.getvalue()

init_db()

# --- 3. Sidebar: Control Panel ---
st.sidebar.header("⚙️ ระบบจัดการข้อมูล")

# 3.1 ลงทะเบียน User ใหม่
with st.sidebar.expander("👤 ลงทะเบียน User (ทำครั้งเดียว)"):
    reg_name = st.text_input("ชื่อผู้ใช้งาน:").strip()
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

# 3.2 สร้างทริป
st.sidebar.markdown("---")
new_trip_name = st.sidebar.text_input("➕ สร้างทริปใหม่:").strip()
if st.sidebar.button("บันทึกทริป"):
    if new_trip_name:
        try:
            conn = get_db_connection()
            conn.execute("INSERT INTO trips (name, status) VALUES (?, 0)", (new_trip_name,))
            conn.commit()
            conn.close()
            st.rerun()
        except: st.sidebar.error("ชื่อทริปซ้ำ")

# 3.3 ถังขยะ
conn = get_db_connection()
with st.sidebar.expander("🗑️ ถังขยะ (ทริปที่ถูกลบ)"):
    deleted_trips = conn.execute("SELECT * FROM trips WHERE status = 1").fetchall()
    if not deleted_trips: st.caption("ถังขยะว่างเปล่า")
    for dt in deleted_trips:
        c_n, c_a = st.columns([2, 1])
        c_n.write(dt['name'])
        b1, b2 = c_a.columns(2)
        if b1.button("🔄", key=f"res_{dt['id']}"):
            conn.execute("UPDATE trips SET status = 0 WHERE id = ?", (dt['id'],))
            conn.commit(); st.rerun()
        if b2.button("❌", key=f"pdel_{dt['id']}"):
            conn.execute("DELETE FROM trips WHERE id = ?", (dt['id'],))
            conn.commit(); st.rerun()

# 3.4 เลือกทริป
active_trips = pd.read_sql_query("SELECT * FROM trips WHERE status = 0", conn)
if active_trips.empty:
    st.title("✈️ ยินดีต้อนรับ")
    st.info("สร้างทริปใหม่ที่ Sidebar เพื่อเริ่มใช้งานครับ")
    conn.close(); st.stop()

current_trip = st.sidebar.selectbox("🗺️ เลือกทริป:", active_trips["name"].tolist())
trip_id = conn.execute("SELECT id FROM trips WHERE name = ?", (current_trip,)).fetchone()["id"]

if st.sidebar.button("🗑️ ย้ายทริปปัจจุบันลงถังขยะ"):
    conn.execute("UPDATE trips SET status = 1 WHERE id = ?", (trip_id,))
    conn.commit(); st.rerun()

# 3.5 สมาชิก
st.sidebar.markdown("---")
st.sidebar.subheader(f"👥 สมาชิก: {current_trip}")
all_u = [r["name"] for r in conn.execute("SELECT name FROM all_users").fetchall()]
existing_m = [r["name"] for r in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
avail_u = [u for u in all_u if u not in existing_m]

selected_u = st.sidebar.selectbox("ดึงเพื่อนเข้าทริป:", ["-- เลือก --"] + avail_u)
if st.sidebar.button("ดึงเข้าทริป") and selected_u != "-- เลือก --":
    conn.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, selected_u))
    conn.commit(); st.rerun()
conn.close()

# --- 4. Main Area ---
if not existing_m:
    st.title(f"📍 {current_trip}")
    st.warning("ดึงสมาชิกเข้าทริปก่อนเริ่มบันทึก")
    st.stop()

st.title(f"📍 {current_trip}")
tab1, tab2, tab3 = st.tabs(["📝 บันทึกบิล", "📊 ประวัติและแก้ไข", "💰 สรุปเคลียร์เงิน"])

# --- TAB 1: บันทึก ---
with tab1:
    with st.form("add_bill", clear_on_submit=True):
        st.header("➕ เพิ่มบิลใหม่")
        d = st.text_input("รายการ:")
        a = st.number_input("จำนวนเงิน:", min_value=0.0, step=50.0)
        p = st.selectbox("คนจ่าย:", existing_m)
        st.write("คนหาร:")
        s_to = [m for m in existing_m if st.checkbox(m, value=True, key=f"add_{m}")]
        f = st.file_uploader("สลิป:", type=['jpg','png','jpeg'])
        if st.form_submit_button("💾 บันทึก"):
            if d and a > 0 and s_to:
                blob = compress_image(f)
                conn = get_db_connection()
                conn.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?,?,?,?,?,?)",
                             (trip_id, d, a, p, ",".join(s_to), blob))
                conn.commit(); conn.close()
                st.toast("บันทึกแล้ว!"); st.rerun()

# --- TAB 2: แก้ไข (รวมการลบคนหารออก) ---
with tab2:
    conn = get_db_connection()
    exps = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()
    if not exps: st.info("ยังไม่มีข้อมูล")
    for r in exps:
        with st.expander(f"📌 {r['description']} | {r['amount']:,.2f} (โดย {r['payer_name']})"):
            c1, c2 = st.columns([1, 1.2])
            with c1:
                if r['image_blob']: st.image(r['image_blob'], use_container_width=True)
                else: st.caption("ไม่มีสลิป")
            with c2:
                with st.form(f"ed_{r['id']}"):
                    u_d = st.text_input("ชื่อรายการ:", value=r['description'])
                    u_a = st.number_input("จำนวนเงิน:", value=r['amount'])
                    u_p = st.selectbox("คนจ่าย:", existing_m, index=existing_m.index(r['payer_name']))
                    
                    # --- จัดการคนหาร (ลบชื่อออกได้ตรงนี้) ---
                    st.write("คนหาร (ติ๊กออกเพื่อลบ):")
                    curr_s = r['split_members'].split(",")
                    u_s = [m for m in existing_m if st.checkbox(m, value=(m in curr_s), key=f"ed_s_{r['id']}_{m}")]
                    
                    u_f = st.file_uploader("เปลี่ยนรูป:", type=['jpg','png','jpeg'], key=f"f_{r['id']}")
                    if st.form_submit_button("💾 อัปเดต"):
                        if u_s:
                            conn = get_db_connection()
                            if u_f:
                                b = compress_image(u_f)
                                conn.execute("UPDATE expenses SET description=?, amount=?, payer_name=?, split_members=?, image_blob=? WHERE id=?", (u_d, u_a, u_p, ",".join(u_s), b, r['id']))
                            else:
                                conn.execute("UPDATE expenses SET description=?, amount=?, payer_name=?, split_members=? WHERE id=?", (u_d, u_a, u_p, ",".join(u_s), r['id']))
                            conn.commit(); conn.close(); st.rerun()
                        else: st.error("ต้องมีคนหารอย่างน้อย 1 คน")
                if st.button(f"🗑️ ลบบิล", key=f"del_{r['id']}"):
                    conn = get_db_connection()
                    conn.execute("DELETE FROM expenses WHERE id=?", (r['id'],))
                    conn.commit(); conn.close(); st.rerun()

# --- TAB 3: สรุปยอด ---
with tab3:
    st.header("🤝 สรุปยอดโอน")
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()
    if not rows: st.info("ไม่มีบิล")
    else:
        balances = {m: 0.0 for m in existing_m}
        for r in rows:
            balances[r['payer_name']] += r['amount']
            split_list = r['split_members'].split(",")
            share = r['amount'] / len(split_list)
            for m in split_list: balances[m] -= share
        
        c1, c2 = st.columns(2)
        with c1:
            for m, b in balances.items():
                if b > 0.01: st.success(f"🟢 {m}: {b:,.2f} บาท")
        with c2:
            for m, b in balances.items():
                if b < -0.01: st.error(f"🔴 {m}: {abs(b):,.2f} บาท")

        debtors = [[m, b] for m, b in balances.items() if b < -0.01]
        creditors = [[m, b] for m, b in balances.items() if b > 0.01]
        st.subheader("🚀 แผนการโอน")
        while debtors and creditors:
            amt = min(abs(debtors[0][1]), creditors[0][1])
            st.info(f"💳 **{debtors[0][0]}** ➡️ **{creditors[0][0]}** : **{amt:,.2f}** บาท")
            debtors[0][1] += amt; creditors[0][1] -= amt
            if abs(debtors[0][1]) < 0.01: debtors.pop(0)
            if abs(creditors[0][1]) < 0.01: creditors.pop(0)
