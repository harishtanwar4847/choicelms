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
                }
                CollateralLedger.create_entry(**collateral_ledger_input)

        loan = self.get_loan()
        loan.update_items()
        loan.fill_items()
        loan.save(ignore_permissions=True)


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
    )
