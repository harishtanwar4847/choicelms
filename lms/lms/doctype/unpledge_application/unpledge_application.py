# -*- coding: utf-8 -*-
# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document

import lms
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

    def process_items(self):
        self.total_collateral_value = 0
        loan = self.get_loan()
        self.lender = loan.lender
        self.customer = loan.customer

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

    def on_submit(self):
        for i in self.unpledge_items:
            if i.unpledge_quantity > 0:
                collateral_ledger_input = {
                    "doctype": "Unpledge Application",
                    "docname": self.name,
                    "request_type": "Unpledge",
                    "isin": i.get("isin"),
                    "quantity": i.get("unpledge_quantity"),
                    "psn": i.get("psn"),
                    "loan_name": self.loan,
                    "lender_approval_status": "Approved",
                }
                CollateralLedger.create_entry(**collateral_ledger_input)

        loan = self.get_loan()
        loan.update_items()
        loan.fill_items()
        loan.save(ignore_permissions=True)
        self.notify_customer()

    def notify_customer(self, check=None):
        msg = ""
        if self.status in ["Approved", "Rejected"]:
            customer = self.get_loan().get_customer()
            user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)

            if self.status == "Approved":
                msg = "Your unpledging of securities was successfully completed."
            elif self.status == "Rejected":
                if check == True:
                    # msg = """Dear {},
                    # Your unpledge request was rejected.
                    # There is a margin shortfall.
                    # You can send another unpledge request when there is no margin shortfall.""".format(
                    #     self.get_loan().get_customer().first_name
                    # )
                    msg = """Your unpledge request was rejected.
                    There is a margin shortfall.
                    You can send another unpledge request when there is no margin shortfall.""".format(
                        self.get_loan().get_customer().first_name
                    )
                else:
                    msg = "Your unpledging of securities was not completed."

            receiver_list = list(
                set([str(customer.phone), str(user_kyc.mobile_number)])
            )
            from frappe.core.doctype.sms_settings.sms_settings import send_sms

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

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
        having_clause=" HAVING quantity > 0"
    )
