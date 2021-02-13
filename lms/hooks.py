# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from . import __version__ as app_version

app_name = "lms"
app_title = "Lms"
app_publisher = "Atrina Technologies Pvt. Ltd."
app_description = "Loan Managment System"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "developers@atritechnocrat.com"
app_license = "MIT"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/lms/css/lms.css"
# app_include_js = "/assets/lms/js/lms.js"

# include js, css files in header of web template
# web_include_css = "/assets/lms/css/lms.css"
# web_include_js = "/assets/lms/js/lms.js"

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Website user home page (by function)
# get_website_user_home_page = "lms.utils.get_home_page"

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Installation
# ------------

# before_install = "lms.install.before_install"
after_install = "lms.after_install"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "lms.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "User": {"on_trash": "lms.delete_user"},
    "File": {
        "before_insert": "lms.lms.doctype.loan_application.loan_application.only_pdf_upload"
    },
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"lms.tasks.all"
# 	],
# 	"daily": [
# 		"lms.tasks.daily"
# 	],
# 	"hourly": [
# 		"lms.tasks.hourly"
# 	],
# 	"weekly": [
# 		"lms.tasks.weekly"
# 	]
# 	"monthly": [
# 		"lms.tasks.monthly"
# 	]
# }

# Testing
# -------

# before_tests = "lms.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "lms.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
override_doctype_dashboards = {
    # "Task": "lms.task.get_dashboard_data"
    "User": "lms.user_dashboard"
}

fixtures = [
    {
        "doctype": "Role",
        "filters": [
            [
                "name",
                "in",
                ["Loan Customer", "Lender", "Spark Manager"],
            ]
        ],
    },
    {"doctype": "Notification", "filters": [["document_type", "in", ["User"]]]},
    "Security",
    "Allowed Security",
    "Security Category",
    "Concentration Rule",
    "Terms and Conditions",
    "Margin Shortfall Action",
    "Lender",
    "SMS Settings",
    "API Doc",
    "LAS Settings",
    "Workflow State",
    "Workflow Action Master",
    "Workflow",
    "Interest Configuration",
    "Consent",
]

scheduler_events = {
    "hourly": [
        "lms.lms.doctype.security_price.security_price.update_all_security_prices"
    ],
    "daily": [
        "lms.lms.doctype.loan.loan.add_all_loans_virtual_interest",
        "lms.lms.doctype.loan.loan.check_for_all_loans_additional_interest",
        "lms.lms.doctype.loan.loan.add_all_loans_penal_interest",
    ],
    "monthly": ["lms.lms.doctype.loan.loan.book_all_loans_virtual_interest_for_month"],
    # "cron": {"* * * * *": ["lms.lms.doctype.cart.cart.cron_for_cart_pledge"]},
}
