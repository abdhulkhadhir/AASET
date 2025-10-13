# -*- coding: utf-8 -*-
"""
Created on Wed Oct  8 12:14:00 2025

@author: seyedhyd
"""

# app.py
import streamlit as st
import pandas as pd
import datetime
import requests
import time
import altair as alt

# Google Sheets connection
from streamlit_gsheets import GSheetsConnection

# Attempt to import streamlit-authenticator (fail with clear message if missing)
try:
    import streamlit_authenticator as stauth
except Exception as e:
    st.error("Missing dependency: streamlit-authenticator. Install with `pip install streamlit-authenticator`.")
    st.stop()

# --- PAGE CONFIG ---
st.set_page_config(page_title="AK & AA Shared Expense Tracker", page_icon="💸", layout="wide")

# --- STYLING (kept from your original) ---
st.markdown("""
<style>
    .main .block-container { padding-top: 2rem; }
    .balance-card {
        background-color: #f0f2f6; border-radius: 15px; padding: 25px;
        text-align: center; box-shadow: 0 4px 8px rgba(0,0,0,0.1); border: 1px solid #e0e0e0;
        transition: transform 0.16s ease, box-shadow 0.2s ease;
    }
    .balance-card:hover { transform: translateY(-4px); box-shadow: 0 6px 12px rgba(0,0,0,0.12); }
    .balance-card h3 { margin: 0; color: #555; font-size: 1.2rem; font-weight: 600; }
    .balance-card .amount { font-size: 2.5rem; font-weight: 700; margin: 10px 0; }
    .balance-card.positive { background-color: #e6ffed; border-color: #b7e4c7; }
    .balance-card.positive .amount { color: #2d6a4f; }
    .balance-card.negative { background-color: #fff0f0; border-color: #ffb3b3; }
    .balance-card.negative .amount { color: #c9184a; }
    .balance-card.neutral { background-color: #e9f5ff; border-color: #a3d5ff; }
    .balance-card.neutral .amount { color: #005f73; }
</style>
""", unsafe_allow_html=True)

# --- GOOGLE SHEETS CONNECTION: attempt to create connection object ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Failed to connect to Google Sheets. Please ensure your `secrets.toml` has a valid `[connections.gsheets]` entry.")
    st.error(f"Connection error: {e}")
    st.stop()

# --- Authentication builder (robust across versions) ---
DEFAULT_COOKIE_DAYS = 1

def build_authenticator_from_secrets():
    """
    Build a streamlit-authenticator Authenticate object from st.secrets.
    Expects:
      st.secrets['credentials']['users'] -> mapping username -> password (plain or bcrypt-hashed)
      st.secrets['auth'] -> {cookie_name, cookie_key, cookie_expiry_days (optional)}
    """
    # Read users
    try:
        user_map = dict(st.secrets["credentials"]["users"])
        if not user_map:
            raise KeyError
    except Exception:
        st.error("Missing credentials in secrets.toml. Add `[credentials.users]` with AK and AA entries.")
        st.stop()

    # Read auth config (cookie)
    try:
        auth_conf = st.secrets.get("auth", {})
        cookie_name = auth_conf.get("cookie_name", None)
        cookie_key = auth_conf.get("cookie_key", None)
        cookie_expiry_days = int(auth_conf.get("cookie_expiry_days", DEFAULT_COOKIE_DAYS))
        if not cookie_name or not cookie_key:
            raise KeyError
    except Exception:
        st.error("Missing auth config in secrets.toml. Add `[auth]` with `cookie_name` and `cookie_key`.")
        st.stop()

    # Prepare credentials structure
    credentials = {"usernames": {}}
    for uname, pwd in user_map.items():
        pwd = str(pwd).strip()
        # If already bcrypt hashed (common prefix), reuse it. Otherwise hash.
        if pwd.startswith("$2b$") or pwd.startswith("$2a$"):
            hashed_pwd = pwd
        else:
            # Try using streamlit_authenticator.Hasher if available
            try:
                # Newer versions use Hasher([...]).generate()
                hashed_pwd = stauth.Hasher([pwd]).generate()[0]
            except Exception:
                # fallback to bcrypt directly
                try:
                    import bcrypt
                    hashed_pwd = bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
                except Exception:
                    st.error("Failed to hash passwords. Ensure `bcrypt` is available or store hashed passwords in secrets.")
                    st.stop()
        credentials["usernames"][uname] = {"name": uname, "password": hashed_pwd}

    # Create the Authenticate object
    authenticator = stauth.Authenticate(
        credentials=credentials,
        cookie_name=cookie_name,
        key=cookie_key,
        cookie_expiry_days=cookie_expiry_days
    )
    return authenticator

# Build authenticator
authenticator = build_authenticator_from_secrets()

# --- Helpers: location, data load/save, calculations ---
def get_location():
    try:
        response = requests.get("https://ipinfo.io/json", timeout=5)
        data = response.json()
        return f"{data.get('city','N/A')}, {data.get('country','N/A')}"
    except Exception:
        return "Location N/A"

@st.cache_data(ttl=60)
def load_data(_conn):
    """Read sheet, coerce columns and types, return DataFrame with expected columns."""
    try:
        df = _conn.read(usecols=list(range(8)), ttl=60)
        if df is None:
            return pd.DataFrame(columns=['Transaction','Amount','Type','Paid by','Date of Transaction','Entered by','Timestamp','Location'])
        df.dropna(how="all", inplace=True)
        expected_cols = ['Transaction','Amount','Type','Paid by','Date of Transaction','Entered by','Timestamp','Location']
        for c in expected_cols:
            if c not in df.columns:
                df[c] = pd.NA
        df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0.0)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
        df['Date of Transaction'] = pd.to_datetime(df['Date of Transaction'], errors='coerce').dt.date
        df = df.sort_values(by="Date of Transaction", na_position='last').reset_index(drop=True)
        return df
    except Exception as e:
        st.error(f"Failed to read sheet data: {e}")
        return pd.DataFrame(columns=['Transaction','Amount','Type','Paid by','Date of Transaction','Entered by','Timestamp','Location'])

def save_data(_conn, df):
    """Write the DataFrame back to Google Sheets in a stable column order."""
    try:
        df_copy = df.copy()
        if 'Date of Transaction' in df_copy.columns:
            df_copy['Date of Transaction'] = pd.to_datetime(df_copy['Date of Transaction'], errors='coerce').dt.strftime('%Y-%m-%d')
        if 'Timestamp' in df_copy.columns:
            df_copy['Timestamp'] = pd.to_datetime(df_copy['Timestamp'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
        desired_order = ['Transaction','Amount','Type','Paid by','Date of Transaction','Entered by','Timestamp','Location']
        for col in desired_order:
            if col not in df_copy.columns:
                df_copy[col] = ""
        df_copy = df_copy[desired_order]
        _conn.update(worksheet="Sheet1", data=df_copy)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Failed to save data to Google Sheets: {e}")

def calculate_balance_and_summary(df):
    if df is None or df.empty:
        return 0.0, {
            'total_paid_by_AK': 0, 'total_paid_by_AA': 0, 'shared_expenses': 0,
            'shared_paid_by_ak': 0, 'shared_paid_by_aa': 0, 'ak_only_paid_by_aa': 0,
            'aa_only_paid_by_ak': 0, 'repayment_ak_to_aa': 0, 'repayment_aa_to_ak': 0,
        }
    summary = {
        'total_paid_by_AK': df[df['Paid by']=='AK']['Amount'].sum(),
        'total_paid_by_AA': df[df['Paid by']=='AA']['Amount'].sum(),
        'shared_expenses': df[df['Type']=='Shared Expense']['Amount'].sum(),
        'shared_paid_by_ak': df[(df['Type']=='Shared Expense') & (df['Paid by']=='AK')]['Amount'].sum(),
        'shared_paid_by_aa': df[(df['Type']=='Shared Expense') & (df['Paid by']=='AA')]['Amount'].sum(),
        'ak_only_paid_by_aa': df[(df['Type']=='For AK only') & (df['Paid by']=='AA')]['Amount'].sum(),
        'aa_only_paid_by_ak': df[(df['Type']=='For AA only') & (df['Paid by']=='AK')]['Amount'].sum(),
        'repayment_ak_to_aa': df[df['Type']=='Repayment from AK to AA']['Amount'].sum(),
        'repayment_aa_to_ak': df[df['Type']=='Repayment from AA to AK']['Amount'].sum(),
    }
    ak_share = summary['shared_expenses'] / 2.0 if summary['shared_expenses'] > 0 else 0.0
    balance = summary['shared_paid_by_ak'] - ak_share
    balance += summary['aa_only_paid_by_ak']
    balance -= summary['ak_only_paid_by_aa']
    balance += summary['repayment_ak_to_aa']
    balance -= summary['repayment_aa_to_ak']
    return balance, summary

def df_equivalent(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        a2 = a.copy().fillna("")
        b2 = b.copy().fillna("")
        common = [c for c in a2.columns if c in b2.columns]
        a2 = a2[common].reset_index(drop=True)
        b2 = b2[common].reset_index(drop=True)
        if a2.shape != b2.shape:
            return False
        return a2.equals(b2)
    except Exception:
        return False

# --- LOGIN FLOW (compatible with recent streamlit-authenticator versions) ---
auth_result = authenticator.login(location="main")  # returns dict in recent versions

if auth_result is None:
    # login widget rendered but user hasn't interacted yet
    st.warning("Please log in to continue.")
    st.stop()

# auth_result typically looks like: {"name": "...", "username":"...", "authenticated": True/False}
if isinstance(auth_result, dict) and auth_result.get("authenticated") is True:
    # successful login
    current_username = auth_result.get("username")
    current_name = auth_result.get("name", current_username)
    # show logout in sidebar (authenticator handles cookie clearing)
    with st.sidebar:
        if authenticator.logout("Logout", "sidebar"):
            st.experimental_rerun()
        st.success(f"Welcome, {current_name}!")
else:
    # authentication failed
    st.error("Invalid username or password.")
    st.stop()

# --- MAIN APP LOGIC (after successful login) ---
transactions_df = load_data(conn)

st.title("💸 AK & AA Shared Expense Tracker")
st.markdown("A persistent expense tracker powered by Google Sheets.")
st.markdown("---")

col1, col2, col3 = st.columns(3)
total_shared = transactions_df['Amount'][transactions_df['Type']=='Shared Expense'].sum() if not transactions_df.empty else 0.0
total_paid_by_user = transactions_df['Amount'][transactions_df['Paid by']==current_username].sum() if not transactions_df.empty else 0.0
col1.metric("Total Shared Spending", f"₹{total_shared:,.2f}")
col2.metric(f"Total Paid by You ({current_username})", f"₹{total_paid_by_user:,.2f}")
col3.metric("Total Transactions", f"{len(transactions_df)}")

st.markdown("---")

balance, summary_data = calculate_balance_and_summary(transactions_df)

_, center_col, _ = st.columns([1,2,1])
with center_col:
    if balance > 0.01:
        card_class, title, amount_display = "positive", "Final Balance: AA owes AK", f"₹{balance:,.2f}"
    elif balance < -0.01:
        card_class, title, amount_display = "negative", "Final Balance: AK owes AA", f"₹{-balance:,.2f}"
    else:
        card_class, title, amount_display = "neutral", "You are all settled up!", "₹0.00"

    st.markdown(f'<div class="balance-card {card_class}"><h3>{title}</h3><p class="amount">{amount_display}</p></div>', unsafe_allow_html=True)
    st.caption(f"Last refreshed: {datetime.datetime.now().strftime('%d %b %Y, %I:%M:%S %p')} (local)")

# --- VISUAL SUMMARY: bar + pie using altair ---
st.markdown("### Quick Visual: Who paid what?")
if not transactions_df.empty:
    by_payer = transactions_df.groupby("Paid by", dropna=False)["Amount"].sum().reset_index()
    bar = alt.Chart(by_payer).mark_bar().encode(
        x=alt.X('Paid by:N', title='Paid by'),
        y=alt.Y('Amount:Q', title='Total Amount (₹)'),
        tooltip=[alt.Tooltip('Paid by:N'), alt.Tooltip('Amount:Q', format=",.2f")]
    ).properties(height=260)

    pie = alt.Chart(by_payer).mark_arc(innerRadius=20).encode(
        theta=alt.Theta(field="Amount", type="quantitative"),
        color=alt.Color(field="Paid by", type="nominal"),
        tooltip=[alt.Tooltip('Paid by:N'), alt.Tooltip('Amount:Q', format=",.2f")]
    ).properties(height=260, width=260)

    c1, c2 = st.columns([2,1])
    c1.altair_chart(bar, use_container_width=True)
    c2.altair_chart(pie, use_container_width=True)
else:
    st.info("No transactions yet — add one in the sidebar to see visual summaries.")

st.markdown("---")

with st.expander("Show Calculation Breakdown"):
    st.subheader("High-Level Summary (from AK's perspective)")
    ak_share = summary_data['shared_expenses']/2.0 if summary_data['shared_expenses']>0 else 0.0
    ak_overpayment = summary_data['shared_paid_by_ak'] - ak_share

    st.markdown("##### 1. Shared Costs Analysis")
    st.markdown(f"- **Total Shared Expenses:** `₹{summary_data['shared_expenses']:,.2f}`\n"
                f"- **Each Person's Share (50%):** `₹{ak_share:,.2f}`\n"
                f"- **Amount AK Paid for Shared Costs:** `₹{summary_data['shared_paid_by_ak']:,.2f}`")
    if ak_overpayment > 0:
        st.success(f"Logic: AK paid `₹{ak_overpayment:,.2f}` more than their share. This is a credit for AK.")
    else:
        st.warning(f"Logic: AK paid `₹{-ak_overpayment:,.2f}` less than their share. This is a debit for AK.")
    st.markdown("---")

    st.markdown("##### 2. Individual Costs & Repayments")
    st.markdown(f"- **Costs for AA Only (Paid by AK):** `₹{summary_data['aa_only_paid_by_ak']:,.2f}` (Credit for AK)\n"
                f"- **Costs for AK Only (Paid by AA):** `₹{summary_data['ak_only_paid_by_aa']:,.2f}` (Debit for AK)\n"
                f"- **Repayments from AA to AK:** `₹{summary_data['repayment_aa_to_ak']:,.2f}` (Reduces AA's debt to AK)\n"
                f"- **Repayments from AK to AA:** `₹{summary_data['repayment_ak_to_aa']:,.2f}` (Reduces AK's debt to AA)")
    st.markdown("---")

    st.markdown("##### 3. Final Calculation")
    st.markdown(f"**Net from Shared Costs:** `₹{ak_overpayment:,.2f}`\n"
                f"**+ Costs AK paid for AA:** `+ ₹{summary_data['aa_only_paid_by_ak']:,.2f}`\n"
                f"**- Costs AA paid for AK:** `- ₹{summary_data['ak_only_paid_by_aa']:,.2f}`\n"
                f"**+ Repayments from AK:** `+ ₹{summary_data['repayment_ak_to_aa']:,.2f}`\n"
                f"**- Repayments from AA:** `- ₹{summary_data['repayment_aa_to_ak']:,.2f}`\n"
                f"**= FINAL BALANCE:** `₹{balance:,.2f}`")
    st.info("A positive final balance means AA owes AK. A negative balance means AK owes AA.")

    with st.expander("Show Detailed Transaction-by-Transaction Log"):
        running_balance = 0.0
        st.markdown(f"**Initial Balance:** `₹{running_balance:,.2f}`")
        st.markdown("---")
        for index, row in transactions_df.iterrows():
            st.markdown(f"**Transaction {index+1}:** *{row['Transaction']}* (`₹{row['Amount']:,.2f}`)")
            logic_text = ""
            balance_change = 0.0
            if row['Type'] == 'Shared Expense':
                share = row['Amount']/2.0
                if row['Paid by'] == 'AK':
                    balance_change = share
                    logic_text = f"Shared cost paid by AK. Balance increases (AA owes more): `+₹{share:,.2f}`."
                else:
                    balance_change = -share
                    logic_text = f"Shared cost paid by AA. Balance decreases (AK owes more): `-₹{share:,.2f}`."
            elif row['Type'] == 'For AA only' and row['Paid by']=='AK':
                balance_change = row['Amount']
                logic_text = f"AK paid for AA. Balance increases: `+₹{row['Amount']:,.2f}`."
            elif row['Type'] == 'For AK only' and row['Paid by']=='AA':
                balance_change = -row['Amount']
                logic_text = f"AA paid for AK. Balance decreases: `-₹{row['Amount']:,.2f}`."
            elif row['Type'] == 'Repayment from AA to AK':
                balance_change = -row['Amount']
                logic_text = f"AA repaid AK. AA's debt reduces. Balance decreases: `-₹{row['Amount']:,.2f}`."
            elif row['Type'] == 'Repayment from AK to AA':
                balance_change = row['Amount']
                logic_text = f"AK repaid AA. AK's debt reduces. Balance increases: `+₹{row['Amount']:,.2f}`."
            st.markdown(f"> *{logic_text}*")
            new_running_balance = running_balance + balance_change
            st.markdown(f"> **New Balance:** `{running_balance:,.2f} + ({balance_change:,.2f}) =` **`₹{new_running_balance:,.2f}`**")
            running_balance = new_running_balance
            st.markdown("---")

# --- SIDEBAR: Add New Transaction (keeps original behavior, improves reliability) ---
with st.sidebar:
    st.header("Add New Transaction")
    with st.form("new_transaction_form", clear_on_submit=True):
        transaction = st.text_input("Transaction Description", placeholder="e.g., Groceries")
        amount = st.number_input("Amount (₹)", min_value=0.01, format="%.2f")
        transaction_date = st.date_input("Date of Transaction", datetime.date.today())
        paid_by = st.selectbox("Paid by", ["AK", "AA"], index=0)
        trans_type = st.selectbox("Type", ['Shared Expense','For AK only','For AA only','Repayment from AK to AA','Repayment from AA to AK'], index=0)
        if st.form_submit_button("Add Transaction"):
            if not transaction or amount <= 0:
                st.warning("Please fill in all fields with a valid amount.")
            else:
                new_entry = pd.DataFrame([{
                    "Transaction": transaction,
                    "Amount": amount,
                    "Type": trans_type,
                    "Paid by": paid_by,
                    "Date of Transaction": transaction_date,
                    "Entered by": current_username,
                    "Timestamp": datetime.datetime.now(datetime.timezone.utc),
                    "Location": get_location()
                }])
                updated_df = pd.concat([transactions_df, new_entry], ignore_index=True)
                save_data(conn, updated_df)
                st.cache_data.clear()
                time.sleep(0.4)
                st.success("Transaction added!")
                st.experimental_rerun()

st.markdown("---")
st.header("Transaction History")

filtered_df = transactions_df.copy()

st.subheader("Filter Transactions")
filter_cols = st.columns([1,1,2])

with filter_cols[0]:
    paid_by_options = transactions_df["Paid by"].dropna().unique().tolist() if not transactions_df.empty else ["AK","AA"]
    paid_by_filter = st.multiselect("Paid by", options=paid_by_options, default=paid_by_options)

with filter_cols[1]:
    type_options = transactions_df["Type"].dropna().unique().tolist() if not transactions_df.empty else ['Shared Expense','For AK only','For AA only','Repayment from AK to AA','Repayment from AA to AK']
    type_filter = st.multiselect("Type", options=type_options, default=type_options)

with filter_cols[2]:
    if not transactions_df.empty and transactions_df['Date of Transaction'].notna().any():
        valid_dates = [d for d in transactions_df['Date of Transaction'].tolist() if pd.notna(d)]
        if valid_dates:
            min_date = min(valid_dates); max_date = max(valid_dates)
            if min_date > max_date: min_date = max_date
            date_range = st.date_input("Select date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
        else:
            date_range = st.date_input("Select date range", value=(datetime.date.today(), datetime.date.today()))
    else:
        date_range = st.date_input("Select date range", value=(datetime.date.today(), datetime.date.today()))

# apply filters
if paid_by_filter:
    filtered_df = filtered_df[filtered_df["Paid by"].isin(paid_by_filter)]
if type_filter:
    filtered_df = filtered_df[filtered_df["Type"].isin(type_filter)]

try:
    if isinstance(date_range, tuple) and len(date_range)==2:
        start_date, end_date = date_range
        filtered_df = filtered_df[
            (filtered_df["Date of Transaction"].notna()) &
            (filtered_df["Date of Transaction"] >= start_date) &
            (filtered_df["Date of Transaction"] <= end_date)
        ]
    else:
        selected = date_range if isinstance(date_range, datetime.date) else date_range[0]
        filtered_df = filtered_df[filtered_df["Date of Transaction"] == selected]
except Exception:
    pass

def color_row(row):
    t = row.get("Type","")
    if t == "Shared Expense":
        return ["background-color: #e6ffe6"] * len(row)
    if "Repayment" in str(t):
        return ["background-color: #fff7e6"] * len(row)
    return ["background-color: #e6f0ff"] * len(row)

try:
    st.dataframe(filtered_df.style.apply(color_row, axis=1), use_container_width=True)
except Exception:
    st.dataframe(filtered_df, use_container_width=True)

st.markdown("---")
st.header("Edit Full Transaction History")
st.info("You can edit, add, or delete entries directly in the table below. This table shows ALL transactions and is not affected by the filters above. Changes are saved automatically.")

column_config = {}
if 'Amount' in transactions_df.columns:
    column_config['Amount'] = st.column_config.NumberColumn("Amount (₹)", format="₹%.2f")
if 'Date of Transaction' in transactions_df.columns:
    column_config['Date of Transaction'] = st.column_config.DateColumn("Transaction Date", format="D MMM YYYY")
if 'Timestamp' in transactions_df.columns:
    column_config['Timestamp'] = st.column_config.DatetimeColumn("Entry Timestamp", format="D MMM YYYY, h:mm a")

edited_df = st.data_editor(transactions_df, num_rows="dynamic", use_container_width=True, column_config=column_config, key="data_editor")

if not df_equivalent(transactions_df, edited_df):
    save_data(conn, edited_df)
    st.toast("Changes saved!", icon="✅")
    st.cache_data.clear()
    time.sleep(0.4)
    st.experimental_rerun()
