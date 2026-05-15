import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image

# ตั้งค่าหน้าเว็บ
st.set_page_config(page_title="Trip Expense Persistent Pro", layout="wide")

# --- ส่วนของการจัดการฐานข้อมูล SQLite ---
DB_FILE = "trip_database.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # ให้เข้าถึงข้อมูลด้วยชื่อคอลัมน์ได้
    return conn

def init_db():
    """สร้างตารางในฐานข้อมูลถ้ายังไม่มี"""
    conn = get_db_connection()
    cursor = conn.cursor()
    # 1. ตารางทริป
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    # 2. ตารางสมาชิก
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER,
            name TEXT,
            FOREIGN KEY(trip_id) REFERENCES trips(id),
            UNIQUE(trip_id, name)
        )
    ''')
    # 3. ตารางค่าใช้จ่าย
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER,
            description TEXT,
            amount REAL,
            payer_name TEXT,
            split_members TEXT, -- เก็บเป็น String คั่นด้วยจุลภาค เช่น "A,B,C"
            image_blob BLOB,     -- เก็บไฟล์รูปภาพเป็น Binary
            FOREIGN KEY(trip_id) REFERENCES trips(id)
        )
    ''')
    conn.commit()
    conn.close()

# เรียกใช้งานการสร้างฐานข้อมูลตั้งแต่เปิดแอป
init_db()

# --- ส่วนติดต่อผู้ใช้ (UI) ---
st.title("✈️ ระบบจัดการค่าใช้จ่ายทริป (เวอร์ชันบันทึกถาวร)")
st.caption("ข้อมูลถูกบันทึกลงฐานข้อมูล สามารถปิดแอปและกลับมาค้นหา อัปเดต หรือแก้ไขได้ตลอดเวลา")

# ฟังก์ชันดึงข้อมูลจาก DB มาแสดงใน UI
conn = get_db_connection()

# ดึงรายชื่อทริปทั้งหมด
trips_df = pd.read_sql_query("SELECT * FROM trips", conn)
trip_list = trips_df["name"].tolist() if not trips_df.empty else []

# --- แถบควบคุมด้านซ้าย (Sidebar) ---
st.sidebar.header("🛠️ ส่วนควบคุมของ Leader")

# 1. สร้างทริปใหม่
new_trip = st.sidebar.text_input("➕ สร้างทริปใหม่:").strip()
if st.sidebar.button("บันทึกทริป"):
    if new_trip:
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO trips (name) VALUES (?)", (new_trip,))
            conn.commit()
            st.sidebar.success(f"บันทึกทริป '{new_trip}' ลงฐานข้อมูลสำเร็จ!")
            st.rerun()
        except sqlite3.IntegrityError:
            st.sidebar.warning("❌ มีชื่อทริปนี้อยู่ในประวัติแล้ว")
    else:
        st.sidebar.error("กรุณากรอกชื่อทริป")

if not trip_list:
    st.info("👋 ยินดีต้อนรับ! กรุณาสร้างทริปแรกที่แถบเครื่องมือด้านซ้ายเพื่อเปิดระบบฐานข้อมูล")
    conn.close()
    st.stop()

# 2. เลือกทริปจากประวัติที่มีอยู่
current_trip_name = st.sidebar.selectbox("🗺️ ประวัติทริปทั้งหมดของคุณ:", trip_list)

# ดึง ID ของทริปปัจจุบัน
trip_id = conn.execute("SELECT id FROM trips WHERE name = ?", (current_trip_name,)).fetchone()["id"]

# 3. การจัดการสมาชิกในทริปนั้นๆ
st.sidebar.subheader(f"👥 สมาชิกใน {current_trip_name}")
new_member = st.sidebar.text_input("➕ เพิ่มชื่อผู้ร่วมทริป:").strip()
if st.sidebar.button("เพิ่มสมาชิก"):
    if new_member:
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, new_member))
            conn.commit()
            st.sidebar.success(f"เพิ่มคุณ {new_member} เรียบร้อย")
            st.rerun()
        except sqlite3.IntegrityError:
            st.sidebar.warning("มีสมาชิกชื่อนี้อยู่ในทริปแล้ว")

# ดึงรายชื่อสมาชิกของทริปปัจจุบัน
members_rows = conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()
members = [row["name"] for row in members_rows]

if members:
    st.sidebar.write(f"**รายชื่อสมาชิก:** " + ", ".join(members))
else:
    st.sidebar.info("ยังไม่มีสมาชิกในทริปนี้")

# --- ปิดการเชื่อมต่อชั่วคราวเพื่อส่งต่อให้ฟอร์ม ---
conn.close()


# --- ตรวจสอบสถานะสมาชิกก่อนอนุญาตให้กรอกบิล ---
if not members:
    st.warning("⚠️ กรุณาเพิ่มสมาชิกอย่างน้อย 1 คนในแถบด้านซ้ายก่อนเริ่มบันทึกค่าใช้จ่าย")
    st.stop()

tab1, tab2, tab3 = st.tabs(["📝 บันทึกค่าใช้จ่ายใหม่", "📊 ตารางประวัติ สรุปผล & แก้ไข", "💰 วิธีเคลียร์เงิน (Settlement)"])

# --- TAB 1: บันทึกค่าใช้จ่ายลงฐานข้อมูล ---
with tab1:
    st.header(f"➕ บันทึกรายจ่ายในทริป: {current_trip_name}")
    
    with st.form("expense_form", clear_on_submit=True):
        description = st.text_input("รายการค่าใช้จ่าย:")
        amount = st.number_input("จำนวนเงิน (บาท):", min_value=0.0, step=100.0, format="%.2f")
        payer = st.selectbox("ใครเป็นคนสำรองจ่ายเงิน?", members)
        
        st.write("**ใครต้องหารรายการนี้บ้าง?**")
        split_with = []
        for member in members:
            if st.checkbox(member, value=True, key=f"add_split_{member}"):
                split_with.append(member)
        
        uploaded_file = st.file_uploader("📸 แนบรูปสลิป/ใบเสร็จ", type=["png", "jpg", "jpeg"])
        
        submit_btn = st.form_submit_button("💾 บันทึกรายการลงฐานข้อมูล")
        
        if submit_btn:
            if not description:
                st.error("กรุณากรอกรายการค่าใช้จ่าย")
            elif amount <= 0:
                st.error("จำนวนเงินต้องมากกว่า 0 บาท")
            elif not split_with:
                st.error("ต้องมีผู้ร่วมหารอย่างน้อย 1 คน")
            else:
                # แปลงรูปภาพเป็น Byte ไบนารีเพื่อเซฟลง DB
                blob_data = None
                if uploaded_file is not None:
                    blob_data = uploaded_file.read()
                
                # รวมชื่อคนหารเป็น string แยกด้วยเครื่องหมายจุลภาค (,)
                split_members_str = ",".join(split_with)
                
                # บันทึกเข้า SQLite
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (trip_id, description, amount, payer, split_members_str, blob_data))
                conn.commit()
                conn.close()
                
                st.success(f"บันทึกข้อมูลและจัดเก็บประวัติรายการ '{description}' สำเร็จ!")
                st.rerun()

# --- ดึงรายการค่าใช้จ่ายจาก DB มาคำนวณใน TAB 2 และ TAB 3 ---
conn = get_db_connection()
expenses_rows = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
conn.close()

# ปรับโครงสร้างข้อมูลที่ดึงจาก DB ให้เป็นรูปแบบ List Object เพื่อความสะดวกในการใช้งาน
expenses_list = []
for row in expenses_rows:
    img_data = None
    if row["image_blob"]:
        img_data = Image.open(io.BytesIO(row["image_blob"]))
        
    expenses_list.append({
        "id": row["id"],
        "รายการ": row["description"],
        "จำนวนเงิน": row["amount"],
        "คนจ่าย": row["payer_name"],
        "คนหาร": row["split_members"].split(",") if row["split_members"] else [],
        "รูปภาพ": img_data
    })

# --- TAB 2: ตารางประวัติสรุปและอัปเดตข้อมูลย้อนหลัง ---
with tab2:
    st.header(f"📋 ประวัติค่าใช้จ่ายทั้งหมดใน: {current_trip_name}")
    
    if not expenses_list:
        st.info("ยังไม่มีข้อมูลค่าใช้จ่ายถูกบันทึกไว้ในประวัติของทริปนี้")
    else:
        total_trip_amount = sum([exp["จำนวนเงิน"] for exp in expenses_list])
        st.metric(label="💰 รวมงบประมาณที่ใช้ไปในทริปนี้ ณ ตอนนี้", value=f"{total_trip_amount:,.2f} บาท")
        st.write("---")
        
        for index, exp in enumerate(expenses_list):
            with st.expander(f"📌 รายการที่ {index+1}: {exp['รายการ']} | 💵 {exp['จำนวนเงิน']:,.2f} บาท (ออกโดย {exp['คนจ่าย']})"):
                col_view, col_edit = st.columns([2, 2])
                
                with col_view:
                    st.write(f"**📝 ชื่อรายการ:** {exp['รายการ']}")
                    st.write(f"**💵 จำนวนเงินสุทธิ:** {exp['จำนวนเงิน']:,.2f} บาท")
                    st.write(f"**👤 ผู้สำรองเงิน:** {exp['คนจ่าย']}")
                    st.write(f"**👥 สมาชิกที่ร่วมหารบิล:** {', '.join(exp['คนหาร'])}")
                    
                    if exp["รูปภาพ"] is not None:
                        st.image(exp["รูปภาพ"], caption="หลักฐานการจ่ายเงินในระบบ", width=300)
                    else:
                        st.caption("🈚 ไม่มีสลิปแนบอยู่")
                        
                with col_edit:
                    st.markdown("#### ✏️ อัปเดตข้อมูล / 🗑️ ลบรายการออกฐานข้อมูล")
                    edit_desc = st.text_input("แก้ไขชื่อรายการ:", value=exp['รายการ'], key=f"ed_desc_{exp['id']}")
                    edit_amount = st.number_input("แก้ไขจำนวนเงิน (บาท):", min_value=0.0, value=float(exp['จำนวนเงิน']), format="%.2f", key=f"ed_amount_{exp['id']}")
                    
                    default_payer_idx = members.index(exp['คนจ่าย']) if exp['คนจ่าย'] in members else 0
                    edit_payer = st.selectbox("แก้ไขคนสำรองจ่าย:", members, index=default_payer_idx, key=f"ed_payer_{exp['id']}")
                    
                    st.write("แก้ไขผู้ร่วมหาร:")
                    edit_split_with = []
                    for member in members:
                        is_checked = member in exp['คนหาร']
                        if st.checkbox(member, value=is_checked, key=f"ed_split_{member}_{exp['id']}"):
                            edit_split_with.append(member)
                            
                    edit_file = st.file_uploader("🔄 เปลี่ยนรูปภาพสลิปใหม่", type=["png", "jpg", "jpeg"], key=f"ed_file_{exp['id']}")
                    
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("💾 บันทึกและอัปเดต", key=f"save_ed_{exp['id']}", type="primary"):
                            if not edit_desc or edit_amount <= 0 or not edit_split_with:
                                st.error("กรุณากรอกข้อมูลให้ครบถ้วนและถูกต้อง")
                            else:
                                conn = get_db_connection()
                                cursor = conn.cursor()
                                split_str = ",".join(edit_split_with)
                                
                                # ตรวจเช็คว่ามีการเปลี่ยนรูปสลิปไหม
                                if edit_file is not None:
                                    new_blob = edit_file.read()
                                    cursor.execute('''
                                        UPDATE expenses 
                                        SET description=?, amount=?, payer_name=?, split_members=?, image_blob=? 
                                        WHERE id=?
                                    ''', (edit_desc, edit_amount, edit_payer, split_str, new_blob, exp['id']))
                                else:
                                    cursor.execute('''
                                        UPDATE expenses 
                                        SET description=?, amount=?, payer_name=?, split_members=? 
                                        WHERE id=?
                                    ''', (edit_desc, edit_amount, edit_payer, split_str, exp['id']))
                                conn.commit()
                                conn.close()
                                st.success("อัปเดตประวัติฐานข้อมูลแล้ว!")
                                st.rerun()
                                
                    with btn_col2:
                        if st.button("🗑️ ลบจากฐานข้อมูล", key=f"del_ed_{exp['id']}"):
                            conn = get_db_connection()
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM expenses WHERE id=?", (exp['id'],))
                            conn.commit()
                            conn.close()
                            st.warning("ลบรายการออกจากประวัติถาวรแล้ว")
                            st.rerun()

# --- TAB 3: สรุปวิธีเคลียร์เงิน (Settlement) ---
with tab3:
    st.header("🤝 คำนวณสรุปยอดบิลโอนเงิน")
    
    if not expenses_list:
        st.info("เมื่อมีการบันทึกค่าใช้จ่ายในประวัติ ระบบจะแสดงขั้นตอนการโอนเงินที่สั้นที่สุดให้ทันที")
    else:
        net_balances = {member: 0.0 for member in members}
        
        for exp in expenses_list:
            payer = exp["คนจ่าย"]
            amount = exp["จำนวนเงิน"]
            split_with = exp["คนหาร"]
            
            if payer in net_balances:
                net_balances[payer] += amount
            
            share = amount / len(split_with) if split_with else 0
            for member in split_with:
                if member in net_balances:
                    net_balances[member] -= share
                    
        col1, col2 = st.columns(2)
        with col1:
            st.write("**🟢 คนที่ต้องได้เงินคืน:**")
            for member, bal in net_balances.items():
                if bal > 0.01: st.write(f"👤 **{member}** ได้รับคืน: `{bal:,.2f}` บาท")
        with col2:
            st.write("**🔴 คนที่ต้องจ่ายเพิ่ม:**")
            for member, bal in net_balances.items():
                if bal < -0.01: st.write(f"👤 **{member}** ต้องจ่ายเพิ่ม: `{abs(bal):,.2f}` บาท")
                
        st.write("---")
        st.subheader("🚀 แผนภาพขั้นตอนการโอนเงิน")
        
        debtors = [[m, bal] for m, bal in net_balances.items() if bal < -0.01]
        creditors = [[m, bal] for m, bal in net_balances.items() if bal > 0.01]
        
        transactions = []
        while debtors and creditors:
            debtor_name, debtor_bal = debtors[0]
            creditor_name, creditor_bal = creditors[0]
            
            amount_to_pay = min(abs(debtor_bal), creditor_bal)
            transactions.append(f"💳 **{debtor_name}** โอนเงินให้ 👉 **{creditor_name}** ยอดรวม **`{amount_to_pay:,.2f}`** บาท")
            
            debtors[0][1] += amount_to_pay
            creditors[0][1] -= amount_to_pay
            if abs(debtors[0][1]) < 0.01: debtors.pop(0)
            if abs(creditors[0][1]) < 0.01: creditors.pop(0)
            
        if transactions:
            for tx in transactions:
                st.info(tx)
        else:
            st.success("🎉 ทุกทริปเครียร์จบเรียบร้อย ไม่มีหนี้ค้างส่งต่อ!")
