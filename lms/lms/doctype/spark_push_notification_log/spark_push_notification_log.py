# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SparkPushNotificationLog(Document):
    def autoname(self):
        self.name = "SPNL-{}-{}".format(
            self.notification_id, str(self.time).replace(" ", "-")
        )
