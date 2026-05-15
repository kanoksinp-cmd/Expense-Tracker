import streamlit as st
import pandas as pd
from PIL import Image

# ตั้งค่าหน้าเว็บ
st.set_page_config(page_title="Trip Expense Splitter Pro", layout="wide")

# ประกาศตัวแปรเก็บข้อมูลใน Session State
if "trips" not in st.session_state:
    st.session_state.trips = {}

st.title("✈️ ระบบจัดการและหารค่าใช้จ่ายสำหรับทริป (Pro Version)")
st.caption("จัดการรายรับ-รายจ่าย แก้ไข ลบรายการ และแนบรูปภาพหลักฐานสลิป")

# --- ส่วนที่ 1: การจัดการทริปและสมาชิก (โดย Leader) ---
st.sidebar.header("🛠️ ส่วนควบคุมของ Leader")

# 1.1 สร้างทริปใหม่
new_trip = st.sidebar.text_input("➕ สร้างทริปใหม่:").strip()
if st.sidebar.button("บันทึกทริป"):
    if new_trip and new_trip not in st.session_state.trips:
        st.session_state.trips[new_trip] = {"members": [], "expenses": []}
        st.sidebar.success(f"สร้างทริป '{new_trip}' สำเร็จ!")
    elif new_trip in st.session_state.trips:
        st.sidebar.warning("มีชื่อทริปนี้อยู่แล้ว")

if not st.session_state.trips:
    st.info("👋 ยินดีต้อนรับ! กรุณาสร้างทริปแรกที่แถบเครื่องมือด้านซ้ายก่อนครับ")
    st.stop()

# 1.2 เลือกทริปที่จะจัดการ
current_trip = st.sidebar.selectbox("🗺️ เลือกทริปที่ต้องการจัดการ:", list(st.session_state.trips.keys()))

# 1.3 เพิ่มสมาชิกในทริป
st.sidebar.subheader(f"👥 สมาชิกใน {current_trip}")
new_member = st.sidebar.text_input("➕ เพิ่มชื่อผู้ร่วมทริป:").strip()
if st.sidebar.button("เพิ่มสมาชิก"):
    if new_member and new_member not in st.session_state.trips[current_trip]["members"]:
        st.session_state.trips[current_trip]["members"].append(new_member)
        st.sidebar.success(f"เพิ่มคุณ {new_member} เข้าทริปแล้ว")
    elif new_member in st.session_state.trips[current_trip]["members"]:
        st.sidebar.warning("มีชื่อสมาชิกคนนี้อยู่แล้ว")

members = st.session_state.trips[current_trip]["members"]
if members:
    st.sidebar.write(f"**รายชื่อสมาชิก:** " + ", ".join(members))
else:
    st.sidebar.info("ยังไม่มีสมาชิกในทริปนี้")


# --- ตรวจสอบสถานะสมาชิกก่อนไปต่อ ---
if not members:
    st.warning("⚠️ กรุณาเพิ่มสมาชิกอย่างน้อย 1 คนก่อนเริ่มใช้งานระบบ")
    st.stop()

tab1, tab2, tab3 = st.tabs(["📝 บันทึกค่าใช้จ่าย", "📊 ตารางสรุป & แก้ไข/ลบ", "💰 วิธีเคลียร์เงิน (Settlement)"])

# --- TAB 1: บันทึกค่าใช้จ่ายใหม่ ---
with tab1:
    st.header(f"➕ เพิ่มรายการค่าใช้จ่าย: {current_trip}")
    
    with st.form("expense_form", clear_on_submit=True):
        description = st.text_input("รายการค่าใช้จ่าย (เช่น ค่าอาหาร, ค่าน้ำมัน):")
        amount = st.number_input("จำนวนเงิน (บาท):", min_value=0.0, step=100.0, format="%.2f")
        payer = st.selectbox("ใครเป็นคนสำรองจ่ายเงิน?", members, key="add_payer")
        
        st.write("**ใครต้องหารรายการนี้บ้าง?**")
        split_with = []
        for member in members:
            if st.checkbox(member, value=True, key=f"add_split_{member}"):
                split_with.append(member)
        
        uploaded_file = st.file_uploader("📸 แนบรูปภาพ/ใบเสร็จ/สลิป (ถ้ามี)", type=["png", "jpg", "jpeg"], key="add_file")
        
        submit_btn = st.form_submit_button("💾 บันทึกรายการ")
        
        if submit_btn:
            if not description:
                st.error("กรุณากรอกรายการค่าใช้จ่าย")
            elif amount <= 0:
                st.error("จำนวนเงินต้องมากกว่า 0 บาท")
            elif not split_with:
                st.error("ต้องมีผู้ร่วมหารอย่างน้อย 1 คน")
            else:
                # จัดการแปลงไฟล์รูปภาพ
                img_data = None
                if uploaded_file is not None:
                    img_data = Image.open(uploaded_file)
                
                # บันทึกข้อมูล
                expense_data = {
                    "รายการ": description,
                    "จำนวนเงิน": amount,
                    "คนจ่าย": payer,
                    "คนหาร": split_with,
                    "รูปภาพ": img_data
                }
                st.session_state.trips[current_trip]["expenses"].append(expense_data)
                st.success(f"บันทึกรายการ '{description}' เรียบร้อย!")
                st.rerun()

# --- TAB 2: ตารางสรุปและจัดการการแก้ไข/ลบ ---
with tab2:
    st.header(f"📊 ตารางสรุปและจัดการข้อมูล: {current_trip}")
    expenses = st.session_state.trips[current_trip]["expenses"]
    
    if not expenses:
        st.info("ยังไม่มีการบันทึกค่าใช้จ่ายในทริปนี้")
    else:
        # สรุปยอดเงินรวมของทริปไว้ด้านบนเพื่อความชัดเจน
        total_trip_amount = sum([exp["จำนวนเงิน"] for exp in expenses])
        st.metric(label="💰 รวมค่าใช้จ่ายทั้งหมดของทริปนี้", value=f"{total_trip_amount:,.2f} บาท")
        st.write("---")
        
        # วนลูปแสดงผลรายการทีละแถวในรูปแบบตารางที่สามารถจัดการได้ (Interactive List)
        for index, exp in enumerate(expenses):
            # ใช้ st.expander เพื่อความสะอาดของหน้าจอ และกดกางออกมาดูรูปหรือแก้ไขได้
            with st.expander(f"📍 รายการที่ {index+1}: {exp['รายการ']} | 💰 {exp['จำนวนเงิน']:,.2f} บาท (โดย {exp['คนจ่าย']})"):
                col_view, col_edit = st.columns([2, 2])
                
                # ฝั่งซ้าย: แสดงรายละเอียดปัจจุบันและรูปภาพ
                with col_view:
                    st.write(f"**📝 รายการ:** {exp['รายการ']}")
                    st.write(f"**💵 จำนวนเงิน:** {exp['จำนวนเงิน']:,.2f} บาท")
                    st.write(f"**👤 ผู้สำรองจ่าย:** {exp['คนจ่าย']}")
                    st.write(f"**👥 ผู้ร่วมหาร:** {', '.join(exp['คนหาร'])}")
                    
                    if exp["รูปภาพ"] is not None:
                        st.image(exp["รูปภาพ"], caption=f"หลักฐานของ: {exp['รายการ']}", width=300)
                    else:
                        st.caption("🈚 ไม่มีรูปภาพแนบในรายการนี้")
                
                # ฝั่งขวา: ฟอร์มสำหรับ แก้ไข หรือ ลบ รายการนี้
                with col_edit:
                    st.markdown("### ✏️ แก้ไขข้อมูล / 🗑️ ลบรายการ")
                    
                    edit_desc = st.text_input("แก้ไขชื่อรายการ:", value=exp['รายการ'], key=f"edit_desc_{index}")
                    edit_amount = st.number_input("แก้ไขจำนวนเงิน (บาท):", min_value=0.0, value=float(exp['จำนวนเงิน']), format="%.2f", key=f"edit_amount_{index}")
                    
                    # ค้นหาตำแหน่ง Index เดิมของคนจ่ายเพื่อแสดงเป็น Default
                    default_payer_idx = members.index(exp['คนจ่าย']) if exp['คนจ่าย'] in members else 0
                    edit_payer = st.selectbox("แก้ไขคนสำรองจ่าย:", members, index=default_payer_idx, key=f"edit_payer_{index}")
                    
                    st.write("แก้ไขคนร่วมหาร:")
                    edit_split_with = []
                    for member in members:
                        # เช็คว่าเดิมทีคนนี้ร่วมหารไหม
                        is_checked = member in exp['คนหาร']
                        if st.checkbox(member, value=is_checked, key=f"edit_split_{member}_{index}"):
                            edit_split_with.append(member)
                    
                    edit_file = st.file_uploader("🔄 เปลี่ยนรูปภาพหลักฐาน", type=["png", "jpg", "jpeg"], key=f"edit_file_{index}")
                    
                    # ปุ่มดำเนินการ
                    btn_col1, btn_col2 = st.columns(2)
                    
                    with btn_col1:
                        if st.button("💾 บันทึกการแก้ไข", key=f"save_btn_{index}", type="primary"):
                            if not edit_desc:
                                st.error("กรุณากรอกชื่อรายการ")
                            elif edit_amount <= 0:
                                st.error("จำนวนเงินต้องมากกว่า 0")
                            elif not edit_split_with:
                                st.error("ต้องมีคนร่วมหารอย่างน้อย 1 คน")
                            else:
                                # อัปเดตข้อมูลในสเตต
                                expenses[index]["รายการ"] = edit_desc
                                expenses[index]["จำนวนเงิน"] = edit_amount
                                expenses[index]["คนจ่าย"] = edit_payer
                                expenses[index]["คนหาร"] = edit_split_with
                                if edit_file is not None:
                                    expenses[index]["รูปภาพ"] = Image.open(edit_file)
                                
                                st.success("อัปเดตข้อมูลเรียบร้อย!")
                                st.rerun()
                                
                    with btn_col2:
                        if st.button("🗑️ ลบรายการนี้", key=f"del_btn_{index}"):
                            # ลบรายการออกจาก List
                            st.session_state.trips[current_trip]["expenses"].pop(index)
                            st.warning("ลบรายการสำเร็จ!")
                            st.rerun()

# --- TAB 3: สรุปวิธีเคลียร์เงิน (Settlement) ---
with tab3:
    st.header("🤝 สรุปขั้นตอนการโอนเงินคืน")
    expenses = st.session_state.trips[current_trip]["expenses"]
    
    if not expenses:
        st.info("บันทึกค่าใช้จ่ายก่อน ระบบจึงจะคำนวณการเคลียร์เงินให้")
    else:
        # ส่วนคำนวณ Net Balance
        net_balances = {member: 0.0 for member in members}
        
        for exp in expenses:
            payer = exp["คนจ่าย"]
            amount = exp["จำนวนเงิน"]
            split_with = exp["คนหาร"]
            
            net_balances[payer] += amount
            share = amount / len(split_with) if split_with else 0
            for member in split_with:
                net_balances[member] -= share
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("**🟢 คนที่ต้องได้เงินคืน:**")
            for member, bal in net_balances.items():
                if bal > 0.01:
                    st.write(f"👤 **{member}** ได้รับคืน: `{bal:,.2f}` บาท")
        
        with col2:
            st.write("**🔴 คนที่ต้องจ่ายเพิ่ม:**")
            for member, bal in net_balances.items():
                if bal < -0.01:
                    st.write(f"👤 **{member}** ต้องจ่ายเพิ่ม: `{abs(bal):,.2f}` บาท")
        
        st.write("---")
        st.subheader("🚀 วิธีโอนเงินเพื่อให้เคลียร์จบเร็วที่สุด")
        
        debtors = [[m, bal] for m, bal in net_balances.items() if bal < -0.01]
        creditors = [[m, bal] for m, bal in net_balances.items() if bal > 0.01]
        
        transactions = []
        while debtors and creditors:
            debtor_name, debtor_bal = debtors[0]
            creditor_name, creditor_bal = creditors[0]
            
            amount_to_pay = min(abs(debtor_bal), creditor_bal)
            transactions.append(f"💳 **{debtor_name}** โอนเงินให้ 👉 **{creditor_name}** เป็นจำนวนยอด **`{amount_to_pay:,.2f}`** บาท")
            
            debtors[0][1] += amount_to_pay
            creditors[0][1] -= amount_to_pay
            
            if abs(debtors[0][1]) < 0.01: debtors.pop(0)
            if abs(creditors[0][1]) < 0.01: creditors.pop(0)
                
        if transactions:
            for tx in transactions:
                st.info(tx)
        else:
            st.success("🎉 ยอดเงินลงตัวทั้งหมดแล้ว ไม่มีใครค้างใครค๊าบ!")
