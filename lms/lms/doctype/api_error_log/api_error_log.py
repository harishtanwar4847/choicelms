# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class APIErrorLog(Document):
    def onload(self):
        if not self.seen:
            self.db_set("seen", 1, update_modified=0)
            frappe.db.commit()


# def set_old_logs_as_seen():
# 	# set logs as seen
# 	frappe.db.sql("""UPDATE `tabAPI Error Log` SET `seen`=1
# 		WHERE `seen`=0 AND `creation` < (NOW() - INTERVAL '7' DAY)""")

# @frappe.whitelist()
# def clear_error_logs():
# 	'''Flush all API Error Logs'''
# 	frappe.only_for('System Manager')
# 	frappe.db.sql('''DELETE FROM `tabAPI Error Log`''')
