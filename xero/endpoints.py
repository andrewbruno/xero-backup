"""Xero API endpoint definitions and entity registry."""

from dataclasses import dataclass


@dataclass
class EntityDef:
    """Definition of a Xero API entity for backup."""

    name: str           # Human-readable name (used for filenames)
    endpoint: str       # API endpoint path (e.g., "Invoices")
    response_key: str   # JSON key containing the record array
    paginated: bool = True
    has_attachments: bool = False
    id_field: str = ""  # Primary key field name


# All entities to back up, in priority order
ENTITY_REGISTRY = [
    # Priority 1 - Core Financial
    EntityDef("contacts", "Contacts", "Contacts",
              has_attachments=True, id_field="ContactID"),
    EntityDef("invoices", "Invoices", "Invoices",
              has_attachments=True, id_field="InvoiceID"),
    EntityDef("accounts", "Accounts", "Accounts",
              paginated=False, has_attachments=True, id_field="AccountID"),
    EntityDef("bank_transactions", "BankTransactions", "BankTransactions",
              has_attachments=True, id_field="BankTransactionID"),

    # Priority 2 - Supporting Records
    EntityDef("payments", "Payments", "Payments",
              id_field="PaymentID"),
    EntityDef("manual_journals", "ManualJournals", "ManualJournals",
              has_attachments=True, id_field="ManualJournalID"),
    EntityDef("credit_notes", "CreditNotes", "CreditNotes",
              has_attachments=True, id_field="CreditNoteID"),
    EntityDef("purchase_orders", "PurchaseOrders", "PurchaseOrders",
              has_attachments=True, id_field="PurchaseOrderID"),
    EntityDef("items", "Items", "Items",
              paginated=False, id_field="ItemID"),
    EntityDef("tax_rates", "TaxRates", "TaxRates",
              paginated=False, id_field="Name"),
    EntityDef("bank_transfers", "BankTransfers", "BankTransfers",
              paginated=False, has_attachments=True, id_field="BankTransferID"),
    EntityDef("linked_transactions", "LinkedTransactions", "LinkedTransactions",
              id_field="LinkedTransactionID"),
    EntityDef("overpayments", "Overpayments", "Overpayments",
              has_attachments=True, id_field="OverpaymentID"),
    EntityDef("prepayments", "Prepayments", "Prepayments",
              has_attachments=True, id_field="PrepaymentID"),

    # Priority 3 - Optional / Reference Data
    EntityDef("employees", "Employees", "Employees",
              paginated=False, id_field="EmployeeID"),
    EntityDef("expense_claims", "ExpenseClaims", "ExpenseClaims",
              paginated=False, id_field="ExpenseClaimID"),
    EntityDef("quotes", "Quotes", "Quotes",
              has_attachments=True, id_field="QuoteID"),
    EntityDef("repeating_invoices", "RepeatingInvoices", "RepeatingInvoices",
              paginated=False, has_attachments=True, id_field="RepeatingInvoiceID"),
    EntityDef("tracking_categories", "TrackingCategories", "TrackingCategories",
              paginated=False, id_field="TrackingCategoryID"),
    EntityDef("currencies", "Currencies", "Currencies",
              paginated=False, id_field="Code"),
    EntityDef("branding_themes", "BrandingThemes", "BrandingThemes",
              paginated=False, id_field="BrandingThemeID"),
    EntityDef("organisations", "Organisation", "Organisations",
              paginated=False, id_field="OrganisationID"),
]

# Entities that support attachments
ATTACHMENT_ENTITIES = [e for e in ENTITY_REGISTRY if e.has_attachments]
