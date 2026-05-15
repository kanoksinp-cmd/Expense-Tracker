import streamlit as st
import pandas as pd
import sqlite3
import os
import hashlib
from datetime import datetime, timedelta
import plotly.express as px

# --- 1. ตั้งค่าฐานข้อมูล ---
DB_FILE = 'expense_tracker.db'
def get_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, profile_pic TEXT, last_active TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, budget REAL, created_by TEXT, created_at TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS trip_members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, username TEXT, status TEXT DEFAULT "accepted")')
        c.execute('CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, category TEXT, amount REAL, note TEXT, bill_path TEXT, created_by TEXT, trip_id INTEGER)')
        c.execute('CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, receiver TEXT, message TEXT, is_read INTEGER DEFAULT 0, created_at TEXT)')
        conn.commit()

init_db()

# --- 2. ฟังก์ชัน Callback สำหรับปุ่ม (ตัวแก้ปัญหาหลัก) ---
def accept_trip_callback(row_id, trip_name, creator, username):
    with get_connection() as conn:
        c = conn.cursor()
        # อัปเดตสถานะในตารางสมาชิกให้เป็นคนในทริปเต็มตัว
        c.execute('UPDATE trip_members SET status="accepted" WHERE id=?', (row_id,))
        # ส่งแจ้งเตือนบอกเจ้าของทริป
        now = datetime.now().strftime("%H:%M")
        c.execute('INSERT INTO notifications(receiver, message, created_at) VALUES (?,?,?)', 
                  (creator, f"🤝 {username} ตอบรับเข้าร่วมทริป '{trip_name}' แล้ว!", now))
        conn.commit()
    st.session_state.menu_selection = "🧳 ทริปของฉัน"
    st.session_state.current_trip_name = trip_name
    st.toast(f"เข้าร่วมทริป {trip_name} สำเร็จ!", icon="✅")

def reject_trip_callback(row_id, trip_name, creator, username):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('DELETE FROM trip_members WHERE id=?', (row_id,))
        now = datetime.now().strftime("%H:%M")
        c.execute('INSERT INTO notifications(receiver, message, created_at) VALUES (?,?,?)', 
                  (creator, f"👎 {username} ปฏิเสธทริป '{trip_name}'", now))
        conn.commit()
    st.toast("ปฏิเสธคำเชิญแล้ว")

# --- 3. UI หน้าหลัก (โฟกัสจุดที่ปุ่มหาย) ---
if 'username' not in st.session_state: st.session_state.username = None

if st.session_state.username:
    user_now = st.session_state.username
    
    # ดึงข้อมูลคำเชิญที่ "ยังไม่ได้กดรับ" (Pending)
    with get_connection() as conn:
        pending_trips = pd.read_sql_query('''
            SELECT tm.id as member_row_id, t.name, t.created_by, t.budget 
            FROM trip_members tm
            JOIN trips t ON tm.trip_id = t.id
            WHERE tm.username = ? AND tm.status = 'pending'
        ''', conn, params=(user_now,))
        
        # ดึงประวัติแจ้งเตือนทั่วไป
        notis = pd.read_sql_query('SELECT * FROM notifications WHERE receiver=? ORDER BY id DESC LIMIT 10', conn, params=(user_now,))

    # Sidebar เมนู
    menu_list = ["🔔 แจ้งเตือน", "🧳 ทริปของฉัน", "➕ สร้างทริปใหม่"]
    if 'menu_selection' not in st.session_state: st.session_state.menu_selection = "🔔 แจ้งเตือน"
    
    menu = st.sidebar.radio("เมนู", menu_list, index=menu_list.index(st.session_state.menu_selection))
    st.session_state.menu_selection = menu

    if "🔔" in menu:
        st.header("🔔 การแจ้งเตือนและคำเชิญทริป")

        # --- ส่วนที่ 1: ปุ่มกดรับ (ต้องมีข้อมูลใน trip_members และ status='pending' ถึงจะขึ้น) ---
        if not pending_trips.empty:
            st.subheader("✉️ คำเชิญใหม่ (กรุณากดเพื่อเข้าร่วม)")
            for _, p in pending_trips.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([5, 2, 1.5])
                    c1.markdown(f"**{p['created_by']}** เชิญคุณเข้าทริป **'{p['name']}'**")
                    c2.button("✅ ตอบรับ", key=f"acc_{p['member_row_id']}", on_click=accept_trip_callback, args=(p['member_row_id'], p['name'], p['created_by'], user_now), use_container_width=True)
                    c3.button("❌ ไม่ไป", key=f"rej_{p['member_row_id']}", on_click=reject_trip_callback, args=(p['member_row_id'], p['name'], p['created_by'], user_now), use_container_width=True)
            st.divider()
        else:
            # หากไม่มีปุ่มขึ้น ให้แสดงคำแนะนำ
            st.info("💡 ไม่มีคำเชิญใหม่ที่รอการตอบรับ (หากเพื่อนเพิ่งเชิญ ให้ลองรีเฟรชหน้าจอ)")

        # --- ส่วนที่ 2: ประวัติ (ที่เห็นในรูปของคุณ) ---
        st.subheader("💬 ประวัติการแจ้งเตือนล่าสุด")
        if notis.empty:
            st.write("ไม่มีประวัติ")
        else:
            for _, n in notis.iterrows():
                st.write(f"[{n['created_at']}] {n['message']}")
            if st.button("ล้างแจ้งเตือนทั้งหมด"):
                with get_connection() as conn:
                    conn.cursor().execute('UPDATE notifications SET is_read=1 WHERE receiver=?', (user_now,))
                    conn.commit()
                st.rerun()

# (หมายเหตุ: โค้ดส่วนอื่นๆ เช่น หน้าจัดการทริป ให้ใช้ตามเวอร์ชันก่อนหน้าได้เลยครับ)
