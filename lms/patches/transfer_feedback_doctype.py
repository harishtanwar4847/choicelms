import frappe


def execute():
    frappe.db.sql("INSERT INTO `tabSpark Feedback` SELECT * FROM `tabFeedback`;")
    frappe.delete_doc("DocType", "Feedback")
    frappe.db.commit()
    # frappe.db.sql("DROP TABLE `tabFeedback`;")
    frappe.db.sql_ddl("DROP TABLE IF EXISTS `tabFeedback`;")
    frappe.db.commit()
