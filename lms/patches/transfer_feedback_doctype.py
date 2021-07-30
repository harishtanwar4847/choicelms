import frappe


def execute():
    frappe.db.sql("INSERT INTO `tabSpark Feedback` SELECT * FROM `tabFeedbacks`;")
    frappe.delete_doc("DocType", "Feedbacks")
    frappe.db.commit()
    frappe.db.sql("DROP TABLE `tabFeedbacks`;")
