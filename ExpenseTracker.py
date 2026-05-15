import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image

# ตั้งค่าหน้าเว็บให้แสดงผลแบบกว้าง scannable ง่าย
st.set_page_config(page_title="Trip Expense Splitter Ultimate", layout="wide")

# --- 1. การจัดการระบบฐานข้อมูล SQLite ---
DB_FILE = "trip_database.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """สร้างโครงสร้างตารางทั้งหมดหากเปิดใช้งานแอปครั้งแรก"""
    conn = get_db_connection()
    cursor = conn.cursor()
    # ตารางทริป
    cursor.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)')
    # ตารางสมาชิก
    cursor.execute('CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, name TEXT, FOREIGN KEY(trip_id) REFERENCES trips(id), UNIQUE(trip_id, name))')
    # ตารางค่าใช้จ่าย (เก็บรูปภาพเป็น BLOB)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, description TEXT, 
            amount REAL, payer_name TEXT, split_members TEXT, image_blob BLOB,
            FOREIGN KEY(trip_id) REFERENCES trips(id)
        )
    ''')
    # ตารางเก็บสรุปยอดเคลียร์เงินโอนที่รวบรวมจากทุกบิล
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, 
            debtor TEXT, creditor TEXT, amount REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(trip_id) REFERENCES trips(id)
        )
    ''')
    conn.commit()
    conn.close()

# เรียกใช้งานฐานข้อมูลทันที
init_db()

# --- 2. ดึงข้อมูลเบื้องต้นเพื่อเปิดใช้งานหน้าแอป ---
conn = get_db_connection()
trips_df = pd.read_sql_query("SELECT * FROM trips", conn)
trip_list = trips_df["name"].tolist() if not trips_df.empty else []

# --- 3. แถบควบคุมด้านซ้าย (Sidebar) สำหรับคุณที่เป็น User/Leader ---
st.sidebar.header("🛠️ ส่วนควบคุมของ Leader")

# 3.1 ฟอร์มสร้างทริปใหม่
new_trip = st.sidebar.text_input("➕ สร้างทริปใหม่ (เก็บประวัติถาวร):").strip()
if st.sidebar.button("บันทึกทริป"):
    if new_trip:
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO trips (name) VALUES (?)", (new_trip,))
            conn.commit()
            st.sidebar.success(f"บันทึกทริป '{new_trip}' สำเร็จ!")
            st.rerun()
        except sqlite3.IntegrityError:
            st.sidebar.warning("❌ มีชื่อทริปนี้อยู่ในระบบแล้ว")
    else:
        st.sidebar.error("กรุณากรอกชื่อทริป")

# หยุดการทำงานชั่วคราวหากยังไม่มีทริปแรกในฐานข้อมูล
if not trip_list:
    st.title("✈️ ระบบจัดการค่าใช้จ่ายทริป (เวอร์ชันสมบูรณ์)")
    st.info("👋 ยินดีต้อนรับ! กรุณาสร้างทริปแรกของคุณที่แถบเครื่องมือด้านซ้ายเพื่อเริ่มต้นระบบฐานข้อมูลครับ")
    conn.close()
    st.stop()

# 3.2 เลือกทริปที่ต้องการเข้าไปแก้ไข/อัปเดตข้อมูล
current_trip_name = st.sidebar.selectbox("🗺️ เลือกประวัติทริปที่ต้องการจัดการ:", trip_list)
trip_id = conn.execute("SELECT id FROM trips WHERE name = ?", (current_trip_name,)).fetchone()["id"]

# 3.3 เพิ่มสมาชิกในทริปที่เลือก
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

# ดึงรายชื่อสมาชิกปัจจุบันขึ้นมาแสดง
members_rows = conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()
members = [row["name"] for row in members_rows]
if members:
    st.sidebar.write(f"**รายชื่อสมาชิก ({len(members)} คน):** " + ", ".join(members))
conn.close()

# หยุดการทำงานหากมีทริปแต่ยังไม่มีเพื่อนร่วมทริป
if not members:
    st.title(f"🗺️ ทริป: {current_trip_name}")
    st.warning("⚠️ กรุณาเพิ่มสมาชิกอย่างน้อย 1 คนในแถบด้านซ้ายก่อนเริ่มบันทึกบิลค่าใช้จ่าย")
    st.stop()


# --- 4. หน้าหลักของแอปพลิเคชันแบ่งเป็น 3 Tab ทำงานครอบคลุมทุกฟังก์ชัน ---
st.title(f"🗺️ ระบบจัดการทริป: {current_trip_name}")
st.caption("ระบบรวบรวมยอดบิล, หารค่าใช้จ่ายรายคน, แนบรูปหลักฐาน และบันทึกผลการเคลียร์เงินสดถาวร")

tab1, tab2, tab3 = st.tabs(["📝 บันทึกค่าใช้จ่ายใหม่", "📊 ตารางประวัติบิล & แก้ไข/ลบ", "💰 สรุปคำนวณรวมยอด & บันทึกเคลียร์เงิน"])

# --- TAB 1: เพิ่มบิลรายจ่ายใหม่และจัดเก็บรูปภาพสลิป ---
with tab1:
    st.header("➕ เพิ่มรายการค่าใช้จ่ายใหม่")
    with st.form("expense_form", clear_on_submit=True):
        description = st.text_input("รายการค่าใช้จ่าย (เช่น ค่าที่พัก, ค่าอาหารมื้อแรก, ค่าน้ำมัน):")
        amount = st.number_input("จำนวนเงินรวมของบิลนี้ (บาท):", min_value=0.0, step=100.0, format="%.2f")
        payer = st.selectbox("ใครเป็นคนออกเงินสำรองจ่ายก่อน?", members)
        
        st.write("**ใครต้องมีส่วนร่วมในการหารบิลนี้บ้าง?** (ติ๊กเลือกทั้งหมดหรือเลือกเฉพาะบางคน)")
        split_with = []
        for member in members:
            if st.checkbox(member, value=True, key=f"add_split_{member}"):
                split_with.append(member)
        
        uploaded_file = st.file_uploader("📸 แนบรูปภาพสลิป/ใบเสร็จเพื่อเป็นหลักฐาน", type=["png", "jpg", "jpeg"])
        submit_btn = st.form_submit_button("💾 บันทึกรายการลงฐานข้อมูล")
        
        if submit_btn:
            if not description or amount <= 0 or not split_with:
                st.error("กรุณากรอกข้อมูลรายการ, จำนวนเงินให้ถูกต้อง และเลือกคนร่วมหารอย่างน้อย 1 คน")
            else:
                blob_data = uploaded_file.read() if uploaded_file is not None else None
                split_members_str = ",".join(split_with)
                
                conn = get_db_connection()
                conn.execute('INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?, ?, ?, ?, ?, ?)',
                             (trip_id, description, amount, payer, split_members_str, blob_data))
                conn.commit()
                conn.close()
                st.success(f"บันทึกประวัติรายการ '{description}' เข้าสู่ระบบสำเร็จ!")
                st.rerun()

# --- ดึงข้อมูลค่าใช้จ่ายทั้งหมดในทริปนี้มาจัดเรียงวัตถุเพื่อป้อนเข้า Tab 2 และ Tab 3 ---
conn = get_db_connection()
expenses_rows = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
conn.close()

expenses_list = []
for row in expenses_rows:
    img_data = Image.open(io.BytesIO(row["image_blob"])) if row["image_blob"] else None
    expenses_list.append({
        "id": row["id"], "รายการ": row["description"], "จำนวนเงิน": row["amount"], 
        "คนจ่าย": row["payer_name"], "คนหาร": row["split_members"].split(",") if row["split_members"] else [], 
        "รูปภาพ": img_data
    })


# --- TAB 2: ตารางประวัติ ส่องสลิป และระบบแก้ไข/ลบข้อมูลย้อนหลังได้ตลอดเวลา ---
with tab2:
    st.header("📋 ประวัติและตารางสรุปบิลทั้งหมด")
    if not expenses_list:
        st.info("ยังไม่มีข้อมูลค่าใช้จ่ายถูกบันทึกไว้ในทริปนี้")
    else:
        total_trip_amount = sum([exp["จำนวนเงิน"] for exp in expenses_list])
        st.metric(label="💰 งบประมาณรวมที่ใช้จ่ายไปทั้งหมดในทริปนี้", value=f"{total_trip_amount:,.2f} บาท")
        st.write("---")
        
        # วนลูปแสดงผลบิลทีละแถวในรูปแบบ Expander เพื่อความสะอาด Scannable ง่าย
        for index, exp in enumerate(expenses_list):
            with st.expander(f"📌 บิลที่ {index+1}: {exp['รายการ']} | 💵 {exp['จำนวนเงิน']:,.2f} บาท (โดยคุณ {exp['คนจ่าย']})"):
                col_view, col_edit = st.columns([2, 2])
                
                # ฝั่งซ้าย: ส่องรายละเอียดบิลเดิมและดูรูปสลิป
                with col_view:
                    st.write(f"**📝 ชื่อรายการบิล:** {exp['รายการ']}")
                    st.write(f"**💵 ยอดเงินในบิล:** {exp['จำนวนเงิน']:,.2f} บาท")
                    st.write(f"**👤 ผู้สำรองเงิน:** {exp['คนจ่าย']}")
                    st.write(f"**👥 ผู้ที่มีรายชื่อร่วมหาร:** {', '.join(exp['คนหาร'])}")
                    if exp["รูปภาพ"] is not None: 
                        st.image(exp["รูปภาพ"], caption=f"หลักฐานบิล: {exp['รายการ']}", width=300)
                    else: 
                        st.caption("🈚 บิลนี้ไม่ได้แนบสลิปไว้")
                        
                # ฝั่งขวา: ฟอร์มอัปเดตข้อมูลสด หรือสั่งลบออกจากคลังข้อมูล
                with col_edit:
                    st.markdown("#### ✏️ อัปเดตข้อมูลบิลนี้ / 🗑️ ลบรายการ")
                    edit_desc = st.text_input("แก้ไขชื่อรายการ:", value=exp['รายการ'], key=f"ed_desc_{exp['id']}")
                    edit_amount = st.number_input("แก้ไขจำนวนเงิน (บาท):", min_value=0.0, value=float(exp['จำนวนเงิน']), format="%.2f", key=f"ed_amount_{exp['id']}")
                    default_payer_idx = members.index(exp['คนจ่าย']) if exp['คนจ่าย'] in members else 0
                    edit_payer = st.selectbox("แก้ไขคนสำรองจ่าย:", members, index=default_payer_idx, key=f"ed_payer_{exp['id']}")
                    
                    edit_split_with = []
                    for member in members:
                        if st.checkbox(member, value=member in exp['คนหาร'], key=f"ed_split_{member}_{exp['id']}"): 
                            edit_split_with.append(member)
                            
                    edit_file = st.file_uploader("🔄 อัปโหลดรูปสลิปใหม่ทับรูปเดิม", type=["png", "jpg", "jpeg"], key=f"ed_file_{exp['id']}")
                    
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("💾 บันทึกและอัปเดตบิล", key=f"save_ed_{exp['id']}", type="primary"):
                            if not edit_desc or edit_amount <= 0 or not edit_split_with:
                                st.error("กรุณากรอกข้อมูลให้ครบถ้วนถูกต้อง")
                            else:
                                conn = get_db_connection()
                                split_str = ",".join(edit_split_with)
                                if edit_file is not None:
                                    conn.execute('UPDATE expenses SET description=?, amount=?, payer_name=?, split_members=?, image_blob=? WHERE id=?', (edit_desc, edit_amount, edit_payer, split_str, edit_file.read(), exp['id']))
                                else:
                                    conn.execute('UPDATE expenses SET description=?, amount=?, payer_name=?, split_members=? WHERE id=?', (edit_desc, edit_amount, edit_payer, split_str, exp['id']))
                                conn.commit()
                                conn.close()
                                st.success("อัปเดตข้อมูลประวัติบิลเรียบร้อย!")
                                st.rerun()
                    with btn_col2:
                        if st.button("🗑️ ลบรายการบิลนี้ทิ้ง", key=f"del_ed_{exp['id']}"):
                            conn = get_db_connection()
                            conn.execute("DELETE FROM expenses WHERE id=?", (exp['id'],))
                            conn.commit()
                            conn.close()
                            st.warning("ลบรายการบิลออกจากฐานข้อมูลแล้ว")
                            st.rerun()


# --- TAB 3: รวมยอดสะสมค่าหารของทุกบิล และทำการบันทึกประวัติการเคลียร์เงินก้อนสุดท้ายถาวร ---
with tab3:
    st.header("🤝 สรุปคำนวณการรวมยอดเคลียร์บิลประจำทริป")
    
    if not expenses_list:
        st.info("กรุณาบันทึกค่าใช้จ่ายในระบบก่อน ระบบจึงจะคำนวณรวมยอดค่าหารให้ครับ")
    else:
        # 3.1 คํานวณยอดสุทธิสะสมสะสมจากทุกบิล (Net Balance = ยอดจ่ายจริงทั้งหมด - ยอดที่ต้องช่วยหารทั้งหมด)
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
                    
        # 3.2 ใช้ Greedy Algorithm เพื่อจับคู่หาเส้นทางการโอนเงินก้อนสั้นที่สุด (รวมผลลัพธ์ของทุกบิลเข้าด้วยกัน)
        debtors = [[m, bal] for m, bal in net_balances.items() if bal < -0.01]
        creditors = [[m, bal] for m, bal in net_balances.items() if bal > 0.01]
        
        calculated_transactions = []
        while debtors and creditors:
            db_name, db_bal = debtors[0]
            cr_name, cr_bal = creditors[0]
            amt = min(abs(db_bal), cr_bal)
            calculated_transactions.append({"debtor": db_name, "creditor": cr_name, "amount": amt})
            debtors[0][1] += amt
            creditors[0][1] -= amt
            if abs(debtors[0][1]) < 0.01: debtors.pop(0)
            if abs(creditors[0][1]) < 0.01: creditors.pop(0)

        # แสดงกระเป๋าเงินสุทธิรายคนให้ Leader ตรวจสอบก่อน
        st.subheader("💵 สถานะกระเป๋าเงินสุทธิรวมทุกบิล (รายคน)")
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.write("**🟢 คนที่จ่ายเงินเกินส่วนกลาง (ต้องได้รับเงินคืน):**")
            for m, b in net_balances.items():
                if b > 0.01: st.write(f"👤 **{m}** ยอดได้รับคืนสุทธิ: `{b:,.2f}` บาท")
        with col_c2:
            st.write("**🔴 คนที่ใช้เงินเกินส่วนกลาง (ต้องควักกระเป๋าจ่ายเพิ่ม):**")
            for m, b in net_balances.items():
                if b < -0.01: st.write(f"👤 **{m}** ยอดที่ต้องจ่ายเพิ่มสุทธิ: `{abs(b):,.2f}` บาท")

        st.write("---")
        st.subheader("🚀 แผนการโอนเงินเพื่อเคลียร์บิลที่สั้นที่สุด")
        for tx in calculated_transactions:
            st.info(f"💳 **{tx['debtor']}** โอนเงินให้ 👉 **{tx['creditor']}** เป็นยอดสุทธิ **`{tx['amount']:,.2f}`** บาท")
            
        # 3.3 ส่วนการบันทึกผลลัพธ์การจับคู่เคลียร์เงินก้อนนี้ลงฐานข้อมูล
        st.write("---")
        st.subheader("🔒 ล็อกผลสรุปยอดเคลียร์เงินลงประวัติทริป")
        st.caption("เมื่อลูกทริปทุกคนทำการโอนเงินคืนตามตารางด้านบนเรียบร้อยแล้ว Leader สามารถกดปุ่มนี้เพื่อจัดเก็บประวัติผลการเคลียร์เงินรอบนี้ลงสู่ฐานข้อมูลถาวรได้ทันที")
        
        if st.button("🎯 บันทึกสรุปยอดเคลียร์เงินนี้ลงรายการประวัติทริป", type="primary"):
            if not calculated_transactions:
                st.success("ทริปนี้ยอดเงินลงตัวเรียบร้อยอยู่แล้ว ไม่มียอดค้างชำระให้บันทึกครับ")
            else:
                conn = get_db_connection()
                # ลบรายการเก่าของทริปนี้ทิ้งก่อนเพื่อป้องกันประวัติทับซ้อนกรณีผู้นำทริปกลับมาแก้ไขบิลแล้วกดเซฟใหม่
                conn.execute("DELETE FROM settlements WHERE trip_id = ?", (trip_id,))
                
                # บันทึกลงตาราง settlements
                for tx in calculated_transactions:
                    conn.execute('INSERT INTO settlements (trip_id, debtor, creditor, amount) VALUES (?, ?, ?, ?)',
                                 (trip_id, tx['debtor'], tx['creditor'], tx['amount']))
                conn.commit()
                conn.close()
                st.success("💾 ทำการอัปเดตและบันทึกผลลัพธ์การเคลียร์เงินสดรวบยอด ลงสู่ประวัติทริปถาวรเรียบร้อยแล้ว!")
                st.rerun()

        # 3.4 ตารางแสดงผลบันทึกประวัติการเคลียร์เงิน (Saved Settlement History)
        st.write("---")
        st.subheader("📋 รายการประวัติการเคลียร์เงินที่บันทึกสำเร็จ (Saved Settlement History)")
        
        conn = get_db_connection()
        saved_settlements = conn.execute("SELECT debtor, creditor, amount, timestamp FROM settlements WHERE trip_id = ? ORDER BY timestamp DESC", (trip_id,)).fetchall()
        conn.close()
        
        if not saved_settlements:
            st.caption("🈚 ทริปนี้ยังไม่มีการบันทึกปิดยอดสรุป (สามารถกดปุ่มล็อกยอดด้านบนเมื่อทำการโอนเงินกันเรียบร้อย)")
        else:
            settle_data = []
            for row in saved_settlements:
                settle_data.append({
                    "ผู้โอนเงิน (Debtor)": row["debtor"],
                    "ผู้รับเงินโอน (Creditor)": row["creditor"],
                    "จำนวนเงินที่โอนสุทธิ (บาท)": f"{row['amount']:,.2f}",
                    "เวลาที่ Leader กดปิดยอด": row["timestamp"]
                })
            st.table(pd.DataFrame(settle_data))
