# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

import lms


class ClientSummary(Document):
    pass


@frappe.whitelist()
def client_summary():
    try:
        loans = frappe.get_all("Loan", fields=["*"])
        for loan in loans:
            customer = frappe.get_doc("Loan Customer", loan.customer)
            user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
            loan_application = frappe.get_all(
                "Loan Application",
                filters={"customer": loan.customer},
                fields=["pledgor_boid"],
            )
            pledgor_boid = loan_application[0].pledgor_boid
            interest_config = frappe.get_value(
                "Interest Configuration",
                {
                    "to_amount": [">=", loan.sanctioned_limit],
                },
                order_by="to_amount asc",
            )
            int_config = frappe.get_doc("Interest Configuration", interest_config)
            if loan.margin_shortfall_amount:
                adp_shortfall = loan.margin_shortfall_amount
            else:
                adp_shortfall = loan.actual_drawing_power
            roi = int_config.base_interest * 12
            if user_kyc.choice_mob_no:
                phone = user_kyc.choice_mob_no
            elif user_kyc.choice_mob_no == "":
                phone = user_kyc.mob_num
            else:
                phone = customer.phone
            client_summary = frappe.get_doc(
                dict(
                    doctype="Client Summary",
                    loan_no=loan.name,
                    client_name=loan.customer_name,
                    pan_no=user_kyc.pan_no,
                    sanctioned_amount=loan.sanctioned_limit,
                    pledged_value=loan.total_collateral_value,
                    drawing_power=loan.drawing_power,
                    loan_balance=loan.balance,
                    adp_shortfall=adp_shortfall,
                    roi_=roi,
                    client_demat_acc=pledgor_boid,
                    customer_contact_no=phone,
                    loan_expiry_date=loan.expiry_date,
                    dpd=loan.day_past_due,
                ),
            ).insert(ignore_permissions=True)
            frappe.db.commit()
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=frappe._("Client Summary"),
        )
