
import re
import json
import pandas as pd
from datetime import datetime
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import DocumentAnalysisFeature, AnalyzeResult
import os
from utility import client

# Initialize the DocumentIntelligenceClient
document_intelligence_client = client()

# Define the path to your document

# Function to format bounding regions
def format_bounding_region(bounding_regions):
    return ", ".join([f"Page {region.page_number}: {region.polygon}" for region in bounding_regions])

# Function to classify transactions and format narration
def classify_transaction(transaction):
    deposits = str(transaction.get("Credit_5", "")).replace(",", "").strip()
    withdrawals = str(transaction.get("Debit_4", "")).replace(",", "").strip()
    narration = transaction.get("Description_2", "")
    if isinstance(narration, float):
        narration = ""
    else:
        narration = str(narration).lower()

    try:
        deposit_amount = float(deposits) if deposits else 0
    except ValueError:
        deposit_amount = 0

    try:
        withdrawal_amount = float(withdrawals) if withdrawals else 0
    except ValueError:
        withdrawal_amount = 0

    if "upi" in narration:
        trxn_type = "UPI"
    elif "imps" in narration:
        trxn_type = "IMPS"
    elif "mps" in narration:
        trxn_type = "MPS"
    elif "neft" in narration:
        trxn_type = "NEFT"
    elif "card" in narration:
        trxn_type = "CARD"
    elif "cheque deposit" in narration:
        trxn_type = "CHEQUE DEPOSIT",
    elif "cheque withdrawal" in narration:
        trxn_type = "CHEQUE WITHDRAWAL"
    elif "cheque bounce" in narration:
        trxn_type = "CHEQUE BOUNCE"
    elif "ecs bounce" in narration:
        trxn_type = "ECS BOUNCE"
    elif "emi" in narration:
        trxn_type = "EMI TRXN"
    elif "loan" in narration:
        trxn_type = "LOAN TRXN"
    elif "payment bounce" in narration:
        trxn_type = "PAYMENT BOUNCE"
    elif "salary" in narration:
        trxn_type = "SALARY TRXN"
    else:
        trxn_type = "Other"

    date_str = transaction.get("Txn Date_0", "")
    try:
        date = pd.to_datetime(date_str, dayfirst=True, errors='coerce')
        if pd.isnull(date):
            date = None
    except ValueError:
        date = None

    salary = False
    if date:
        day = date.day
        start_week = day <= 7
        end_week = day > 24

        if "salary" in narration and (start_week or end_week) and trxn_type in {"MPS", "IMPS", "NEFT"}:
            salary = True

    if salary:
        return "SALARY", deposit_amount, trxn_type
    elif deposit_amount > 0:
        return "CASH DEPOSITS", deposit_amount, trxn_type
    elif withdrawal_amount > 0:
        return "CASH WITHDRAWALS", withdrawal_amount, trxn_type
    else:
        return "OTHER", 0, trxn_type

# Function to replace NaN with empty strings
def replace_nan_with_empty(value):
    if pd.isna(value):
        return ""
    return value

def parse_balance(balance_str):
    if isinstance(balance_str, float):
        return balance_str  # If already a float, return it directly
    balance_str = str(balance_str).replace(",", "").strip()
    balance_str = re.sub(r"[^\d.]", "", balance_str)  # Remove any non-numeric characters except dot
    try:
        return float(balance_str)
    except ValueError:
        return 0.0

def format_narration(narration):
    if isinstance(narration, float):
        narration = str(narration)  # Convert float to string
    parts = [part.strip() for part in narration.split(',') if part.strip()]
    return ", ".join([f'"{part}"' for part in parts])

def extract_account_details(key_value_dict):
    account_details = {
        "account_number": key_value_dict.get('Account Number\n:', ''),
        "customer_address": key_value_dict.get('Address\n:', ''),
        "customer_name": key_value_dict.get('Account Name\n:', ''),
        "ifsc_code": key_value_dict.get('IFS Code', '').lstrip(':'),  # Removing leading colon if present
        "statement_period": {
            "from_date": "",
            "to_date": ""
        }
    }
    return account_details

def extract_statement_period(statement_period_str):
    # Define the regex pattern for extracting dates
    pattern = r'Account Statement from (\d{1,2} \w{3} \d{4}) to (\d{1,2} \w{3} \d{4})'
    match = re.search(pattern, statement_period_str, re.IGNORECASE)
    
    if match:
        from_date_str = match.group(1)
        to_date_str = match.group(2)
        
        # Convert dates to desired format
        try:
            from_date = datetime.strptime(from_date_str, '%d %b %Y').strftime('%d %b %Y')
            to_date = datetime.strptime(to_date_str, '%d %b %Y').strftime('%d %b %Y')
        except ValueError:
            # If parsing fails, use original strings
            from_date = from_date_str
            to_date = to_date_str
        
        return from_date, to_date
    else:
        print(f"No match found in: {statement_period_str}")
    return "", ""

def process_sbi_stmt(path_to_sample_documents: str):
    result = None
    first_page_text_str = ""
    try:
        if not os.path.exists(path_to_sample_documents):
            raise ValueError("FILE DOES NOT EXIST")
        with open(path_to_sample_documents, "rb") as f:
            poller = document_intelligence_client.begin_analyze_document(
                model_id="prebuilt-layout",
                analyze_request=f,
                features=[DocumentAnalysisFeature.KEY_VALUE_PAIRS],
                content_type="application/octet-stream",
            )
            result: AnalyzeResult = poller.result()
    except Exception as e:
        raise ValueError("CAN NOT READ THE DOCUMENT")

    if result.pages:
        first_page = result.pages[0]
        first_page_text = []
        for line in first_page.lines:
            first_page_text.append(line.content.strip())
        first_page_text_str = " ".join(first_page_text)

        if "SBI".lower() not in first_page_text_str.lower():
            raise ValueError("INCORRECT_BANK_STATEMENT")
    else:
        return []

    parsing_status = "false"
    if result.pages:
        parsing_status = "true"

        key_value_pairs = {}
        if result.key_value_pairs:
            for kv_pair in result.key_value_pairs:
                if kv_pair.key and kv_pair.value:
                    key_value_pairs[kv_pair.key.content.strip()] = kv_pair.value.content.strip()

        account_details = extract_account_details(key_value_pairs)

        # Extract statement period from text
        from_date, to_date = extract_statement_period(first_page_text_str)
        account_details["statement_period"]["from_date"] = from_date
        account_details["statement_period"]["to_date"] = to_date

        tables = []
        if result.tables:
            for table in result.tables:
                data = []
                for row_idx in range(table.row_count):
                    row_data = []
                    for column_idx in range(table.column_count):
                        cell = [cell for cell in table.cells if cell.row_index == row_idx and cell.column_index == column_idx]
                        if cell:
                            row_data.append(cell[0].content)
                        else:
                            row_data.append(None)
                    data.append(row_data)
                df = pd.DataFrame(data[1:], columns=data[0])
                df.columns = [f"{col}_{i}" for i, col in enumerate(df.columns)]
                tables.append(df)

        if tables:
            combined_df = pd.concat(tables, ignore_index=True, sort=False)
        else:
            combined_df = pd.DataFrame()

        flattened_dict = combined_df.to_dict('records')

        analyzed_details = {
            "CASH DEPOSITS": [],
            "CASH WITHDRAWALS": [],
            "CHEQUE DEPOSITS": [],
            "CHEQUE WITHDRAWALS": [],
            "CHEQUE BOUNCE": [],
            "SALARY": [],
            "ECS BOUNCES": [],
            "EMI TRXN": [],
            "LOAN TRXN": [],
            "PAYMENT BOUNCES": [],
            "SALARY TRXN": [],
            "trxn_details": [],
            "EOD BALANCE": {
                "daywise_eod_balance": [],
                "monthwise_eod_balance": []
            }
        }

        eod_balance = {}

        for transaction in flattened_dict:
            classification, amount, trxn_type = classify_transaction(transaction)
            balance_str = transaction.get("Balance_6", "")
            balance = parse_balance(balance_str)

            if classification in analyzed_details:
                analyzed_details[classification].append({
                    "amount": amount,
                    "balance": balance,
                    "date": transaction.get("Txn Date_0", ""),
                    "narration": format_narration(transaction.get("Description_2", "")),
                    "trxn_type": trxn_type
                })

            analyzed_details["trxn_details"].append({
                "amount": amount,
                "balance": balance,
                "date": transaction.get("Txn Date_0", ""),
                "narration": format_narration(transaction.get("Description_2", "")),
                "trxn_type": trxn_type
            })

            # EOD balance calculation
            date_str = transaction.get("Txn Date_0", "")
            try:
                date = pd.to_datetime(date_str, dayfirst=True, errors='coerce')
                if pd.notnull(date):
                    date_key = date.date()
                    if date_key not in eod_balance:
                        eod_balance[date_key] = {
                            "balance": balance,
                            "count": 1
                        }
                    else:
                        eod_balance[date_key]["balance"] += balance
                        eod_balance[date_key]["count"] += 1
            except ValueError:
                pass

        # Calculate daywise EOD balance
        analyzed_details["EOD BALANCE"]["daywise_eod_balance"] = [
            {
                "date": date_key.strftime("%Y-%m-%d"),
                "average_balance": balance_info["balance"] / balance_info["count"]
            }
            for date_key, balance_info in eod_balance.items()
        ]

        # Calculate monthwise EOD balance
        monthwise_eod_balance = {}
        for date_key, balance_info in eod_balance.items():
            month_year = date_key.strftime("%Y-%m")
            if month_year not in monthwise_eod_balance:
                monthwise_eod_balance[month_year] = {
                    "balances": [],
                    "count": 0
                }
            monthwise_eod_balance[month_year]["balances"].append(balance_info["balance"])
            monthwise_eod_balance[month_year]["count"] += 1

        analyzed_details["EOD BALANCE"]["monthwise_eod_balance"] = [
            {
                "month": month_year,
                "25th_percentile_eod_balance": pd.Series(balance_info["balances"]).quantile(0.25),
                "50th_percentile_eod_balance": pd.Series(balance_info["balances"]).quantile(0.50),
                "75th_percentile_eod_balance": pd.Series(balance_info["balances"]).quantile(0.75),
                "avg_eod_balance": sum(balance_info["balances"]) / balance_info["count"],
                "max_eod_balance": max(balance_info["balances"]),
                "min_eod_balance": min(balance_info["balances"]),
            }
            for month_year, balance_info in monthwise_eod_balance.items()
        ]

    final_output = {
        "account_details": account_details,
        "analyzed_details": analyzed_details,
        "parsing_status": parsing_status,
        "fraud_details": []
    }
    print("O/p", final_output)
    return final_output

if __name__ == "__main__":
    path_to_sample_documents = "/path/to/your/sbi_bank_statement.pdf"
    process_sbi_stmt(path_to_sample_documents)