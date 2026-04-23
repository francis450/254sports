import frappe
from frappe import _
from frappe.utils import nowdate, now_datetime, getdate, add_days, get_first_day


@frappe.whitelist()
def get_warehouses():
    """Return warehouses for the warehouse toggle, scoped to the user's permissions."""
    warehouses = frappe.get_all(
        "Warehouse",
        filters={"is_group": 0, "disabled": 0, "warehouse_type": ["!=", "Transit"]},
        fields=["name", "warehouse_name"],
        order_by="warehouse_name asc",
    )
    allowed = _get_allowed_warehouses()
    if allowed is not None:
        warehouses = [w for w in warehouses if w.name in allowed]
    return warehouses


@frappe.whitelist()
def search_items(query, warehouse):
    """Search items by name/code with stock level from Bin for the given warehouse."""
    if not query:
        return []
    _require_allowed_warehouse(warehouse, _("You do not have permission to access warehouse {0}."))

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
    allowed = _get_allowed_warehouses()
    if allowed is not None and warehouse not in allowed:
        frappe.throw(_("You do not have permission to access warehouse {0}.").format(warehouse))
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

    _require_allowed_warehouse(
        warehouse, _("You do not have permission to record sales for warehouse {0}.")
    )

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


@frappe.whitelist(methods=["POST"])
def mark_invoice_paid(invoice_name, payment_mode):
    """
    Create and submit a Payment Entry for an existing outstanding Sales Invoice,
    marking it as paid. Called from the Quick Sale feed's "Mark Paid" button.
    """
    invoice = frappe.get_doc("Sales Invoice", invoice_name)
    invoice_warehouse = _get_sales_invoice_warehouse(invoice_name)
    _require_allowed_warehouse(
        invoice_warehouse, _("You do not have permission to access warehouse {0}.")
    )

    if invoice.docstatus != 1:
        frappe.throw(_("Invoice {0} is not submitted.").format(invoice_name))
    if (invoice.outstanding_amount or 0) <= 0:
        frappe.throw(_("Invoice {0} has no outstanding amount.").format(invoice_name))

    company = invoice.company

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
    pe.party = invoice.customer
    pe.paid_amount = invoice.outstanding_amount
    pe.received_amount = invoice.outstanding_amount
    pe.paid_to = paid_to
    pe.paid_from = frappe.db.get_value("Company", company, "default_receivable_account")
    pe.reference_no = invoice.name
    pe.reference_date = nowdate()
    pe.append(
        "references",
        {
            "reference_doctype": "Sales Invoice",
            "reference_name": invoice.name,
            "allocated_amount": invoice.outstanding_amount,
        },
    )
    pe.insert(ignore_permissions=True)
    pe.submit()
    frappe.db.commit()

    return {"payment_entry": pe.name, "invoice": invoice_name}


@frappe.whitelist()
def get_period_sales(warehouse, period="today"):
    """Return Sales Invoices for the given warehouse within the requested period.
    period: "today" | "week" (Mon–today) | "month" (1st–today)
    """
    _require_allowed_warehouse(warehouse, _("You do not have permission to access warehouse {0}."))
    today = nowdate()

    if period == "week":
        from_date = add_days(today, -getdate(today).weekday())  # rewind to Monday
    elif period == "month":
        from_date = str(get_first_day(today))
    else:
        from_date = today

    invoices = frappe.db.sql(
        """
        SELECT
            si.name,
            si.customer,
            si.grand_total,
            si.posting_date,
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
            AND si.posting_date BETWEEN %(from_date)s AND %(today)s
            AND (
                si.set_warehouse = %(warehouse)s
                OR (si.set_warehouse IS NULL AND sii.warehouse = %(warehouse)s)
                OR (si.set_warehouse = '' AND sii.warehouse = %(warehouse)s)
            )
        GROUP BY si.name
        ORDER BY si.posting_date DESC, si.posting_time DESC
        """,
        {"from_date": from_date, "today": today, "warehouse": warehouse},
        as_dict=True,
    )
    return invoices


@frappe.whitelist()
def get_item_groups():
    """Return leaf item groups for the category filter."""
    return frappe.get_all(
        "Item Group",
        filters={"is_group": 0},
        fields=["name"],
        order_by="name asc",
    )


@frappe.whitelist()
def get_sales_report(from_date, to_date, payment_status="All", customer=None,
                     item_code=None, item_group=None, warehouse=None):
    """
    Return filtered sales data for the Sales Report page.
    Runs two queries:
      1. Invoices matching all filters.
      2. Credit customers summary (outstanding > 0, same date/optional filters).
    """
    # ── Build shared conditions & values ──────────────────────────────────────
    conditions = [
        "si.docstatus = 1",
        "si.posting_date BETWEEN %(from_date)s AND %(to_date)s",
    ]
    values = {"from_date": from_date, "to_date": to_date}

    # Enforce User Permission warehouse restrictions
    allowed = _get_allowed_warehouses()
    if warehouse:
        _require_allowed_warehouse(
            warehouse, _("You do not have permission to view data for warehouse {0}.")
        )
    if not warehouse and allowed is not None:
        wh_list_sql = ", ".join(frappe.db.escape(w) for w in allowed)
        conditions.append(
            f"(si.set_warehouse IN ({wh_list_sql}) OR sii.warehouse IN ({wh_list_sql}))"
        )

    need_item_join = False

    if customer:
        conditions.append("si.customer LIKE %(customer)s")
        values["customer"] = f"%{customer}%"

    if item_code:
        conditions.append(
            "(sii.item_code LIKE %(item_code)s OR sii.item_name LIKE %(item_code)s)"
        )
        values["item_code"] = f"%{item_code}%"

    if item_group:
        conditions.append("i.item_group = %(item_group)s")
        values["item_group"] = item_group
        need_item_join = True

    if warehouse:
        conditions.append(
            "(si.set_warehouse = %(warehouse)s OR sii.warehouse = %(warehouse)s)"
        )
        values["warehouse"] = warehouse

    item_join = (
        "LEFT JOIN `tabItem` i ON i.item_code = sii.item_code"
        if need_item_join else ""
    )

    # ── 1. Invoices query ──────────────────────────────────────────────────────
    invoice_conditions = list(conditions)
    if payment_status == "Paid":
        invoice_conditions.append("si.outstanding_amount = 0")
    elif payment_status == "Credit":
        invoice_conditions.append("si.outstanding_amount > 0")

    where_invoices = " AND ".join(invoice_conditions)

    invoices = frappe.db.sql(
        f"""
        SELECT
            si.name,
            si.customer,
            si.posting_date,
            si.posting_time,
            si.grand_total,
            si.outstanding_amount,
            si.status,
            GROUP_CONCAT(
                CONCAT(sii.qty, 'x ', sii.item_name)
                ORDER BY sii.idx ASC
                SEPARATOR ', '
            ) AS items_summary
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        {item_join}
        WHERE {where_invoices}
        GROUP BY si.name
        ORDER BY si.posting_date DESC, si.posting_time DESC
        """,
        values,
        as_dict=True,
    )

    # ── 2. Credit customers summary ────────────────────────────────────────────
    credit_conditions = list(conditions)
    credit_conditions.append("si.outstanding_amount > 0")
    where_credit = " AND ".join(credit_conditions)

    credit_customers = frappe.db.sql(
        f"""
        SELECT
            si.customer,
            SUM(si.outstanding_amount) AS total_outstanding,
            COUNT(si.name) AS invoice_count,
            MIN(si.posting_date) AS oldest_date
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        {item_join}
        WHERE {where_credit}
        GROUP BY si.customer
        ORDER BY total_outstanding DESC
        """,
        values,
        as_dict=True,
    )

    # ── 3. Summary totals ──────────────────────────────────────────────────────
    total_sales = sum(inv.grand_total or 0 for inv in invoices)
    total_outstanding = sum(inv.outstanding_amount or 0 for inv in invoices)
    total_paid = total_sales - total_outstanding
    credit_count = sum(1 for inv in invoices if (inv.outstanding_amount or 0) > 0)

    return {
        "invoices": invoices,
        "summary": {
            "total_sales": total_sales,
            "total_paid": total_paid,
            "total_outstanding": total_outstanding,
            "invoice_count": len(invoices),
            "credit_count": credit_count,
        },
        "credit_customers": credit_customers,
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


def _get_allowed_warehouses():
    """Return a set of permitted warehouse names for the current user.
    Returns None when the user is unrestricted (Administrator, System Manager,
    or no Warehouse User Permissions configured for this user).
    """
    if frappe.session.user == "Administrator":
        return None
    if "System Manager" in frappe.get_roles(frappe.session.user):
        return None
    perms = frappe.get_all(
        "User Permission",
        filters={"user": frappe.session.user, "allow": "Warehouse"},
        fields=["for_value"],
    )
    if not perms:
        return None  # no warehouse restrictions — user can access all
    return {p.for_value for p in perms}


def _require_allowed_warehouse(warehouse, permission_message=None):
    warehouse = (warehouse or "").strip()
    if not warehouse:
        frappe.throw(_("Please select a warehouse."))

    allowed = _get_allowed_warehouses()
    if allowed is not None and warehouse not in allowed:
        permission_message = permission_message or _("You do not have permission to access warehouse {0}.")
        frappe.throw(permission_message.format(warehouse))

    return warehouse


def _get_sales_invoice_warehouse(invoice_name):
    warehouse = frappe.db.get_value("Sales Invoice", invoice_name, "set_warehouse")
    if warehouse:
        return warehouse

    item_warehouses = frappe.get_all(
        "Sales Invoice Item",
        filters={"parent": invoice_name},
        pluck="warehouse",
        distinct=True,
    )
    item_warehouses = [warehouse for warehouse in item_warehouses if warehouse]
    if len(item_warehouses) == 1:
        return item_warehouses[0]

    if not item_warehouses:
        frappe.throw(_("Invoice {0} has no warehouse assigned.").format(invoice_name))

    frappe.throw(_("Invoice {0} spans multiple warehouses and cannot be handled here.").format(invoice_name))


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
