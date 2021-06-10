# -*- coding: utf-8 -*-
# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document

import lms
from lms.lms.doctype.collateral_ledger.collateral_ledger import CollateralLedger


class SellCollateralApplication(Document):
    def get_loan(self):
        return frappe.get_doc("Loan", self.loan)

    def before_insert(self):
        self.process_items()

    def before_save(self):
        self.process_items()
        self.process_sell_items()

    def process_items(self):
        self.total_collateral_value = 0
        loan = self.get_loan()
        self.lender = loan.lender
        self.customer = loan.customer
        triggered_margin_shortfall = frappe.get_all(
            "Loan Margin Shortfall",
            filters={"loan": self.loan, "status": "Sell Triggered"},
        )
        if triggered_margin_shortfall:
            self.loan_margin_shortfall = triggered_margin_shortfall[0].name
            loan_margin_shortfall = frappe.get_doc("Loan Margin Shortfall", triggered_margin_shortfall[0].name)
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

    def on_update(self):
        if self.status == "Rejected":
            msg = "Dear Customer, \nSorry! Your sell collateral request was turned down due to technical reasons. Please try again after sometime or reach out to us through 'Contact Us' on the app \n-Spark Loans"

            receiver_list = list(
                set(
                    [
                        str(self.get_loan().get_customer().phone),
                        str(self.get_loan().get_customer().get_kyc().mobile_number),
                    ]
                )
            )
            from frappe.core.doctype.sms_settings.sms_settings import send_sms

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

            if self.loan_margin_shortfall:
                # if frappe.session.user != self.owner:

                # if shortfall is not recoverd then margin shortfall status will change from request pending to pending
                loan_margin_shortfall = frappe.get_doc(
                    "Loan Margin Shortfall", self.loan_margin_shortfall
                )
                if (
                    loan_margin_shortfall.status == "Request Pending"
                    and loan_margin_shortfall.shortfall_percentage > 0
                ):
                    loan_margin_shortfall.status = "Pending"
                    loan_margin_shortfall.save(ignore_permissions=True)
                    frappe.db.commit()

    def on_submit(self):
        for i in self.sell_items:
            if i.sell_quantity > 0:
                collateral_ledger_input = {
                    "doctype": "Sell Collateral Application",
                    "docname": self.name,
                    "request_type": "Sell Collateral",
                    "isin": i.get("isin"),
                    "quantity": i.get("sell_quantity"),
                    "psn": i.get("psn"),
                    "loan_name": self.loan,
                    "lender_approval_status": "Approved",
                }
                CollateralLedger.create_entry(**collateral_ledger_input)

        lender = self.get_lender()
        dp_reinbursement_charges = lender.dp_reimbursement_charges
        total_dp_reinbursement_charges = len(self.sell_items) * dp_reinbursement_charges
        # return dp_reinbursement_charges,len(self.sell_items),total_dp_reinbursement_charges

        loan = self.get_loan()
        loan.update_items()
        loan.fill_items()
        loan.save(ignore_permissions=True)
        loan.create_loan_transaction(
            transaction_type="Sell Collateral",
            amount=self.net_proceeds,
            # amount=self.selling_collateral_value,
            approve=True,
            loan_margin_shortfall_name=self.loan_margin_shortfall,
        )
        loan.create_loan_transaction(
            transaction_type="DP Reimbursement Charges",
            amount=total_dp_reinbursement_charges,
            approve=True,
            loan_margin_shortfall_name=self.loan_margin_shortfall,
        )
        if self.owner == frappe.session.user and self.loan_margin_shortfall:
            msg = "Dear Customer, \nSale of securities initiated by the lending partner for your loan account {} is now completed .The sale proceeds have been credited to your loan account and collateral value updated. Please check the app for details.".format(
                self.loan
            )
        else:
            msg = "Dear Customer, \nCongratulations! Your sell collateral request has been successfully executed and sale proceeds credited to your loan account. Kindly check the app for details \n-Spark Loans"

        if msg:
            receiver_list = list(
                set(
                    [
                        str(self.get_loan().get_customer().phone),
                        str(self.get_loan().get_customer().get_kyc().mobile_number),
                    ]
                )
            )
            from frappe.core.doctype.sms_settings.sms_settings import send_sms

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)
        # loan.update_loan_balance()

    def validate(self):
        for i, item in enumerate(
            sorted(self.items, key=lambda item: item.security_name), start=1
        ):
            item.idx = i

    def get_lender(self):
        return frappe.get_doc("Lender", self.lender)

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
