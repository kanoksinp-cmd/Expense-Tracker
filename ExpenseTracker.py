import streamlit as st
import pandas as pd
import sqlite3
import os
import hashlib
from datetime import datetime, timedelta

# --- การตั้งค่าพื้นฐาน ---
DB_FILE = 'expense_tracker.db'
BILL_DIR = "bills"
PROFILE_DIR = "profiles"

if not os.path.exists(BILL_DIR):
    os.makedirs(BILL_DIR)
if not os.path.exists(PROFILE_DIR):
    os.makedirs(PROFILE_DIR)

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return hashed_text
    return False

def get_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def create_tables():
    conn = get_connection()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, password TEXT, profile_pic TEXT, last_active TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS trips(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, budget REAL DEFAULT 0.0, description TEXT, created_by TEXT, created_at TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, category TEXT, amount REAL, 
                  note TEXT, bill_path TEXT, created_by TEXT, updated_by TEXT, trip_id INTEGER)''')
    
    # Migration
    try:
        c.execute('SELECT profile_pic FROM users LIMIT 1')
    except sqlite3.OperationalError:
        c.execute('ALTER TABLE users ADD COLUMN profile_pic TEXT')
        c.execute('ALTER TABLE users ADD COLUMN last_active TEXT')

    for col, c_type in [('note', 'TEXT'), ('created_by', 'TEXT DEFAULT "System"'), ('updated_by', 'TEXT DEFAULT "System"'), ('trip_id', 'INTEGER DEFAULT NULL')]:
        try:
            c.execute(f'SELECT {col} FROM transactions LIMIT 1')
        except sqlite3.OperationalError:
            c.execute(f'ALTER TABLE transactions ADD COLUMN {col} {c_type}')
    conn.commit()
    conn.close()

create_tables()

def save_bill(uploaded_file, username):
    if uploaded_file:
        file_ext = uploaded_file.name.split('.')[-1]
        filename = f"{username}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{file_ext}"
        file_path = os.path.join(BILL_DIR, filename)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return file_path
    return None

def save_profile_pic(uploaded_file, username):
    if uploaded_file:
        file_ext = uploaded_file.name.split('.')[-1]
        file_path = os.path.join(PROFILE_DIR, f"profile_{username}.{file_ext}")
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        conn = get_connection()
        conn.cursor().execute('UPDATE users SET profile_pic=? WHERE username=?', (file_path, username))
        conn.commit()
        conn.close()
        return file_path
    return None

def update_user_active(username):
    conn = get_connection()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.cursor().execute('UPDATE users SET last_active=? WHERE username=?', (now_str, username))
    conn.commit()
    conn.close()

def get_user_status(last_active_str):
    if not last_active_str: return "⚫ ออฟไลน์"
    try:
        last_active = datetime.strptime(last_active_str, "%Y-%m-%d %H:%M:%S")
        return "🟢 ออนไลน์" if datetime.now() - last_active < timedelta(minutes=3) else "⚫ ออฟไลน์"
    except: return "⚫ ออฟไลน์"

def delete_transaction(t_id):
    conn = get_connection()
    conn.cursor().execute('DELETE FROM transactions WHERE id=?', (t_id,))
    conn.commit()
    conn.close()

st.set_page_config(page_title="Group Expense Tracker", page_icon="💰", layout="wide")
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'editing_id' not in st.session_state: st.session_state.editing_id = None
if 'view_bill_id' not in st.session_state: st.session_state.view_bill_id = None

def main():
    if not st.session_state.logged_in:
        st.title("🔒 Group Login")
        auth_mode = st.tabs(["เข้าสู่ระบบ", "สมัครสมาชิก"])
        with auth_mode[0]:
            user = st.text_input("Username")
            pw = st.text_input("Password", type='password')
            if st.button("Login"):
                conn = get_connection()
                res = conn.cursor().execute('SELECT password FROM users WHERE username = ?', (user,)).fetchone()
                if res and
