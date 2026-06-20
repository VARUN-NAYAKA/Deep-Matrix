MOCK_LOAN_FILE = {
    "pages": [
        {
            "page_number": 1,
            "text": """
CHASE BANK STATEMENT
Account Holder: John Doe
Account Number: *******1234
Statement Period: Oct 01, 2024 - Oct 31, 2024
Summary:
Beginning Balance: $5,230.12
Total Deposits: $3,500.00
Total Withdrawals: $2,100.00
Ending Balance: $6,630.12

Transactions:
Oct 10: Deposit - Payroll Direct Deposit - $3,000.00
Oct 15: Withdrawal - Electric Bill - $120.00
Oct 20: Deposit - Zelle Transfer - $500.00
Oct 25: Withdrawal - Grocery - $80.00
"""
        },
        {
            "page_number": 2,
            "text": """
CHASE BANK STATEMENT
Account Holder: John Doe
Account Number: *******1234
Statement Period: Nov 01, 2024 - Nov 30, 2024
Summary:
Beginning Balance: $6,630.12
Total Deposits: $3,100.00
Total Withdrawals: $1,800.00
Ending Balance: $7,930.12

Transactions:
Nov 10: Deposit - Payroll Direct Deposit - $3,000.00
Nov 12: Withdrawal - Car Loan Payment - $350.00
Nov 18: Deposit - Zelle Transfer - $100.00
Nov 28: Withdrawal - Grocery - $95.00
"""
        },
        {
            "page_number": 3,
            "text": """
CHASE BANK STATEMENT
Account Holder: John Doe
Account Number: *******1234
Statement Period: Dec 01, 2024 - Dec 31, 2024
Summary:
Beginning Balance: $7,930.12
Total Deposits: $13,400.00
Total Withdrawals: $4,500.00
Ending Balance: $16,830.12

Transactions:
Dec 10: Deposit - Payroll Direct Deposit - $3,000.00
Dec 15: Deposit - Special Bonus Transfer - $10,000.00
Dec 20: Withdrawal - Holiday shopping - $2,500.00
Dec 28: Withdrawal - Rent Payment - $2,000.00
"""
        },
        {
            "page_number": 4,
            "text": """
Form W-2 Wage and Tax Statement 2023
Copy B - To Be Filed With Employee's Federal Tax Return
OMB No. 1545-0008
Box a - Employee's social security number: ***-**-6789
Box b - Employer identification number (EIN): 12-3456789
Box c - Employer's name: Acme Tech Corporation, 100 Innovation Way, San Francisco, CA
Box e - Employee's name: John Doe
Box 1 - Wages, tips, other compensation: $95,000.00
Box 2 - Federal income tax withheld: $12,500.00
Box 3 - Social security wages: $95,000.00
Box 4 - Social security tax withheld: $5,890.00
"""
        },
        {
            "page_number": 5,
            "text": """
Form W-2 Wage and Tax Statement 2024
Copy B - To Be Filed With Employee's Federal Tax Return
OMB No. 1545-0008
Box a - Employee's social security number: ***-**-6789
Box b - Employer identification number (EIN): 12-3456789
Box c - Employer's name: Acme Tech Corporation, 100 Innovation Way, San Francisco, CA
Box e - Employee's name: John Doe
Box 1 - Wages, tips, other compensation: $102,000.00
Box 2 - Federal income tax withheld: $14,100.00
Box 3 - Social security wages: $102,000.00
Box 4 - Social security tax withheld: $6,324.00
"""
        },
        {
            "page_number": 6,
            "text": """
Acme Tech Corporation - Pay Stub
Pay Date: November 15, 2024
Employee Name: John Doe
Employee ID: EMP-998822
Pay Period: Nov 01, 2024 - Nov 15, 2024

Earnings Statement:
Regular Earnings: $4,250.00
Bonus: $0.00
Gross Pay (Current): $4,250.00
Gross Pay (Year-to-Date): $89,250.00

Deductions:
Federal Tax: $580.00
State Tax: $210.00
Health Insurance: $150.00
401k Contribution: $425.00
Net Pay: $2,885.00
"""
        },
        {
            "page_number": 7,
            "text": """
Acme Tech Corporation - Pay Stub
Pay Date: November 30, 2024
Employee Name: John Doe
Employee ID: EMP-998822
Pay Period: Nov 16, 2024 - Nov 30, 2024

Earnings Statement:
Regular Earnings: $4,250.00
Bonus: $0.00
Gross Pay (Current): $4,250.00
Gross Pay (Year-to-Date): $93,500.00

Deductions:
Federal Tax: $580.00
State Tax: $210.00
Health Insurance: $150.00
401k Contribution: $425.00
Net Pay: $2,885.00
"""
        },
        {
            "page_number": 8,
            "text": """
Department of the Treasury—Internal Revenue Service
Form 1040 U.S. Individual Income Tax Return 2024
Filing Status: Single
Taxpayer: John Doe
SSN: ***-**-6789
Wages, salaries, tips (Form W-2, Box 1): $102,000.00
Taxable Interest: $120.00
Total Income (Line 9): $102,120.00
Adjusted Gross Income (Line 11): $102,120.00
Standard Deduction: $14,600.00
Taxable Income (Line 15): $87,520.00
"""
        },
        {
            "page_number": 9,
            "text": """
CLOSING DISCLOSURE
Closing Date: Dec 15, 2024
Transaction Information:
Borrower: John Doe, 123 Main St, Seattle, WA
Seller: Jane Smith, 456 Oak Ave, Seattle, WA
Lender: Apex Mortgage Group

Loan Terms:
Loan Amount: $320,000.00
Interest Rate: 6.25%
Monthly Principal & Interest: $1,970.38
Prepayment Penalty: No
Balloon Payment: No

Projected Payments:
Payment Calculation:
Principal & Interest: $1,970.38
Estimated Escrow (Taxes & Insurance): $479.62
Total Monthly Payment (PITI): $2,450.00

Costs at Closing:
Purchase Price: $400,000.00
Loan Amount: $320,000.00
Down Payment / Funds from Borrower: $80,000.00
Closing Costs: $8,500.00
Total Cash to Close: $88,500.00
Loan Type: Conventional Fixed Rate
"""
        }
    ],
    "documents": [
        {"id": "doc_1", "doc_type": "Bank Statement", "start_page": 1, "end_page": 1, "pages": [1], "metadata": {"bank_name": "Chase"}},
        {"id": "doc_2", "doc_type": "Bank Statement", "start_page": 2, "end_page": 2, "pages": [2], "metadata": {"bank_name": "Chase"}},
        {"id": "doc_3", "doc_type": "Bank Statement", "start_page": 3, "end_page": 3, "pages": [3], "metadata": {"bank_name": "Chase"}},
        {"id": "doc_4", "doc_type": "W-2", "start_page": 4, "end_page": 4, "pages": [4], "metadata": {"tax_year": "2023"}},
        {"id": "doc_5", "doc_type": "W-2", "start_page": 5, "end_page": 5, "pages": [5], "metadata": {"tax_year": "2024"}},
        {"id": "doc_6", "doc_type": "Paystub", "start_page": 6, "end_page": 6, "pages": [6], "metadata": {}},
        {"id": "doc_7", "doc_type": "Paystub", "start_page": 7, "end_page": 7, "pages": [7], "metadata": {}},
        {"id": "doc_8", "doc_type": "Form 1040 (Tax Return)", "start_page": 8, "end_page": 8, "pages": [8], "metadata": {"tax_year": "2024"}},
        {"id": "doc_9", "doc_type": "Closing Disclosure", "start_page": 9, "end_page": 9, "pages": [9], "metadata": {}}
    ]
}
