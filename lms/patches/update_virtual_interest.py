import frappe


def execute():
    frappe.db.begin()
    virtual_interests = frappe.get_all("Virtual Interest", fields=["*"])
    for virtual_interest in virtual_interests:
        frappe.db.sql("""
        update `tabVirtual Interest` set customer_name = (select customer_name from `tabLoan` where name = '{}')
        """.format(virtual_interest.loan))
    frappe.db.commit()
