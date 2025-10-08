# -*- coding: utf-8 -*-
"""
Created on Wed Oct  8 12:14:00 2025

@author: seyedhyd
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import datetime
import requests

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Ak & Aa Shared Expense Tracker (AASET)",
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


# --- FILE PATHS & DATA HANDLING ---
DATA_FILE = Path(__file__).parent / "transactions.csv"

def get_location():
    """Fetches the user's estimated location based on IP address."""
    try:
        response = requests.get("https://ipinfo.io/json", timeout=5)
        data = response.json()
        return f"{data.get('city', 'N/A')}, {data.get('country', 'N/A')}"
    except requests.RequestException:
        return "Location N/A"

def load_data():
    """Loads transaction data from the CSV file, creating it if it doesn't exist."""
    if not DATA_FILE.is_file():
        df = pd.DataFrame(columns=[
            'Transaction', 'Amount', 'Type', 'Paid by', 'Date of Transaction', 
            'Entered by', 'Timestamp', 'Location'
        ])
        df.to_csv(DATA_FILE, index=False)
    
    df = pd.read_csv(DATA_FILE)
    df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
    df['Date of Transaction'] = pd.to_datetime(df['Date of Transaction'], errors='coerce').dt.date
    return df

def save_data(df):
    """Saves the DataFrame to the CSV file."""
    df.to_csv(DATA_FILE, index=False)

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
            
            # Using get method to avoid KeyError if username doesn't exist
            if user_credentials.get(username) == password:
                st.session_state["user_logged_in"] = True
                st.session_state["user"] = username
                del st.session_state["password"]
                del st.session_state["username"]
            else:
                st.session_state["user_logged_in"] = False
                st.error("😕 User not known or password incorrect")
        except Exception as e:
            st.error(f"Credentials not found in secrets.toml or error: {e}")
            st.session_state["user_logged_in"] = False

    if st.session_state.get("user_logged_in", False):
        return True

    login_form()
    return False

# --- MAIN APP LOGIC ---
if not check_password():
    st.stop()

# --- Display Logout Button ---
st.sidebar.write(f"Welcome, **{st.session_state['user']}**!")
if st.sidebar.button("Logout"):
    st.session_state["user_logged_in"] = False
    st.rerun()

# --- Load Data ---
transactions_df = load_data()

# --- BALANCE CALCULATION ---
def calculate_balance_and_summary(df):
    """
    Calculates the balance from AK's perspective based on independent transaction components.
    A positive balance means AA owes AK. A negative balance means AK owes AA.
    """
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
    
    balance = 0.0
    
    # 1. Net contribution from shared expenses
    ak_share = summary['shared_expenses'] / 2
    # This calculates (AK's contribution to shared pool) - (AK's actual share)
    balance += (summary['shared_paid_by_ak'] - ak_share)

    # 2. Individual expenses
    balance += summary['aa_only_paid_by_ak']  # AK paid for AA (+)
    balance -= summary['ak_only_paid_by_aa']  # AA paid for AK (-)

    # 3. Repayments
    # Following detailed log logic: if AK repays AA, their net contribution increases.
    balance += summary['repayment_ak_to_aa'] 
    # If AA repays AK, the debt owed to AK is reduced.
    balance -= summary['repayment_aa_to_ak']

    return balance, summary


# --- UI DISPLAY ---
st.title("💸 AK & AA Shared Expense Tracker")
st.markdown("---")

# --- Dashboard Metrics ---
col1, col2, col3 = st.columns(3)
total_shared = transactions_df[transactions_df['Type'] == 'Shared Expense']['Amount'].sum()
total_paid_by_user = transactions_df[transactions_df['Paid by'] == st.session_state['user']]['Amount'].sum()
col1.metric("Total Shared Spending", f"₹{total_shared:,.2f}")
col2.metric(f"Total Paid by You ({st.session_state['user']})", f"₹{total_paid_by_user:,.2f}")
col3.metric("Total Transactions", f"{len(transactions_df)}")

st.markdown("---")

# --- Net Balance Display ---
balance, summary_data = calculate_balance_and_summary(transactions_df)

# Centering the card
_, center_col, _ = st.columns([1, 2, 1])
with center_col:
    if balance > 0.01:
        card_class = "positive"
        title = "Final Balance: AA owes AK"
        amount_display = f"₹{balance:,.2f}"
    elif balance < -0.01:
        card_class = "negative"
        title = "Final Balance: AK owes AA"
        amount_display = f"₹{-balance:,.2f}"
    else:
        card_class = "neutral"
        title = "You are all settled up!"
        amount_display = "₹0.00"

    st.markdown(f"""
    <div class="balance-card {card_class}">
        <h3>{title}</h3>
        <p class="amount">{amount_display}</p>
    </div>
    """, unsafe_allow_html=True)


# --- Calculation Transparency ---
with st.expander("Show Calculation Breakdown", expanded=False):
    st.subheader("High-Level Summary")
    
    ak_share = summary_data['shared_expenses'] / 2
    ak_overpayment = summary_data['shared_paid_by_ak'] - ak_share
    
    st.markdown("##### 1. Shared Costs Analysis")
    st.markdown(f"""
    - **Total Shared Expenses:** `₹{summary_data['shared_expenses']:,.2f}`
    - **Each Person's Share (50%):** `₹{ak_share:,.2f}`
    - **Amount AK Paid for Shared Costs:** `₹{summary_data['shared_paid_by_ak']:,.2f}`
    - **Amount AA Paid for Shared Costs:** `₹{summary_data['shared_paid_by_aa']:,.2f}`
    """)
    if ak_overpayment > 0:
        st.success(f"Logic: AK paid `₹{ak_overpayment:,.2f}` more than their share, which AA underpaid. This amount is a credit for AK.")
    else:
        st.warning(f"Logic: AK paid `₹{-ak_overpayment:,.2f}` less than their share. This amount is a debit for AK.")
    st.markdown("---")

    st.markdown("##### 2. Individual Costs & Repayments")
    st.markdown(f"""
    - **Costs for AA Only (Paid by AK):** `₹{summary_data['aa_only_paid_by_ak']:,.2f}` (Credit for AK)
    - **Costs for AK Only (Paid by AA):** `₹{summary_data['ak_only_paid_by_aa']:,.2f}` (Debit for AK)
    - **Repayments from AK to AA:** `₹{summary_data['repayment_ak_to_aa']:,.2f}` (Debit for AK)
    - **Repayments from AA to AK:** `₹{summary_data['repayment_aa_to_ak']:,.2f}` (Credit for AK)
    """)
    st.markdown("---")

    st.markdown("##### 3. Final Calculation Narrative")
    balance_step1 = -summary_data['ak_only_paid_by_aa']
    st.markdown(f"**Step 1:** Start with the amount AK owes AA for 'AK only' costs paid by AA: `₹{-balance_step1:,.2f}`")
    
    balance_step2 = balance_step1 + ak_overpayment
    st.markdown(f"**Step 2:** Add the amount AK overpaid on shared costs (a credit for AK): `₹{balance_step1:,.2f} + ₹{ak_overpayment:,.2f} = ₹{balance_step2:,.2f}`")
    
    balance_step3 = balance_step2 + summary_data['aa_only_paid_by_ak']
    st.markdown(f"**Step 3:** Add costs AK paid for AA only (another credit for AK): `₹{balance_step2:,.2f} + ₹{summary_data['aa_only_paid_by_ak']:,.2f} = ₹{balance_step3:,.2f}`")

    balance_step4 = balance_step3 + summary_data['repayment_aa_to_ak']
    st.markdown(f"**Step 4:** Add repayments AA made to AK (a credit for AK): `₹{balance_step3:,.2f} + ₹{summary_data['repayment_aa_to_ak']:,.2f} = ₹{balance_step4:,.2f}`")
    
    balance_step5 = balance_step4 - summary_data['repayment_ak_to_aa']
    st.markdown(f"**Step 5:** Subtract repayments AK made to AA (a debit for AK): `₹{balance_step4:,.2f} - ₹{summary_data['repayment_ak_to_aa']:,.2f} = ₹{balance_step5:,.2f}`")
    
    st.markdown(f"**Final Balance:** A positive final number (`₹{balance:,.2f}`) means **AA owes AK**. A negative number would mean AK owes AA.")


    with st.expander("Show Detailed Transaction-by-Transaction Log"):
        running_balance = 0.0
        st.write("*(Balance from AK's perspective: Positive means AA owes AK)*")
        log = f"**Starting Balance: ₹0.00**\n\n---\n"
        
        for _, row in transactions_df.iterrows():
            amount = row['Amount']
            paid_by = row['Paid by']
            trans_type = row['Type']
            desc = row['Transaction']
            
            old_balance = running_balance
            logic = ""
            
            if trans_type == 'Shared Expense':
                change = amount / 2
                if paid_by == 'AK':
                    running_balance += change
                    logic = f"AK paid. AK's balance increases by half. `+{change:,.2f}`"
                else:
                    running_balance -= change
                    logic = f"AA paid. AK's balance decreases by half. `-{change:,.2f}`"
            elif trans_type == 'For AA only' and paid_by == 'AK':
                running_balance += amount
                logic = f"AK paid for AA. AK's balance increases. `+{amount:,.2f}`"
            elif trans_type == 'For AK only' and paid_by == 'AA':
                running_balance -= amount
                logic = f"AA paid for AK. AK's balance decreases. `-{amount:,.2f}`"
            elif trans_type == 'Repayment from AA to AK':
                running_balance -= amount
                logic = f"AA repaid AK. AK's balance decreases. `-{amount:,.2f}`"
            elif trans_type == 'Repayment from AK to AA':
                running_balance += amount # This assumes repayment increases AK's net contribution
                logic = f"AK repaid AA. AK's balance increases. `+{amount:,.2f}`"
            
            if logic:
                log += f"**Transaction**: *{desc}* (₹{amount:,.2f})\n\n"
                log += f"- **Logic**: {logic}\n"
                log += f"- **Balance**: `₹{old_balance:,.2f} -> ₹{running_balance:,.2f}`\n\n---\n"
        
        st.markdown(log)

# --- Data Entry in Sidebar ---
with st.sidebar:
    st.header("Add New Transaction")
    with st.form("new_transaction_form", clear_on_submit=True):
        transaction = st.text_input("Transaction Description", placeholder="e.g., Groceries")
        amount = st.number_input("Amount (₹)", min_value=0.01, format="%.2f")
        transaction_date = st.date_input("Date of Transaction", datetime.date.today())
        paid_by = st.selectbox("Paid by", ["AK", "AA"], index=0)
        trans_type_options = [
            'Shared Expense', 
            'For AK only', 
            'For AA only', 
            'Repayment from AK to AA', 
            'Repayment from AA to AK'
        ]
        trans_type = st.selectbox("Type", trans_type_options, index=0)
        
        submitted = st.form_submit_button("Add Transaction")

        if submitted:
            if not transaction or amount <= 0:
                st.warning("Please fill in all fields with a valid amount.")
            else:
                new_entry = pd.DataFrame([{
                    "Transaction": transaction,
                    "Amount": amount,
                    "Type": trans_type,
                    "Paid by": paid_by,
                    "Date of Transaction": transaction_date,
                    "Entered by": st.session_state["user"],
                    "Timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "Location": get_location()
                }])
                
                updated_df = pd.concat([transactions_df, new_entry], ignore_index=True)
                save_data(updated_df)
                st.success("Transaction added!")
                st.rerun()

st.markdown("---")
st.header("Transaction History")

# --- Filters for the History View ---
filt_col1, filt_col2, filt_col3 = st.columns([2, 2, 1])
with filt_col1:
    paid_by_filter = st.multiselect(
        "Filter by who paid:",
        options=transactions_df['Paid by'].unique(),
        default=transactions_df['Paid by'].unique()
    )
with filt_col2:
    if not transactions_df.empty and pd.api.types.is_datetime64_any_dtype(pd.to_datetime(transactions_df['Date of Transaction'], errors='coerce')):
        min_date = transactions_df['Date of Transaction'].min()
        max_date = transactions_df['Date of Transaction'].max()
        if min_date and max_date and isinstance(min_date, datetime.date) and isinstance(max_date, datetime.date):
             date_range = st.date_input(
                "Filter by transaction date:",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
            )
        else:
            date_range = None
    else:
        date_range = None
        
# Apply filters
filtered_df = transactions_df[transactions_df['Paid by'].isin(paid_by_filter)]
if date_range and len(date_range) == 2:
    start_date, end_date = date_range
    filtered_df = filtered_df[
        (filtered_df['Date of Transaction'] >= start_date) & 
        (filtered_df['Date of Transaction'] <= end_date)
    ]


st.info("You can edit or delete entries directly in the table below. Changes are saved automatically.")

# --- Interactive Data Editor ---
edited_df = st.data_editor(
    filtered_df,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Amount": st.column_config.NumberColumn(
            "Amount (₹)",
            format="₹%.2f",
        ),
        "Date of Transaction": st.column_config.DateColumn(
            "Transaction Date",
            format="D MMM YYYY",
        ),
        "Timestamp": st.column_config.DatetimeColumn(
            "Entry Timestamp",
            format="D MMM YYYY, h:mm a",
        ),
    },
    key="data_editor"
)

# --- Save edits back to the CSV ---
# This part is tricky with filtering. The logic needs to update the original dataframe.
if not filtered_df.equals(edited_df):
    # Update the original dataframe with changes from the edited one
    transactions_df.update(edited_df)
    # Handle deleted rows
    deleted_indices = filtered_df.index.difference(edited_df.index)
    transactions_df = transactions_df.drop(index=deleted_indices)
    
    save_data(transactions_df)
    st.toast("Changes saved!", icon="✅")
    st.rerun()
