from types import new_class
from warnings import filters

import frappe
from frappe.website.utils import cleanup_page_name


def execute():
    website_settings = frappe.get_single("Website Settings")
    website_settings.head_html = (
        """<link rel="icon" href="/assets/lms/favicon.ico" type="image/x-icon" />"""
    )
    website_settings.save(ignore_permissions=True)
    frappe.db.commit()
