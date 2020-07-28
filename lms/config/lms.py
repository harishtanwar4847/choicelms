from __future__ import unicode_literals
from frappe import _

def get_data():
	return [
		{
			'label': _('Masters'),
			'items': [
				{ 'type': 'doctype', 'name': 'Allowed Security Master', 'onboard': 1 },
				{ 'type': 'doctype', 'name': 'Security Category', 'onboard': 1 },
				{ 'type': 'doctype', 'name': 'Terms and Conditions', 'onboard': 1 },
			]
		},
		{
			'label': _('Settings & Configurations'),
			'items': [
				{ 'type': 'doctype', 'name': 'LAS Settings', 'onboard': 1 },
				{ 'type': 'doctype', 'name': 'Concentration Rule', 'onboard': 1 },
			]
		},
		{
			'label': _('Tokens & Logs'),
			'items': [
				{ 'type': 'doctype', 'name': 'User Token', 'onboard': 1 },
				{ 'type': 'doctype', 'name': 'App Error Log', 'onboard': 1 },
				{ 'type': 'doctype', 'name': 'SMS Log', 'onboard': 1 },
			]
		},
		{
			'label': _('User Details'),
			'items': [
				{ 'type': 'doctype', 'name': 'User', 'onboard': 1 },
				{ 'type': 'doctype', 'name': 'Approved Terms and Conditions', 'onboard': 1 },
				{ 'type': 'doctype', 'name': 'User KYC', 'onboard': 1 },
				{ 'type': 'doctype', 'name': 'User KYC Change Application', 'onboard': 1 },
			]
		},
		{
			'label': _('Loan'),
			'items': [
				{ 'type': 'doctype', 'name': 'Cart', 'onboard': 1 },
				{ 'type': 'doctype', 'name': 'Loan Application', 'onboard': 1 },
				{ 'type': 'doctype', 'name': 'Loan', 'onboard': 1 },
			]
		}
	]

def get_data1():
    return [
        {
            "label": _("Loan"),
            "items": [
                {
                    "type": "doctype",
                            "name": "Loan",
                                    "label": _("Loan"),
                                    "description": _("Loan"),
                                    "onboard": 1
                },
                {
                    "type": "doctype",
                            "name": "Loan Status History",
                                    "label": _("Loan Status History"),
                                    "description": _("Loan Status History"),
                                    "onboard": 1
                },
                {
                    "type": "doctype",
                            "name": "Allowed Security Master",
                                    "label": _("Allowed Security Master"),
                                    "description": _("Allowed Security Master"),
                                    "onboard": 1
                },
                {
                    "type": "doctype",
                            "name": "User Security Edit History",
                                    "label": _("User Security Edit History"),
                                    "description": _("User Security Edit History"),
                                    "onboard": 1
                }
            ]
        },
        {
            "label": _("Cart"),
            "items": [
                {
                    "type": "doctype",
                            "name": "Cart",
                                    "label": _("Cart"),
                                    "description": _("Cart"),
                                    "onboard": 1
                }
            ]
        },
        {
            "label": _("Masters"),
            "items": [
                {
                    "type": "doctype",
                            "name": "User Bank Details",
                                    "label": _("User Bank Details"),
                                    "description": _("User Bank Details"),
                                    "onboard": 1
                },
                {
                    "type": "doctype",
                            "name": "User Account Volation Log",
                                    "label": _("User Account Volation Log"),
                                    "description": _("User Account Volation Log"),
                                    "onboard": 1
                },
                {
                    "type": "doctype",
                            "name": "Volation Type",
                                    "label": _("Volation Type"),
                                    "description": _("Volation Type"),
                                    "onboard": 1
                },
                {
                    "type": "doctype",
                            "name": "User KYC",
                                    "label": _("User KYC"),
                                    "description": _("User KYC"),
                                    "onboard": 1
                },
                {
                    "type": "doctype",
                            "name": "Document Type",
                                    "label": _("Document Type"),
                                    "description": _("Document Type"),
                                    "onboard": 1
                },
                {
                    "type": "doctype",
                            "name": "Mobile OTP",
                                    "label": _("Mobile OTP"),
                                    "description": _("Mobile OTP"),
                                    "onboard": 1
                },
                {
                    "type": "doctype",
                            "name": "Security Category",
                                    "label": _("Security Category"),
                                    "description": _("Security Category"),
                                    "onboard": 1
                },
                {
                    "type": "doctype",
                            "name": "Concentration Rule",
                                    "label": _("Concentration Rule"),
                                    "description": _("Concentration Rule"),
                                    "onboard": 1
                }
            ]
        }

    ]
