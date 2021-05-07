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

        loan = self.get_loan()
        loan.update_items()
        loan.fill_items()
        loan.save(ignore_permissions=True)
        loan.create_loan_transaction(
            transaction_type="Sell Collateral",
            amount=self.selling_collateral_value,
            approve=True,
        )
        loan.update_loan_balance()

    def validate(self):
        for i, item in enumerate(sorted(self.items, key=lambda item: item.security_name), start=1):
            item.idx = i


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
    )
