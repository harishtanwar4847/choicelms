from __future__ import unicode_literals

from frappe import _


def get_data():
    return [
        {
            "label": _("Masters"),
            "items": [
                {"type": "doctype", "name": "Lender", "onboard": 1},
                {"type": "doctype", "name": "Allowed Security", "onboard": 1},
                {"type": "doctype", "name": "Security Category", "onboard": 1},
                {"type": "doctype", "name": "Terms and Conditions", "onboard": 1},
                {"type": "doctype", "name": "Security Price", "onboard": 1},
            ],
        },
        {
            "label": _("Settings & Configurations"),
            "items": [
                {"type": "doctype", "name": "LAS Settings", "onboard": 1},
                {"type": "doctype", "name": "Concentration Rule", "onboard": 1},
                {"type": "doctype", "name": "Margin Shortfall Action", "onboard": 1},
                {"type": "doctype", "name": "SMS Settings", "onboard": 1},
            ],
        },
        {
            "label": _("Tokens & Logs"),
            "items": [
                {"type": "doctype", "name": "User Token", "onboard": 1},
                {"type": "doctype", "name": "App Error Log", "onboard": 1},
                {"type": "doctype", "name": "SMS Log", "onboard": 1},
            ],
        },
        {
            "label": _("User Details"),
            "items": [
                {"type": "doctype", "name": "User", "onboard": 1},
                {
                    "type": "doctype",
                    "name": "Approved Terms and Conditions",
                    "onboard": 1,
                },
                {"type": "doctype", "name": "User KYC", "onboard": 1},
                {
                    "type": "doctype",
                    "name": "User KYC Change Application",
                    "onboard": 1,
                },
            ],
        },
        {
            "label": _("Loan"),
            "items": [
                {"type": "doctype", "name": "Cart", "onboard": 1},
                {"type": "doctype", "name": "Loan Application", "onboard": 1},
                {"type": "doctype", "name": "Loan", "onboard": 1},
                {"type": "doctype", "name": "Loan Withdraw Ledger", "onboard": 1},
            ],
        },
    ]
