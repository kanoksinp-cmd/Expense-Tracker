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

# --- 3. Sidebar: ศูนย์ควบคุม ---
st.sidebar.header("⚙️ ระบบจัดการข้อมูล")

with st.sidebar.expander("👤 ลงทะเบียน User"):
    reg_name = st.text_input("ระบุชื่อผู้ใช้งาน:").strip()
    if st.button("ลงทะเบียน"):
        if reg_name:
            try:
                conn = get_db_connection()
                conn.execute("INSERT INTO all_users (name) VALUES (?)", (reg_name,))
                conn.commit()
                conn.close()
                st.rerun()
            except: st.sidebar.error("ชื่อนี้มีในระบบแล้ว")

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

conn = get_db_connection()
active_trips_df = pd.read_sql_query("SELECT * FROM trips WHERE status = 0", conn)
active_trip_list = active_trips_df["name"].tolist() if not active_trips_df.empty else []

if not active_trip_list:
    st.title("✈️ ระบบจัดการทริป")
    st.info("กรุณาสร้างทริปใหม่ที่เมนูซ้ายมือ")
    st.stop()

st.sidebar.markdown("---")
current_trip = st.sidebar.selectbox("🗺️ เลือกทริป:", active_trip_list)
trip_id = conn.execute("SELECT id FROM trips WHERE name = ? AND status = 0", (current_trip,)).fetchone()["id"]

st.sidebar.subheader(f"👥 สมาชิกใน {current_trip}")
all_users = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
existing_members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
available_users = [u for u in all_users if u not in existing_members]

selected_u = st.sidebar.selectbox("ดึงเพื่อนเข้าทริป:", ["-- เลือก --"] + available_users)
if st.sidebar.button("เพิ่มเข้าทริป"):
    if selected_u != "-- เลือก --":
        conn.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, selected_u))
        conn.commit()
        st.rerun()
conn.close()

if not existing_members:
    st.title(f"📍 ทริป: {current_trip}")
    st.warning("⚠️ กรุณาเลือกสมาชิกเข้าทริปก่อน")
    st.stop()

# --- 4. ส่วนแสดงผลหลัก ---
st.title(f"📍 ทริป: {current_trip}")
tab1, tab2, tab3 = st.tabs(["📝 บันทึกบิล", "📊 ประวัติและแก้ไข", "💰 สรุปเคลียร์เงิน"])

# --- TAB 1: บันทึกบิล (เพิ่มปุ่มถอดคนหาร) ---
with tab1:
    st.header("➕ เพิ่มบิลค่าใช้จ่าย")
    
    # ส่วนของปุ่มเลือก/ถอดทั้งหมด
    col_btn1, col_btn2, _ = st.columns([1, 1, 3])
    if col_btn1.button("✅ เลือกทุกคน", use_container_width=True):
        for m in existing_members: st.session_state[f"cb_{m}"] = True
    if col_btn2.button("⬜ ล้างทั้งหมด", use_container_width=True):
        for m in existing_members: st.session_state[f"cb_{m}"] = False

    with st.form("add_bill_form"):
        desc = st.text_input("รายการ:")
        amt = st.number_input("จำนวนเงิน (บาท):", min_value=0.0, step=50.0)
        payer = st.selectbox("ใครเป็นคนสำรองจ่าย?", existing_members)
        
        st.write("คนหาร:")
        split_to = []
        # ใช้ session_state ควบคุมค่าเริ่มต้นของ checkbox
        for m in existing_members:
            default_val = st.session_state.get(f"cb_{m}", True)
            if st.checkbox(m, value=default_val, key=f"add_{m}"):
                split_to.append(m)
        
        file = st.file_uploader("สลิป:", type=['jpg','png','jpeg'])
        
        if st.form_submit_button("💾 บันทึกรายการ"):
            if desc and amt > 0 and split_to:
                blob = compress_image(file)
                conn = get_db_connection()
                conn.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?,?,?,?,?,?)",
                             (trip_id, desc, amt, payer, ",".join(split_to), blob))
                conn.commit()
                conn.close()
                st.success("บันทึกสำเร็จ!")
                st.rerun()
            else:
                st.error("กรุณากรอกข้อมูลให้ครบและเลือกคนหารอย่างน้อย 1 คน")

# --- TAB 2: ประวัติและแก้ไข ---
with tab2:
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()

    if not expenses:
        st.info("ยังไม่มีข้อมูลบิล")
    else:
        for row in expenses:
            current_split = row['split_members'].split(",") if row['split_members'] else []
            with st.expander(f"📌 {row['description']} | {row['amount']:,.2f} บาท (โดย {row['payer_name']})"):
                c_view, c_edit = st.columns([1, 1.2])
                with c_view:
                    if row['image_blob']: st.image(row['image_blob'], use_container_width=True)
                    else: st.caption("ไม่มีรูปภาพ")
                
                with c_edit:
                    with st.form(f"edit_{row['id']}"):
                        u_desc = st.text_input("ชื่อรายการ:", value=row['description'])
                        u_amt = st.number_input("จำนวนเงิน:", value=row['amount'])
                        u_payer = st.selectbox("คนจ่าย:", existing_members, index=existing_members.index(row['payer_name']))
                        
                        st.write("คนหาร:")
                        u_split_to = [m for m in existing_members if st.checkbox(m, value=(m in current_split), key=f"edit_mem_{row['id']}_{m}")]
                        u_file = st.file_uploader("อัปเดตรูปสลิป:", type=['jpg','png','jpeg'], key=f"edit_img_{row['id']}")
                        
                        if st.form_submit_button("💾 อัปเดต"):
                            if u_desc and u_amt > 0 and u_split_to:
                                conn = get_db_connection()
                                blob_sql = ", image_blob=?" if u_file else ""
                                params = [u_desc, u_amt, u_payer, ",".join(u_split_to)]
                                if u_file: params.append(compress_image(u_file))
                                params.append(row['id'])
                                conn.execute(f"UPDATE expenses SET description=?, amount=?, payer_name=?, split_members=?{blob_sql} WHERE id=?", params)
                                conn.commit()
                                conn.close()
                                st.rerun()
                    
                    if st.button(f"🗑️ ลบรายการ", key=f"del_{row['id']}"):
                        conn = get_db_connection()
                        conn.execute("DELETE FROM expenses WHERE id=?", (row['id'],))
                        conn.commit()
                        conn.close()
                        st.rerun()

# --- TAB 3: สรุปเคลียร์เงิน ---
with tab3:
    st.header("🤝 สรุปยอดโอนเงิน")
    conn = get_db_connection()
    expenses_rows = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()

    if not expenses_rows:
        st.info("ยังไม่มีข้อมูล")
    else:
        net_balances = {m: 0.0 for m in existing_members}
        for row in expenses_rows:
            s_list = row['split_members'].split(",") if row['split_members'] else []
            if not s_list: continue
            net_balances[row['payer_name']] += row['amount']
            share = row['amount'] / len(s_list)
            for m in s_list: net_balances[m] -= share
        
        c1, c2 = st.columns(2)
        with c1:
            st.write("**🟢 คนที่ต้องได้รับคืน:**")
            for m, b in net_balances.items():
                if b > 0.01: st.success(f"{m}: {b:,.2f} บาท")
        with c2:
            st.write("**🔴 คนที่ต้องจ่าย:**")
            for m, b in net_balances.items():
                if b < -0.01: st.error(f"{m}: {abs(b):,.2f} บาท")

        # อัลกอริทึมเคลียร์เงิน
        debtors = sorted([[m, b] for m, b in net_balances.items() if b < -0.01], key=lambda x: x[1])
        creditors = sorted([[m, b] for m, b in net_balances.items() if b > 0.01], key=lambda x: x[1], reverse=True)
        
        st.write("---")
        st.subheader("🚀 แผนโอนเงิน")
        while debtors and creditors:
            amt = min(abs(debtors[0][1]), creditors[0][1])
            st.info(f"💳 **{debtors[0][0]}** โอนให้ **{creditors[0][0]}** ยอด **{amt:,.2f}** บาท")
            debtors[0][1] += amt
            creditors[0][1] -= amt
            if abs(debtors[0][1]) < 0.01: debtors.pop(0)
            if abs(creditors[0][1]) < 0.01: creditors.pop(0)
