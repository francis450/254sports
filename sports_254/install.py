import frappe


def after_install():
    """Post-install setup for 254 Sports."""
    _ensure_walkin_customer_group()
    _ensure_walkin_customer()


def _ensure_walkin_customer_group():
    if frappe.db.exists("Customer Group", "Walk-in"):
        return
    try:
        group = frappe.new_doc("Customer Group")
        group.customer_group_name = "Walk-in"
        group.parent_customer_group = "All Customer Groups"
        group.insert(ignore_permissions=True)
        frappe.db.commit()
        print("Created Customer Group: Walk-in")
    except Exception as e:
        print(f"Could not create Walk-in Customer Group: {e}")


def _ensure_walkin_customer():
    if frappe.db.exists("Customer", "Walk-in Customer"):
        return
    try:
        group = "Walk-in" if frappe.db.exists("Customer Group", "Walk-in") else "All Customer Groups"
        c = frappe.new_doc("Customer")
        c.customer_name = "Walk-in Customer"
        c.customer_type = "Individual"
        c.customer_group = group
        c.territory = frappe.db.get_single_value("Selling Settings", "territory") or "Kenya"
        c.insert(ignore_permissions=True)
        frappe.db.commit()
        print("Created Customer: Walk-in Customer")
    except Exception as e:
        print(f"Could not create Walk-in Customer: {e}")
