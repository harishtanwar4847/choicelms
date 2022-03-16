# -*- coding: utf-8 -*-
# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document

import lms
from lms.firebase import FirebaseAdmin
from lms.lms.doctype.collateral_ledger.collateral_ledger import CollateralLedger


class UnpledgeApplication(Document):
    def get_loan(self):
        return frappe.get_doc("Loan", self.loan)

    def before_insert(self):
        self.process_items()

    def before_save(self):
        loan_margin_shortfall = frappe.get_all(
            "Loan Margin Shortfall",
            {"loan": self.loan, "status": "Pending"},
            page_length=1,
        )
        if self.status == "Rejected" and not loan_margin_shortfall:
            self.notify_customer()
        else:
            self.process_items()
            self.process_sell_items()

    def process_items(self, instrument_type="Share"):
        self.total_collateral_value = 0
        loan = self.get_loan()
        self.lender = loan.lender
        self.customer = loan.customer
        if not self.customer_name:
            self.customer_name = loan.customer_name
        allowable_value = loan.max_unpledge_amount()
        self.max_unpledge_amount = allowable_value["maximum_unpledge_amount"]

        pending_sell_request_id = frappe.db.get_value(
            "Sell Collateral Application",
            {"loan": loan.name, "status": "Pending"},
            "name",
        )
        if pending_sell_request_id:
            self.pending_sell_request_id = pending_sell_request_id
        else:
            self.pending_sell_request_id = ""

        securities_list = [i.isin for i in self.items]

        query = """
            SELECT
                security_name, isin, price
            FROM
                `tabSecurity`
            WHERE
                instrument_type = '{}' and isin in {};
        """.format(
            instrument_type, lms.convert_list_to_tuple_string(securities_list)
        )

        res_ = frappe.db.sql(query, as_dict=1)
        res = {i.isin: i for i in res_}

        for i in self.items:
            i.security_name = res.get(i.isin).security_name
            i.price = res.get(i.isin).price
            i.amount = i.quantity * i.price
            self.total_collateral_value += i.amount

    def process_sell_items(self):
        if self.status != "Pending":
            return

        self.unpledge_collateral_value = 0

        price_map = {i.isin: i.price for i in self.items}
        unpledge_quantity_map = {i.isin: 0 for i in self.items}

        for i in self.unpledge_items:
            if i.unpledge_quantity > i.quantity:
                frappe.throw(
                    "Can not unpledge {}(PSN: {}) more than {}".format(
                        i.isin, i.psn, i.quantity
                    )
                )
            unpledge_quantity_map[i.isin] = (
                unpledge_quantity_map[i.isin] + i.unpledge_quantity
            )
            i.price = price_map.get(i.isin)
            self.unpledge_collateral_value += i.unpledge_quantity * price_map.get(
                i.isin
            )

        for i in self.items:
            if unpledge_quantity_map.get(i.isin) > i.quantity:
                frappe.throw(
                    "Can not unpledge {} more than {}".format(i.isin, i.quantity)
                )

    def before_submit(self):
        # check if all securities are sold
        unpledge_quantity_map = {i.isin: 0 for i in self.items}

        if len(self.unpledge_items):
            for i in self.unpledge_items:
                unpledge_quantity_map[i.isin] = (
                    unpledge_quantity_map[i.isin] + i.unpledge_quantity
                )
        else:
            frappe.throw("Please add items to unpledge")

        for i in self.items:
            # print(unpledge_quantity_map.get(i.isin), i.quantity)
            if unpledge_quantity_map.get(i.isin) < i.quantity:
                frappe.throw(
                    "You need to unpledge all {} of isin {}".format(i.quantity, i.isin)
                )

        loan_items = frappe.get_all(
            "Loan Item", filters={"parent": self.loan}, fields=["*"]
        )
        for i in loan_items:
            for j in self.unpledge_items:
                if i["isin"] == j.isin and i["pledged_quantity"] < j.unpledge_quantity:
                    frappe.throw(
                        "Sufficient quantity not available for ISIN {unpledge_isin},\nCurrent Quantity= {loan_qty} Requested Unpledge Quantity {unpledge_quantity}\nPlease Reject this Application".format(
                            unpledge_isin=j.isin,
                            loan_qty=i["pledged_quantity"],
                            unpledge_quantity=j.unpledge_quantity,
                        )
                    )

    def on_submit(self):
        for i in self.unpledge_items:
            if i.unpledge_quantity > 0:
                collateral_ledger_data = {
                    "pledgor_boid": i.pledgor_boid,
                    "pledgee_boid": i.pledgee_boid,
                }
                collateral_ledger_input = {
                    "doctype": "Unpledge Application",
                    "docname": self.name,
                    "request_type": "Unpledge",
                    "isin": i.get("isin"),
                    "quantity": i.get("unpledge_quantity"),
                    "price": i.get("price"),
                    "security_name": i.get("security_name"),
                    "security_category": i.get("security_category"),
                    "psn": i.get("psn"),
                    "loan_name": self.loan,
                    "lender_approval_status": "Approved",
                    "data": collateral_ledger_data,
                }
                CollateralLedger.create_entry(**collateral_ledger_input)

        loan = self.get_loan()
        loan.update_items()
        loan.fill_items()
        loan.save(ignore_permissions=True)

        lender = self.get_lender()
        dp_reimburse_unpledge_charges = lender.dp_reimburse_unpledge_charges
        if lender.dp_reimburse_unpledge_charge_type == "Fix":
            total_dp_reimburse_unpledge_charges = (
                len(self.items) * dp_reimburse_unpledge_charges
            )
        elif lender.dp_reimburse_unpledge_charge_type == "Percentage":
            total_dp_reimburse_unpledge_charges = (
                len(self.items) * dp_reimburse_unpledge_charges / 100
            )

        if total_dp_reimburse_unpledge_charges:
            loan.create_loan_transaction(
                transaction_type="DP Reimbursement(Unpledge)",
                amount=total_dp_reimburse_unpledge_charges,
                approve=True,
            )

        self.notify_customer()

    def notify_customer(self, check=None):
        msg = ""
        fcm_notification = {}
        if self.status in ["Approved", "Rejected"]:
            customer = self.get_loan().get_customer()
            user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
            doc = user_kyc.as_dict()
            doc["unpledge_application"] = {"status": self.status}
            frappe.enqueue_doc(
                "Notification", "Unpledge Application", method="send", doc=doc
            )
            if self.status == "Approved":
                msg = "Dear Customer,\nCongratulations! Your unpledge request has been successfully executed. Kindly check the app now. -Spark Loans"
                fcm_notification = frappe.get_doc(
                    "Spark Push Notification",
                    "Unpledge application accepted",
                    fields=["*"],
                )
            elif self.status == "Rejected":
                if check == True:
                    # msg = """Dear {},
                    # Your unpledge request was rejected.
                    # There is a margin shortfall.
                    # You can send another unpledge request when there is no margin shortfall.""".format(
                    #     self.get_loan().get_customer().first_name
                    # )
                    msg = """Your unpledge request was rejected. There is a margin shortfall. You can send another unpledge request when there is no margin shortfall.""".format(
                        self.get_loan().get_customer().first_name
                    )
                else:
                    msg = "Dear Customer,\nSorry! Your unpledge application was turned down due to technical reasons. Please try again after sometime or reach us through 'Contact Us' on the app  -Spark Loans"
                    fcm_notification = frappe.get_doc(
                        "Spark Push Notification",
                        "Unpledge application rejected",
                        fields=["*"],
                    )

            receiver_list = list(
                set([str(customer.phone), str(user_kyc.mobile_number)])
            )
            from frappe.core.doctype.sms_settings.sms_settings import send_sms

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

        if fcm_notification:
            lms.send_spark_push_notification(
                fcm_notification=fcm_notification,
                message=fcm_notification.message,
                loan=self.loan,
                customer=customer,
            )

    def validate(self):
        for i, item in enumerate(
            sorted(self.items, key=lambda item: item.security_name), start=1
        ):
            item.idx = i

    def unpledge_with_margin_shortfall(self):
        loan_margin_shortfall = frappe.get_all(
            "Loan Margin Shortfall",
            {"loan": self.loan, "status": "Pending"},
            page_length=1,
        )

        if self.status == "Pending" and loan_margin_shortfall:
            self.status = "Rejected"
            self.workflow_state = "Rejected"
            check = True
            self.save(ignore_permissions=True)
            frappe.db.commit()
            self.notify_customer(check)

    def get_lender(self):
        return frappe.get_doc("Lender", self.lender)

    # def check(self):
    #     loan = self.get_loan()
    #     final_drawing_power = (loan.total_collateral_value - self.unpledge_collateral_value)*loan.allowable_ltv/100
    #     print(loan.total_collateral_value,"loan.total_collateral_value")
    #     print(self.unpledge_collateral_value,"self.unpledge_collateral_value")
    #     print(final_drawing_power,"final_drawing_power")
    #     if self.status == "Pending" and final_drawing_power < loan.balance:
    #         self.status = "Rejected"
    #         self.workflow_state = "Rejected"
    #         self.save(ignore_permissions=True)
    #         frappe.db.commit()
    #         self.notify_customer(check=True)


@frappe.whitelist()
def get_collateral_details(unpledge_application_name):
    doc = frappe.get_doc("Unpledge Application", unpledge_application_name)
    loan = doc.get_loan()
    isin_list = [i.isin for i in doc.items]
    return loan.get_collateral_list(
        group_by_psn=True,
        where_clause="and cl.isin IN {}".format(
            lms.convert_list_to_tuple_string(isin_list)
        ),
        having_clause=" HAVING quantity > 0",
    )
