# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SparkPushNotificationLog(Document):
    def autoname(self):
        self.name = "{}-{}".format(
            self.loan_customer,
            str(self.time.strftime("%d %b at %H:%M %p")).replace(" ", "-"),
        )
