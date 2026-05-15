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
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """สร้างตารางในฐานข้อมูลรวมถึงตารางเก็บประวัติเคลียร์หนี้"""
    conn = get_db_connection()
    cursor = conn.cursor()
    # 1. ตารางทริป
    cursor.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)')
    # 2. ตารางสมาชิก
    cursor.execute('CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, name TEXT, FOREIGN KEY(trip_id) REFERENCES trips(id), UNIQUE(trip_id, name))')
    # 3. ตารางค่าใช้จ่าย
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, description TEXT, 
            amount REAL, payer_name TEXT, split_members TEXT, image_blob BLOB,
            FOREIGN KEY(trip_id) REFERENCES trips(id)
        )
    ''')
    # 4. ตารางเก็บผลลัพธ์การเคลียร์เงินโอน (ฟีเจอร์ใหม่)
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

# --- ดึงข้อมูลทริป ---
conn = get_db_connection()
trips_df = pd.read_sql_query("SELECT * FROM trips", conn)
trip_list = trips_df["name"].tolist() if not trips_df.empty else []

# --- แถบควบคุมด้านซ้าย (Sidebar) ---
st.sidebar.header("🛠️ ส่วนควบคุมของ Leader")
new_trip = st.sidebar.text_input("➕ สร้างทริปใหม่:").strip()
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

if not trip_list:
    st.info("👋 ยินดีต้อนรับ! กรุณาสร้างทริปแรกที่แถบเครื่องมือด้านซ้ายเพื่อเปิดระบบฐานข้อมูล")
    conn.close()
    st.stop()

current_trip_name = st.sidebar.selectbox("🗺️ ประวัติทริปทั้งหมดของคุณ:", trip_list)
trip_id = conn.execute("SELECT id FROM trips WHERE name = ?", (current_trip_name,)).fetchone()["id"]

# การจัดการสมาชิก
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

members_rows = conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()
members = [row["name"] for row in members_rows]
if members:
    st.sidebar.write(f"**รายชื่อสมาชิก:** " + ", ".join(members))
conn.close()

if not members:
    st.warning("⚠️ กรุณาเพิ่มสมาชิกอย่างน้อย 1 คนในแถบด้านซ้ายก่อนเริ่มบันทึกค่าใช้จ่าย")
    st.stop()

tab1, tab2, tab3 = st.tabs(["📝 บันทึกค่าใช้จ่ายใหม่", "📊 ตารางประวัติ สรุปผล & แก้ไข", "💰 คำนวณ & บันทึกการเคลียร์เงิน"])

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
            if not description or amount <= 0 or not split_with:
                st.error("กรุณากรอกข้อมูลและเลือกคนร่วมหารบิลให้ถูกต้อง")
            else:
                blob_data = uploaded_file.read() if uploaded_file is not None else None
                split_members_str = ",".join(split_with)
                
                conn = get_db_connection()
                conn.execute('INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?, ?, ?, ?, ?, ?)',
                             (trip_id, description, amount, payer, split_members_str, blob_data))
                conn.commit()
                conn.close()
                st.success(f"บันทึกประวัติรายการ '{description}' สำเร็จ!")
                st.rerun()

# --- ดึงรายการค่าใช้จ่ายมาใช้งาน ---
conn = get_db_connection()
expenses_rows = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
conn.close()

expenses_list = []
for row in expenses_rows:
    img_data = Image.open(io.BytesIO(row["image_blob"])) if row["image_blob"] else None
    expenses_list.append({"id": row["id"], "รายการ": row["description"], "จำนวนเงิน": row["amount"], "คนจ่าย": row["payer_name"], "คนหาร": row["split_members"].split(",") if row["split_members"] else [], "รูปภาพ": img_data})

# --- TAB 2: ตารางประวัติสรุปและอัปเดตข้อมูลย้อนหลัง ---
with tab2:
    st.header(f"📋 ประวัติค่าใช้จ่ายทั้งหมดใน: {current_trip_name}")
    if not expenses_list:
        st.info("ยังไม่มีข้อมูลค่าใช้จ่ายถูกบันทึกไว้")
    else:
        total_trip_amount = sum([exp["จำนวนเงิน"] for exp in expenses_list])
        st.metric(label="💰 รวมงบประมาณที่ใช้ไปในทริปนี้", value=f"{total_trip_amount:,.2f} บาท")
        st.write("---")
        
        for index, exp in enumerate(expenses_list):
            with st.expander(f"📌 รายการที่ {index+1}: {exp['รายการ']} | 💵 {exp['จำนวนเงิน']:,.2f} บาท (โดย {exp['คนจ่าย']})"):
                col_view, col_edit = st.columns([2, 2])
                with col_view:
                    st.write(f"**📝 ชื่อรายการ:** {exp['รายการ']}")
                    st.write(f"**💵 จำนวนเงิน:** {exp['จำนวนเงิน']:,.2f} บาท")
                    st.write(f"**👤 ผู้สำรองเงิน:** {exp['คนจ่าย']}")
                    st.write(f"**👥 สมาชิกที่ร่วมหารบิล:** {', '.join(exp['คนหาร'])}")
                    if exp["รูปภาพ"] is not None: st.image(exp["รูปภาพ"], width=300)
                        
                with col_edit:
                    st.markdown("#### ✏️ อัปเดตข้อมูล / 🗑️ ลบรายการ")
                    edit_desc = st.text_input("แก้ไขชื่อรายการ:", value=exp['รายการ'], key=f"ed_desc_{exp['id']}")
                    edit_amount = st.number_input("แก้ไขจำนวนเงิน (บาท):", min_value=0.0, value=float(exp['จำนวนเงิน']), format="%.2f", key=f"ed_amount_{exp['id']}")
                    default_payer_idx = members.index(exp['คนจ่าย']) if exp['คนจ่าย'] in members else 0
                    edit_payer = st.selectbox("แก้ไขคนสำรองจ่าย:", members, index=default_payer_idx, key=f"ed_payer_{exp['id']}")
                    
                    edit_split_with = []
                    for member in members:
                        if st.checkbox(member, value=member in exp['คนหาร'], key=f"ed_split_{member}_{exp['id']}"): edit_split_with.append(member)
                    edit_file = st.file_uploader("🔄 เปลี่ยนรูปภาพสลิปใหม่", type=["png", "jpg", "jpeg"], key=f"ed_file_{exp['id']}")
                    
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("💾 บันทึกและอัปเดต", key=f"save_ed_{exp['id']}", type="primary"):
                            conn = get_db_connection()
                            split_str = ",".join(edit_split_with)
                            if edit_file is not None:
                                conn.execute('UPDATE expenses SET description=?, amount=?, payer_name=?, split_members=?, image_blob=? WHERE id=?', (edit_desc, edit_amount, edit_payer, split_str, edit_file.read(), exp['id']))
                            else:
                                conn.execute('UPDATE expenses SET description=?, amount=?, payer_name=?, split_members=? WHERE id=?', (edit_desc, edit_amount, edit_payer, split_str, exp['id']))
                            conn.commit()
                            conn.close()
                            st.success("อัปเดตข้อมูลแล้ว!")
                            st.rerun()
                    with btn_col2:
                        if st.button("🗑️ ลบรายการนี้", key=f"del_ed_{exp['id']}"):
                            conn = get_db_connection()
                            conn.execute("DELETE FROM expenses WHERE id=?", (exp['id'],))
                            conn.commit()
                            conn.close()
                            st.warning("ลบรายการแล้ว")
                            st.rerun()

# --- TAB 3: คำนวณ & บันทึกการเคลียร์เงินลงระบบบันทึกประวัติ ---
with tab3:
    st.header("🤝 คำนวณยอดบิลโอนเงินประจำทริป")
    
    if not expenses_list:
        st.info("กรุณาบันทึกค่าใช้จ่ายในระบบก่อนคำนวณเงิน")
    else:
        # ส่วนที่ 3.1: คำนวณสมดุลเงิน (Net Balance) ปัจจุบัน
        net_balances = {member: 0.0 for member in members}
        for exp in expenses_list:
            payer = exp["คนจ่าย"]
            amount = exp["จำนวนเงิน"]
            split_with = exp["คนหาร"]
            
            if payer in net_balances: net_balances[payer] += amount
            share = amount / len(split_with) if split_with else 0
            for member in split_with:
                if member in net_balances: net_balances[member] -= share
                    
        # คำนวณแผนการโอนเงินสด (Greedy Algorithm)
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

        # แสดงยอดสเตตัสปัจจุบันให้ Leader เห็นก่อน
        col1, col2 = st.columns(2)
        with col1:
            st.write("**🟢 คนที่ต้องได้เงินคืน:**")
            for m, b in net_balances.items():
                if b > 0.01: st.write(f"👤 **{m}** ได้คืน `{b:,.2f}` บาท")
        with col2:
            st.write("**🔴 คนที่ต้องจ่ายเพิ่ม:**")
            for m, b in net_balances.items():
                if b < -0.01: st.write(f"👤 **{m}** ต้องจ่าย `{abs(b):,.2f}` บาท")

        st.write("---")
        st.subheader("💡 ยอดคำนวณการสรุปการโอนเงินรอบนี้")
        for tx in calculated_transactions:
            st.info(f"💳 **{tx['debtor']}** โอนเงินให้ 👉 **{tx['creditor']}** เป็นยอด **`{tx['amount']:,.2f}`** บาท")
            
        # --- ปุ่มสำหรับสั่งเซฟประวัติผลลัพธ์การโอนเงินลงฐานข้อมูล ---
        st.write("---")
        st.subheader("🔒 ส่วนการล็อกผลลัพธ์ลงรายการประวัติทริป")
        st.caption("เมื่อทุกคนจ่ายเงินโอนตามด้านบนครบแล้ว Leader สามารถกดปุ่มด้านล่างเพื่อเซฟยอดธุรกรรมเก็บลงประวัติทริปนี้ถาวรได้ครับ")
        
        if st.button("🎯 บันทึกสรุปยอดเคลียร์เงินบิลลงประวัติทริป", type="primary"):
            if not calculated_transactions:
                st.success("ทริปนี้ยอดเงินลงตัวเรียบร้อยแล้ว ไม่มียอดหนี้ให้บันทึกครับ")
            else:
                conn = get_db_connection()
                # ลบประวัติการเคลียร์เงินเก่าของทริปนี้ออกก่อน (เพื่อป้องกันข้อมูลทับซ้อนหากกดบันทึกซ้ำหลังจากมีการแก้ไขบิล)
                conn.execute("DELETE FROM settlements WHERE trip_id = ?", (trip_id,))
                
                # บันทึกยอดธุรกรรมทั้งหมดลงฐานข้อมูลตาราง Settlements
                for tx in calculated_transactions:
                    conn.execute('''
                        INSERT INTO settlements (trip_id, debtor, creditor, amount)
                        VALUES (?, ?, ?, ?)
                    ''', (trip_id, tx['debtor'], tx['creditor'], tx['amount']))
                conn.commit()
                conn.close()
                st.success("💾 บันทึกสรุปผลลัพธ์ยอดโอนเคลียร์เงิน ลงในรายการประวัติของทริปเรียบร้อยแล้ว!")
                st.rerun()

        # --- ส่วนแสดงตารางประวัติผลลัพธ์การเคลียร์เงินที่บันทึกไว้ ---
        st.write("---")
        st.subheader("📋 รายการบันทึกประวัติการเคลียร์เงินที่บันทึกสำเร็จ (Saved History)")
        
        conn = get_db_connection()
        saved_settlements = conn.execute("SELECT debtor, creditor, amount, timestamp FROM settlements WHERE trip_id = ? ORDER BY timestamp DESC", (trip_id,)).fetchall()
        conn.close()
        
        if not saved_settlements:
            st.caption("🈚 ยังไม่ได้บันทึกปิดยอดสรุปสำหรับทริปนี้ (กดปุ่มด้านบนเมื่อทริปสิ้นสุด)")
        else:
            settle_data = []
            for row in saved_settlements:
                settle_data.append({
                    "ผู้โอนเงิน (Debtor)": row["debtor"],
                    "ผู้รับเงินโอน (Creditor)": row["creditor"],
                    "จำนวนเงินที่โอน (บาท)": f"{row['amount']:,.2f}",
                    "เวลาที่บันทึกสำเร็จ": row["timestamp"]
                })
            st.table(pd.DataFrame(settle_data))
