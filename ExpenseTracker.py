# --- [เพิ่มส่วนนี้] 2.5 ระบบจัดการธีม 7 แบบ ---
THEMES = {
    "🟢 Emerald Explorer": {
        "bg": "#F4F7F5", "sidebar": "#E6EDE8", "text": "#1F2937", 
        "primary": "#10B981", "card": "#FFFFFF", "tab_active": "#10B981"
    },
    "🔵 Ocean Breeze": {
        "bg": "#F0F4F8", "sidebar": "#D9E2EC", "text": "#102A43", 
        "primary": "#0284C7", "card": "#FFFFFF", "tab_active": "#0284C7"
    },
    "🟣 Cyber Punk (Dark)": {
        "bg": "#0F172A", "sidebar": "#1E293B", "text": "#F8FAFC", 
        "primary": "#D946EF", "card": "#1E293B", "tab_active": "#D946EF"
    },
    "🟡 Sunset Glow": {
        "bg": "#FFFBEB", "sidebar": "#FEF3C7", "text": "#451A03", 
        "primary": "#F59E0B", "card": "#FFFFFF", "tab_active": "#F59E0B"
    },
    "🔴 Rose Gold": {
        "bg": "#FAF5F5", "sidebar": "#F3E8E8", "text": "#4C0519", 
        "primary": "#E11D48", "card": "#FFFFFF", "tab_active": "#E11D48"
    },
    "🛞 Stealth Dark": {
        "bg": "#1F2937", "sidebar": "#111827", "text": "#F9FAFB", 
        "primary": "#3B82F6", "card": "#374151", "tab_active": "#3B82F6"
    },
    "💼 Classic Pro": {
        "bg": "#FFFFFF", "sidebar": "#F3F4F6", "text": "#111827", 
        "primary": "#4F46E5", "card": "#F9FAFB", "tab_active": "#4F46E5"
    }
}

# กล่องเลือกธีมใน Sidebar
selected_theme_name = st.sidebar.selectbox("🎨 เปลี่ยนธีมหน้าจอ:", list(THEMES.keys()), index=0)
theme = THEMES[selected_theme_name]

# แทรก CSS เพื่อเปลี่ยนสีพื้นหลังและองค์ประกอบต่างๆ แบบ Dynamic
st.markdown(f"""
    <style>
        /* สีพื้นหลังหลักของแอป */
        .stApp {{
            background-color: {theme['bg']} !important;
            color: {theme['text']} !important;
        }}
        
        /* สีพื้นหลัง Sidebar */
        [data-testid="stSidebar"] {{
            background-color: {theme['sidebar']} !important;
        }}
        
        /* ปรับแต่งปุ่มและองค์ประกอบที่เป็น Primary */
        button[kind="primary"] {{
            background-color: {theme['primary']} !important;
            color: white !important;
            border: none !important;
        }}
        
        /* ตกแต่งกล่องข้อความ/ฟอร์มให้เข้ากับธีม */
        div[data-testid="stForm"] {{
            background-color: {theme['card']} !important;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
        }}
        
        /* เปลี่ยนสีข้อความหัวข้อทั่วไป */
        h1, h2, h3, p, span, label {{
            color: {theme['text']} !important;
        }}
    </style>
""", unsafe_allow_html=True)
# --- [จบส่วนเพิ่มระบบธีม] ---
