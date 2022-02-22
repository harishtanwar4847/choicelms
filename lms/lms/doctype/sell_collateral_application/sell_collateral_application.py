# -*- coding: utf-8 -*-
# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document

import lms
from lms.firebase import FirebaseAdmin
from lms.lms.doctype.collateral_ledger.collateral_ledger import CollateralLedger


class SellCollateralApplication(Document):
    def get_loan(self):
        return frappe.get_doc("Loan", self.loan)

    def before_insert(self):
        self.process_items()

    def before_save(self):
        self.process_items()
        self.process_sell_items()
        if self.status == "Rejected":
            fcm_notification = frappe.get_doc(
                "Spark Push Notification", "Sell request rejected", fields=["*"]
            )
            self.notify_customer(
                fcm_notification=fcm_notification, message=fcm_notification.message
            )

    def process_items(self):
        self.total_collateral_value = 0
        loan = self.get_loan()
        self.lender = loan.lender
        self.customer = loan.customer
        if not self.customer_name:
            self.customer_name = loan.customer_name

        pending_unpledge_request_id = frappe.db.get_value(
            "Unpledge Application", {"loan": loan.name, "status": "Pending"}, "name"
        )
        if pending_unpledge_request_id:
            self.pending_unpledge_request_id = pending_unpledge_request_id
        else:
            self.pending_unpledge_request_id = ""

        triggered_margin_shortfall = frappe.get_all(
            "Loan Margin Shortfall",
            filters={"loan": self.loan, "status": "Sell Triggered"},
        )
        if self.loan_margin_shortfall:
            loan_margin_shortfall = frappe.get_doc(
                "Loan Margin Shortfall", self.loan_margin_shortfall
            )
            if loan_margin_shortfall.status in ["Request Pending"]:
                self.current_shortfall_amount = loan_margin_shortfall.shortfall

        if triggered_margin_shortfall:
            self.loan_margin_shortfall = triggered_margin_shortfall[0].name
            loan_margin_shortfall = frappe.get_doc(
                "Loan Margin Shortfall", triggered_margin_shortfall[0].name
            )
            self.initial_shortfall_amount = loan_margin_shortfall.shortfall
            loan_margin_shortfall.fill_items()
            self.current_shortfall_amount = loan_margin_shortfall.shortfall

        securities_list = [i.isin for i in self.items]

        query = """
            SELECT
                security_name, isin, price
            FROM
                `tabSecurity`
            WHERE
                isin in {};
        """.format(
            lms.convert_list_to_tuple_string(securities_list)
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

        self.selling_collateral_value = 0

        price_map = {i.isin: i.price for i in self.items}
        sell_quantity_map = {i.isin: 0 for i in self.items}

        for i in self.sell_items:
            if i.sell_quantity > i.quantity:
                frappe.throw(
                    "Can not sell {}(PSN: {}) more than {}".format(
                        i.isin, i.psn, i.quantity
                    )
                )
            sell_quantity_map[i.isin] = sell_quantity_map[i.isin] + i.sell_quantity
            i.price = price_map.get(i.isin)
            self.selling_collateral_value += i.sell_quantity * price_map.get(i.isin)

        for i in self.items:
            if sell_quantity_map.get(i.isin) > i.quantity:
                frappe.throw("Can not sell {} more than {}".format(i.isin, i.quantity))

    def before_submit(self):
        # check if all securities are sold
        sell_quantity_map = {i.isin: 0 for i in self.items}

        for i in self.sell_items:
            sell_quantity_map[i.isin] = sell_quantity_map[i.isin] + i.sell_quantity

        for i in self.items:
            # print(sell_quantity_map.get(i.isin), i.quantity)
            if sell_quantity_map.get(i.isin) < i.quantity:
                frappe.throw(
                    "You need to sell all {} of isin {}".format(i.quantity, i.isin)
                )
        """22-06-21 informed by vinayak"""
        # if self.lender_selling_amount > self.selling_collateral_value:
        #     frappe.throw(
        #         "Can not sell amount more than {}".format(self.selling_collateral_value)
        #     )
        if self.lender_selling_amount <= 0:
            frappe.throw("Please fix the Lender Selling Amount.")

        loan_items = frappe.get_all(
            "Loan Item", filters={"parent": self.loan}, fields=["*"]
        )
        for i in loan_items:
            for j in self.sell_items:
                if i["isin"] == j.isin and i["pledged_quantity"] < j.sell_quantity:
                    frappe.throw(
                        "Sufficient quantity not available for ISIN {sell_isin},\nCurrent Quantity= {loan_qty} Requested Sell Quantity {sell_quantity}\nPlease Reject this Application".format(
                            sell_isin=j.isin,
                            loan_qty=i["pledged_quantity"],
                            sell_quantity=j.sell_quantity,
                        )
                    )

    def on_update(self):
        if self.status == "Rejected":
            msg = "Dear Customer,\nSorry! Your sell collateral request was turned down due to technical reasons. Please try again after sometime or reach out to us through 'Contact Us' on the app  -Spark Loans"

            receiver_list = list(
                set(
                    [
                        str(self.get_customer().phone),
                        str(self.get_customer().get_kyc().mobile_number),
                    ]
                )
            )
            from frappe.core.doctype.sms_settings.sms_settings import send_sms

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

        if self.loan_margin_shortfall:
            loan_margin_shortfall = frappe.get_doc(
                "Loan Margin Shortfall", self.loan_margin_shortfall
            )
            if loan_margin_shortfall.status == "Request Pending":
                under_process_la = frappe.get_all(
                    "Loan Application",
                    filters={
                        "loan": self.loan,
                        "status": [
                            "not IN",
                            ["Approved", "Rejected", "Pledge Failure"],
                        ],
                        "pledge_status": ["!=", "Failure"],
                        "loan_margin_shortfall": loan_margin_shortfall.name,
                    },
                )
                pending_loan_transaction = frappe.get_all(
                    "Loan Transaction",
                    filters={
                        "loan": self.loan,
                        "status": ["not IN", ["Approved", "Rejected"]],
                        "loan_margin_shortfall": loan_margin_shortfall.name,
                    },
                )
                pending_sell_collateral_application = frappe.get_all(
                    "Sell Collateral Application",
                    filters={
                        "loan": self.loan,
                        "status": ["not IN", ["Approved", "Rejected"]],
                        "loan_margin_shortfall": loan_margin_shortfall.name,
                    },
                )
                if (
                    (
                        not pending_loan_transaction
                        and not pending_sell_collateral_application
                        and not under_process_la
                    )
                    and loan_margin_shortfall.status == "Request Pending"
                    and loan_margin_shortfall.shortfall_percentage > 0
                ):
                    loan_margin_shortfall.status = "Pending"
                    loan_margin_shortfall.save(ignore_permissions=True)
                    frappe.db.commit()

    def on_submit(self):
        for i in self.sell_items:
            if i.sell_quantity > 0:
                collateral_ledger_data = {
                    "pledgor_boid": i.pledgor_boid,
                    "pledgee_boid": i.pledgee_boid,
                }
                collateral_ledger_input = {
                    "doctype": "Sell Collateral Application",
                    "docname": self.name,
                    "request_type": "Sell Collateral",
                    "isin": i.get("isin"),
                    "quantity": i.get("sell_quantity"),
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
        dp_reimburse_sell_charges = lender.dp_reimburse_sell_charges
        sell_charges = lender.sell_collateral_charges

        if lender.dp_reimburse_sell_charge_type == "Fix":
            total_dp_reimburse_sell_charges = (
                len(self.items) * dp_reimburse_sell_charges
            )
        elif lender.dp_reimburse_sell_charge_type == "Percentage":
            total_dp_reimburse_sell_charges = (
                len(self.items) * dp_reimburse_sell_charges / 100
            )
        if lender.sell_collateral_charge_type == "Fix":
            sell_collateral_charges = sell_charges
        elif lender.sell_collateral_charge_type == "Percentage":
            sell_collateral_charges = self.lender_selling_amount * sell_charges / 100
        # sell_collateral_charges = self.validate_loan_charges_amount(
        #     lender,
        #     sell_collateral_charges,
        #     "sell_collateral_minimum_amount",
        #     "sell_collateral_maximum_amount",
        # )

        # is_for_interest = False
        # interest_entry = frappe.get_value(
        #     "Loan Transaction",
        #     {
        #         "loan": self.loan,
        #         "transaction_type": "Interest",
        #         "unpaid_interest": [">", 0],
        #     },
        #     "name",
        # )
        # if interest_entry:
        #     is_for_interest = True
        loan.create_loan_transaction(
            transaction_type="Sell Collateral",
            amount=self.lender_selling_amount,
            # amount=self.selling_collateral_value,
            approve=True,
            loan_margin_shortfall_name=self.loan_margin_shortfall,
            # is_for_interest=is_for_interest,
        )
        # DP Reimbursement(Sell)
        # Sell Collateral Charges
        if total_dp_reimburse_sell_charges:
            loan.create_loan_transaction(
                transaction_type="DP Reimbursement(Sell)",
                amount=total_dp_reimburse_sell_charges,
                approve=True,
                loan_margin_shortfall_name=self.loan_margin_shortfall,
            )
        if sell_collateral_charges:
            loan.create_loan_transaction(
                transaction_type="Sell Collateral Charges",
                amount=sell_collateral_charges,
                approve=True,
                loan_margin_shortfall_name=self.loan_margin_shortfall,
            )
        if self.owner == frappe.session.user and self.loan_margin_shortfall:
            doc = frappe.get_doc("User KYC", self.get_customer().choice_kyc).as_dict()
            doc["sell_triggered_completion"] = {"loan": self.loan}
            # if self.status in ["Pending", "Approved", "Rejected"]:
            frappe.enqueue_doc(
                "Notification", "Sale Triggered Completion", method="send", doc=doc
            )
            msg = "Dear Customer,\nSale of securities initiated by the lending partner for your loan account  {} is now completed .The sale proceeds have been credited to your loan account and collateral value updated. Please check the app for details. Spark Loans".format(
                self.loan
            )
            fcm_notification = frappe.get_doc(
                "Spark Push Notification", "Sale triggerred completed", fields=["*"]
            )
            message = fcm_notification.message.format(loan=self.loan)
        else:
            msg = "Dear Customer,\nCongratulations! Your sell collateral request has been successfully executed and sale proceeds credited to your loan account. Kindly check the app for details -Spark Loans"
            fcm_notification = frappe.get_doc(
                "Spark Push Notification", "Sell request executed", fields=["*"]
            )
            message = fcm_notification.message

        if msg:
            receiver_list = list(
                set(
                    [
                        str(self.get_customer().phone),
                        str(self.get_customer().get_kyc().mobile_number),
                    ]
                )
            )
            from frappe.core.doctype.sms_settings.sms_settings import send_sms

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)
        # loan.update_loan_balance()
        self.notify_customer(fcm_notification=fcm_notification, message=message)

    def validate(self):
        for i, item in enumerate(
            sorted(self.items, key=lambda item: item.security_name), start=1
        ):
            item.idx = i

    def get_lender(self):
        return frappe.get_doc("Lender", self.lender)

    def get_customer(self):
        return frappe.get_doc("Loan Customer", self.customer)

    def notify_customer(self, fcm_notification={}, message=""):
        doc = self.get_customer().get_kyc().as_dict()
        doc["sell_collateral_application"] = {"status": self.status}
        frappe.enqueue_doc(
            "Notification", "Sell Collateral Application", method="send", doc=doc
        )

        if fcm_notification:
            lms.send_spark_push_notification(
                fcm_notification=fcm_notification,
                message=message,
                loan=self.loan,
                customer=self.get_customer(),
            )


@frappe.whitelist()
def get_collateral_details(sell_collateral_application_name):
    doc = frappe.get_doc(
        "Sell Collateral Application", sell_collateral_application_name
    )
    loan = doc.get_loan()
    isin_list = [i.isin for i in doc.items]
    return loan.get_collateral_list(
        group_by_psn=True,
        where_clause="and cl.isin IN {}".format(
            lms.convert_list_to_tuple_string(isin_list)
        ),
        having_clause=" HAVING quantity > 0",
    )
