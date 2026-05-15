import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image

# 1. ตั้งค่าหน้าจอ
st.set_page_config(page_title="Trip Expense Splitter Pro", layout="wide")

# --- 1.5 ดีไซน์และตั้งค่าธีม 7 แบบทันสมัย ---
THEMES = {
    "🟢 Emerald Explorer (Light)": {
        "bg": "#F4F7F5", "sidebar": "#E6EDE8", "text": "#1F2937", "text_light": "#4B5563",
        "primary": "#10B981", "card": "#FFFFFF", "border": "#E5E7EB"
    },
    "🔵 Ocean Breeze (Light)": {
        "bg": "#F0F4F8", "sidebar": "#D9E2EC", "text": "#102A43", "text_light": "#334E68",
        "primary": "#0284C7", "card": "#FFFFFF", "border": "#E1E8ED"
    },
    "🟣 Cyber Punk (Dark)": {
        "bg": "#0F172A", "sidebar": "#1E293B", "text": "#F8FAFC", "text_light": "#94A3B8",
        "primary": "#D946EF", "card": "#1E293B", "border": "#334155"
    },
    "🟡 Sunset Glow (Light)": {
        "bg": "#FFFBEB", "sidebar": "#FEF3C7", "text": "#451A03", "text_light": "#78350F",
        "primary": "#F59E0B", "card": "#FFFFFF", "border": "#FDE68A"
    },
    "🔴 Rose Gold (Light)": {
        "bg": "#FAF5F5", "sidebar": "#F3E8E8", "text": "#4C0519", "text_light": "#881337",
        "primary": "#E11D48", "card": "#FFFFFF", "border": "#FFE4E6"
    },
    "🛞 Stealth Dark (Dark)": {
        "bg": "#1F2937", "sidebar": "#111827", "text": "#F9FAFB", "text_light": "#9CA3AF",
        "primary": "#3B82F6", "card": "#374151", "border": "#4B5563"
    },
    "💼 Classic Pro (Light)": {
        "bg": "#FFFFFF", "sidebar": "#F3F4F6", "text": "#111827", "text_light": "#374151",
        "primary": "#4F46E5", "card": "#F9FAFB", "border": "#E5E7EB"
    }
}

# สร้าง Sidebar ส่วนเลือกธีมด้านบนสุดเพื่อป้องกันสไตล์เพี้ยน
st.sidebar.header("🎨 หน้าตาแอปพลิเคชัน")
selected_theme_name = st.sidebar.selectbox("เลือกธีมหน้าจอ:", list(THEMES.keys()), index=0)
theme = THEMES[selected_theme_name]

# สั่งพ่น CSS ควบคุม UI ทั้งหมดให้เป็นไปตามแนวทางของธีมที่เลือก
st.markdown(f"""
    <style>
        .stApp {{
            background-color: {theme['bg']} !important;
            color: {theme['text']} !important;
        }}
        [data-testid="stSidebar"] {{
            background-color: {theme['sidebar']} !important;
        }}
        h1, h2, h3, h4, h5, h6, p, span, label, .stMarkdown {{
            color: {theme['text']} !important;
        }}
        div[data-testid="stForm"] {{
            background-color: {theme['card']} !important;
            border: 1px solid {theme['border']} !important;
            border-radius: 12px;
            padding: 24px;
        }}
        /* จัดการกับกล่องสี่เหลี่ยม Checkbox */
        div[data-testid="stCheckbox"] label span {{
            color: {theme['text']} !important;
        }}
        /* สีของ Input Text, Number และ Selectbox */
        .stTextInput input, .stNumberInput input, div[data-baseweb="select"] {{
            background-color: {theme['card']} !important;
            color: {theme['text']} !important;
            border-color: {theme['border']} !important;
        }}
        /* ตกแต่งตารางประวัติให้ฟอนต์สีไม่อ่านยาก */
        .stTable table {{
            color: {theme['text']} !important;
            background-color: {theme['card']} !important;
        }}
        /* ปุ่มแก้ไขสีของปุ่ม Primary ให้ตรงกับธีม */
        button[kind="primary"] {{
            background-color: {theme['primary']} !important;
            border-color: {theme['primary']} !important;
            color: #FFFFFF !important;
        }}
    </style>
""", unsafe_allow_html=True)


# 2. ฟังก์ชันจัดการฐานข้อมูล
DB_FILE = "trip_database.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # ตาราง User
    cursor.execute('CREATE TABLE IF NOT EXISTS all_users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)')
    
    # ตาราง Trips
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            name TEXT UNIQUE NOT NULL, 
            status INTEGER DEFAULT 0
        )
    ''')
    
    # ตรวจสอบและอัปเดต Schema สำหรับกรณีมีไฟล์เดิมอยู่แล้ว
    try:
        cursor.execute('ALTER TABLE trips ADD COLUMN status INTEGER DEFAULT 0')
    except:
        pass

    # ตารางสมาชิก
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

# ฟังก์ชันบีบอัดรูปภาพ
def compress_image(uploaded_file):
    if uploaded_file is None:
        return None
    img = Image.open(uploaded_file)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.thumbnail((800, 800))  # จำกัดความกว้าง/สูงไม่เกิน 800px
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=70) # บีบอัดคุณภาพ 70%
    return buffer.getvalue()

init_db()


# --- 3. Sidebar: ศูนย์ควบคุม ---
st.sidebar.markdown("---")
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
            conn.execute("INSERT INTO trips (name, status) VALUES (?, 0)", (new_trip_name,))
            conn.commit()
            conn.close()
            st.toast(f"สร้างทริป {new_trip_name} เรียบร้อย!", icon='🗺️')
            st.rerun()
        except: 
            st.sidebar.error("ชื่อทริปซ้ำ")

# 3.3 เลือกทริป และ ถังขยะ
conn = get_db_connection()
active_trips_df = pd.read_sql_query("SELECT * FROM trips WHERE status = 0", conn)
active_trip_list = active_trips_df["name"].tolist() if not active_trips_df.empty else []

# เมนูถังขยะ
with st.sidebar.expander("🗑️ ถังขยะ (ทริปที่ถูกลบ)"):
    deleted_trips = conn.execute("SELECT * FROM trips WHERE status = 1").fetchall()
    if not deleted_trips:
        st.caption("ไม่มีรายการในถังขยะ")
    else:
        for dt in deleted_trips:
            c_name, c_act = st.columns([2, 1])
            c_name.write(dt['name'])
            sub_col1, sub_col2 = c_act.columns(2)
            if sub_col1.button("🔄", key=f"res_{dt['id']}", help="กู้คืน"):
                conn.execute("UPDATE trips SET status = 0 WHERE id = ?", (dt['id'],))
                conn.commit()
                st.rerun()
            if sub_col2.button("❌", key=f"pdel_{dt['id']}", help="ลบถาวร"):
                conn.execute("DELETE FROM settlements WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM expenses WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM members WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM trips WHERE id = ?", (dt['id'],))
                conn.commit()
                st.rerun()

if not active_trip_list:
    st.title("✈️ ระบบจัดการทริป")
    st.info("กรุณาสร้างทริปใหม่ หรือกู้คืนทริปจากถังขยะที่เมนูซ้ายมือ")
    conn.close()
    st.stop()

st.sidebar.markdown("---")
current_trip = st.sidebar.selectbox("🗺️ เลือกทริปที่ต้องการจัดการ:", active_trip_list)
trip_id = conn.execute("SELECT id FROM trips WHERE name = ? AND status = 0", (current_trip,)).fetchone()["id"]

# ปุ่มย้ายลงถังขยะ
if st.sidebar.button("🗑️ ย้ายทริปนี้ไปถังขยะ", type="secondary"):
    conn.execute("UPDATE trips SET status = 1 WHERE id = ?", (trip_id,))
    conn.commit()
    st.toast(f"ย้าย {current_trip} ลงถังขยะแล้ว")
    st.rerun()

# 3.4 สมาชิกในทริป
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
        st.rerun()
conn.close()


# --- 4. ส่วนแสดงผลหลัก ---
if not existing_members:
    st.title(f"📍 ทริป: {current_trip}")
    st.warning("⚠️ กรุณาเลือกสมาชิกเข้าทริปก่อนเริ่มบันทึกบิล")
    st.stop()

st.title(f"📍 ทริป: {current_trip}")
tab1, tab2, tab3 = st.tabs(["📝 บันทึกบิล", "📊 ประวัติและแก้ไข", "💰 สรุปเคลียร์เงิน"])


# --- TAB 1: บันทึกบิล ---
with tab1:
    with st.form("add_bill", clear_on_submit=True):
        st.header("➕ เพิ่มบิลค่าใช้จ่าย")
        desc = st.text_input("รายการ:")
        amt = st.number_input("จำนวนเงิน (บาท):", min_value=0.0, step=50.0)
        payer = st.selectbox("ใครเป็นคนสำรองจ่าย?", existing_members)
        
        st.write("คนหาร:")
        split_to = [m for m in existing_members if st.checkbox(m, value=True, key=f"add_{m}")]
        
        file = st.file_uploader("สลิป:", type=['jpg','png','jpeg'])
        
        if st.form_submit_button("💾 บันทึกรายการ", type="primary"):
            if desc and amt > 0 and split_to:
                blob = compress_image(file)
                conn = get_db_connection()
                conn.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?,?,?,?,?,?)",
                             (trip_id, desc, amt, payer, ",".join(split_to), blob))
                conn.commit()
                conn.close()
                st.toast("บันทึกสำเร็จ!", icon='✅')
                st.rerun()
            else:
                st.error("กรุณากรอกข้อมูลให้ครบถ้วน และเลือกคนหารอย่างน้อย 1 คน")


# --- TAB 2: ประวัติและการแก้ไข ---
with tab2:
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()

    if not expenses:
        st.info("ยังไม่มีข้อมูลบิล")
    else:
        for row in expenses:
            current_split_members = row['split_members'].split(",") if row['split_members'] else []
            
            with st.expander(f"📌 {row['description']} | {row['amount']:,.2f} บาท (โดย {row['payer_name']})"):
                c_view, c_edit = st.columns([1, 1.2])
                with c_view:
                    if row['image_blob']:
                        st.image(row['image_blob'], use_container_width=True)
                    else: 
                        st.caption("ไม่มีรูปภาพสลิป")
                
                with c_edit:
                    with st.form(f"edit_{row['id']}"):
                        u_desc = st.text_input("ชื่อรายการ:", value=row['description'])
                        u_amt = st.number_input("จำนวนเงิน:", value=row['amount'])
                        u_payer = st.selectbox("คนจ่าย:", existing_members, index=existing_members.index(row['payer_name']))
                        
                        st.write("คนหาร:")
                        u_split_to = []
                        for m in existing_members:
                            is_checked = m in current_split_members
                            if st.checkbox(m, value=is_checked, key=f"edit_mem_{row['id']}_{m}"):
                                u_split_to.append(m)
                        
                        u_file = st.file_uploader("อัปเดตรูปสลิป:", type=['jpg','png','jpeg'], key=f"edit_img_{row['id']}")
                        
                        submit_btn = st.form_submit_button("💾 อัปเดตการแก้ไข", type="primary")
                        
                        if submit_btn:
                            if u_desc and u_amt > 0 and u_split_to:
                                conn = get_db_connection()
                                if u_file:
                                    new_blob = compress_image(u_file)
                                    conn.execute("""
                                        UPDATE expenses 
                                        SET description=?, amount=?, payer_name=?, split_members=?, image_blob=? 
                                        WHERE id=?
                                    """, (u_desc, u_amt, u_payer, ",".join(u_split_to), new_blob, row['id']))
                                else:
                                    conn.execute("""
                                        UPDATE expenses 
                                        SET description=?, amount=?, payer_name=?, split_members=? 
                                        WHERE id=?
                                    """, (u_desc, u_amt, u_payer, ",".join(u_split_to), row['id']))
                                conn.commit()
                                conn.close()
                                st.toast("อัปเดตเรียบร้อย!", icon='✅')
                                st.rerun()
                            else:
                                st.error("กรุณากรอกข้อมูลให้ครบถ้วน และต้องมีคนหารอย่างน้อย 1 คน")
                    
                    if st.button(f"🗑️ ลบบิลนี้", key=f"del_exp_{row['id']}", type="secondary"):
                        conn = get_db_connection()
                        conn.execute("DELETE FROM expenses WHERE id=?", (row['id'],))
                        conn.commit()
                        conn.close()
                        st.toast("ลบบิลเรียบร้อยแล้ว")
                        st.rerun()


# --- TAB 3: สรุปและเคลียร์เงิน ---
with tab3:
    st.header("🤝 สรุปยอดโอนเงินรวบยอด")
    conn = get_db_connection()
    expenses_rows = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()

    if not expenses_rows:
        st.info("ยังไม่มีบิลให้คำนวณ")
    else:
        net_balances = {m: 0.0 for m in existing_members}
        for row in expenses_rows:
            p, a, s_str = row['payer_name'], row['amount'], row['split_members']
            if not s_str: 
                continue
            s_list = s_str.split(",")
            net_balances[p] += a
            share = a / len(s_list)
            for m in s_list:
                net_balances[m] -= share
        
        c1, c2 = st.columns(2)
        with c1:
            st.write("**🟢 คนที่ต้องได้รับเงินคืน:**")
            for m, b in net_balances.items():
                if b > 0.01: st.success(f"{m}: `{b:,.2f}` บาท")
        with c2:
            st.write("**🔴 คนที่ต้องจ่ายเพิ่ม:**")
            for m, b in net_balances.items():
                if b < -0.01: st.error(f"{m}: `{abs(b):,.2f}` บาท")

        debtors = [[m, b] for m, b in net_balances.items() if b < -0.01]
        creditors = [[m, b] for m, b in net_balances.items() if b > 0.01]
        
        st.write("---")
        st.subheader("🚀 แผนโอนเงินที่สั้นที่สุด")
        final_tx = []
        while debtors and creditors:
            amt = min(abs(debtors[0][1]), creditors[0][1])
            st.info(f"💳 **{debtors[0][0]}** โอนให้ **{creditors[0][0]}** ยอด **{amt:,.2f}** บาท")
            final_tx.append((debtors[0][0], creditors[0][0], amt))
            debtors[0][1] += amt
            creditors[0][1] -= amt
            if abs(debtors[0][1]) < 0.01: debtors.pop(0)
            if abs(creditors[0][1]) < 0.01: creditors.pop(0)

        if st.button("🎯 บันทึกสรุปยอดปิดทริป", type="primary"):
            conn = get_db_connection()
            conn.execute("DELETE FROM settlements WHERE trip_id = ?", (trip_id,))
            for t in final_tx:
                conn.execute("INSERT INTO settlements (trip_id, debtor, creditor, amount) VALUES (?,?,?,?)", (trip_id, t[0], t[1], t[2]))
            conn.commit()
            conn.close()
            st.success("บันทึกประวัติการเคลียร์เงินแล้ว!")
            st.rerun()

        st.write("---")
        st.subheader("📋 ประวัติการเคลียร์เงินที่บันทึกไว้")
        conn = get_db_connection()
        saved = conn.execute("SELECT * FROM settlements WHERE trip_id = ?", (trip_id,)).fetchall()
        conn.close()
        if saved:
            st.table(pd.DataFrame([{"จาก": s['debtor'], "ถึง": s['creditor'], "จำนวน": f"{s['amount']:,.2f}"} for s in saved]))
        else: 
            st.caption("ยังไม่มีบันทึก")
