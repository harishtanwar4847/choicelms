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
app_logo_url = "/assets/lms/images/logo_mo.svg"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/lms/css/lms.css"
# app_include_js = "/assets/lms/js/lms.js"
app_include_js = "/assets/lms/js/doctype.js"

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
home_page = "home"

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

permission_query_conditions = {
    # "Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
    # "Lender": "lms.hooks.lender_permission_query",
    "Cart": "lms.cart_permission_query",
    "Loan Application": "lms.loan_application_permission_query",
    "Collateral Ledger": "lms.collateral_ledger_permission_query",
    "Loan": "lms.loan_permission_query",
    "Loan Transaction": "lms.loan_transaction_permission_query",
    "Loan Margin Shortfall": "lms.loan_margin_shortfall_permission_query",
    "Unpledge Application": "lms.unpledge_application_permission_query",
    "Sell Collateral Application": "lms.sell_collateral_application_permission_query",
    "Top up Application": "lms.top_up_application_permission_query",
    "Virtual Interest": "lms.virtual_interest_permission_query",
    "Lender Ledger": "lms.lender_ledger_permission_query",
    "Allowed Security": "lms.allowed_security_permission_query",
    "Interest Configuration": "lms.interest_configuration_permission_query",
    "Lender": "lms.lender_permission_query",
    "Loan Payment Log": "lms.loan_payment_log_permission_query",
    "Security Category": "lms.security_category_permission_query",
}

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
        "before_insert": [
            "lms.lms.doctype.loan_application.loan_application.only_pdf_upload",
            "lms.lms.doctype.top_up_application.top_up_application.only_pdf_upload",
        ]
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
    "API Doc",
]

scheduler_events = {
    "hourly": [
        "lms.lms.doctype.security_price.security_price.update_all_security_prices"
    ],
    # "daily": [
    #     "lms.lms.doctype.loan.loan.add_all_loans_virtual_interest",
    #     "lms.lms.doctype.loan.loan.check_for_all_loans_additional_interest",
    #     "lms.lms.doctype.loan.loan.add_all_loans_penal_interest",
    # ],
    # "monthly": ["lms.lms.doctype.loan.loan.book_all_loans_virtual_interest_for_month"],
    # "all": ["lms.lms.doctype.loan_margin_shortfall.loan_margin_shortfall.mark_sell_triggered"],
    "cron": {
        "*/5 * * * *": [
            "lms.lms.doctype.loan_application.loan_application.process_pledge",
            "lms.lms.doctype.loan_margin_shortfall.loan_margin_shortfall.mark_sell_triggered",
        ],  # At every 5 minutes
        "30 17,5 * * *": [
            "lms.lms.doctype.loan_transaction.loan_transaction.reject_blank_transaction_and_settlement_recon_api"
        ],
        "0 0 * * *": [
            "lms.lms.doctype.loan.loan.add_all_loans_virtual_interest"
        ],  # At 12:00 AM daily
        "0 1 * * *": [
            "lms.lms.doctype.loan.loan.book_all_loans_virtual_interest_for_month"
        ],  # At 01:00 AM on 1st day-of-every-month(monthly)
        "0 2 * * *": [
            "lms.lms.doctype.loan.loan.check_for_all_loans_additional_interest"
        ],  # At 02:00 AM daily
        "0 3 * * *": [
            "lms.lms.doctype.loan.loan.add_all_loans_penal_interest"
        ],  # At 03:00 AM daily
        "30 9 * * *": [
            "lms.lms.doctype.security_price.security_price.update_all_schemeNav"
        ],  # At 09:30 AM daily
        # "* * * * *": [
        #     "lms.lms.doctype.loan_margin_shortfall.loan_margin_shortfall.mark_sell_triggered"
        # ],  # At every minute
        "30 23 * * *": ["lms.system_report_enqueue"],  # At 11:30 PM daily
        "15 0 * * *": [
            "lms.lms.doctype.spark_loan_renewal_application.spark_loan_renewal_application.all_loans_renewal_update_doc"
        ],  # At 12:15 AM daily
    },
}
