import streamlit as st
import pandas as pd

# ตั้งค่าหน้าเว็บ
st.set_page_config(page_title="Trip Expense Splitter", layout="wide")

# ประกาศตัวแปรจำลองฐานข้อมูลใน Session State (ข้อมูลจะอยู่จนกว่าจะปิดแอป)
if "trips" not in st.session_state:
    st.session_state.trips = {}

st.title("✈️ ระบบจัดการและหารค่าใช้จ่ายสำหรับทริป (Trip Expense Manager)")
st.caption("ควบคุมและจัดการโดย Leader ประจำทริป")

# --- ส่วนที่ 1: การจัดการทริปและสมาชิก (โดย User/Admin) ---
st.sidebar.header("🛠️ ส่วนควบคุมของ Leader")

# 1.1 สร้างทริปใหม่
new_trip = st.sidebar.text_input("➕ สร้างทริปใหม่ (เช่น ทริปญี่ปุ่น 2026):").strip()
if st.sidebar.button("บันทึกทริป"):
    if new_trip and new_trip not in st.session_state.trips:
        st.session_state.trips[new_trip] = {"members": [], "expenses": []}
        st.sidebar.success(f"สร้างทริป '{new_trip}' สำเร็จ!")
    elif new_trip in st.session_state.trips:
        st.sidebar.warning("มีชื่อทริปนี้อยู่แล้ว")

# ตรวจสอบว่ามีทริปในระบบหรือยัง
if not st.session_state.trips:
    st.info("👋 ยินดีต้อนรับ! กรุณาสร้างทริปแรกที่แถบเครื่องมือด้านซ้ายก่อนครับ")
    st.stop()

# 1.2 เลือกทริปที่จะจัดการ
current_trip = st.sidebar.selectbox("🗺️ เลือกทริปที่ต้องการจัดการ:", list(st.session_state.trips.keys()))

# 1.3 เพิ่มสมาชิกในทริปที่เลือก
st.sidebar.subheader(f"👥 สมาชิกใน {current_trip}")
new_member = st.sidebar.text_input("➕ เพิ่มชื่อผู้ร่วมทริป:").strip()
if st.sidebar.button("เพิ่มสมาชิก"):
    if new_member and new_member not in st.session_state.trips[current_trip]["members"]:
        st.session_state.trips[current_trip]["members"].append(new_member)
        st.sidebar.success(f"เพิ่มคุณ {new_member} เข้าทริปแล้ว")
    elif new_member in st.session_state.trips[current_trip]["members"]:
        st.sidebar.warning("มีชื่อสมาชิกคนนี้อยู่แล้ว")

# แสดงรายชื่อสมาชิกปัจจุบัน
members = st.session_state.trips[current_trip]["members"]
if members:
    st.sidebar.write(f"**รายชื่อสมาชิก ({len(members)} คน):** " + ", ".join(members))
else:
    st.sidebar.info("ยังไม่มีสมาชิกในทริปนี้ กรุณาเพิ่มรายชื่อ")


# --- ส่วนที่ 2: หน้าหลักการบันทึกค่าใช้จ่าย ---
if not members:
    st.warning("⚠️ กรุณาเพิ่มสมาชิกอย่างน้อย 1 คนก่อนเริ่มบันทึกค่าใช้จ่าย")
    st.stop()

tab1, tab2, tab3 = st.tabs(["📝 บันทึกค่าใช้จ่าย", "📊 ประวัติและสรุป", "💰 วิธีเคลียร์เงิน (Settlement)"])

with tab1:
    st.header(f"➕ บันทึกรายจ่ายประจำทริป: {current_trip}")
    
    with st.form("expense_form", clear_on_submit=True):
        description = st.text_input("รายการค่าใช้จ่าย (เช่น ค่าที่พัก, ค่าน้ำมัน, ค่าอาหารมื้อแรก):")
        amount = st.number_input("จำนวนเงิน (บาท):", min_value=0.0, step=100.0, format="%.2f")
        payer = st.selectbox("ใครเป็นคนสำรองจ่ายเงิน?", members)
        
        st.write("**ใครต้องหารรายการนี้บ้าง?** (เลือกทั้งหมด หรือเลือกเฉพาะบางคน)")
        # สร้าง Checkbox ให้เลือกว่าใครร่วมหารบ้าง
        split_with = []
        for member in members:
            if st.checkbox(member, value=True, key=f"split_{member}"):
                split_with.append(member)
                
        submit_btn = st.form_submit_button("💾 บันทึกรายการ")
        
        if submit_btn:
            if not description:
                st.error("กรุณากรอกรายการค่าใช้จ่าย")
            elif amount <= 0:
                st.error("จำนวนเงินต้องมากกว่า 0 บาท")
            elif not split_with:
                st.error("ต้องมีผู้ร่วมหารอย่างน้อย 1 คน")
            else:
                # บันทึกข้อมูลลงสถานะทริป
                expense_data = {
                    "รายการ": description,
                    "จำนวนเงิน": amount,
                    "คนจ่าย": payer,
                    "คนหาร": split_with
                }
                st.session_state.trips[current_trip]["expenses"].append(expense_data)
                st.success(f"บันทึกรายการ '{description}' เรียบร้อย!")

with tab2:
    st.header(f"📊 ตารางสรุปของทริป: {current_trip}")
    expenses = st.session_state.trips[current_trip]["expenses"]
    
    if not expenses:
        st.info("ยังไม่มีการบันทึกค่าใช้จ่ายในทริปนี้")
    else:
        # แปลงข้อมูลเป็น DataFrame เพื่อแสดงผลให้สวยงาม
        df_display = []
        for exp in expenses:
            df_display.append({
                "รายการ": exp["รายการ"],
                "จำนวนเงิน (บาท)": exp["จำนวนเงิน"],
                "ผู้สำรองจ่าย": exp["คนจ่าย"],
                "ผู้ร่วมหาร": ", ".join(exp["คนหาร"])
            })
        st.dataframe(pd.DataFrame(df_display), use_container_width=True)
        
        total_trip_amount = sum([exp["จำนวนเงิน"] for exp in expenses])
        st.metric(label="💰 รวมค่าใช้จ่ายทั้งหมดของทริปนี้", value=f"{total_trip_amount:,.2f} บาท")

with tab3:
    st.header("🤝 สรุปยอดเคลียร์เงินบิล")
    expenses = st.session_state.trips[current_trip]["expenses"]
    
    if not expenses:
        st.info("บันทึกค่าใช้จ่ายก่อน ระบบจึงจะคำนวณการเคลียร์เงินให้")
    else:
        # คำนวณยอดสุทธิสุทธิของแต่ละคน (Net Balance)
        # Net balance = (เงินที่จ่ายไปทั้งหมด) - (เงินที่ตัวเองต้องช่วยหารทั้งหมด)
        net_balances = {member: 0.0 for member in members}
        
        for exp in expenses:
            payer = exp["คนจ่าย"]
            amount = exp["จำนวนเงิน"]
            split_with = exp["คนหาร"]
            
            # คนจ่ายได้เงินคืนตามจำนวนเต็มก่อน
            net_balances[payer] += amount
            
            # หารเฉลี่ยตามจำนวนคนที่มีส่วนร่วมในบิลนั้นๆ
            share = amount / len(split_with)
            for member in split_with:
                net_balances[member] -= share
        
        # แสดงสถานะยอดเงินของแต่ละคน
        st.subheader("💵 สถานะกระเป๋าเงินของแต่ละคน")
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**คนที่ต้องได้เงินคืน (จ่ายเกินส่วนตัวเอง):**")
            for member, bal in net_balances.items():
                if bal > 0.01: # เลี่ยงปัญหานิยมปัดเศษคอมพิวเตอร์
                    st.write(f"🟢 **{member}** ได้รับคืน: `{bal:,.2f}` บาท")
        
        with col2:
            st.write("**คนที่ต้องจ่ายเพิ่ม (ใช้เงินไปมากกว่าที่ออก):**")
            for member, bal in net_balances.items():
                if bal < -0.01:
                    st.write(f"🔴 **{member}** ต้องจ่ายเพิ่ม: `{abs(bal):,.2f}` บาท")
        
        st.write("---")
        st.subheader("🚀 สรุปขั้นตอนการโอนเงิน (โอนแบบจ่ายน้อยที่สุด)")
        
        # Algorithm คำนวณการเคลียร์หนี้แบบจับคู่ (Greedy Debt Settler)
        debtors = [[m, bal] for m, bal in net_balances.items() if bal < -0.01]
        creditors = [[m, bal] for m, bal in net_balances.items() if bal > 0.01]
        
        transactions = []
        
        while debtors and creditors:
            # ดึงคนที่ติดหนี้มากที่สุด และคนที่จะได้เงินคืนมากที่สุด
            debtor_name, debtor_bal = debtors[0]
            creditor_name, creditor_bal = creditors[0]
            
            # จำนวนเงินที่จะโอนในรอบนี้
            amount_to_pay = min(abs(debtor_bal), creditor_bal)
            
            transactions.append(f"👤 **{debtor_name}** โอนเงินให้ **{creditor_name}** เป็นจำนวน 👉 `{amount_to_pay:,.2f}` บาท")
            
            # อัปเดตยอดคงเหลือ
            debtors[0][1] += amount_to_pay
            creditors[0][1] -= amount_to_pay
            
            # ถ้าใครเคลียร์ยอดหมดแล้ว ให้เอาออกจากลิสต์
            if abs(debtors[0][1]) < 0.01:
                debtors.pop(0)
            if abs(creditors[0][1]) < 0.01:
                creditors.pop(0)
                
        if transactions:
            for tx in transactions:
                st.write(tx)
        else:
            st.success("🎉 ทุกคนลงตัวกันหมดแล้ว ไม่ต้องโอนเงินเพิ่ม!")
