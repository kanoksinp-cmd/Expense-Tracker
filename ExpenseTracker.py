import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image

# 1. ตั้งค่าหน้าจอ
st.set_page_config(page_title="Trip Expense Splitter Pro", layout="wide")

# ==========================================
# 🎨 เพิ่มระบบจัดการธีม (5 แบบ)
# ==========================================
THEMES = {
    "🌐 Modern Dark Blue (สุขุม ทันสมัย)": {
        "primary": "#1E88E5", "bg_sidebar": "#0E1117", "bg_card": "#1E2530", "text": "#FFFFFF", "accent": "#00E676"
    },
    "🌿 Pastel Forest (ธรรมชาติ พาสเทล)": {
        "primary": "#4CAF50", "bg_sidebar": "#F1F8E9", "bg_card": "#FFFFFF", "text": "#2E7D32", "accent": "#81C784"
    },
    "🏖️ Ocean Breeze (สดใส ทะเลหน้าร้อน)": {
        "primary": "#00ACC1", "bg_sidebar": "#E0F7FA", "bg_card": "#FFFFFF", "text": "#006064", "accent": "#FFB74D"
    },
    "🥞 Warm Caramel (คาเฟ่ มินิมอล อบอุ่น)": {
        "primary": "#D84315", "bg_sidebar": "#FFE0B2", "bg_card": "#FFFFFF", "text": "#4E342E", "accent": "#FFB74D"
    },
    "🍇 Cyber Neon (จี๊ดจ๊าด สายปาร์ตี้กลางคืน)": {
        "primary": "#E040FB", "bg_sidebar": "#12005e", "bg_card": "#1c0066", "text": "#FFFFFF", "accent": "#00E5FF"
    }
}

# ส่วนเลือกธีมบน Sidebar (วางไว้บนสุด)
st.sidebar.header("🎨 ปรับแต่งหน้าตาแอป")
selected_theme_name = st.sidebar.selectbox("เลือกธีมที่ชอบ:", list(THEMES.keys()))
theme = THEMES[selected_theme_name]

# ฝัง CSS เพื่อเปลี่ยนสไตล์ตามธีมที่เลือก
custom_css = f"""
<style>
    /* เปลี่ยนสีปุ่มหลัก Primary Button */
    div.stButton > button[kind="primary"] {{
        background-color: {theme['primary']} !important;
        color: white !important;
        border: none !important;
    }}
    /* เปลี่ยนสีกรอบ Expander และ Card ส่วนประวัติ */
    .stAlert, div[data-testid="stExpander"] {{
        border-left: 5px solid {theme['primary']} !important;
        background-color: {theme['bg_card']} !important;
    }}
    /* ปรับแต่งความสวยงามเพิ่มเติม */
    h1, h2, h3 {{
        color: {theme['primary']} !important;
    }}
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)
st.sidebar.markdown("---")

# ==========================================
# 2. ฟังก์ชันจัดการฐานข้อมูล (เหมือนเดิม)
# ==========================================
DB_FILE = "trip_database.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS all_users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            name TEXT UNIQUE NOT NULL, 
            status INTEGER DEFAULT 0
        )
    ''')
    try:
        cursor.execute('ALTER TABLE trips ADD COLUMN status INTEGER DEFAULT 0')
    except:
        pass

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
    if uploaded_file is None:
        return None
    img = Image.open(uploaded_file)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.thumbnail((800, 800))  
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=70) 
    return buffer.getvalue()

init_db()

# --- 3. Sidebar: ศูนย์ควบคุม ---
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
        
        if st.form_submit_button("💾 บันทึกรายการ", type="primary"): # เปลี่ยนประเภทเพื่อรองรับธีม
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
                        
                        submit_btn = st.form_submit_button("💾 อัปเดตการแก้ไข", type="primary") # เปลี่ยนประเภทเพื่อรองรับธีม
                        
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
