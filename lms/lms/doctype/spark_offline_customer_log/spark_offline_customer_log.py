# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class SparkOfflineCustomerLog(Document):
    def before_save(self):
        if (
            self.user_status == "Success"
            and self.customer_status == "Success"
            and self.ckyc_status == "Success"
            and self.bank_status == "Success"
        ):
            self.status = "Success"
        elif (
            self.user_status == "Failure"
            and self.customer_status == "Failure"
            and self.ckyc_status == "Failure"
            and self.bank_status == "Failure"
        ):
            self.status = "Failure"
        else:
            self.status = "Partial Success"
