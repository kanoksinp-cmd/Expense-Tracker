import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import sqlite3
import os
import hashlib
from datetime import datetime, timedelta
import plotly.express as px

# =========================
# 1. ตั้งค่าฐานข้อมูล
# =========================

DB_FILE = 'expense_tracker.db'
BILL_DIR = "bills"
PROFILE_DIR = "profiles"

for folder in [BILL_DIR, PROFILE_DIR]:
    if not os.path.exists(folder):
        os.makedirs(folder)

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    with get_connection() as conn:
        c = conn.cursor()

        c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT,
            profile_pic TEXT,
            last_active TEXT
        )
        ''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            budget REAL,
            created_by TEXT,
            created_at TEXT
        )
        ''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS trip_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER,
            username TEXT
        )
        ''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            type TEXT,
            category TEXT,
            amount REAL,
            note TEXT,
            bill_path TEXT,
            created_by TEXT,
            trip_id INTEGER
        )
        ''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            receiver TEXT,
            message TEXT,
            is_read INTEGER DEFAULT 0,
            created_at TEXT
        )
        ''')

        # Auto Migration
        cols = [
            ('users', 'last_active', 'TEXT'),
            ('transactions', 'created_by', 'TEXT'),
            ('transactions', 'bill_path', 'TEXT')
        ]

        for table, col, col_type in cols:
            try:
                c.execute(f'SELECT {col} FROM {table} LIMIT 1')
            except sqlite3.OperationalError:
                c.execute(f'ALTER TABLE {table} ADD COLUMN {col} {col_type}')

        conn.commit()

init_db()

# =========================
# 2. ฟังก์ชันช่วย
# =========================

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def update_online_status(username):
    if username:
        with get_connection() as conn:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.cursor().execute(
                'UPDATE users SET last_active=? WHERE username=?',
                (now, username)
            )
            conn.commit()

def get_status_icon(last_active_str):
    if not last_active_str:
        return "⚪ ออฟไลน์"

    try:
        last_dt = datetime.strptime(
            last_active_str,
            "%Y-%m-%d %H:%M:%S"
        )

        if datetime.now() - last_dt < timedelta(minutes=5):
            return "🟢 ออนไลน์"

    except:
        pass

    return "⚪ ออฟไลน์"

def send_notification(receiver, msg, conn=None):
    local_conn = conn if conn else get_connection()

    now = datetime.now().strftime("%H:%M")

    local_conn.cursor().execute(
        '''
        INSERT INTO notifications(receiver, message, created_at)
        VALUES (?,?,?)
        ''',
        (receiver, msg, now)
    )

    if not conn:
        local_conn.commit()
        local_conn.close()

# =========================
# 3. Streamlit Config
# =========================

st.set_page_config(
    page_title="Trip Expense Master",
    layout="wide"
)

# Auto Refresh ทุก 5 วินาที
st_autorefresh(interval=5000, key="refresh")

# =========================
# 4. Session State
# =========================

if 'username' not in st.session_state:
    st.session_state.username = None

if 'editing_tx_id' not in st.session_state:
    st.session_state.editing_tx_id = None

if 'current_trip_name' not in st.session_state:
    st.session_state.current_trip_name = None

# =========================
# 5. Login / Register
# =========================

if not st.session_state.username:

    st.title("💰 Trip Expense Tracker")

    tab_l, tab_r = st.tabs(["เข้าสู่ระบบ", "สมัครสมาชิก"])

    # Login
    with tab_l:

        u = st.text_input("Username", key="login_u")
        p = st.text_input("Password", type='password', key="login_p")

        if st.button("Login", use_container_width=True):

            with get_connection() as conn:
                res = conn.cursor().execute(
                    '''
                    SELECT password
                    FROM users
                    WHERE username=?
                    ''',
                    (u,)
                ).fetchone()

            if res and res[0] == make_hashes(p):

                st.session_state.username = u

                update_online_status(u)

                st.success("เข้าสู่ระบบสำเร็จ")

                st.rerun()

            else:
                st.error("ชื่อหรือรหัสผ่านไม่ถูกต้อง")

    # Register
    with tab_r:

        su = st.text_input("ชื่อผู้ใช้", key="reg_u")
        sp = st.text_input("รหัสผ่าน", type='password', key="reg_p")

        if st.button("Register", use_container_width=True):

            with get_connection() as conn:

                try:
                    conn.cursor().execute(
                        '''
                        INSERT INTO users(username, password)
                        VALUES (?,?)
                        ''',
                        (su, make_hashes(sp))
                    )

                    conn.commit()

                    st.success("สมัครสำเร็จ!")

                except:
                    st.error("ชื่อนี้มีผู้ใช้งานแล้ว")

# =========================
# 6. หลัง Login
# =========================

else:

    user_now = st.session_state.username

    update_online_status(user_now)

    with get_connection() as conn:

        my_trips = pd.read_sql_query(
            '''
            SELECT *
            FROM trips
            WHERE id IN (
                SELECT trip_id
                FROM trip_members
                WHERE username = ?
            )
            ''',
            conn,
            params=(user_now,)
        )

        notis = pd.read_sql_query(
            '''
            SELECT *
            FROM notifications
            WHERE receiver=?
            ORDER BY id DESC
            LIMIT 5
            ''',
            conn,
            params=(user_now,)
        )

    # =========================
    # Sidebar
    # =========================

    st.sidebar.title(f"👤 {user_now}")

    unread_count = len(notis[notis['is_read'] == 0])

    noti_text = (
        f"🔔 แจ้งเตือน ({unread_count})"
        if unread_count > 0
        else "🔔 แจ้งเตือน"
    )

    menu = st.sidebar.radio(
        "เมนู",
        [
            noti_text,
            "🧳 ทริปของฉัน",
            "➕ สร้างทริปใหม่"
        ]
    )

    if st.sidebar.button("Log out"):

        st.session_state.username = None
        st.session_state.current_trip_name = None

        st.rerun()

    # =========================
    # หน้าแจ้งเตือน
    # =========================

    if "🔔" in menu:

        st.header("🔔 แจ้งเตือนล่าสุด")

        if notis.empty:

            st.info("ไม่มีข้อความ")

        else:

            for _, n in notis.iterrows():

                st.markdown(
                    f"**[{n['created_at']}]** {n['message']}"
                )

            if st.button("อ่านทั้งหมด"):

                with get_connection() as conn:

                    conn.cursor().execute(
                        '''
                        UPDATE notifications
                        SET is_read=1
                        WHERE receiver=?
                        ''',
                        (user_now,)
                    )

                    conn.commit()

                st.rerun()

    # =========================
    # หน้าทริป
    # =========================

    elif menu == "🧳 ทริปของฉัน":

        if my_trips.empty:

            st.info("คุณยังไม่มีทริป")

        else:

            trip_options = my_trips['name'].tolist()

            # FIX selectbox state
            if len(trip_options) > 0:

                if st.session_state.current_trip_name not in trip_options:
                    st.session_state.current_trip_name = trip_options[0]

            sel_trip = st.selectbox(
                "เลือกทริป",
                trip_options,
                index=trip_options.index(
                    st.session_state.current_trip_name
                ),
                key="trip_select_box"
            )

            st.session_state.current_trip_name = sel_trip

            if sel_trip:

                t_rows = my_trips[
                    my_trips['name'] == sel_trip
                ]

                if not t_rows.empty:

                    t_row = t_rows.iloc[0]

                    t_id = t_row['id']

                    is_creator = (
                        t_row['created_by'] == user_now
                    )

                    tab1, tab2, tab3 = st.tabs([
                        "📝 รายจ่าย",
                        "📊 สรุป",
                        "👥 สมาชิก"
                    ])

                    # =========================
                    # TAB 1
                    # =========================

                    with tab1:

                        st.subheader("บันทึกรายรับ-รายจ่าย")

                        with st.form("exp_form", clear_on_submit=True):

                            ttype = st.selectbox(
                                "ประเภท",
                                ["รายจ่าย", "รายรับ"]
                            )

                            amt = st.number_input(
                                "จำนวนเงิน",
                                min_value=0.0,
                                step=100.0
                            )

                            cat = st.selectbox(
                                "หมวดหมู่",
                                [
                                    "อาหาร",
                                    "เดินทาง",
                                    "ที่พัก",
                                    "ช้อปปิ้ง",
                                    "อื่นๆ"
                                ]
                            )

                            note = st.text_area("โน้ต")

                            uploaded_file = st.file_uploader(
                                "แนบใบเสร็จ",
                                type=["jpg", "jpeg", "png"]
                            )

                            if st.form_submit_button("บันทึก"):

                                if amt <= 0:

                                    st.error("จำนวนเงินต้องมากกว่า 0")

                                else:

                                    with get_connection() as conn:

                                        cur = conn.cursor()

                                        cur.execute(
                                            '''
                                            INSERT INTO transactions(
                                                date,
                                                type,
                                                category,
                                                amount,
                                                note,
                                                trip_id,
                                                created_by
                                            )
                                            VALUES (?,?,?,?,?,?,?)
                                            ''',
                                            (
                                                datetime.now().strftime("%Y-%m-%d"),
                                                ttype,
                                                cat,
                                                amt,
                                                note,
                                                t_id,
                                                user_now
                                            )
                                        )

                                        tx_id = cur.lastrowid

                                        # Save bill
                                        if uploaded_file is not None:

                                            file_ext = uploaded_file.name.split(".")[-1]

                                            bill_path = (
                                                f"{BILL_DIR}/receipt_{tx_id}.{file_ext}"
                                            )

                                            with open(bill_path, "wb") as f:
                                                f.write(uploaded_file.getbuffer())

                                            cur.execute(
                                                '''
                                                UPDATE transactions
                                                SET bill_path=?
                                                WHERE id=?
                                                ''',
                                                (bill_path, tx_id)
                                            )

                                        # Send notification
                                        m_list = cur.execute(
                                            '''
                                            SELECT username
                                            FROM trip_members
                                            WHERE trip_id=?
                                            AND username!=?
                                            ''',
                                            (t_id, user_now)
                                        ).fetchall()

                                        for m in m_list:

                                            send_notification(
                                                m[0],
                                                f"💰 {user_now} เพิ่ม {ttype} ฿{amt:,.2f}",
                                                conn=conn
                                            )

                                        conn.commit()

                                    st.success("บันทึกสำเร็จ")

                                    st.rerun()

                    # =========================
                    # TAB 2
                    # =========================

                    with tab2:

                        with get_connection() as conn:

                            df = pd.read_sql_query(
                                '''
                                SELECT *
                                FROM transactions
                                WHERE trip_id=?
                                ''',
                                conn,
                                params=(t_id,)
                            )

                        if df.empty:

                            st.info("ยังไม่มีรายการ")

                        else:

                            total_expense = df[
                                df['type'] == 'รายจ่าย'
                            ]['amount'].sum()

                            st.metric(
                                "รายจ่ายรวม",
                                f"฿{total_expense:,.2f}"
                            )

                            exp_df = df[
                                df['type'] == 'รายจ่าย'
                            ]

                            if not exp_df.empty:

                                fig = px.pie(
                                    exp_df,
                                    values='amount',
                                    names='category',
                                    hole=0.4
                                )

                                st.plotly_chart(
                                    fig,
                                    use_container_width=True
                                )

                            st.dataframe(df)

                    # =========================
                    # TAB 3
                    # =========================

                    with tab3:

                        st.subheader("สมาชิก")

                        with get_connection() as conn:

                            members = pd.read_sql_query(
                                '''
                                SELECT u.username, u.last_active
                                FROM trip_members tm
                                JOIN users u
                                ON tm.username = u.username
                                WHERE tm.trip_id = ?
                                ''',
                                conn,
                                params=(t_id,)
                            )

                        for _, m_row in members.iterrows():

                            status = get_status_icon(
                                m_row['last_active']
                            )

                            st.write(
                                f"{status} {m_row['username']}"
                            )

                        # Invite
                        if is_creator:

                            st.divider()

                            st.subheader("เชิญเพื่อน")

                            search_user = st.text_input(
                                "ชื่อผู้ใช้"
                            )

                            if search_user:

                                with get_connection() as conn:

                                    cur = conn.cursor()

                                    user_exists = cur.execute(
                                        '''
                                        SELECT COUNT(*)
                                        FROM users
                                        WHERE username=?
                                        ''',
                                        (search_user,)
                                    ).fetchone()[0]

                                    is_member = cur.execute(
                                        '''
                                        SELECT COUNT(*)
                                        FROM trip_members
                                        WHERE trip_id=?
                                        AND username=?
                                        ''',
                                        (t_id, search_user)
                                    ).fetchone()[0]

                                    if user_exists == 0:

                                        st.warning("ไม่พบผู้ใช้")

                                    elif is_member > 0:

                                        st.info("อยู่ในทริปแล้ว")

                                    else:

                                        if st.button(
                                            f"เชิญ {search_user}"
                                        ):

                                            cur.execute(
                                                '''
                                                INSERT INTO trip_members(
                                                    trip_id,
                                                    username
                                                )
                                                VALUES (?,?)
                                                ''',
                                                (
                                                    t_id,
                                                    search_user
                                                )
                                            )

                                            conn.commit()

                                            # DEBUG
                                            check = cur.execute(
                                                '''
                                                SELECT *
                                                FROM trip_members
                                                WHERE trip_id=?
                                                AND username=?
                                                ''',
                                                (
                                                    t_id,
                                                    search_user
                                                )
                                            ).fetchall()

                                            st.write(check)

                                            send_notification(
                                                search_user,
                                                f"✉️ {user_now} เชิญคุณเข้าทริป '{sel_trip}'",
                                                conn=conn
                                            )

                                            conn.commit()

                                            st.success("เชิญสำเร็จ")

                                            st.rerun()

    # =========================
    # สร้างทริปใหม่
    # =========================

    elif menu == "➕ สร้างทริปใหม่":

        st.header("สร้างทริปใหม่")

        with st.form("new_trip"):

            name = st.text_input("ชื่อทริป")

            bud = st.number_input(
                "งบประมาณ",
                min_value=0.0,
                step=500.0
            )

            if st.form_submit_button("สร้าง"):

                if name:

                    with get_connection() as conn:

                        cur = conn.cursor()

                        cur.execute(
                            '''
                            INSERT INTO trips(
                                name,
                                budget,
                                created_by,
                                created_at
                            )
                            VALUES (?,?,?,?)
                            ''',
                            (
                                name,
                                bud,
                                user_now,
                                datetime.now().strftime("%Y-%m-%d")
                            )
                        )

                        new_id = cur.lastrowid

                        cur.execute(
                            '''
                            INSERT INTO trip_members(
                                trip_id,
                                username
                            )
                            VALUES (?,?)
                            ''',
                            (
                                new_id,
                                user_now
                            )
                        )

                        conn.commit()

                    st.success("สร้างทริปสำเร็จ")

                    st.rerun()

                else:

                    st.error("กรุณากรอกชื่อทริป")
