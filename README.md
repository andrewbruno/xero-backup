# Xero Business Account Backup

Back up all data from a Xero business account before closure. Exports everything as JSON + CSV files, fetches financial reports, and downloads all file attachments.

## What Gets Backed Up

**Entities (JSON + CSV):**
Contacts, Invoices, Accounts, Bank Transactions, Payments, Manual Journals, Credit Notes, Purchase Orders, Items, Tax Rates, Bank Transfers, Linked Transactions, Overpayments, Prepayments, Employees, Expense Claims, Quotes, Repeating Invoices, Tracking Categories, Currencies, Branding Themes, Organisation details

**Reports (JSON + CSV):**
Trial Balance, Balance Sheet, Profit & Loss, Aged Receivables, Aged Payables, Bank Summary

**Attachments:**
All files attached to invoices, bills, contacts, bank transactions, etc.

## Setup

### 1. Register a Xero App

1. Go to https://developer.xero.com/app/manage
2. Click **New app**
3. Choose **Web app**
4. Set the redirect URI to: `http://localhost:8484/callback`
5. Note your **Client ID** and **Client Secret**

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Credentials

```bash
cp .env.example .env
```

Edit `.env` and fill in your Client ID and Client Secret:

```
XERO_CLIENT_ID=your_client_id_here
XERO_CLIENT_SECRET=your_client_secret_here
```

## Usage

### Full Backup

```bash
python backup.py
```

On first run, your browser will open for Xero authorization. Log in and authorize the app. Tokens are saved to `.xero_tokens.json` so subsequent runs won't require re-authorization (tokens last 60 days).

### Options

```bash
# Verbose output (debug logging)
python backup.py --verbose

# Custom output directory
python backup.py --output-dir ./my-backups

# Skip attachments (faster, data-only backup)
python backup.py --skip-attachments

# Skip financial reports
python backup.py --skip-reports

# Back up specific entities only
python backup.py --entities invoices,contacts,payments

# Combine options
python backup.py --skip-attachments --skip-reports --entities invoices,contacts
```

## Output Structure

```
backups/
  2026-02-26T14-30-00/
    json/                     # Full JSON data (authoritative backup)
      contacts.json
      invoices.json
      accounts.json
      ...
    csv/                      # Flattened CSV (human-readable)
      contacts.csv
      invoices.csv
      accounts.csv
      ...
    reports/                  # Financial reports
      trial_balance.json
      trial_balance.csv
      balance_sheet.json
      balance_sheet.csv
      ...
    attachments/              # Downloaded files
      invoices/{InvoiceID}/
        receipt.pdf
      contacts/{ContactID}/
        logo.png
      ...
    backup_manifest.json      # Summary with counts, errors, duration
    backup.log                # Detailed log file
```

## Rate Limits

The tool respects Xero's API rate limits (60 calls/min, 5000 calls/day per organisation). For a typical small business, a full backup uses ~250 API calls and takes a few minutes. Larger accounts with thousands of invoices and attachments may take 30+ minutes.

## Re-running

The tool is safe to re-run:
- Each run creates a new timestamped directory
- Attachment downloads are idempotent (existing files are skipped)
- Token refresh is automatic
