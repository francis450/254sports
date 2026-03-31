import frappe
from frappe import _
from frappe.utils import nowdate, now_datetime


@frappe.whitelist()
def get_warehouses():
    """Return all warehouses for the warehouse toggle."""
    warehouses = frappe.get_all(
        "Warehouse",
        filters={"is_group": 0, "disabled": 0, "warehouse_type": ["!=", "Transit"]},
        fields=["name", "warehouse_name"],
        order_by="warehouse_name asc",
    )
    return warehouses


@frappe.whitelist()
def search_items(query, warehouse):
    """Search items by name/code with stock level from Bin for the given warehouse."""
    if not query:
        return []

    items = frappe.db.sql(
        """
        SELECT
            i.name,
            i.item_name,
            i.item_code,
            i.standard_rate,
            i.stock_uom,
            COALESCE(b.actual_qty, 0) AS actual_qty
        FROM `tabItem` i
        LEFT JOIN `tabBin` b
            ON b.item_code = i.item_code
            AND b.warehouse = %(warehouse)s
        WHERE
            i.disabled = 0
            AND i.is_sales_item = 1
            AND (
                i.item_name LIKE %(q)s
                OR i.item_code LIKE %(q)s
            )
        ORDER BY i.item_name ASC
        LIMIT 20
        """,
        {"q": f"%{query}%", "warehouse": warehouse},
        as_dict=True,
    )
    return items


@frappe.whitelist()
def get_today_sales(warehouse):
    """Return all Sales Invoices posted today for the given warehouse."""
    today = nowdate()
    invoices = frappe.db.sql(
        """
        SELECT
            si.name,
            si.customer,
            si.grand_total,
            si.posting_time,
            si.outstanding_amount,
            si.status,
            GROUP_CONCAT(
                CONCAT(sii.qty, 'x ', sii.item_name)
                ORDER BY sii.idx ASC
                SEPARATOR ', '
            ) AS items_summary
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE
            si.docstatus = 1
            AND si.posting_date = %(today)s
            AND (
                si.set_warehouse = %(warehouse)s
                OR (si.set_warehouse IS NULL AND sii.warehouse = %(warehouse)s)
                OR (si.set_warehouse = '' AND sii.warehouse = %(warehouse)s)
            )
        GROUP BY si.name
        ORDER BY si.posting_time DESC
        """,
        {"today": today, "warehouse": warehouse},
        as_dict=True,
    )
    return invoices


@frappe.whitelist(methods=["POST"])
def submit_quick_sale(customer_name, warehouse, items, payment_mode):
    """
    Execute a complete sale in one server-side transaction:
    1. Resolve / create customer
    2. Create + submit Sales Invoice (with update_stock)
    3. Create + submit Payment Entry for non-credit modes
    4. Return invoice name and total
    """
    import json

    if isinstance(items, str):
        items = json.loads(items)

    if not items:
        frappe.throw(_("Please add at least one item."))

    # ── 1. Resolve customer ────────────────────────────────────────────────────
    customer_name = (customer_name or "").strip()

    if not customer_name:
        resolved_customer = _get_walkin_customer()
    elif frappe.db.exists("Customer", customer_name):
        resolved_customer = customer_name
    else:
        resolved_customer = _create_customer(customer_name)

    # ── 2. Build Sales Invoice ─────────────────────────────────────────────────
    invoice = frappe.new_doc("Sales Invoice")
    invoice.customer = resolved_customer
    invoice.posting_date = nowdate()
    invoice.posting_time = now_datetime().strftime("%H:%M:%S")
    invoice.set_warehouse = warehouse
    invoice.update_stock = 1  # deduct stock at invoice submission
    invoice.is_pos = 0  # prevent POS validation; payments handled via Payment Entry

    # Determine income account (default)
    company = frappe.defaults.get_defaults().get("company") or frappe.db.get_single_value(
        "Global Defaults", "default_company"
    )
    invoice.company = company

    for row in items:
        invoice.append(
            "items",
            {
                "item_code": row.get("item_code"),
                "qty": float(row.get("qty", 1)),
                "rate": float(row.get("rate", 0)),
                "warehouse": warehouse,
            },
        )

    invoice.insert(ignore_permissions=True)
    invoice.submit()

    # ── 3. Payment Entry for paid modes ───────────────────────────────────────
    if payment_mode != "Credit":
        mode_map = {
            "Cash": _get_cash_account(company),
            "M-Pesa": _get_mpesa_account(company),
            "Bank Transfer": _get_bank_account(company),
        }
        paid_to = mode_map.get(payment_mode) or _get_cash_account(company)

        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Receive"
        pe.company = company
        pe.posting_date = nowdate()
        pe.party_type = "Customer"
        pe.party = resolved_customer
        pe.paid_amount = invoice.grand_total
        pe.received_amount = invoice.grand_total
        pe.paid_to = paid_to
        pe.paid_from = frappe.db.get_value(
            "Company", company, "default_receivable_account"
        )
        pe.reference_no = invoice.name
        pe.reference_date = nowdate()
        pe.append(
            "references",
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": invoice.name,
                "allocated_amount": invoice.grand_total,
            },
        )
        pe.insert(ignore_permissions=True)
        pe.submit()

    frappe.db.commit()

    return {
        "invoice": invoice.name,
        "total": invoice.grand_total,
        "customer": resolved_customer,
        "status": "Paid" if payment_mode != "Credit" else "Credit",
    }


# ── Helpers ────────────────────────────────────────────────────────────────────


def _get_walkin_customer():
    walkin_name = "Walk-in Customer"
    if frappe.db.exists("Customer", walkin_name):
        return walkin_name
    # fallback: create it
    return _create_customer(walkin_name, is_walkin=True)


def _create_customer(name, is_walkin=False):
    group = _get_walkin_group()
    c = frappe.new_doc("Customer")
    c.customer_name = name
    c.customer_type = "Individual"
    c.customer_group = group
    c.territory = frappe.db.get_single_value("Selling Settings", "territory") or "Kenya"
    c.insert(ignore_permissions=True)
    return c.name


def _get_walkin_group():
    if frappe.db.exists("Customer Group", "Walk-in"):
        return "Walk-in"
    # fall back to default
    default = frappe.db.get_single_value("Selling Settings", "customer_group")
    return default or "All Customer Groups"


def _get_cash_account(company):
    acc = frappe.db.get_value(
        "Account",
        {"account_type": "Cash", "company": company, "is_group": 0},
        "name",
    )
    if not acc:
        acc = frappe.db.get_value("Company", company, "default_cash_account")
    return acc


def _get_bank_account(company):
    acc = frappe.db.get_value(
        "Account",
        {"account_type": "Bank", "company": company, "is_group": 0},
        "name",
    )
    if not acc:
        acc = _get_cash_account(company)
    return acc


def _get_mpesa_account(company):
    # Look for an account with "mpesa" in the name (case-insensitive)
    acc = frappe.db.get_value(
        "Account",
        {
            "company": company,
            "is_group": 0,
            "account_name": ["like", "%mpesa%"],
        },
        "name",
    )
    if not acc:
        acc = frappe.db.get_value(
            "Account",
            {
                "company": company,
                "is_group": 0,
                "account_name": ["like", "%M-Pesa%"],
            },
            "name",
        )
    if not acc:
        acc = _get_cash_account(company)
    return acc
