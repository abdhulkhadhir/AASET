# -*- coding: utf-8 -*-
"""
Created on Wed Oct  8 12:14:00 2025

@author: seyedhyd
"""

import streamlit as st
import pandas as pd
import datetime
import requests
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURATION ---
st.set_page_config(
    page_title="AK & AA Shared Expense Tracker",
    page_icon="💸",
    layout="wide"
)

# --- STYLING ---
st.markdown("""
<style>
    /* Main container styling */
    .main .block-container {
        padding-top: 2rem;
    }
    /* Custom card for balance display */
    .balance-card {
        background-color: #f0f2f6;
        border-radius: 15px;
        padding: 25px;
        text-align: center;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        border: 1px solid #e0e0e0;
    }
    .balance-card h3 {
        margin: 0;
        color: #555;
        font-size: 1.2rem;
        font-weight: 600;
    }
    .balance-card .amount {
        font-size: 2.5rem;
        font-weight: 700;
        margin: 10px 0;
    }
    .balance-card.positive {
        background-color: #e6ffed;
        border-color: #b7e4c7;
    }
    .balance-card.positive .amount {
        color: #2d6a4f;
    }
    .balance-card.negative {
        background-color: #fff0f0;
        border-color: #ffb3b3;
    }
    .balance-card.negative .amount {
        color: #c9184a;
    }
     .balance-card.neutral {
        background-color: #e9f5ff;
        border-color: #a3d5ff;
    }
    .balance-card.neutral .amount {
        color: #005f73;
    }
</style>
""", unsafe_allow_html=True)

# --- GOOGLE SHEETS CONNECTION ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Failed to connect to Google Sheets. Please ensure your `secrets.toml` file is configured correctly under `[connections.gsheets]` and includes the spreadsheet URL.")
    st.error(f"Error details: {e}")
    st.stop()


def get_location():
    """Fetches the user's estimated location based on IP address."""
    try:
        response = requests.get("https://ipinfo.io/json", timeout=5)
        data = response.json()
        return f"{data.get('city', 'N/A')}, {data.get('country', 'N/A')}"
    except requests.RequestException:
        return "Location N/A"

@st.cache_data(ttl=60)
def load_data(_conn):
    """Loads and cleans transaction data from the Google Sheet."""
    try:
        df = _conn.read(usecols=list(range(8)), ttl=60) # Use TTL here for caching
        df.dropna(how="all", inplace=True)
        df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
        df['Date of Transaction'] = pd.to_datetime(df['Date of Transaction'], errors='coerce').dt.date
        df = df.sort_values(by="Date of Transaction").reset_index(drop=True)
        return df
    except Exception as e:
        st.error(f"Failed to load data from Google Sheets: {e}")
        return pd.DataFrame(columns=[
            'Transaction', 'Amount', 'Type', 'Paid by', 'Date of Transaction', 
            'Entered by', 'Timestamp', 'Location'
        ])

def save_data(_conn, df):
    """Saves the DataFrame to the Google Sheet using the correct .update() method."""
    try:
        # Convert date/time columns to strings for compatibility
        df_copy = df.copy()
        df_copy['Date of Transaction'] = pd.to_datetime(df_copy['Date of Transaction']).dt.strftime('%Y-%m-%d')
        df_copy['Timestamp'] = pd.to_datetime(df_copy['Timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # The .update() method is the correct way to write data with this library.
        # It clears the sheet and writes the new dataframe in one operation.
        _conn.update(worksheet="Sheet1", data=df_copy)
        st.cache_data.clear() # Clear cache after writing
    except Exception as e:
        st.error(f"Failed to save data to Google Sheets: {e}")

# --- AUTHENTICATION ---
def check_password():
    """Returns `True` if the user is authenticated."""
    def login_form():
        with st.form("Credentials"):
            st.text_input("Username", key="username")
            st.text_input("Password", type="password", key="password")
            st.form_submit_button("Log in", on_click=password_entered)

    def password_entered():
        try:
            user_credentials = st.secrets["credentials"]["users"]
            username = st.session_state["username"]
            password = st.session_state["password"]
            
            if user_credentials.get(username) == password:
                st.session_state["user_logged_in"] = True
                st.session_state["user"] = username
                del st.session_state["password"]
                del st.session_state["username"]
            else:
                st.session_state["user_logged_in"] = False
                st.error("😕 User not known or password incorrect")
        except KeyError:
             st.error("User credentials not found in secrets.toml. Please ensure they are under `[credentials.users]`.")
             st.session_state["user_logged_in"] = False
        except Exception as e:
            st.error(f"An error occurred during login: {e}")
            st.session_state["user_logged_in"] = False


    if st.session_state.get("user_logged_in", False):
        return True

    login_form()
    return False

# --- MAIN APP LOGIC ---
if not check_password():
    st.stop()

st.sidebar.write(f"Welcome, **{st.session_state['user']}**!")
if st.sidebar.button("Logout"):
    st.session_state["user_logged_in"] = False
    st.rerun()

transactions_df = load_data(conn)

# --- BALANCE CALCULATION (CLEANED UP) ---
def calculate_balance_and_summary(df):
    """Calculates the balance and a summary dictionary for display."""
    if df.empty:
        return 0.0, {
            'total_paid_by_AK': 0, 'total_paid_by_AA': 0, 'shared_expenses': 0,
            'shared_paid_by_ak': 0, 'shared_paid_by_aa': 0, 'ak_only_paid_by_aa': 0,
            'aa_only_paid_by_ak': 0, 'repayment_ak_to_aa': 0, 'repayment_aa_to_ak': 0,
        }
        
    summary = {
        'total_paid_by_AK': df[df['Paid by'] == 'AK']['Amount'].sum(),
        'total_paid_by_AA': df[df['Paid by'] == 'AA']['Amount'].sum(),
        'shared_expenses': df[df['Type'] == 'Shared Expense']['Amount'].sum(),
        'shared_paid_by_ak': df[(df['Type'] == 'Shared Expense') & (df['Paid by'] == 'AK')]['Amount'].sum(),
        'shared_paid_by_aa': df[(df['Type'] == 'Shared Expense') & (df['Paid by'] == 'AA')]['Amount'].sum(),
        'ak_only_paid_by_aa': df[(df['Type'] == 'For AK only') & (df['Paid by'] == 'AA')]['Amount'].sum(),
        'aa_only_paid_by_ak': df[(df['Type'] == 'For AA only') & (df['Paid by'] == 'AK')]['Amount'].sum(),
        'repayment_ak_to_aa': df[df['Type'] == 'Repayment from AK to AA']['Amount'].sum(),
        'repayment_aa_to_ak': df[df['Type'] == 'Repayment from AA to AK']['Amount'].sum(),
    }
    
    # Balance from AK's perspective: Positive means AA owes AK.
    ak_share = summary['shared_expenses'] / 2.0 if summary['shared_expenses'] > 0 else 0.0
    
    # Start with what AK is owed (or owes) from shared costs
    balance = summary['shared_paid_by_ak'] - ak_share
    
    # Add what AK is owed for paying for AA's things
    balance += summary['aa_only_paid_by_ak']
    
    # Subtract what AK owes AA for paying for AK's things
    balance -= summary['ak_only_paid_by_aa']
    
    # When AK repays AA, AK's debt to AA is reduced. This moves the balance in AK's favor (more positive).
    balance += summary['repayment_ak_to_aa'] 
    
    # When AA repays AK, AA's debt to AK is reduced. This moves the balance against AK's favor (more negative).
    balance -= summary['repayment_aa_to_ak']

    return balance, summary

# --- UI DISPLAY ---
st.title("💸 AK & AA Shared Expense Tracker")
st.markdown("A persistent expense tracker powered by Google Sheets.")
st.markdown("---")

col1, col2, col3 = st.columns(3)
total_shared = transactions_df['Amount'][transactions_df['Type'] == 'Shared Expense'].sum()
total_paid_by_user = transactions_df['Amount'][transactions_df['Paid by'] == st.session_state['user']].sum()
col1.metric("Total Shared Spending", f"₹{total_shared:,.2f}")
col2.metric(f"Total Paid by You ({st.session_state['user']})", f"₹{total_paid_by_user:,.2f}")
col3.metric("Total Transactions", f"{len(transactions_df)}")

st.markdown("---")

balance, summary_data = calculate_balance_and_summary(transactions_df)

_, center_col, _ = st.columns([1, 2, 1])
with center_col:
    if balance > 0.01:
        card_class, title, amount_display = "positive", "Final Balance: AA owes AK", f"₹{balance:,.2f}"
    elif balance < -0.01:
        card_class, title, amount_display = "negative", "Final Balance: AK owes AA", f"₹{-balance:,.2f}"
    else:
        card_class, title, amount_display = "neutral", "You are all settled up!", "₹0.00"

    st.markdown(f'<div class="balance-card {card_class}"><h3>{title}</h3><p class="amount">{amount_display}</p></div>', unsafe_allow_html=True)


with st.expander("Show Calculation Breakdown"):
    st.subheader("High-Level Summary (from AK's perspective)")
    
    ak_share = summary_data['shared_expenses'] / 2.0 if summary_data['shared_expenses'] > 0 else 0.0
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
            st.markdown(f"**Transaction {index + 1}:** *{row['Transaction']}* (`₹{row['Amount']:,.2f}`)")
            
            logic_text = ""
            balance_change = 0.0

            if row['Type'] == 'Shared Expense':
                share = row['Amount'] / 2.0
                if row['Paid by'] == 'AK':
                    balance_change = share
                    logic_text = f"Shared cost paid by AK. Balance increases (AA owes more): `+₹{share:,.2f}`."
                else: # Paid by AA
                    balance_change = -share
                    logic_text = f"Shared cost paid by AA. Balance decreases (AK owes more): `-₹{share:,.2f}`."
            elif row['Type'] == 'For AA only' and row['Paid by'] == 'AK':
                balance_change = row['Amount']
                logic_text = f"AK paid for AA. Balance increases: `+₹{row['Amount']:,.2f}`."
            elif row['Type'] == 'For AK only' and row['Paid by'] == 'AA':
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


with st.sidebar:
    st.header("Add New Transaction")
    with st.form("new_transaction_form", clear_on_submit=True):
        transaction = st.text_input("Transaction Description", placeholder="e.g., Groceries")
        amount = st.number_input("Amount (₹)", min_value=0.01, format="%.2f")
        transaction_date = st.date_input("Date of Transaction", datetime.date.today())
        paid_by = st.selectbox("Paid by", ["AK", "AA"], index=0)
        trans_type = st.selectbox("Type", ['Shared Expense', 'For AK only', 'For AA only', 'Repayment from AK to AA', 'Repayment from AA to AK'], index=0)
        
        if st.form_submit_button("Add Transaction"):
            if not transaction or amount <= 0:
                st.warning("Please fill in all fields with a valid amount.")
            else:
                new_entry = pd.DataFrame([{
                    "Transaction": transaction, "Amount": amount, "Type": trans_type,
                    "Paid by": paid_by, "Date of Transaction": transaction_date,
                    "Entered by": st.session_state["user"], "Timestamp": datetime.datetime.now(datetime.timezone.utc),
                    "Location": get_location()
                }])
                
                updated_df = pd.concat([transactions_df, new_entry], ignore_index=True)
                save_data(conn, updated_df)
                st.success("Transaction added!")
                st.rerun()

st.markdown("---")
st.header("Transaction History")

filtered_df = transactions_df.copy()
st.subheader("Filter Transactions")
filter_cols = st.columns([1, 1, 2])

with filter_cols[0]:
    paid_by_filter = st.multiselect(
        "Paid by",
        options=transactions_df["Paid by"].unique(),
        default=transactions_df["Paid by"].unique()
    )

with filter_cols[1]:
    type_filter = st.multiselect(
        "Type",
        options=transactions_df["Type"].unique(),
        default=transactions_df["Type"].unique()
    )

with filter_cols[2]:
    if not transactions_df.empty and pd.api.types.is_datetime64_any_dtype(transactions_df["Date of Transaction"]):
        min_date = transactions_df["Date of Transaction"].min()
        max_date = transactions_df["Date of Transaction"].max()
        if min_date > max_date: # Handle case where there's only one date
             min_date = max_date
        date_range = st.date_input(
            "Select date range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )
    else:
        date_range = st.date_input("Select date range", value=(datetime.date.today(), datetime.date.today()))


if paid_by_filter:
    filtered_df = filtered_df[filtered_df["Paid by"].isin(paid_by_filter)]
if type_filter:
    filtered_df = filtered_df[filtered_df["Type"].isin(type_filter)]
if len(date_range) == 2:
    filtered_df = filtered_df[
        (filtered_df["Date of Transaction"] >= date_range[0]) &
        (filtered_df["Date of Transaction"] <= date_range[1])
    ]

st.dataframe(filtered_df, use_container_width=True)

st.markdown("---")
st.header("Edit Full Transaction History")
st.info("You can edit, add, or delete entries directly in the table below. This table shows ALL transactions and is not affected by the filters above. Changes are saved automatically.")

edited_df = st.data_editor(
    transactions_df,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Amount": st.column_config.NumberColumn("Amount (₹)", format="₹%.2f"),
        "Date of Transaction": st.column_config.DateColumn("Transaction Date", format="D MMM YYYY"),
        "Timestamp": st.column_config.DatetimeColumn("Entry Timestamp", format="D MMM YYYY, h:mm a"),
    },
    key="data_editor"
)

if not transactions_df.equals(edited_df):
    save_data(conn, edited_df)
    st.toast("Changes saved!", icon="✅")
    st.rerun()
