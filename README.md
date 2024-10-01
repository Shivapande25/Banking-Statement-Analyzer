# Banking-Statement-Analyzer
The Financial Statement Analyzer is a Python tool for parsing bank statements from ICICI Bank and SBI. It extracts account details, categorizes transactions, tracks end-of-day balances, and provides basic fraud detection. This project facilitates financial analysis and can be easily extended to support other banks.


## Table of Contents
- Overview
- Supported Banks
- Goals
- Installation
- Usage
- Output Structure
- Dependencies
- To do

## Overview:
The Bank Statement Parser processes PDF-based bank statements, extracts key financial information, and categorizes transactions into various types such as UPI, IMPS, NEFT, salary, cheque deposits, etc. The extracted data can then be utilized for financial analysis, fraud detection, and more.

## Supported Banks:
- ICICI Bank: Handles ICICI bank statements.
- SBI (State Bank of India): Similar functionality is provided for SBI bank statements.

## Goals
Goals
The key objectives of the Bank Statement Parser include:
1. Extracting Key Account Information: Automatically pull account numbers, IFSC codes, customer names, and addresses from the bank statements.
2. Transaction Categorization: Classify transactions into categories such as salary, cash deposits/withdrawals, cheque transactions, loan payments, EMI, and more.
3. Balance Tracking: Track end-of-day (EOD) balance for each transaction day and compute month-wise statistics like the average, minimum, and maximum EOD balances.
4. Fraud Detection: Basic fraud flagging mechanism based on transaction patterns and markers.
5. Customizable for Multiple Banks: Although the current implementation supports ICICI and SBI, it can be extended to handle other bank formats with minor adjustments.
6. Detailed Analysis: Provides a breakdown of the financial activities with easy-to-understand transaction details.

### Installation
1. Clone the repository:
   ```
   git clone https://github.com/yourusername/bank-statement-parser.git
   cd bank-statement-parser
   ```
2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Set up your Azure API credentials:
   You’ll need an Azure Document Intelligence account for PDF analysis. Export your credentials as environment variables:
   ```
   export AZURE_DOCUMENT_API_KEY="your-azure-api-key"
   export AZURE_DOCUMENT_ENDPOINT="your-azure-endpoint"
   ```
4. Usage:
   1. Place the Bank Statement PDF: Place the ICICI or SBI bank statement PDF in the project directory.
   2. Modify the script to point to your PDF file: In the ```bank_statement_parser.py```file, change the file path to your specific bank statement:
   ```
   path_to_sample_documents = "/path/to/your/icici_bank_statement.pdf"
   ```
   3. Run the parser:
   ```
   python bank_statement_parser.py
   ```

### Output Structure
The script generates a structured output containing:

#### Account Details:
Account Number
Customer Name and Address
IFSC Code
Statement Period

#### Transaction Details: 
Transactions are categorized and structured as:
Cash Deposits
Cash Withdrawals
Cheque Deposits/Withdrawals
Salary Transactions
EMI and Loan Transactions
Payment and ECS Bounces
Others

#### EOD Balance:
Day-wise End-of-Day balance tracking
Month-wise statistics for EOD balance, including average, minimum, and maximum balances.
Fraud Detection: A basic fraud flagging mechanism that identifies unusual transaction patterns based on predefined rules.

### Dependencies 
The required Python packages are listed in the ```requirements.txt``` file. Install them with:
```
pip install -r requirements.txt
```
Key dependencies include:
```pandas```: For data manipulation and EOD balance calculations.
```azure-ai-documentintelligence```: For processing bank statement PDFs using Azure’s Document Intelligence API.
```re```: For regular expression-based data extraction.
```json```: For handling JSON outputs.

### To-Do
1. Extend Support for Additional Banks: Expand parsing capability for other banks beyond ICICI and SBI.
2. Enhanced Fraud Detection: Implement more robust fraud detection logic with machine learning.
3. Optimize for Performance: Improve efficiency when processing large bank statements with thousands of transactions.

