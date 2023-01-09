# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import json
from datetime import datetime, timedelta

import frappe
from frappe.model.document import Document
from num2words import num2words

import lms
from lms.firebase import FirebaseAdmin
from lms.lms.doctype import loan_transaction
from lms.lms.doctype.loan_transaction.loan_transaction import LoanTransaction
from lms.lms.doctype.user_token.user_token import send_sms


class Loan(Document):
    # def after_insert(self):
    #     self.create_loan_charges()

    def maximum_withdrawable_amount(self, withdraw_req_name=None, req_time=None):
        balance = self.balance

        virtual_interest_sum = frappe.db.sql(
            "select sum(base_amount) as amount from `tabVirtual Interest` where loan = '{}' and is_booked_for_base = 0".format(
                self.name
            ),
            as_dict=1,
        )
        if virtual_interest_sum[0]["amount"]:
            balance += virtual_interest_sum[0]["amount"]

        if req_time and withdraw_req_name:
            pending_withdraw_requests_amt = frappe.db.sql(
                "select sum(amount) as amount from `tabLoan Transaction` where loan = '{}' and lender = '{}' and status in ('Pending','Ready for Approval') and transaction_type = 'Withdrawal' and creation < '{}' and name != '{}'".format(
                    self.name, self.lender, req_time, withdraw_req_name
                ),
                as_dict=1,
            )
            if pending_withdraw_requests_amt[0]["amount"]:
                balance += pending_withdraw_requests_amt[0]["amount"]
        else:
            pending_withdraw_requests_amt = frappe.db.sql(
                "select sum(amount) as amount from `tabLoan Transaction` where loan = '{}' and lender = '{}' and status in ('Pending','Ready for Approval') and transaction_type = 'Withdrawal'".format(
                    self.name, self.lender
                ),
                as_dict=1,
            )
            if pending_withdraw_requests_amt[0]["amount"]:
                balance += pending_withdraw_requests_amt[0]["amount"]

        max_withdraw_amount = self.drawing_power - balance
        if max_withdraw_amount < 0:
            max_withdraw_amount = 0.0

        return round(max_withdraw_amount, 2)

    def get_lender(self):
        return frappe.get_doc("Lender", self.lender)

    def create_loan_charges_old(self):
        lender = self.get_lender()

        # Processing fees
        amount = lender.lender_processing_fees
        if lender.lender_processing_fees_type == "Percentage":
            amount = (amount / 100) * self.sanctioned_limit
        self.create_loan_transaction(
            "Processing Fees",
            amount,
            approve=True,
        )

        # Stamp Duty
        amount = lender.stamp_duty
        if lender.stamp_duty_type == "Percentage":
            amount = (amount / 100) * self.sanctioned_limit
        self.create_loan_transaction(
            "Stamp Duty",
            amount,
            approve=True,
        )

        # Documentation Charges
        amount = lender.documentation_charges
        if lender.documentation_charge_type == "Percentage":
            amount = (amount / 100) * self.sanctioned_limit
        self.create_loan_transaction(
            "Documentation Charges",
            amount,
            approve=True,
        )

        # Mortgage Charges
        amount = lender.mortgage_charges
        if lender.mortgage_charge_type == "Percentage":
            amount = (amount / 100) * self.sanctioned_limit
        self.create_loan_transaction(
            "Mortgage Charges",
            amount,
            approve=True,
        )

    def create_loan_charges(self):
        lender = self.get_lender()
        # Processing fees
        import calendar

        date = frappe.utils.now_datetime()
        days_in_year = 366 if calendar.isleap(date.year) else 365
        processing_fees = lender.lender_processing_fees
        if lender.lender_processing_fees_type == "Percentage":
            days_left_to_expiry = days_in_year
            amount = (
                (processing_fees / 100)
                * self.sanctioned_limit
                / days_in_year
                * days_left_to_expiry
            )
            processing_fees = self.validate_loan_charges_amount(
                lender,
                amount,
                "lender_processing_minimum_amount",
                "lender_processing_maximum_amount",
            )
        if processing_fees > 0:
            processing_fees_reference = self.create_loan_transaction(
                "Processing Fees",
                processing_fees,
                approve=True,
            )

            # # GST on Charges
            # if lender.cgst_on_processing_fees > 0:
            #     cgst = processing_fees * (lender.cgst_on_processing_fees / 100)
            #     gst_percent = lender.cgst_on_processing_fees
            #     # charge_reference.charge_reference.db_set(
            #     #     "charge_reference", reference.transaction_type
            #     # )
            #     self.create_loan_transaction(
            #         "CGST on Processing Fees",
            #         cgst,
            #         gst_percent,
            #         charge_reference=processing_fees_reference.name,
            #         approve=True,
            #     )
            # if lender.sgst_on_processing_fees > 0:
            #     sgst = processing_fees * (lender.sgst_on_processing_fees / 100)
            #     gst_percent = lender.sgst_on_processing_fees
            #     self.create_loan_transaction(
            #         "SGST on Processing Fees",
            #         sgst,
            #         gst_percent,
            #         charge_reference=processing_fees_reference.name,
            #         approve=True,
            #     )
            # if lender.igst_on_processing_fees > 0:
            #     igst = processing_fees * (lender.igst_on_processing_fees / 100)
            #     gst_percent = lender.igst_on_processing_fees
            #     self.create_loan_transaction(
            #         "IGST on Processing Fees",
            #         igst,
            #         gst_percent,
            #         charge_reference=processing_fees_reference.name,
            #         approve=True,
            #     )

        # Stamp Duty
        stamp_duty = lender.stamp_duty
        if lender.stamp_duty_type == "Percentage":
            amount = (stamp_duty / 100) * self.sanctioned_limit
            stamp_duty = self.validate_loan_charges_amount(
                lender,
                amount,
                "lender_stamp_duty_minimum_amount",
                "lender_stamp_duty_maximum_amount",
            )

        if stamp_duty > 0:
            stamp_duty_reference = self.create_loan_transaction(
                "Stamp Duty",
                stamp_duty,
                approve=True,
            )
            # Charges on GST
            # if lender.cgst_on_stamp_duty > 0:
            #     cgst = stamp_duty * (lender.cgst_on_stamp_duty / 100)
            #     gst_percent = lender.cgst_on_stamp_duty
            #     self.create_loan_transaction(
            #         "CGST on Stamp Duty",
            #         cgst,
            #         gst_percent,
            #         charge_reference=stamp_duty_reference.name,
            #         approve=True,
            #     )
            # if lender.sgst_on_stamp_duty > 0:
            #     sgst = stamp_duty * (lender.sgst_on_stamp_duty / 100)
            #     gst_percent = lender.sgst_on_stamp_duty
            #     self.create_loan_transaction(
            #         "SGST on Stamp Duty",
            #         sgst,
            #         gst_percent,
            #         charge_reference=stamp_duty_reference.name,
            #         approve=True,
            #     )
            # if lender.igst_on_stamp_duty > 0:
            #     igst = stamp_duty * (lender.igst_on_stamp_duty / 100)
            #     gst_percent = lender.igst_on_stamp_duty
            #     self.create_loan_transaction(
            #         "IGST on Stamp Duty",
            #         igst,
            #         gst_percent,
            #         charge_reference=stamp_duty_reference.name,
            #         approve=True,
            #     )

        # Documentation Charges
        documentation_charges = lender.documentation_charges
        if lender.documentation_charge_type == "Percentage":
            amount = (documentation_charges / 100) * self.sanctioned_limit
            documentation_charges = self.validate_loan_charges_amount(
                lender,
                amount,
                "lender_documentation_minimum_amount",
                "lender_documentation_maximum_amount",
            )

        if documentation_charges > 0:
            documentation_charges_reference = self.create_loan_transaction(
                "Documentation Charges",
                documentation_charges,
                approve=True,
            )
            # GST Charges on
            # if lender.cgst_on_documentation_charges > 0:
            #     cgst = documentation_charges * (
            #         lender.cgst_on_documentation_charges / 100
            #     )
            #     gst_percent = lender.cgst_on_documentation_charges
            #     self.create_loan_transaction(
            #         "CGST on Documentation Charges",
            #         cgst,
            #         gst_percent,
            #         charge_reference=documentation_charges_reference.name,
            #         approve=True,
            #     )
            # if lender.sgst_on_documentation_charges > 0:
            #     sgst = documentation_charges * (
            #         lender.sgst_on_documentation_charges / 100
            #     )
            #     gst_percent = lender.sgst_on_documentation_charges
            #     self.create_loan_transaction(
            #         "SGST on Documentation Charges",
            #         sgst,
            #         gst_percent,
            #         charge_reference=documentation_charges_reference.name,
            #         approve=True,
            #     )
            # if lender.igst_on_documentation_charges > 0:
            #     igst = documentation_charges * (
            #         lender.igst_on_documentation_charges / 100
            #     )
            #     gst_percent = lender.igst_on_documentation_charges
            #     self.create_loan_transaction(
            #         "IGST on Documentation Charges",
            #         igst,
            #         gst_percent,
            #         charge_reference=documentation_charges_reference.name,
            #         approve=True,
            #     )

        # Mortgage Charges
        mortgage_charges = lender.mortgage_charges
        if lender.mortgage_charge_type == "Percentage":
            amount = (mortgage_charges / 100) * self.sanctioned_limit
            mortgage_charges = self.validate_loan_charges_amount(
                lender,
                amount,
                "lender_mortgage_minimum_amount",
                "lender_mortgage_maximum_amount",
            )
        if mortgage_charges > 0:
            mortgage_charges_reference = self.create_loan_transaction(
                "Mortgage Charges",
                mortgage_charges,
                approve=True,
            )
            # Charges on GST
            # if lender.cgst_on_mortgage_charges > 0:
            #     cgst = mortgage_charges * (lender.cgst_on_mortgage_charges / 100)
            #     gst_percent = lender.cgst_on_mortgage_charges
            #     self.create_loan_transaction(
            #         "CGST on Mortgage Charges",
            #         cgst,
            #         gst_percent,
            #         charge_reference=mortgage_charges_reference.name,
            #         approve=True,
            #     )
            # if lender.sgst_on_mortgage_charges > 0:
            #     sgst = mortgage_charges * (lender.sgst_on_mortgage_charges / 100)
            #     gst_percent = lender.sgst_on_mortgage_charges
            #     self.create_loan_transaction(
            #         "SGST on Mortgage Charges",
            #         sgst,
            #         gst_percent,
            #         charge_reference=mortgage_charges_reference.name,
            #         approve=True,
            #     )
            # if lender.igst_on_mortgage_charges > 0:
            #     igst = mortgage_charges * (lender.igst_on_mortgage_charges / 100)
            #     gst_percent = lender.igst_on_mortgage_charges
            #     self.create_loan_transaction(
            #         "IGST on Mortgage Charges",
            #         igst,
            #         gst_percent,
            #         charge_reference=mortgage_charges_reference.name,
            #         approve=True,
            #     )

        if self.instrument_type == "Mutual Fund":
            lien_initiate_charges = lender.lien_initiate_charges
            if lender.lien_initiate_charge_type == "Percentage":
                days_left_to_expiry = days_in_year
                amount = (
                    (lien_initiate_charges / 100)
                    * self.sanctioned_limit
                    / days_in_year
                    * days_left_to_expiry
                )
                lien_initiate_charges = self.validate_loan_charges_amount(
                    lender,
                    amount,
                    "lien_initiate_charge_minimum_amount",
                    "lien_initiate_charge_maximum_amount",
                )

            if lien_initiate_charges > 0:
                lien_initiate_charges_reference = self.create_loan_transaction(
                    "Lien Charges",
                    lien_initiate_charges,
                    approve=True,
                )
                # Charges on GST
                # if lender.cgst_on_lien_charges > 0:
                #     cgst = lien_initiate_charges * (lender.cgst_on_lien_charges / 100)
                #     gst_percent = lender.cgst_on_lien_charges
                #     self.create_loan_transaction(
                #         "CGST on Lien Charges",
                #         cgst,
                #         gst_percent,
                #         charge_reference=lien_initiate_charges_reference.name,
                #         approve=True,
                #     )
                # if lender.sgst_on_lien_charges > 0:
                #     sgst = lien_initiate_charges * (lender.sgst_on_lien_charges / 100)
                #     gst_percent = lender.sgst_on_lien_charges
                #     self.create_loan_transaction(
                #         "SGST on Lien Charges",
                #         sgst,
                #         gst_percent,
                #         charge_reference=lien_initiate_charges_reference.name,
                #         approve=True,
                #     )
                # if lender.igst_on_lien_charges > 0:
                #     igst = lien_initiate_charges * (lender.igst_on_lien_charges / 100)
                #     gst_percent = lender.igst_on_lien_charges
                #     self.create_loan_transaction(
                #         "IGST on Lien Charges",
                #         igst,
                #         gst_percent,
                #         charge_reference=lien_initiate_charges_reference.name,
                #         approve=True,
                #     )

    def validate_loan_charges_amount(self, lender_doc, amount, min_field, max_field):
        lender_dict = lender_doc.as_dict()
        if (lender_dict[min_field] > 0) and (amount < lender_dict[min_field]):
            amount = lender_dict[min_field]
        elif (lender_dict[max_field] > 0) and (amount > lender_dict[max_field]):
            amount = lender_dict[max_field]
        return amount

    def create_loan_transaction(
        self,
        transaction_type,
        amount,
        gst_percent=None,
        charge_reference=None,
        approve=False,
        transaction_id=None,
        loan_margin_shortfall_name=None,
        is_for_interest=None,
        razorpay_event=None,
        order_id=None,
    ):
        loan_transaction = frappe.get_doc(
            {
                "doctype": "Loan Transaction",
                "loan": self.name,
                "lender": self.lender,
                "amount": round(amount, 2),
                "transaction_type": transaction_type,
                "gst_percent": gst_percent,
                "record_type": LoanTransaction.loan_transaction_map.get(
                    transaction_type, "DR"
                ),
                "time": frappe.utils.now_datetime(),
            }
        )

        if transaction_id:
            loan_transaction.transaction_id = transaction_id
        if loan_margin_shortfall_name:
            loan_transaction.loan_margin_shortfall = loan_margin_shortfall_name
        if is_for_interest:
            loan_transaction.is_for_interest = is_for_interest
        if razorpay_event:
            loan_transaction.razorpay_event = razorpay_event
        if order_id:
            loan_transaction.order_id = order_id
        if charge_reference:
            loan_transaction.charge_reference = charge_reference
        if gst_percent:
            loan_transaction.gst_percent = gst_percent

        loan_transaction.insert(ignore_permissions=True)

        if approve:
            if not transaction_id:
                loan_transaction.transaction_id = loan_transaction.name
            loan_transaction.status = "Approved"
            loan_transaction.workflow_state = "Approved"
            loan_transaction.docstatus = 1
            loan_transaction.save(ignore_permissions=True)

        frappe.db.commit()
        return loan_transaction

    def get_customer(self):
        return frappe.get_doc("Loan Customer", self.customer)

    def update_loan_balance(self, check_for_shortfall=True):
        summary = self.get_transaction_summary()
        # frappe.db.set_value(
        #     self.doctype,
        #     self.name,
        #     "balance",
        #     round(summary.get("outstanding"), 2),
        #     update_modified=False,
        # )
        # frappe.db.set_value(
        #     self.doctype,
        #     self.name,
        #     "balance_str",
        #     lms.amount_formatter(round(summary.get("outstanding"), 2)),
        #     update_modified=False,
        # )
        self.balance = round(summary.get("outstanding"), 2)
        self.balance_str = lms.amount_formatter(round(summary.get("outstanding"), 2))
        self.save(ignore_permissions=True)
        if check_for_shortfall:
            # TODO: Change this in min max branch also increase loan scenario
            self.check_for_shortfall(on_approval=True)

    # def on_update(self):
    #     frappe.enqueue_doc("Loan", self.name, method="check_for_shortfall")

    def get_transaction_summary(self):
        # sauce: https://stackoverflow.com/a/23827026/9403680
        sql = """
			SELECT loan
				, SUM(COALESCE(CASE WHEN record_type = 'DR' THEN amount END,0)) total_debits
				, SUM(COALESCE(CASE WHEN record_type = 'CR' THEN amount END,0)) total_credits
				, SUM(COALESCE(CASE WHEN record_type = 'DR' THEN amount END,0))
				- SUM(COALESCE(CASE WHEN record_type = 'CR' THEN amount END,0)) outstanding
			FROM `tabLoan Transaction`
			WHERE loan = '{}' AND docstatus = 1
			GROUP BY loan
			HAVING outstanding <> 0;
		""".format(
            self.name
        )

        res = frappe.db.sql(sql, as_dict=1)

        return (
            res[0]
            if len(res)
            else frappe._dict(
                {
                    "loan": self.name,
                    "total_debits": 0,
                    "total_credits": 0,
                    "outstanding": 0,
                }
            )
        )

    def fill_items(self):
        self.total_collateral_value = 0
        drawing_power = 0
        if self.instrument_type == "Shares":
            for i in self.items:
                i.amount = i.price * i.pledged_quantity
                self.total_collateral_value += i.amount

            drawing_power = round(
                (self.total_collateral_value * (self.allowable_ltv / 100)), 2
            )
        else:  # for Drawing power Calculation
            for i in self.items:
                i.amount = i.price * i.pledged_quantity
                i.eligible_amount = (i.eligible_percentage / 100) * i.amount
                self.total_collateral_value += i.amount
                drawing_power += i.eligible_amount

            drawing_power = round(
                drawing_power,
                2,
            )

        self.drawing_power = (
            drawing_power
            if drawing_power <= self.sanctioned_limit
            else self.sanctioned_limit
        )
        # Updating actual drawing power
        self.actual_drawing_power = round(
            (drawing_power),
            2,
        )

    def get_collateral_list(
        self, group_by_psn=False, where_clause="", having_clause=""
    ):
        # sauce: https://stackoverflow.com/a/23827026/9403680
        sql = """
			SELECT
				cl.loan, cl.isin, cl.psn, cl.pledgor_boid, cl.pledgee_boid, cl.prf, cl.scheme_code, cl.folio, cl.amc_code,
				s.price, s.security_name,
                (select sc.category_name from `tabSecurity Category` sc  where sc.name = als.security_category) as security_category
				, SUM(COALESCE(CASE WHEN request_type = 'Pledge' THEN quantity END,0))
				- SUM(COALESCE(CASE WHEN request_type = 'Unpledge' THEN quantity END,0))
				- SUM(COALESCE(CASE WHEN request_type = 'Sell Collateral' THEN quantity END,0)) quantity
			FROM `tabCollateral Ledger` cl
			LEFT JOIN `tabSecurity` s
				ON cl.isin = s.isin
			LEFT JOIN `tabAllowed Security` als
				ON cl.isin = als.isin AND cl.lender = als.lender
			WHERE cl.loan = '{loan}' {where_clause} AND cl.lender_approval_status = 'Approved'
			GROUP BY cl.isin, cl.folio{group_by_psn_clause}{having_clause};
		""".format(
            loan=self.name,
            where_clause=where_clause if where_clause else "",
            group_by_psn_clause=" ,cl.psn" if group_by_psn else "",
            having_clause=having_clause if having_clause else "",
        )

        return frappe.db.sql(sql, debug=True, as_dict=1)

    def get_collateral_list_old(
        self, group_by_psn=False, where_clause="", having_clause=""
    ):
        # sauce: https://stackoverflow.com/a/23827026/9403680
        sql = """
			SELECT
				cl.loan, cl.isin, cl.psn, cl.pledgor_boid, cl.pledgee_boid, cl.scheme_code, cl.folio, cl.amc_code,
				s.price, s.security_name,
				als.security_category
				, SUM(COALESCE(CASE WHEN request_type = 'Pledge' THEN quantity END,0))
				- SUM(COALESCE(CASE WHEN request_type = 'Unpledge' THEN quantity END,0))
				- SUM(COALESCE(CASE WHEN request_type = 'Sell Collateral' THEN quantity END,0)) quantity
			FROM `tabCollateral Ledger` cl
			LEFT JOIN `tabSecurity` s
				ON cl.isin = s.isin
			LEFT JOIN `tabAllowed Security` als
				ON cl.isin = als.isin AND cl.lender = als.lender
			WHERE cl.loan = '{loan}' {where_clause} AND cl.lender_approval_status = 'Approved'
			GROUP BY cl.isin{group_by_psn_clause}{having_clause};
		""".format(
            loan=self.name,
            where_clause=where_clause if where_clause else "",
            group_by_psn_clause=" ,cl.psn" if group_by_psn else "",
            having_clause=having_clause if having_clause else "",
        )

        return frappe.db.sql(sql, debug=True, as_dict=1)

    def update_collateral_ledger(self, price, isin):
        sql = """Update `tabCollateral Ledger`
        set price = {}, value = ({}*quantity)
        where loan = '{}' and isin = '{}' """.format(
            price, price, self.name, isin
        )

        return frappe.db.sql(sql, as_dict=1)

    def update_items(self):
        check = False

        collateral_list = self.get_collateral_list()
        collateral_list_map = {
            "{}{}".format(i.isin, i.folio if i.folio else ""): i
            for i in collateral_list
        }
        # updating existing and
        # setting check flag
        for i in self.items:
            isin_folio_combo = "{}{}".format(i.isin, i.folio if i.folio else "")
            curr = collateral_list_map.get(isin_folio_combo)
            # curr = collateral_list_map.get(i.isin)
            # print(check, i.price, curr.price, not check or i.price != curr.price)
            if (not check or i.price != curr.price) and i.pledged_quantity > 0:
                check = True
                self.update_collateral_ledger(curr.price, curr.isin)

            i.price = curr.price
            i.pledged_quantity = curr.quantity

            del collateral_list_map[isin_folio_combo]

        # adding new items if any
        for i in collateral_list_map.values():
            loan_item = frappe.get_doc(
                {
                    "doctype": "Loan Item",
                    "isin": i.isin,
                    "security_name": i.security_name,
                    "security_category": i.security_category,
                    "pledged_quantity": i.quantity,
                    "price": i.price,
                }
            )

            self.append("items", loan_item)

        return check

    def update_items_old(self):
        check = False

        collateral_list = self.get_collateral_list()
        collateral_list_map = {i.isin: i for i in collateral_list}
        # updating existing and
        # setting check flag
        for i in self.items:
            curr = collateral_list_map.get(i.isin)
            # print(check, i.price, curr.price, not check or i.price != curr.price)
            if (not check or i.price != curr.price) and i.pledged_quantity > 0:
                check = True
                self.update_collateral_ledger(curr.price, curr.isin)

            i.price = curr.price
            i.pledged_quantity = curr.quantity

            del collateral_list_map[curr.isin]

        # adding new items if any
        for i in collateral_list_map.values():
            loan_item = frappe.get_doc(
                {
                    "doctype": "Loan Item",
                    "isin": i.isin,
                    "security_name": i.security_name,
                    "security_category": i.security_category,
                    "pledged_quantity": i.quantity,
                    "price": i.price,
                }
            )

            self.append("items", loan_item)

        return check

    def check_for_shortfall(self, on_approval=False):
        try:
            current_hour = frappe.utils.now_datetime().hour
            las_settings = frappe.get_single("LAS Settings")
            between_market_hours = (
                frappe.utils.now_datetime().date()
                not in lms.holiday_list(is_market_holiday=1)
                and (
                    las_settings.market_start_time
                    <= current_hour
                    < las_settings.market_end_time
                )
            )
            check = False
            old_total_collateral_value = self.total_collateral_value

            securities_price_map = lms.get_security_prices([i.isin for i in self.items])
            check = self.update_items()

            msg_type = ["A sale", "sell"]
            if self.instrument_type == "Mutual Fund":
                msg_type = ["An invoke", "invoke"]

            if check:
                self.fill_items()
                self.save(ignore_permissions=True)

                loan_margin_shortfall = self.get_margin_shortfall()
                if loan_margin_shortfall.status == "Sell Triggered":
                    lender = frappe.db.sql(
                        "select u.email,u.first_name from `tabUser` as u left join `tabHas Role` as r on u.email=r.parent where role='Lender'",
                        as_dict=1,
                    )
                    if lender:
                        msg = "Hello {}, Sell is Triggered for Margin Shortfall of Loan {}. Please take Action.".format(
                            lender[0].get("first_name"), self.name
                        )

                        frappe.enqueue(
                            method=frappe.sendmail,
                            recipients=[lender[0].get("email")],
                            sender=None,
                            subject="Sell Triggered Notification",
                            message=msg,
                        )
                else:
                    old_shortfall_action = loan_margin_shortfall.margin_shortfall_action
                    loan_margin_shortfall.fill_items()
                    if old_shortfall_action:
                        loan_margin_shortfall.set_deadline(old_shortfall_action)

                    if loan_margin_shortfall.is_new():
                        if loan_margin_shortfall.shortfall_percentage > 0:
                            loan_margin_shortfall.insert(ignore_permissions=True)
                            # if (
                            #     frappe.utils.now_datetime()
                            #     > loan_margin_shortfall.deadline
                            # ):
                            #     loan_margin_shortfall.status = "Sell Triggered"
                            #     loan_margin_shortfall.save(ignore_permissions=True)
                    else:
                        if loan_margin_shortfall.shortfall_percentage == 0:
                            loan_margin_shortfall.status = "Resolved"
                            loan_margin_shortfall.action_time = (
                                frappe.utils.now_datetime()
                            )
                            # if (
                            #     loan_margin_shortfall.shortfall_percentage > 0
                            #     and frappe.utils.now_datetime()
                            #     > loan_margin_shortfall.deadline
                            # ):
                            #     loan_margin_shortfall.status = "Sell Triggered"
                            #     mess = "Dear Customer,\nURGENT NOTICE. {} has been triggered in your loan account {} due to inaction on your part to mitigate margin shortfall.The lender will {} required collateral and deposit the proceeds in your loan account to fulfill the shortfall. Kindly check the app for details. Spark Loans".format(
                            #         msg_type[0], self.name, msg_type[1]
                            #     )
                            #     fcm_notification = frappe.get_doc(
                            #         "Spark Push Notification",
                            #         "Sale triggerred inaction",
                            #         fields=["*"],
                            #     )
                            #     message = fcm_notification.message.format(
                            #         sale="sale", loan=self.name
                            #     )
                            #     if self.instrument_type == "Mutual Fund":
                            #         message = fcm_notification.message.format(
                            #             sale="invoke", loan=self.name
                            #         )
                            #         fcm_notification = fcm_notification.as_dict()
                            #         fcm_notification["title"] = "Invoke triggerred"
                            #     # message = fcm_notification.message.format(loan=self.name)
                            #     doc = frappe.get_doc(
                            #         "User KYC", self.get_customer().choice_kyc
                            #     ).as_dict()
                            #     doc["loan_margin_shortfall"] = {"loan": self.name}
                            #     email_subject = "Sale Triggered Cross Deadline"
                            #     if self.instrument_type == "Mutual Fund":
                            #         email_subject = "MF Sale Triggered Cross Deadline"
                            #     frappe.enqueue_doc(
                            #         "Notification",
                            #         email_subject,
                            #         method="send",
                            #         doc=doc,
                            #     )
                            #     frappe.enqueue(
                            #         method=send_sms,
                            #         receiver_list=[self.get_customer().phone],
                            #         msg=mess,
                            #     )
                            #     lms.send_spark_push_notification(
                            #         fcm_notification=fcm_notification,
                            #         message=message,
                            #         loan=self.name,
                            #         customer=self.get_customer(),
                            #     )
                            loan_margin_shortfall.save(ignore_permissions=True)

                if (
                    loan_margin_shortfall.status in ["Pending", "Request Pending"]
                    and frappe.utils.now_datetime().hour == 0
                    and frappe.db.exists(
                        "Loan Margin Shortfall", loan_margin_shortfall.name
                    )
                ):
                    self.timer_start_stop_notification(loan_margin_shortfall)

                if between_market_hours or (not between_market_hours and on_approval):
                    # 1st scenario - after market hours but not with cron
                    # 2nd scenario - between market hours with cron and approval also

                    # alerts comparison with percentage and amount
                    self.send_alerts_to_customer(old_total_collateral_value)
                    # update pending withdraw allowable for this loan
                    self.update_pending_withdraw_requests()
                    # update pending topup requests for this loan
                    # self.update_pending_topup_amount()
                    # update pending sell collateral application for this loan
                    self.update_pending_sell_collateral_amount()
                    unpledge_application = self.get_unpledge_application()
                    if unpledge_application:
                        unpledge_application.unpledge_with_margin_shortfall()
                frappe.db.commit()
        except Exception:
            frappe.log_error(
                frappe.get_traceback() + "\n\nloan name :-\n" + self.name,
                title=frappe._("Check for Shortfall Error"),
            )

    def timer_start_stop_notification(self, loan_margin_shortfall):
        today = frappe.utils.now_datetime().date()
        yesterday = today - timedelta(days=1)
        fcm_notification = {}
        message = ""
        doc = frappe.get_doc("User KYC", self.get_customer().choice_kyc).as_dict()
        if isinstance(loan_margin_shortfall.creation, str):
            loan_margin_shortfall.creation = datetime.strptime(
                loan_margin_shortfall.creation, "%Y-%m-%d %H:%M:%S.%f"
            )

        if yesterday not in lms.holiday_list(
            is_bank_holiday=1
        ) and today in lms.holiday_list(is_bank_holiday=1):
            date_array = set(
                loan_margin_shortfall.creation.date() + timedelta(days=x)
                for x in range(
                    0,
                    (
                        loan_margin_shortfall.deadline.date()
                        - loan_margin_shortfall.creation.date()
                    ).days
                    + 1,
                )
            )
            holidays = sorted(
                list(date_array.intersection(set(lms.holiday_list(is_bank_holiday=1))))
            )

            if (
                loan_margin_shortfall.creation.date()
                in lms.holiday_list(is_bank_holiday=1)
                and loan_margin_shortfall.creation.date()
                == frappe.utils.now_datetime().date()
            ):
                datetime_list = [loan_margin_shortfall.creation.date()]
                holidays.pop(0)
            else:
                datetime_list = []

            creation = loan_margin_shortfall.creation.date() + timedelta(days=1)
            for days in holidays:
                if days == creation and days >= frappe.utils.now_datetime().date():
                    datetime_list.append(days)
                    creation += timedelta(days=1)
                else:
                    break

            stop_time = str(
                lms.date_str_format(date=datetime_list[0].day)
            ) + datetime_list[0].strftime(" %B %I:%M:%S %p")
            start_time = str(
                lms.date_str_format(date=(datetime_list[-1] + timedelta(days=1)).day)
            ) + datetime_list[-1].strftime(" %B %I:%M:%S %p")

            fcm_notification = frappe.get_doc(
                "Spark Push Notification", "Margin shortfall timer paused", fields=["*"]
            )
            message = fcm_notification.message.format(
                loan=self.name, stop_time=stop_time, start_time=start_time
            )
            msg = "Dear Customer,\nDue to bank holiday the margin shortfall timer on your loan account {loan} has been paused on {stop_time} and will resume on {start_time}. Please check the app and take an appropriate action. -Spark Loans".format(
                loan=self.name, stop_time=stop_time, start_time=start_time
            )

            doc["loan_margin_shortfall"] = {
                "loan": self.name,
                "stop_time": stop_time,
                "start_time": start_time,
            }
            frappe.enqueue_doc(
                "Notification",
                "Margin shortfall - Timer Paused",
                method="send",
                doc=doc,
            )

        elif yesterday in lms.holiday_list(
            is_bank_holiday=1
        ) and today not in lms.holiday_list(is_bank_holiday=1):
            fcm_notification = frappe.get_doc(
                "Spark Push Notification",
                "Margin shortfall timer resumed",
                fields=["*"],
            )
            message = fcm_notification.message.format(loan=self.name)
            msg = frappe.get_doc(
                "Spark SMS Notification", "Margin shortfall - timer resumed"
            ).message.format(loan=self.name)
            # msg = "Dear Customer,The margin shortfall timer has been resumed on your loan account {loan} Please check the app and take appropriate action. -Spark Loans".format(
            #     loan=self.name
            # )
            doc["loan_margin_shortfall"] = {"loan": self.name}
            frappe.enqueue_doc(
                "Notification",
                "Margin shortfall - Timer Resumed",
                method="send",
                doc=doc,
            )

        if message and msg:
            # lms.send_sms_notification(customer=self.get_customer,msg=msg)
            frappe.enqueue(
                method=send_sms, receiver_list=[self.get_customer().phone], msg=msg
            )
            lms.send_spark_push_notification(
                fcm_notification=fcm_notification,
                message=message,
                loan=self.name,
                customer=self.get_customer(),
            )

    def send_alerts_to_customer(self, old_total_collateral_value):
        try:
            customer = self.get_customer()

            if customer.alerts_based_on_percentage:
                if self.total_collateral_value > (
                    old_total_collateral_value
                    + (
                        old_total_collateral_value
                        * int(customer.alerts_based_on_percentage)
                        / 100
                    )
                ):
                    try:
                        fa = FirebaseAdmin()
                        fa.send_data(
                            data={
                                "event": "Alert price UP by {}%".format(
                                    customer.alerts_based_on_percentage
                                ),
                            },
                            tokens=lms.get_firebase_tokens(customer.user),
                        )
                    except Exception:
                        pass
                    finally:
                        fa.delete_app()

                elif self.total_collateral_value < (
                    old_total_collateral_value
                    - (
                        old_total_collateral_value
                        * customer.alerts_based_on_percentage
                        / 100
                    )
                ):
                    try:
                        fa = FirebaseAdmin()
                        fa.send_data(
                            data={
                                "event": "Alert price DOWN by {}%".format(
                                    customer.alerts_based_on_percentage
                                ),
                            },
                            tokens=lms.get_firebase_tokens(customer.user),
                        )
                    except Exception:
                        pass
                    finally:
                        fa.delete_app()

            elif customer.alerts_based_on_amount:
                if self.total_collateral_value > (
                    old_total_collateral_value + customer.alerts_based_on_amount
                ):
                    try:
                        fa = FirebaseAdmin()
                        fa.send_data(
                            data={
                                "event": "Alert price UP by Rs. {}".format(
                                    customer.alerts_based_on_amount
                                ),
                            },
                            tokens=lms.get_firebase_tokens(customer.user),
                        )
                    except Exception:
                        pass
                    finally:
                        fa.delete_app()

                elif self.total_collateral_value < (
                    old_total_collateral_value - customer.alerts_based_on_amount
                ):
                    try:
                        fa = FirebaseAdmin()
                        fa.send_data(
                            data={
                                "event": "Alert price DOWN by Rs. {}".format(
                                    customer.alerts_based_on_amount
                                ),
                            },
                            tokens=lms.get_firebase_tokens(customer.user),
                        )
                    except Exception:
                        pass
                    finally:
                        fa.delete_app()
        except Exception as e:
            frappe.log_error()

    def update_pending_withdraw_requests(self):
        all_pending_withdraw_requests = frappe.get_all(
            "Loan Transaction",
            filters={
                "loan": self.name,
                "transaction_type": "Withdrawal",
                "status": "Pending",
                "creation": ("<=", frappe.utils.now_datetime()),
            },
            fields=["*"],
            order_by="creation asc",
        )
        for withdraw_req in all_pending_withdraw_requests:
            max_withdraw_amount = self.maximum_withdrawable_amount(
                withdraw_req["name"], withdraw_req["creation"]
            )
            loan_transaction_doc = frappe.get_doc(
                "Loan Transaction", withdraw_req["name"]
            )
            loan_transaction_doc.db_set("allowable", max_withdraw_amount)

    def get_margin_shortfall(self):
        sell_triggered_shortfall_name = frappe.db.get_value(
            "Loan Margin Shortfall",
            {"loan": self.name, "status": "Sell Triggered"},
            "name",
        )
        margin_shortfall_name = frappe.db.get_value(
            "Loan Margin Shortfall",
            {"loan": self.name, "status": ["in", ["Pending", "Request Pending"]]},
            "name",
        )
        if not margin_shortfall_name and not sell_triggered_shortfall_name:
            margin_shortfall = frappe.new_doc("Loan Margin Shortfall")
            margin_shortfall.loan = self.name
            return margin_shortfall

        return frappe.get_doc(
            "Loan Margin Shortfall",
            sell_triggered_shortfall_name
            if sell_triggered_shortfall_name
            else margin_shortfall_name,
        )

    def get_updated_total_collateral_value(self):
        securities = [i.isin for i in self.items]

        securities_price_map = lms.get_security_prices(securities)

        updated_total_collateral_value = 0

        for i in self.items:
            updated_total_collateral_value += (
                i.pledged_quantity * securities_price_map.get(i.isin)
            )

        return updated_total_collateral_value

    def get_rebate_threshold(self):
        rebate_threshold = frappe.db.get_value(
            "Lender", self.lender, "rebait_threshold"
        )
        return 0 if not rebate_threshold else rebate_threshold

    def get_default_threshold(self):
        default_threshold = frappe.db.get_value(
            "Lender", self.lender, "default_interest_threshold"
        )
        return 0 if not default_threshold else default_threshold

    def get_default_interest(self):
        default_interest = frappe.db.get_value(
            "Lender", self.lender, "default_interest"
        )
        return 0 if not default_interest else default_interest

    def calculate_virtual_and_additional_interest(self, input_date=None):
        # for Virtual Interest Entry
        # virtual_interest_doc = self.add_virtual_interest(input_date)
        self.add_virtual_interest(input_date)

        # Now, check if additional interest applicable
        self.check_for_additional_interest(input_date)

        # check if penal interest applicable
        self.add_penal_interest(input_date)

    def add_virtual_interest(self, input_date=None):
        try:
            if input_date:
                input_date = datetime.strptime(input_date, "%Y-%m-%d")
            else:
                input_date = frappe.utils.now_datetime()

            if self.balance > 0:
                if self.is_default == 1:
                    interest_configuration = frappe.db.get_value(
                        "Interest Configuration",
                        {
                            "lender": self.lender,
                            "from_amount": ["<=", self.balance],
                            "to_amount": [">=", self.balance],
                        },
                        "name",
                    )
                else:
                    interest_configuration = ""

                input_date -= timedelta(days=1)

                input_date = input_date.replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )

                virtual_interest_doc_list = frappe.get_all(
                    "Virtual Interest",
                    filters={"loan": self.name, "lender": self.lender},
                    fields=["time"],
                )

                # Check if entry exists for particular date
                if not input_date in [
                    fields["time"] for fields in virtual_interest_doc_list
                ]:
                    # get no of days in month
                    num_of_days_in_month = (
                        (input_date.replace(day=1) + timedelta(days=32)).replace(day=1)
                        - timedelta(days=1)
                    ).day

                    # calculate daily base interest
                    base_interest_daily = self.base_interest / num_of_days_in_month
                    base_amount = self.balance * base_interest_daily / 100

                    # calculate daily rebate interest
                    rebate_interest_daily = self.rebate_interest / num_of_days_in_month
                    rebate_amount = self.balance * rebate_interest_daily / 100

                    virtual_interest_doc = frappe.get_doc(
                        {
                            "doctype": "Virtual Interest",
                            "lender": self.lender,
                            "loan": self.name,
                            "time": input_date,
                            "base_interest": self.base_interest,
                            "rebate_interest": self.rebate_interest,
                            "base_amount": base_amount,
                            "rebate_amount": rebate_amount,
                            "loan_balance": self.balance,
                            "interest_configuration": interest_configuration,
                            "customer_name": self.customer_name,
                        }
                    )
                    virtual_interest_doc.save(ignore_permissions=True)
                    # return virtual_interest_doc.as_dict()

                    if frappe.utils.now_datetime().day == 1:
                        interest_calculation = frappe.get_doc(
                            dict(
                                doctype="Interest Calculation",
                                loan_no=self.name,
                                client_name=self.customer_name,
                                date=input_date.date(),
                                transaction_type="-",
                                crdr="-",
                                debit="-",
                                loan_balance=self.balance,
                                interest_with_rebate=base_amount + rebate_amount,
                                interest_without_rebate=base_amount,
                                creation_date=frappe.utils.now_datetime().date(),
                            ),
                        ).insert(ignore_permissions=True)
            input_date += timedelta(days=1)
            self.day_past_due = self.calculate_day_past_due(input_date)
            self.map_loan_summary_values()
            self.save(ignore_permissions=True)
            frappe.db.commit()

        except Exception:
            frappe.log_error(
                message=frappe.get_traceback()
                + "\nVirtual Interest Details:\n"
                + json.dumps(
                    {
                        "loan": self.name,
                        "customer_id": self.customer,
                        "customer_name": self.customer_name,
                    }
                ),
                title=frappe._("Virtual Interest Error"),
            )

    def check_for_additional_interest(self, input_date=None):
        try:
            # daily scheduler - executes at start of day i.e 00:00
            if input_date:
                current_date = datetime.strptime(input_date, "%Y-%m-%d")
            else:
                current_date = frappe.utils.now_datetime()

            additional_interest_transaction_list = frappe.get_all(
                "Loan Transaction",
                filters={
                    "loan": self.name,
                    "lender": self.lender,
                    "transaction_type": "Additional Interest",
                },
                fields=["time"],
            )

            # job_date = (current_date - timedelta(days=1)).replace(
            #     hour=23, minute=59, second=59, microsecond=999999
            # )
            last_day_of_prev_month = current_date.replace(day=1) - timedelta(days=1)
            prev_month = last_day_of_prev_month.month
            prev_month_year = last_day_of_prev_month.year

            # check if any not paid booked interest transaction entry plus check if Is Additional Interest not applied
            booked_interest = frappe.db.sql(
                "select * from `tabLoan Transaction` where loan='{}' and lender='{}' and transaction_type='Interest' and unpaid_interest > 0 and additional_interest is null and DATE_FORMAT(time, '%m')={} and DATE_FORMAT(time, '%Y')={} order by time desc limit 1".format(
                    self.name, self.lender, prev_month, prev_month_year
                ),
                as_dict=1,
            )

            if booked_interest:
                # check if days spent greater than rebate threshold
                rebate_threshold = int(self.get_rebate_threshold())
                if rebate_threshold:
                    transaction_time = booked_interest[0]["time"] + timedelta(
                        days=rebate_threshold
                    )

                    if current_date > transaction_time and not transaction_time.replace(
                        hour=23, minute=59, second=59, microsecond=999999
                    ) in [
                        fields["time"]
                        for fields in additional_interest_transaction_list
                    ]:
                        # Sum of rebate amounts
                        rebate_interest_sum = frappe.db.sql(
                            "select sum(rebate_amount) as amount from `tabVirtual Interest` where loan = '{}' and lender = '{}' and DATE_FORMAT(time, '%Y') = {} and DATE_FORMAT(time, '%m') = {}".format(
                                self.name, self.lender, prev_month_year, prev_month
                            ),
                            as_dict=1,
                        )

                        # Additional Interest Entry
                        additional_interest_transaction = frappe.get_doc(
                            {
                                "doctype": "Loan Transaction",
                                "loan": self.name,
                                "lender": self.lender,
                                "transaction_type": "Additional Interest",
                                "record_type": "DR",
                                "amount": round(rebate_interest_sum[0]["amount"], 2),
                                "unpaid_interest": round(
                                    rebate_interest_sum[0]["amount"], 2
                                ),
                                "time": transaction_time.replace(
                                    hour=23, minute=59, second=59, microsecond=999999
                                ),
                            }
                        )
                        additional_interest_transaction.insert(ignore_permissions=True)
                        additional_interest_transaction.transaction_id = (
                            additional_interest_transaction.name
                        )
                        # Update booked interest entry
                        booked_interest_transaction_doc = frappe.get_doc(
                            "Loan Transaction", booked_interest[0]["name"]
                        )
                        booked_interest_transaction_doc.db_set(
                            "additional_interest", additional_interest_transaction.name
                        )
                        additional_interest_transaction.status = "Approved"
                        additional_interest_transaction.workflow_state = "Approved"
                        additional_interest_transaction.docstatus = 1
                        additional_interest_transaction.save(ignore_permissions=True)

                        # Mark as booked for rebate
                        frappe.db.sql(
                            "update `tabVirtual Interest` set is_booked_for_rebate = 1 where loan = '{}' and is_booked_for_rebate = 0 and DATE_FORMAT(time, '%Y') = {} and DATE_FORMAT(time, '%m') = {}".format(
                                self.name, prev_month_year, prev_month
                            )
                        )

                        frappe.db.commit()
                        self.reload()
                        self.map_loan_summary_values()
                        self.save(ignore_permissions=True)

                        frappe.db.commit()

                        doc = frappe.get_doc(
                            "User KYC", self.get_customer().choice_kyc
                        ).as_dict()
                        doc["loan_name"] = self.name
                        doc[
                            "transaction_type"
                        ] = additional_interest_transaction.transaction_type
                        doc["unpaid_interest"] = round(
                            additional_interest_transaction.unpaid_interest, 2
                        )

                        frappe.enqueue_doc(
                            "Notification", "Interest Due", method="send", doc=doc
                        )

                        msg = frappe.get_doc(
                            "Spark SMS Notification", "Rebate reversed"
                        ).message.format(
                            round(additional_interest_transaction.unpaid_interest, 2),
                            self.name,
                        )
                        # msg = "Dear Customer,\nRebate of Rs.  {}  was reversed in your loan account {}. This will appear as 'Addl Interest' in your loan account. \nPlease pay the interest due before the 15th of this month in order to avoid the penal interest/charges.Kindly check the app for details - Spark Loans".format(
                        #     round(additional_interest_transaction.unpaid_interest, 2),
                        #     self.name,
                        # )
                        fcm_notification = frappe.get_doc(
                            "Spark Push Notification", "Rebate reversed", fields=["*"]
                        )
                        message = fcm_notification.message.format(
                            unpaid_interest=round(
                                additional_interest_transaction.unpaid_interest, 2
                            ),
                            loan=self.name,
                        )

                        if msg:
                            # lms.send_sms_notification(customer=self.get_customer,msg=msg)
                            receiver_list = [str(self.get_customer().phone)]
                            if doc.mob_num:
                                receiver_list.append(str(doc.mob_num))
                            if doc.choice_mob_no:
                                receiver_list.append(str(doc.choice_mob_no))

                            receiver_list = list(set(receiver_list))

                            frappe.enqueue(
                                method=send_sms, receiver_list=receiver_list, msg=msg
                            )

                        lms.send_spark_push_notification(
                            fcm_notification=fcm_notification,
                            message=message,
                            loan=self.name,
                            customer=self.get_customer(),
                        )
                        return additional_interest_transaction.as_dict()
        except Exception:
            frappe.log_error(
                message=frappe.get_traceback()
                + "\nAdditional Interest Details:\n"
                + json.dumps(
                    {
                        "loan": self.name,
                        "customer_id": self.customer,
                        "customer_name": self.customer_name,
                    }
                ),
                title=frappe._("Additional Interest Error"),
            )

    def book_virtual_interest_for_month(self, input_date=None):
        try:
            if input_date:
                current_date = datetime.strptime(input_date, "%Y-%m-%d")
            else:
                current_date = frappe.utils.now_datetime()

            # Check if entry exists for particular date and date should be 1
            booked_interest_transaction_list = frappe.get_all(
                "Loan Transaction",
                filters={
                    "loan": self.name,
                    "lender": self.lender,
                    "transaction_type": "Interest",
                },
                fields=["time"],
            )

            job_date = (current_date - timedelta(days=1)).replace(
                hour=23, minute=59, second=59, microsecond=999999
            )

            if current_date.day == 1 and not job_date in [
                fields["time"] for fields in booked_interest_transaction_list
            ]:
                prev_month = job_date.month
                prev_month_year = job_date.year
                # return [job_date, prev_month, prev_month_year]

                check_if_exist = frappe.db.sql(
                    "select count(name) as total_count from `tabLoan Transaction` where loan = '{}' and lender = '{}' and transaction_type = 'Interest' and DATE_FORMAT(time, '%Y') = {} and DATE_FORMAT(time, '%m') = {}".format(
                        self.name, self.lender, prev_month_year, prev_month
                    ),
                    as_dict=1,
                )

                if check_if_exist[0]["total_count"] == 0:
                    # Add loan 'Interests' transaction Entry
                    virtual_interest_sum = frappe.db.sql(
                        "select sum(base_amount) as amount from `tabVirtual Interest` where loan = '{}' and lender = '{}' and DATE_FORMAT(time, '%Y') = {} and DATE_FORMAT(time, '%m') = {}".format(
                            self.name, self.lender, prev_month_year, prev_month
                        ),
                        as_dict=1,
                    )
                    if virtual_interest_sum[0]["amount"] != None:

                        loan_transaction = frappe.get_doc(
                            {
                                "doctype": "Loan Transaction",
                                "loan": self.name,
                                "lender": self.lender,
                                "amount": round(virtual_interest_sum[0]["amount"], 2),
                                "unpaid_interest": round(
                                    virtual_interest_sum[0]["amount"], 2
                                ),
                                "transaction_type": "Interest",
                                "record_type": "DR",
                                "time": job_date,
                            }
                        )
                        loan_transaction.insert(ignore_permissions=True)
                        loan_transaction.transaction_id = loan_transaction.name
                        loan_transaction.status = "Approved"
                        loan_transaction.workflow_state = "Approved"
                        loan_transaction.docstatus = 1
                        loan_transaction.save(ignore_permissions=True)

                        # Book Virtual Interest for previous month
                        frappe.db.sql(
                            "update `tabVirtual Interest` set is_booked_for_base = 1 where loan = '{}' and is_booked_for_base = 0 and DATE_FORMAT(time, '%Y') = {} and DATE_FORMAT(time, '%m') = {}".format(
                                self.name, prev_month_year, prev_month
                            )
                        )
                        self.reload()
                        self.day_past_due = self.calculate_day_past_due(current_date)
                        self.save(ignore_permissions=True)
                        frappe.db.commit()
                        interest_calculation = frappe.get_doc(
                            dict(
                                doctype="Interest Calculation",
                                loan_no=self.name,
                                client_name=self.customer_name,
                                date=job_date.date(),
                                transaction_type="Interest",
                                crdr="DR",
                                debit=round(virtual_interest_sum[0]["amount"], 2),
                                loan_balance=loan_transaction.closing_balance,
                            ),
                        ).insert(ignore_permissions=True)
                        frappe.db.commit()

                        doc = frappe.get_doc(
                            "User KYC", self.get_customer().choice_kyc
                        ).as_dict()
                        doc["loan_name"] = self.name
                        doc["transaction_type"] = loan_transaction.transaction_type
                        doc["unpaid_interest"] = round(
                            loan_transaction.unpaid_interest, 2
                        )

                        frappe.enqueue_doc(
                            "Notification", "Interest Due", method="send", doc=doc
                        )

                        msg = frappe.get_doc(
                            "Spark SMS Notification", "Interest Due"
                        ).message.format(
                            round(loan_transaction.unpaid_interest, 2), self.name
                        )
                        # msg = "Dear Customer,\nAn interest of Rs.  {} is due on your loan account {}.\nPlease pay the interest due before the 7th of this month in order to continue to enjoy the rebate provided on the interest rate. Kindly check the app for details. - Spark Loans".format(
                        #     round(loan_transaction.unpaid_interest, 2), self.name
                        # )

                        fcm_notification = frappe.get_doc(
                            "Spark Push Notification", "Interest due", fields=["*"]
                        )
                        message = fcm_notification.message.format(
                            unpaid_interest=round(loan_transaction.unpaid_interest, 2),
                            loan=self.name,
                        )
                        if msg:
                            # lms.send_sms_notification(customer=self.get_customer,msg=msg)
                            receiver_list = [str(self.get_customer().phone)]
                            if doc.mob_num:
                                receiver_list.append(str(doc.mob_num))
                            if doc.choice_mob_no:
                                receiver_list.append(str(doc.choice_mob_no))

                            receiver_list = list(set(receiver_list))

                            frappe.enqueue(
                                method=send_sms, receiver_list=receiver_list, msg=msg
                            )

                        lms.send_spark_push_notification(
                            fcm_notification=fcm_notification,
                            message=message,
                            loan=self.name,
                            customer=self.get_customer(),
                        )
        except Exception:
            frappe.log_error(
                message=frappe.get_traceback()
                + "\nBooked Interest Details:\n"
                + json.dumps(
                    {
                        "loan": self.name,
                        "customer_id": self.customer,
                        "customer_name": self.customer_name,
                    }
                ),
                title=frappe._("Booked Interest Error"),
            )

    def add_penal_interest_old(self, input_date=None):
        try:
            # daily scheduler - executes at start of day i.e 00:00
            # get not paid booked interest
            if input_date:
                current_date = datetime.strptime(input_date, "%Y-%m-%d")
            else:
                current_date = frappe.utils.now_datetime()

            penal_interest_transaction_list = frappe.get_all(
                "Loan Transaction",
                filters={
                    "loan": self.name,
                    "lender": self.lender,
                    "transaction_type": "Penal Interest",
                },
                fields=["time"],
            )

            # current_date = (current_date - timedelta(days=1)).replace(
            #     hour=23, minute=59, second=59, microsecond=999999
            # )
            last_day_of_prev_month = current_date.replace(day=1) - timedelta(days=1)
            # num_of_days_in_prev_month = last_day_of_prev_month.day
            prev_month = last_day_of_prev_month.month
            prev_month_year = last_day_of_prev_month.year

            last_day_of_current_month = (
                current_date.replace(day=1) + timedelta(days=32)
            ).replace(day=1) - timedelta(days=1)
            num_of_days_in_current_month = last_day_of_current_month.day

            # check if any not paid booked interest exist
            booked_interest = frappe.db.sql(
                "select * from `tabLoan Transaction` where loan='{}' and lender='{}' and transaction_type='Interest' and unpaid_interest > 0 and DATE_FORMAT(time, '%m')={} and DATE_FORMAT(time, '%Y')={} order by time desc limit 1".format(
                    self.name, self.lender, prev_month, prev_month_year
                ),
                as_dict=1,
            )

            if booked_interest:
                # get default threshold
                default_threshold = int(self.get_default_threshold())
                if default_threshold:
                    transaction_time = booked_interest[0]["time"] + timedelta(
                        days=default_threshold
                    )
                    # check if interest booked time is more than default threshold
                    if current_date > transaction_time and not current_date in [
                        fields["time"] for fields in penal_interest_transaction_list
                    ]:
                        # if yes, apply penalty interest
                        # calculate daily penalty interest
                        default_interest = int(self.get_default_interest())
                        if default_interest:
                            default_interest_daily = (
                                default_interest / num_of_days_in_current_month
                            )
                            amount = self.balance * default_interest_daily / 100

                            # frappe.db.begin()
                            # Penal Interest Entry
                            penal_interest_transaction = frappe.get_doc(
                                {
                                    "doctype": "Loan Transaction",
                                    "loan": self.name,
                                    "lender": self.lender,
                                    "transaction_type": "Penal Interest",
                                    "record_type": "DR",
                                    "amount": round(amount, 2),
                                    "unpaid_interest": round(amount, 2),
                                    "time": current_date,
                                }
                            )
                            penal_interest_transaction.insert(ignore_permissions=True)
                            penal_interest_transaction.transaction_id = (
                                penal_interest_transaction.name
                            )
                            penal_interest_transaction.status = "Approved"
                            penal_interest_transaction.workflow_state = "Approved"
                            penal_interest_transaction.docstatus = 1
                            penal_interest_transaction.save(ignore_permissions=True)

                            frappe.db.commit()

                            doc = frappe.get_doc(
                                "User KYC", self.get_customer().choice_kyc
                            ).as_dict()
                            doc["loan_name"] = self.name
                            doc[
                                "transaction_type"
                            ] = penal_interest_transaction.transaction_type
                            doc["unpaid_interest"] = round(
                                penal_interest_transaction.unpaid_interest, 2
                            )

                            frappe.enqueue_doc(
                                "Notification", "Interest Due", method="send", doc=doc
                            )
                            msg = frappe.get_doc(
                                "Spark SMS Notification", "Penal interest charged"
                            ).message.format(
                                round(penal_interest_transaction.unpaid_interest, 2),
                                self.name,
                            )
                            # msg = "Dear Customer,\nPenal interest of Rs.{}  has been debited to your loan account {} .\nPlease pay the total interest due immediately in order to avoid further penal interest / charges. Kindly check the app for details - Spark Loans".format(
                            #     round(penal_interest_transaction.unpaid_interest, 2),
                            #     self.name,
                            # )
                            fcm_notification = frappe.get_doc(
                                "Spark Push Notification",
                                "Penal interest charged",
                                fields=["*"],
                            )
                            message = fcm_notification.message.format(
                                unpaid_interest=round(
                                    penal_interest_transaction.unpaid_interest, 2
                                ),
                                loan=self.name,
                            )

                            if msg:
                                # lms.send_sms_notification(customer=self.get_customer,msg=msg)
                                receiver_list = [str(self.get_customer().phone)]
                                if doc.mob_num:
                                    receiver_list.append(str(doc.mob_num))
                                if doc.choice_mob_no:
                                    receiver_list.append(str(doc.choice_mob_no))

                                receiver_list = list(set(receiver_list))

                                frappe.enqueue(
                                    method=send_sms,
                                    receiver_list=receiver_list,
                                    msg=msg,
                                )

                            lms.send_spark_push_notification(
                                fcm_notification=fcm_notification,
                                message=message,
                                loan=self.name,
                                customer=self.get_customer(),
                            )

                            return penal_interest_transaction.as_dict()
        except Exception:
            frappe.log_error(
                message=frappe.get_traceback()
                + "\nPenal Interest Details:\n"
                + json.dumps(
                    {
                        "loan": self.name,
                        "customer_id": self.customer,
                        "customer_name": self.customer_name,
                    }
                ),
                title=frappe._("Penal Interest Error"),
            )

    def add_penal_interest(self, input_date=None):
        try:
            # daily scheduler - executes at start of day i.e 00:00
            # get not paid booked interest
            if input_date:
                current_date = datetime.strptime(input_date, "%Y-%m-%d")
            else:
                current_date = frappe.utils.now_datetime()

            penal_interest_transaction_list = frappe.get_all(
                "Loan Transaction",
                filters={
                    "loan": self.name,
                    "lender": self.lender,
                    "transaction_type": "Penal Interest",
                },
                fields=["time"],
            )

            last_day_of_current_month = (
                current_date.replace(day=1) + timedelta(days=32)
            ).replace(day=1) - timedelta(days=1)
            num_of_days_in_current_month = last_day_of_current_month.day

            # check if any not paid booked interest exist
            unpaid_interest = frappe.db.sql(
                "select SUM(unpaid_interest) as unpaid_interest, time, transaction_type, creation from `tabLoan Transaction` where loan='{}' and lender='{}' and transaction_type='Interest' and unpaid_interest > 0 order by time asc".format(
                    self.name, self.lender
                ),
                as_dict=1,
            )

            if (
                unpaid_interest[0]["unpaid_interest"] != None
                and unpaid_interest[0]["unpaid_interest"] > 0
            ):
                # get default threshold
                default_threshold = int(self.get_default_threshold())
                if default_threshold:
                    transaction_time = unpaid_interest[0]["time"] + timedelta(
                        days=default_threshold
                    )
                    # check if interest booked time is more than default threshold
                    if current_date > transaction_time and not current_date.date() in [
                        fields["time"].date()
                        for fields in penal_interest_transaction_list
                    ]:
                        # if yes, apply penalty interest
                        # calculate daily penalty interest
                        default_interest = int(self.get_default_interest())
                        if default_interest:
                            default_interest_daily = (
                                default_interest / num_of_days_in_current_month
                            )
                            amount = self.balance * default_interest_daily / 100

                            # Penal Interest Entry
                            penal_interest_transaction = frappe.get_doc(
                                {
                                    "doctype": "Loan Transaction",
                                    "loan": self.name,
                                    "lender": self.lender,
                                    "transaction_type": "Penal Interest",
                                    "record_type": "DR",
                                    "amount": round(amount, 2),
                                    "unpaid_interest": round(amount, 2),
                                    "time": current_date,
                                }
                            )
                            penal_interest_transaction.insert(ignore_permissions=True)
                            penal_interest_transaction.transaction_id = (
                                penal_interest_transaction.name
                            )
                            penal_interest_transaction.status = "Approved"
                            penal_interest_transaction.workflow_state = "Approved"
                            penal_interest_transaction.docstatus = 1
                            penal_interest_transaction.save(ignore_permissions=True)

                            frappe.db.commit()

                            doc = frappe.get_doc(
                                "User KYC", self.get_customer().choice_kyc
                            ).as_dict()
                            doc["loan_name"] = self.name
                            doc[
                                "transaction_type"
                            ] = penal_interest_transaction.transaction_type
                            doc["unpaid_interest"] = round(
                                penal_interest_transaction.unpaid_interest, 2
                            )

                            frappe.enqueue_doc(
                                "Notification", "Interest Due", method="send", doc=doc
                            )
                            msg = frappe.get_doc(
                                "Spark SMS Notification", "Penal interest charged"
                            ).message.format(
                                round(penal_interest_transaction.unpaid_interest, 2),
                                self.name,
                            )
                            # msg = "Dear Customer,\nPenal interest of Rs.{}  has been debited to your loan account {} .\nPlease pay the total interest due immediately in order to avoid further penal interest / charges. Kindly check the app for details - Spark Loans".format(
                            #     round(penal_interest_transaction.unpaid_interest, 2),
                            #     self.name,
                            # )
                            fcm_notification = frappe.get_doc(
                                "Spark Push Notification",
                                "Penal interest charged",
                                fields=["*"],
                            )
                            message = fcm_notification.message.format(
                                unpaid_interest=round(
                                    penal_interest_transaction.unpaid_interest, 2
                                ),
                                loan=self.name,
                            )

                            if msg:
                                # lms.send_sms_notification(customer=self.get_customer,msg=msg)
                                receiver_list = [str(self.get_customer().phone)]
                                if doc.mob_num:
                                    receiver_list.append(str(doc.mob_num))
                                if doc.choice_mob_no:
                                    receiver_list.append(str(doc.choice_mob_no))

                                receiver_list = list(set(receiver_list))

                                frappe.enqueue(
                                    method=send_sms,
                                    receiver_list=receiver_list,
                                    msg=msg,
                                )

                            lms.send_spark_push_notification(
                                fcm_notification=fcm_notification,
                                message=message,
                                loan=self.name,
                                customer=self.get_customer(),
                            )

                            return penal_interest_transaction.as_dict()
        except Exception:
            frappe.log_error(
                message=frappe.get_traceback()
                + "\nPenal Interest Details:\n"
                + json.dumps(
                    {
                        "loan": self.name,
                        "customer_id": self.customer,
                        "customer_name": self.customer_name,
                    }
                ),
                title=frappe._("Penal Interest Error"),
            )

    def before_save(self):
        self.total_collateral_value_str = lms.amount_formatter(
            self.total_collateral_value
        )
        self.drawing_power_str = lms.amount_formatter(self.drawing_power)
        self.sanctioned_limit_str = lms.amount_formatter(self.sanctioned_limit)
        self.balance_str = lms.amount_formatter(self.balance)
        if self.custom_base_interest <= 0 or self.custom_rebate_interest <= 0:
            frappe.throw("Base interest and Rebate Interest should be greater than 0")

        if self.wef_date < frappe.utils.now_datetime().date():
            frappe.throw("W.e.f date should be Current date or Future date")

        if self.balance > 0:
            interest_configuration = frappe.db.get_value(
                "Interest Configuration",
                {
                    "lender": self.lender,
                    "from_amount": ["<=", self.balance],
                    "to_amount": [">=", self.balance],
                },
                ["name", "base_interest", "rebait_interest"],
                as_dict=1,
            )
            if self.is_default == 1:
                self.custom_base_interest = interest_configuration["base_interest"]
                self.custom_rebate_interest = interest_configuration["rebait_interest"]

            if (
                self.custom_base_interest != self.base_interest
                or self.custom_rebate_interest != self.custom_rebate_interest
            ):
                self.custom_base_interest = self.base_interest
                self.custom_rebate_interest = self.custom_rebate_interest
                # add notification

    def save_loan_sanction_history(self, agreement_file, event="New loan"):
        loan_sanction_history = frappe.get_doc(
            {
                "doctype": "Loan Sanction History",
                "loan": self.name,
                "sanctioned_limit": self.sanctioned_limit,
                "agreement_file": agreement_file,
                "time": frappe.utils.now_datetime(),
                "event": event,
            }
        )
        loan_sanction_history.save(ignore_permissions=True)

    def max_topup_amount(self):
        lender = self.get_lender()
        # allowed_security = frappe.db.sql(
        #         'select distinct isin from `tabAllowed Security` where allowed = 1',as_dict=True)
        actual_drawing_power = 0
        total_collateral_value = 0
        if self.instrument_type == "Mutual Fund":
            allowed_security = frappe.db.sql_list(
                """select distinct als.isin from `tabAllowed Security` als JOIN `tabLoan Item` l ON als.isin = l.isin where als.allowed = 1 and als.lender = '{}'  """.format(
                    lender.name
                )
            )
            for i in self.items:
                if i.isin in allowed_security:
                    i.amount = i.price * i.pledged_quantity
                    i.eligible_amount = (i.eligible_percentage / 100) * i.amount
                    total_collateral_value += i.amount
                    actual_drawing_power += i.eligible_amount
            max_topup_amount = actual_drawing_power - self.sanctioned_limit
        else:
            max_topup_amount = (
                self.total_collateral_value * (self.allowable_ltv / 100)
            ) - self.sanctioned_limit

        # show available top up amount only if topup amount is greater than 10% of sanctioned limit
        # if self.instrument_type == "Mutual Fund":  # for Mutual Fund Topup
        if self.sanctioned_limit > lender.maximum_sanctioned_limit:
            max_topup_amount = 0
        elif (
            (actual_drawing_power / self.sanctioned_limit * 100) - 100 >= 10
            and max_topup_amount >= 1000
            and self.instrument_type == "Mutual Fund"
        ) or (
            max_topup_amount > (self.sanctioned_limit * 0.1)
            and max_topup_amount >= 1000
            and self.instrument_type == "Shares"
        ):
            if (
                max_topup_amount + self.sanctioned_limit
            ) > lender.maximum_sanctioned_limit:
                max_topup_amount = (
                    lender.maximum_sanctioned_limit - self.sanctioned_limit
                )
        else:
            max_topup_amount = 0
        # else:  # for Share Topup
        #     if self.sanctioned_limit > lender.maximum_sanctioned_limit:
        #         max_topup_amount = 0
        #     elif (
        #         max_topup_amount > (self.sanctioned_limit * 0.1)
        #         and max_topup_amount >= 1000
        #     ):
        #         if (
        #             max_topup_amount + self.sanctioned_limit
        #         ) > lender.maximum_sanctioned_limit:
        #             max_topup_amount = (
        #                 lender.maximum_sanctioned_limit - self.sanctioned_limit
        # #             )
        #     else:
        #         max_topup_amount = 0

        return round(lms.round_down_amount_to_nearest_thousand(max_topup_amount), 2)

    def update_pending_topup_amount(self):
        pending_topup_request = frappe.get_all(
            "Top up Application",
            filters={
                "loan": self.name,
                "status": ["IN", ["Pending", "Esign Done"]],
            },
            fields=["*"],
            order_by="creation asc",
        )
        for topup_app in pending_topup_request:
            max_topup_amount = (
                self.total_collateral_value * (self.allowable_ltv / 100)
            ) - self.sanctioned_limit
            topup_doc = frappe.get_doc("Top up Application", topup_app["name"])
            if max_topup_amount > (self.sanctioned_limit * 0.1):
                if max_topup_amount > 1000:
                    max_topup_amount = lms.round_down_amount_to_nearest_thousand(
                        max_topup_amount
                    )
                else:
                    max_topup_amount = round(max_topup_amount, 1)

                topup_doc.db_set(
                    "top_up_amount",
                    max_topup_amount,
                )
            else:
                topup_doc.db_set("top_up_amount", 0)
            frappe.db.commit()

    def max_unpledge_amount(self):
        if self.instrument_type == "Shares":
            minimum_collateral_value = (100 / self.allowable_ltv) * self.balance
            maximum_unpledge_amount = (
                self.total_collateral_value - minimum_collateral_value
            )

            return {
                "minimum_collateral_value": round(minimum_collateral_value, 2)
                if minimum_collateral_value > 0
                else 0.0,
                "maximum_unpledge_amount": round(maximum_unpledge_amount, 2)
                if maximum_unpledge_amount > 0
                else 0.0,
            }
        else:
            return {}

    def update_pending_sell_collateral_amount(self):
        all_pending_sell_collateral_applications = frappe.get_all(
            "Sell Collateral Application",
            filters={
                "loan": self.name,
                "status": "Pending",
                "creation": ("<=", frappe.utils.now_datetime()),
            },
            fields=["*"],
            order_by="creation asc",
        )
        for sell_collateral_req in all_pending_sell_collateral_applications:
            sell_collateral = frappe.get_doc(
                "Sell Collateral Application", sell_collateral_req["name"]
            )
            sell_collateral.process_items()
            sell_collateral.process_sell_items()
            sell_collateral.save(ignore_permissions=True)

    def get_unpledge_application(self):
        unpledge_application_name = frappe.db.get_value(
            "Unpledge Application", {"loan": self.name, "status": "Pending"}, "name"
        )

        return (
            frappe.get_doc("Unpledge Application", unpledge_application_name)
            if unpledge_application_name
            else None
        )

    # def validate(self):
    #     #remove row from items if pledge quantity is 0
    #     for i in self.items:
    #         if i.pledged_quantity <= 0:
    #             self.items.remove(i)

    def create_tnc_file(self, topup_amount):
        lender = self.get_lender()
        customer = self.get_customer()
        user_kyc = customer.get_kyc()
        # loan = self.get_loan()

        if user_kyc.address_details:
            address_details = frappe.get_doc(
                "Customer Address Details", user_kyc.address_details
            )
            address = (
                (
                    (str(address_details.perm_line1) + ", ")
                    if address_details.perm_line1
                    else ""
                )
                + (
                    (str(address_details.perm_line2) + ", ")
                    if address_details.perm_line2
                    else ""
                )
                + (
                    (str(address_details.perm_line3) + ", ")
                    if address_details.perm_line3
                    else ""
                )
                + str(address_details.perm_city)
                + ", "
                + str(address_details.perm_dist)
                + ", "
                + str(address_details.perm_state)
                + ", "
                + str(address_details.perm_country)
                + ", "
                + str(address_details.perm_pin)
            )
        else:
            address = ""

        doc = {
            "esign_date": "__________",
            "loan_application_number": self.name,
            "borrower_name": user_kyc.fullname,
            "borrower_address": address,
            # "sanctioned_amount": topup_amount,
            # "sanctioned_amount_in_words": num2words(
            #     topup_amount, lang="en_IN"
            # ).title(),
            "sanctioned_amount": lms.validate_rupees(
                (topup_amount + self.sanctioned_limit)
            ),
            "sanctioned_amount_in_words": lms.number_to_word(
                lms.validate_rupees((topup_amount + self.sanctioned_limit))
            ).title(),
            "old_sanctioned_amount": lms.validate_rupees(self.sanctioned_limit),
            "old_sanctioned_amount_in_words": lms.number_to_word(
                lms.validate_rupees(self.sanctioned_limit)
            ).title(),
            "rate_of_interest": lender.rate_of_interest,
            "default_interest": lender.default_interest,
            "rebait_threshold": lender.rebait_threshold,
            "renewal_charges": lms.validate_rupees(lender.renewal_charges)
            if lender.renewal_charge_type == "Fix"
            else lms.validate_percent(lender.renewal_charges),
            "renewal_charge_type": lender.renewal_charge_type,
            "renewal_charge_in_words": lms.number_to_word(
                lms.validate_rupees(lender.renewal_charges)
            ).title()
            if lender.renewal_charge_type == "Fix"
            else "",
            "renewal_min_amt": lms.validate_rupees(lender.renewal_minimum_amount),
            "renewal_max_amt": lms.validate_rupees(lender.renewal_maximum_amount),
            "documentation_charge": lms.validate_rupees(lender.documentation_charges)
            if lender.documentation_charge_type == "Fix"
            else lms.validate_percent(lender.documentation_charges),
            "documentation_charge_type": lender.documentation_charge_type,
            "documentation_charge_in_words": lms.number_to_word(
                lms.validate_rupees(lender.documentation_charges)
            ).title()
            if lender.documentation_charge_type == "Fix"
            else "",
            "documentation_min_amt": lms.validate_rupees(
                lender.lender_documentation_minimum_amount
            ),
            "documentation_max_amt": lms.validate_rupees(
                lender.lender_documentation_maximum_amount
            ),
            "lender_processing_fees_type": lender.lender_processing_fees_type,
            "processing_charge": lms.validate_rupees(lender.lender_processing_fees)
            if lender.lender_processing_fees_type == "Fix"
            else lms.validate_percent(lender.lender_processing_fees),
            "processing_charge_in_words": lms.number_to_word(
                lms.validate_rupees(lender.lender_processing_fees)
            ).title()
            if lender.lender_processing_fees_type == "Fix"
            else "",
            "processing_min_amt": lms.validate_rupees(
                lender.lender_processing_minimum_amount
            ),
            "processing_max_amt": lms.validate_rupees(
                lender.lender_processing_maximum_amount
            ),
            # "documentation_charges": lender.documentation_charges,
            # "stamp_duty_charges": (lender.stamp_duty / 100)
            # * self.sanctioned_limit,  # CR loan agreement changes
            # "stamp_duty_charges": int(lender.lender_stamp_duty_minimum_amount),
            "transaction_charges_per_request": lms.validate_rupees(
                lender.transaction_charges_per_request
            ),
            "security_selling_share": lender.security_selling_share,
            "cic_charges": lms.validate_rupees(lender.cic_charges),
            "total_pages": lender.total_pages,
            "lien_initiate_charge_type": lender.lien_initiate_charge_type,
            "invoke_initiate_charge_type": lender.invoke_initiate_charge_type,
            "revoke_initiate_charge_type": lender.revoke_initiate_charge_type,
            "lien_initiate_charge_minimum_amount": lms.validate_rupees(
                lender.lien_initiate_charge_minimum_amount
            ),
            "lien_initiate_charge_maximum_amount": lms.validate_rupees(
                lender.lien_initiate_charge_maximum_amount
            ),
            "lien_initiate_charges": lms.validate_rupees(lender.lien_initiate_charges)
            if lender.lien_initiate_charge_type == "Fix"
            else lms.validate_percent(lender.lien_initiate_charges),
            "invoke_initiate_charges_minimum_amount": lms.validate_rupees(
                lender.invoke_initiate_charges_minimum_amount
            ),
            "invoke_initiate_charges_maximum_amount": lms.validate_rupees(
                lender.invoke_initiate_charges_maximum_amount
            ),
            "invoke_initiate_charges": lms.validate_rupees(
                lender.invoke_initiate_charges
            )
            if lender.invoke_initiate_charge_type == "Fix"
            else lms.validate_percent(lender.invoke_initiate_charges),
            "revoke_initiate_charges_minimum_amount": lms.validate_rupees(
                lender.revoke_initiate_charges_minimum_amount
            ),
            "revoke_initiate_charges_maximum_amount": lms.validate_rupees(
                lender.revoke_initiate_charges_maximum_amount
            ),
            "revoke_initiate_charges": lms.validate_rupees(
                lender.revoke_initiate_charges
            )
            if lender.revoke_initiate_charge_type == "Fix"
            else lms.validate_percent(lender.revoke_initiate_charges),
        }

        agreement_template = lender.get_loan_enhancement_agreement_template()

        agreement = frappe.render_template(
            agreement_template.get_content(), {"doc": doc}
        )

        from frappe.utils.pdf import get_pdf

        agreement_pdf = get_pdf(agreement)

        tnc_dir_path = frappe.utils.get_files_path("tnc")
        import os

        if not os.path.exists(tnc_dir_path):
            os.mkdir(tnc_dir_path)
        tnc_file = "tnc/{}.pdf".format(self.name)
        tnc_file_path = frappe.utils.get_files_path(tnc_file)

        with open(tnc_file_path, "wb") as f:
            f.write(agreement_pdf)
        f.close()

    def calculate_day_past_due(self, input_date):
        day_past_due = frappe.db.sql(
            "select sum(unpaid_interest) as total_amount, DATEDIFF('{}', time) as dpd from `tabLoan Transaction` where loan = '{}' and transaction_type = 'Interest' and unpaid_interest >0 order by creation asc".format(
                input_date, self.name
            ),
            as_dict=True,
        )
        if day_past_due[0]["total_amount"]:
            return day_past_due[0]["dpd"]
        else:
            return 0

    def map_loan_summary_values(self):
        self.base_interest_amount = frappe.db.sql(
            "select sum(base_amount) as amount from `tabVirtual Interest` where loan = '{}' and is_booked_for_base = 0".format(
                self.name
            ),
            as_dict=1,
        )[0]["amount"]
        self.rebate_interest_amount = frappe.db.sql(
            "select sum(rebate_amount) as amount from `tabVirtual Interest` where loan = '{}' and is_booked_for_rebate = 0".format(
                self.name
            ),
            as_dict=1,
        )[0]["amount"]


@frappe.whitelist()
def check_for_topup_increase_loan(loan_name):
    loan = frappe.get_doc("Loan", loan_name)
    app = ""
    top_up = frappe.get_value(
        "Top up Application",
        {"loan": loan.name, "status": ["in", ["Pending", "Esign Done"]]},
        "name",
    )
    increase_loan = frappe.get_value(
        "Loan Application",
        {
            "loan": loan.name,
            "status": ["in", ["Pending", "Esign Done"]],
            "application_type": "Increase Loan",
        },
        "name",
    )

    if top_up:
        app = top_up
    elif increase_loan:
        app = increase_loan

    return app


def check_loans_for_shortfall(loans):
    for loan_name in loans:
        frappe.enqueue_doc("Loan", loan_name, method="check_for_shortfall")


@frappe.whitelist()
def check_all_loans_for_shortfall():
    chunks = lms.chunk_doctype(doctype="Loan", limit=50)

    for start in chunks.get("chunks"):
        loan_list = frappe.db.get_all(
            "Loan",
            limit_page_length=chunks.get("limit"),
            limit_start=start,
        )

        frappe.enqueue(
            method="lms.lms.doctype.loan.loan.check_loans_for_shortfall",
            loans=[i.name for i in loan_list],
            queue="long",
        )


# @frappe.whitelist()
# def check_single_loan_for_shortfall(loan_name):
#     loan = frappe.get_doc("Loan", loan_name)
#     loan.check_for_shortfall()


@frappe.whitelist()
def daily_virtual_job(loan_name, input_date=None):
    frappe.enqueue_doc(
        "Loan",
        loan_name,
        method="add_virtual_interest",
        input_date=input_date,
    )


# @frappe.whitelist()
# def daily_cron_job(loan_name, input_date=None):
#     frappe.enqueue_doc(
#         "Loan",
#         loan_name,
#         method="calculate_virtual_and_additional_interest",
#         input_date=input_date,
#     )


@frappe.whitelist()
def daily_penal_job(loan_name, input_date=None):
    frappe.enqueue_doc(
        "Loan",
        loan_name,
        method="add_penal_interest",
        input_date=input_date,
    )


@frappe.whitelist()
def additional_interest_job(loan_name, input_date=None):
    frappe.enqueue_doc(
        "Loan",
        loan_name,
        method="check_for_additional_interest",
        input_date=input_date,
    )


def add_loans_virtual_interest(loans):
    for loan in loans:
        loan = frappe.get_doc("Loan", loan)
        loan.add_virtual_interest()


@frappe.whitelist()
def add_all_loans_virtual_interest():
    chunks = lms.chunk_doctype(doctype="Loan", limit=10)

    for start in chunks.get("chunks"):
        all_loans = frappe.db.get_all(
            "Loan", limit_page_length=chunks.get("limit"), limit_start=start
        )

        frappe.enqueue(
            method="lms.lms.doctype.loan.loan.add_loans_virtual_interest",
            loans=[loan for loan in all_loans],
            queue="long",
        )


def check_for_loans_additional_interest(loans):
    for loan in loans:
        loan = frappe.get_doc("Loan", loan)
        loan.check_for_additional_interest()


@frappe.whitelist()
def check_for_all_loans_additional_interest():
    chunks = lms.chunk_doctype(doctype="Loan", limit=10)

    for start in chunks.get("chunks"):
        all_loans = frappe.db.get_all(
            "Loan", limit_page_length=chunks.get("limit"), limit_start=start
        )

        frappe.enqueue(
            method="lms.lms.doctype.loan.loan.check_for_loans_additional_interest",
            loans=[loan for loan in all_loans],
            queue="long",
        )


def add_loans_penal_interest(loans):
    for loan in loans:
        loan = frappe.get_doc("Loan", loan)
        loan.add_penal_interest()


@frappe.whitelist()
def add_all_loans_penal_interest():
    chunks = lms.chunk_doctype(doctype="Loan", limit=10)

    for start in chunks.get("chunks"):
        all_loans = frappe.db.get_all(
            "Loan", limit_page_length=chunks.get("limit"), limit_start=start
        )

        frappe.enqueue(
            method="lms.lms.doctype.loan.loan.add_loans_penal_interest",
            loans=[loan for loan in all_loans],
            queue="long",
        )


@frappe.whitelist()
def book_virtual_interest_for_month(loan_name, input_date=None):
    frappe.enqueue_doc(
        "Loan",
        loan_name,
        method="book_virtual_interest_for_month",
        input_date=input_date,
    )


def book_loans_virtual_interest_for_month(loans):
    for loan in loans:
        loan = frappe.get_doc("Loan", loan)
        loan.book_virtual_interest_for_month()


@frappe.whitelist()
def book_all_loans_virtual_interest_for_month():
    chunks = lms.chunk_doctype(doctype="Loan", limit=10)

    for start in chunks.get("chunks"):
        all_loans = frappe.db.get_all(
            "Loan", limit_page_length=chunks.get("limit"), limit_start=start
        )

        frappe.enqueue(
            method="lms.lms.doctype.loan.loan.book_loans_virtual_interest_for_month",
            loans=[loan for loan in all_loans],
            queue="long",
        )


# def job_dates_for_penal(loan_name):
#     current_date_ = frappe.utils.now_datetime()
#     current_date_ = current_date_.replace(day=1)
#     loan = frappe.get_doc("Loan", loan_name)
#     last_date = (current_date_.replace(day=1) + timedelta(days=32)).replace(
#         day=1
#     ) - timedelta(days=1)
#     while current_date_ <= last_date:
#         loan.add_penal_interest(current_date_.strftime("%Y-%m-%d"))
#         current_date_ += timedelta(days=1)


@frappe.whitelist()
def interest_booked_till_date(loan_name):
    interest_booked = frappe.db.sql(
        "select sum(amount) as total_amount from `tabLoan Transaction` where loan = '{}' and transaction_type in ('Interest', 'Additional Interest', 'Penal Interest')".format(
            loan_name
        ),
        as_dict=1,
    )[0]["total_amount"]
    return 0.0 if interest_booked == None else interest_booked
