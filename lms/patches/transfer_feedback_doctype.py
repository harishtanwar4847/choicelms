import frappe


def execute():
    frappe.db.sql_ddl(
        "CREATE TABLE `tabSpark Feedback` AS (SELECT * FROM `tabFeedback`);"
    )
    frappe.delete_doc("DocType", "Feedback")
    frappe.db.sql_ddl("drop table if exists `tabFeedback`")
    frappe.db.commit()
