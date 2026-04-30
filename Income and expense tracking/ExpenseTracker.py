import streamlit as st
import pandas as pd
import sqlite3
import os
import hashlib
from datetime import datetime

# --- Configuration & Database ---
DB_FILE = 'expense_tracker.db'
BILL_DIR = "bills"

if not os.path.exists(BILL_DIR):
    os.makedirs(BILL_DIR)

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return hashed_text
    return False

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    return conn

def create_tables():
    conn = get_connection()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, password TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  username TEXT, 
                  date TEXT, 
                  type TEXT, 
                  category TEXT, 
                  amount REAL, 
                  bill_path TEXT)''')
    conn.commit()
    conn.close()

create_tables()

# --- Functions ---
def save_bill(uploaded_file, username):
    if uploaded_file is not None:
        file_ext = uploaded_file.name.split('.')[-1]
        filename = f"{username}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{file_ext}"
        file_path = os.path.join(BILL_DIR, filename)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return file_path
    return None

# --- UI Setup ---
st.set_page_config(page_title="Expense Tracker", page_icon="💰", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# --- Authentication Logic ---
def main():
    if not st.session_state.logged_in:
        st.title("🔒 Access Control")
        auth_mode = st.tabs(["Login", "Register"])
        
        with auth_mode[0]:
            user = st.text_input("Username", key="login_user")
            pw = st.text_input("Password", type='password', key="login_pw")
            if st.button("Login"):
                conn = get_connection()
                c = conn.cursor()
                c.execute('SELECT password FROM users WHERE username = ?', (user,))
                result = c.fetchone()
                conn.close()
                if result and check_hashes(pw, result[0]):
                    st.session_state.logged_in = True
                    st.session_state.username = user
                    st.success(f"Welcome back, {user}!")
                    st.rerun()
                else:
                    st.error("Invalid Username or Password")

        with auth_mode[1]:
            new_user = st.text_input("New Username")
            new_pw = st.text_input("New Password", type='password')
            if st.button("Create Account"):
                if new_user and new_pw:
                    conn = get_connection()
                    c = conn.cursor()
                    try:
                        c.execute('INSERT INTO users(username, password) VALUES (?,?)', 
                                  (new_user, make_hashes(new_pw)))
                        conn.commit()
                        st.success("Registration successful! Please login.")
                    except sqlite3.IntegrityError:
                        st.error("Username already exists.")
                    finally:
                        conn.close()
                else:
                    st.warning("Please fill in all fields.")

    else:
        # --- App Interface (Logged In) ---
        st.sidebar.title(f"👤 {st.session_state.username}")
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()

        menu = st.sidebar.radio("Navigation", ["Dashboard", "Add Transaction"])

        if menu == "Add Transaction":
            st.header("📝 New Record")
            with st.form("transaction_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    t_date = st.date_input("Date", datetime.now())
                    t_type = st.selectbox("Type", ["Income", "Expense"])
                with col2:
                    t_cat = st.selectbox("Category", ["Food", "Transport", "Bills", "Salary", "Shopping", "Others"])
                    t_amount = st.number_input("Amount", min_value=0.0, step=0.5)
                
                t_bill = st.file_uploader("Upload Receipt (Optional)", type=['jpg', 'png', 'jpeg'])
                
                if st.form_submit_button("Save Record"):
                    bill_path = save_bill(t_bill, st.session_state.username)
                    conn = get_connection()
                    c = conn.cursor()
                    c.execute('''INSERT INTO transactions(username, date, type, category, amount, bill_path) 
                                 VALUES (?,?,?,?,?,?)''', 
                              (st.session_state.username, t_date.strftime("%Y-%m-%d"), t_type, t_cat, t_amount, bill_path))
                    conn.commit()
                    conn.close()
                    st.success("Saved successfully!")

        elif menu == "Dashboard":
            st.header("📊 Financial Summary")
            conn = get_connection()
            query = 'SELECT * FROM transactions WHERE username = ?'
            df = pd.read_sql_query(query, conn, params=(st.session_state.username,))
            conn.close()

            if not df.empty:
                # Top-level metrics
                income = df[df['type'] == 'Income']['amount'].sum()
                expense = df[df['type'] == 'Expense']['amount'].sum()
                balance = income - expense
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Total Income", f"{income:,.2f}")
                m2.metric("Total Expense", f"{expense:,.2f}")
                m3.metric("Balance", f"{balance:,.2f}")

                # Charts
                st.divider()
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.subheader("Transaction History")
                    st.dataframe(df[['date', 'type', 'category', 'amount']].sort_values('date', ascending=False), use_container_width=True)
                
                with c2:
                    st.subheader("Expense by Category")
                    expense_df = df[df['type'] == 'Expense']
                    if not expense_df.empty:
                        pie_data = expense_df.groupby('category')['amount'].sum()
                        st.pie_chart(pie_data)
                    else:
                        st.info("No expense data for chart")

                # Receipt viewer
                st.divider()
                st.subheader("🔍 View Receipt")
                receipt_list = df[df['bill_path'].notnull()]
                if not receipt_list.empty:
                    selected_id = st.selectbox("Select Transaction ID", receipt_list['id'])
                    path = receipt_list[receipt_list['id'] == selected_id]['bill_path'].values[0]
                    if os.path.exists(path):
                        st.image(path, width=400)
                else:
                    st.info("No receipts uploaded yet.")
            else:
                st.info("No data available yet. Start by adding a transaction!")

if __name__ == '__main__':
    main()
