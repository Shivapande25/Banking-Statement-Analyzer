import re
import json
import os
import pandas as pd
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import DocumentAnalysisFeature, AnalyzeResult
from util.bank_stmt_parser.azure_parser import client

# Initialize the DocumentIntelligenceClient
document_intelligence_client = client()


# Function to format bounding regions
def format_bounding_region(bounding_regions):
    return ", ".join([f"Page {region.page_number}: {region.polygon}" for region in bounding_regions])


# Function to classify transactions and format narration
def classify_transaction(transaction):
    deposits = str(transaction.get("DEPOSITS_3", "")).replace(",", "").strip()
    withdrawals = str(transaction.get("WITHDRAWALS_4", "")).replace(",", "").strip()

    narration = transaction.get("PARTICULARS_2", "")
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

    # Determine the transaction type based on narration keywords
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
    else:
        trxn_type = "OTHER"

    # Check if the transaction is a salary transaction
    date_str = transaction.get("DATE_0", "")
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

        # Salary condition: keyword 'salary' (OR), first or last week (AND), transaction type (AND)
        if "salary" in narration and (start_week or end_week) and trxn_type in {"MPS", "IMPS", "NEFT"}:
            salary = True

    if salary:
        return "SALARY", deposit_amount, trxn_type
    elif "cheque deposit" in narration:
        return "CHEQUE DEPOSIT", deposit_amount, trxn_type
    elif "cheque withdrawal" in narration or "withdrawal by chq" in narration:
        return "CHEQUE WITHDRAWAL", withdrawal_amount, trxn_type
    elif "cheque bounce" in narration or "bounce by chq" in narration:
        return "CHEQUE BOUNCE", withdrawal_amount, trxn_type
    elif deposit_amount > 0:
        return "CASH DEPOSIT", deposit_amount, trxn_type
    elif withdrawal_amount > 0:
        return "CASH WITHDRAWAL", withdrawal_amount, trxn_type
    elif "ecs bounce" in narration:
        return "ECS BOUNCE", withdrawal_amount, trxn_type
    elif "emi" in narration:
        return "EMI TRXN", deposit_amount, trxn_type
    elif "loan" in narration:
        return "LOAN TRXN", withdrawal_amount, trxn_type
    elif "payment bounce" in narration:
        return "PAYMENT BOUNCE", withdrawal_amount, trxn_type
    elif "salary" in narration:
        return "SALARY TRXN", deposit_amount, trxn_type
    else:
        return "OTHER", 0, trxn_type


# Function to replace NaN with empty strings
def replace_nan_with_empty(value):
    if pd.isna(value):
        return ""
    return value


# Function to parse balance string safely
def parse_balance(balance_str):
    balance_str = balance_str.replace(",", "").strip()
    balance_str = re.sub(r"[^\d.]", "", balance_str)  # Remove any non-numeric characters except dot
    try:
        return float(balance_str)
    except ValueError:
        return 0.0


# Function to format narration as "string1","string2"
def format_narration(narration):
    parts = [part.strip() for part in narration.split(',') if part.strip()]
    return ", ".join([f'"{part}"' for part in parts])


def extract_data_from_text(text):
    data = {
        "account_number": "",
        "customer_address": "",
        "customer_name": "",
        "ifsc_code": "",
        "statement_period": {
            "from_date": "",
            "to_date": ""
        }
    }

    # Regex patterns
    account_number_pattern = re.compile(r'ACCOUNT TYPE\s*(?:[^\d]*)(\d{12,})')
    address_pattern = re.compile(r'\d{1,5}[-\s\w]+(?:,\s\w+){2,}', re.IGNORECASE)
    name_pattern = re.compile(r'\bMR\.[^\d]+', re.IGNORECASE)
    ifsc_pattern = re.compile(r'IFSC Code:\s*([A-Z0-9]+)', re.IGNORECASE)
    period_pattern = re.compile(
        r'Statement of Transactions in Savings Account Number:.*?for the period (\w+ \d{2}, \d{4}) - (\w+ \d{2}, \d{4})',
        re.DOTALL)

    # Extract data
    account_number_match = account_number_pattern.search(text)
    if account_number_match:
        data["account_number"] = account_number_match.group(1)

    address_match = address_pattern.search(text)
    if address_match:
        data["customer_address"] = address_match.group().strip()

    name_match = name_pattern.search(text)
    if name_match:
        data["customer_name"] = name_match.group().strip()

    ifsc_match = ifsc_pattern.search(text)
    if ifsc_match:
        data["ifsc_code"] = ifsc_match.group(1).strip()

    period_match = period_pattern.search(text)
    if period_match:
        data["statement_period"]["from_date"] = period_match.group(1).strip()
        data["statement_period"]["to_date"] = period_match.group(2).strip()

    return data


def process_icici_bank_statement(path_to_sample_documents: str):
    result = None
    try:
        if not os.path.exists(path_to_sample_documents):
            raise ValueError("File does not exist")
        with open(path_to_sample_documents, "rb") as f:
            poller = document_intelligence_client.begin_analyze_document(
                model_id="prebuilt-layout",
                analyze_request=f,
                features=[DocumentAnalysisFeature.KEY_VALUE_PAIRS],
                content_type="application/octet-stream",
            )
            result = poller.result()
    except Exception as e:
        print(f"Error during document analysis: {e}")
        raise ValueError("UNABLE TO READ THE DOCUMENT")

    if not result:
        raise ValueError("No result from document analysis")
    if result.pages:
        first_page = result.pages[0]
        first_page_text = []
        for line in first_page.lines:
            first_page_text.append(line.content.strip())  # Strip any leading/trailing whitespace
        first_page_text_str = " ".join(first_page_text)  # Join all lines into a single string

        # Check if "ICICI Bank" is in the first page text
        if "ICICI Bank".lower() not in first_page_text_str.lower():
            raise ValueError("INCORRECT_BANK_STATEMENT")
    else:
        return []

    for page_number, page in enumerate(result.pages, start=1):
        page_text = []
        for line in page.lines:
            page_text.append(line.content)

    # Extract and process text data
    parsing_status = "false"
    if result.pages:
        parsing_status = "true"

        first_page = result.pages[0]
        text = "\n".join([line.content for line in first_page.lines])

        # Extract account details from text
        account_details = extract_data_from_text(text)

        # Extract key-value pairs
        key_value_pairs = {}
        if result.key_value_pairs:
            for kv_pair in result.key_value_pairs:
                if kv_pair.key and kv_pair.value:
                    key_value_pairs[kv_pair.key.content.strip()] = kv_pair.value.content.strip()

        # Process tables
        tables = []
        if result.tables:
            for table in result.tables:
                data = []
                for row_idx in range(table.row_count):
                    row_data = []
                    for column_idx in range(table.column_count):
                        cell = [cell for cell in table.cells if
                                cell.row_index == row_idx and cell.column_index == column_idx]
                        if cell:
                            row_data.append(cell[0].content)
                        else:
                            row_data.append(None)
                    data.append(row_data)
                df = pd.DataFrame(data[1:], columns=data[0])
                # Add suffix to column names to avoid duplicates
                df.columns = [f"{col}_{i}" for i, col in enumerate(df.columns)]
                tables.append(df)

        # Convert the combined DataFrame to a list of flattened dictionaries (records)
        if tables:
            combined_df = pd.concat(tables, ignore_index=True, sort=False)
        else:
            combined_df = pd.DataFrame()

        flattened_dict = combined_df.to_dict('records')

        # Process transactions and organize into analyzed_details
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

        for transaction in flattened_dict:
            classification, amount, trxn_type = classify_transaction(transaction)
            balance_str = str(transaction.get("BALANCE_5", "0"))
            balance = parse_balance(balance_str)

            transaction_detail = {
                "amount": replace_nan_with_empty(amount),
                "balance": replace_nan_with_empty(balance),
                "date": replace_nan_with_empty(transaction.get("DATE_0", "")),
                "narration": format_narration(replace_nan_with_empty(transaction.get("PARTICULARS_2", ""))),
                "trxn_type": replace_nan_with_empty(trxn_type)
            }
            analyzed_details["trxn_details"].append(transaction_detail)

            if classification == "CASH DEPOSIT":
                analyzed_details["CASH DEPOSITS"].append(transaction_detail)
            elif classification == "CASH WITHDRAWAL":
                analyzed_details["CASH WITHDRAWALS"].append(transaction_detail)
            elif classification == "CHEQUE DEPOSIT":
                analyzed_details["CHEQUE DEPOSITS"].append(transaction_detail)
            elif classification == "CHEQUE WITHDRAWAL":
                analyzed_details["CHEQUE WITHDRAWALS"].append(transaction_detail)
            elif classification == "SALARY":
                analyzed_details["SALARY"].append(transaction_detail)
            elif classification == "ECS BOUNCE":
                analyzed_details["ECS BOUNCES"].append(transaction_detail)
            elif classification == "EMI TRXN":
                analyzed_details["EMI TRXN"].append(transaction_detail)
            elif classification == "LOAN TRXN":
                analyzed_details["LOAN TRXN"].append(transaction_detail)
            elif classification == "PAYMENT BOUNCE":
                analyzed_details["PAYMENT BOUNCES"].append(transaction_detail)
            elif classification == "SALARY TRXN":
                analyzed_details["SALARY TRXN"].append(transaction_detail)
            else:
                pass

            # Add EOD balance for each transaction date
            date_str = transaction.get("DATE_0", "")
            try:
                date = pd.to_datetime(date_str, dayfirst=True, errors='coerce')
                if pd.notnull(date):
                    analyzed_details["EOD BALANCE"]["daywise_eod_balance"].append({
                        "date": replace_nan_with_empty(date_str),
                        "balance": replace_nan_with_empty(balance)
                    })
            except ValueError:
                pass

        # Calculate monthwise EOD balance statistics
        if analyzed_details["EOD BALANCE"]["daywise_eod_balance"]:
            eod_df = pd.DataFrame(analyzed_details["EOD BALANCE"]["daywise_eod_balance"])
            eod_df['date'] = pd.to_datetime(eod_df['date'], dayfirst=True, errors='coerce')
            eod_df = eod_df.dropna(subset=['date'])
            eod_df['month'] = eod_df['date'].dt.to_period('M').astype(str)

            monthwise_stats = eod_df.groupby('month')['balance'].agg(
                ['mean', 'min', 'max', lambda x: x.quantile(0.25), lambda x: x.quantile(0.50),
                 lambda x: x.quantile(0.75)])
            monthwise_stats.columns = ['avg eod balance', 'min eod balance', 'max eod balance',
                                       '25th percentile eod balance', '50th percentile eod balance',
                                       '75th percentile eod balance']
            analyzed_details["EOD BALANCE"]["monthwise_eod_balance"] = monthwise_stats.reset_index().to_dict('records')

        # Final output with added fraud details and parsing status
        final_output = {
            "account_details": account_details,
            "analyzed_details": analyzed_details,
            "fraud_details": {
                "fraud_flag": "false",
                "fraud_markers": []
            },
            "parsing_status": parsing_status
        }
    return final_output


if __name__ == "__main__":
    path_to_sample_documents = "/path/to/your/icici_bank_statement.pdf"
    process_icici_bank_statement(path_to_sample_documents)