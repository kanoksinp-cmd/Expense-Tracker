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

# --- 3. Sidebar: Control Center ---
st.sidebar.header("⚙️ ระบบจัดการข้อมูล")

# 3.1 ลงทะเบียน User
with st.sidebar.expander("👤 ลงทะเบียน User (ทำครั้งเดียว)"):
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

# 3.3 เลือกทริป และ ถังขยะ
conn = get_db_connection()
active_trips_df = pd.read_sql_query("SELECT * FROM trips WHERE status = 0", conn)
active_trip_list = active_trips_df["name"].tolist() if not active_trips_df.empty else []

with st.sidebar.expander("🗑️ ถังขยะ (ทริปที่ถูกลบ)"):
    deleted_trips = conn.execute("SELECT * FROM trips WHERE status = 1").fetchall()
    if not deleted_trips: st.caption("ถังขยะว่างเปล่า")
    for dt in deleted_trips:
        c_n, c_a = st.columns([2, 1])
        c_n.write(dt['name'])
        s1, s2 = c_a.columns(2)
        if s1.button("🔄", key=f"r_{dt['id']}", help="กู้คืน"):
            conn.execute("UPDATE trips SET status = 0 WHERE id = ?", (dt['id'],))
            conn.commit(); st.rerun()
        if s2.button("❌", key=f"p_{dt['id']}", help="ลบถาวร"):
            conn.execute("DELETE FROM trips WHERE id = ?", (dt['id'],))
            conn.commit(); st.rerun()

if not active_trip_list:
    st.title("✈️ ระบบจัดการทริป")
    st.info("กรุณาสร้างทริปที่เมนูซ้ายมือ")
    conn.close(); st.stop()

st.sidebar.markdown("---")
current_trip = st.sidebar.selectbox("🗺️ เลือกทริป:", active_trip_list)
trip_id = conn.execute("SELECT id FROM trips WHERE name = ?", (current_trip,)).fetchone()["id"]

if st.sidebar.button("🗑️ ย้ายทริปนี้ลงถังขยะ"):
    conn.execute("UPDATE trips SET status = 1 WHERE id = ?", (trip_id,))
    conn.commit(); st.rerun()

# 3.4 สมาชิก
st.sidebar.subheader(f"👥 สมาชิก: {current_trip}")
all_users = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
existing_members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
available_users = [u for u in all_users if u not in existing_members]

selected_u = st.sidebar.selectbox("ดึงเพื่อนเข้าทริป:", ["-- เลือก --"] + available_users)
if st.sidebar.button("ดึงเข้าทริป"):
    if selected_u != "-- เลือก --":
        conn.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, selected_u))
        conn.commit(); st.rerun()
conn.close()

# --- 4. Main Display ---
if not existing_members:
    st.title(f"📍 {current_trip}"); st.warning("⚠️ กรุณาเลือกสมาชิกเข้าทริป"); st.stop()

st.title(f"📍 ทริป: {current_trip}")
tab1, tab2, tab3 = st.tabs(["📝 บันทึกบิล", "📊 ประวัติและแก้ไข", "💰 สรุปเคลียร์เงิน"])

with tab1:
    with st.form("add_bill", clear_on_submit=True):
        st.header("➕ เพิ่มบิล")
        desc = st.text_input("รายการ:")
        amt = st.number_input("เงิน (บาท):", min_value=0.0, step=50.0)
        payer = st.selectbox("ใครจ่าย?", existing_members)
        st.write("คนหาร:")
        split_to = [m for m in existing_members if st.checkbox(m, value=True, key=f"add_{m}")]
        file = st.file_uploader("สลิป:", type=['jpg','png','jpeg'])
        if st.form_submit_button("💾 บันทึก"):
            if desc and amt > 0 and split_to:
                blob = compress_image(file)
                conn = get_db_connection()
                conn.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?,?,?,?,?,?)",
                             (trip_id, desc, amt, payer, ",".join(split_to), blob))
                conn.commit(); conn.close(); st.toast("บันทึกแล้ว!"); st.rerun()

with tab2:
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()
    if not expenses: st.info("ยังไม่มีข้อมูล")
    else:
        for row in expenses:
            with st.expander(f"📌 {row['description']} | {row['amount']:,.2f} บาท"):
                c1, c2 = st.columns([1, 1.2])
                with c1:
                    if row['image_blob']: st.image(row['image_blob'], use_container_width=True)
                    else: st.caption("ไม่มีรูป")
                with c2:
                    with st.form(f"ed_{row['id']}"):
                        u_desc = st.text_input("รายการ:", value=row['description'])
                        u_amt = st.number_input("เงิน:", value=row['amount'])
                        u_payer = st.selectbox("คนจ่าย:", existing_members, index=existing_members.index(row['payer_name']))
                        st.write("คนหาร:")
                        cur_split = row['split_members'].split(",")
                        u_split = [m for m in existing_members if st.checkbox(m, value=(m in cur_split), key=f"ed_sp_{row['id']}_{m}")]
                        u_file = st.file_uploader("เปลี่ยนสลิป:", type=['jpg','png','jpeg'], key=f"ed_img_{row['id']}")
                        if st.form_submit_button("💾 อัปเดต"):
                            if u_split:
                                conn = get_db_connection()
                                blob = compress_image(u_file) if u_file else row['image_blob']
                                conn.execute("UPDATE expenses SET description=?, amount=?, payer_name=?, split_members=?, image_blob=? WHERE id=?",
                                             (u_desc, u_amt, u_payer, ",".join(u_split), blob, row['id']))
                                conn.commit(); conn.close(); st.rerun()
                    if st.button("🗑️ ลบบิล", key=f"del_{row['id']}"):
                        conn = get_db_connection(); conn.execute("DELETE FROM expenses WHERE id=?", (row['id'],)); conn.commit(); st.rerun()

with tab3:
    st.header("🤝 สรุปยอดเคลียร์เงิน")
    conn = get_db_connection()
    expenses_rows = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()
    if not expenses_rows: st.info("ไม่มีบิล")
    else:
        net = {m: 0.0 for m in existing_members}
        for r in expenses_rows:
            p, a, s_list = r['payer_name'], r['amount'], r['split_members'].split(",")
            net[p] += a
            share = a / len(s_list)
            for m in s_list: net[m] -= share
        
        c1, c2 = st.columns(2)
        with c1: 
            for m, b in net.items(): 
                if b > 0.01: st.success(f"{m}: ได้คืน {b:,.2f}")
        with c2: 
            for m, b in net.items(): 
                if b < -0.01: st.error(f"{m}: จ่ายเพิ่ม {abs(b):,.2f}")

        debtors = [[m, b] for m, b in net.items() if b < -0.01]
        creditors = [[m, b] for m, b in net.items() if b > 0.01]
        st.subheader("🚀 แผนการโอนเงิน")
        while debtors and creditors:
            amt = min(abs(debtors[0][1]), creditors[0][1])
            st.info(f"💳 **{debtors[0][0]}** ➡️ **{creditors[0][0]}** : **{amt:,.2f}** บาท")
            debtors[0][1] += amt; creditors[0][1] -= amt
            if abs(debtors[0][1]) < 0.01: debtors.pop(0)
            if abs(creditors[0][1]) < 0.01: creditors.pop(0)
