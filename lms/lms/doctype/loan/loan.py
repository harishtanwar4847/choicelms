# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

from datetime import datetime, timedelta

import frappe
from frappe.model.document import Document

import lms
from lms.firebase import FirebaseAdmin
from lms.lms.doctype.loan_transaction.loan_transaction import LoanTransaction


class Loan(Document):
    def after_insert(self):
        self.create_loan_charges()

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
                "select sum(amount) as amount from `tabLoan Transaction` where loan = '{}' and lender = '{}' and status = 'Pending' and transaction_type = 'Withdrawal' and creation < '{}' and name != '{}'".format(
                    self.name, self.lender, req_time, withdraw_req_name
                ),
                as_dict=1,
            )
            if pending_withdraw_requests_amt[0]["amount"]:
                balance += pending_withdraw_requests_amt[0]["amount"]
        else:
            pending_withdraw_requests_amt = frappe.db.sql(
                "select sum(amount) as amount from `tabLoan Transaction` where loan = '{}' and lender = '{}' and status = 'Pending' and transaction_type = 'Withdrawal'".format(
                    self.name, self.lender
                ),
                as_dict=1,
            )
            if pending_withdraw_requests_amt[0]["amount"]:
                balance += pending_withdraw_requests_amt[0]["amount"]

        max_withdraw_amount = self.drawing_power - balance
        if max_withdraw_amount < 0:
            max_withdraw_amount = 0

        return round(max_withdraw_amount, 2)

    def get_lender(self):
        return frappe.get_doc("Lender", self.lender)

    def create_loan_charges(self):
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

    def create_loan_transaction(
        self,
        transaction_type,
        amount,
        approve=False,
        transaction_id=None,
        loan_margin_shortfall_name=None,
        is_for_interest=None,
    ):
        loan_transaction = frappe.get_doc(
            {
                "doctype": "Loan Transaction",
                "loan": self.name,
                "lender": self.lender,
                "amount": round(amount, 2),
                "transaction_type": transaction_type,
                "record_type": LoanTransaction.loan_transaction_map.get(
                    transaction_type, "DR"
                ),
                # "time": frappe.utils.now_datetime(),
                "time": frappe.utils.now_datetime(),
            }
        )

        if transaction_id:
            loan_transaction.transaction_id = transaction_id
        if loan_margin_shortfall_name:
            loan_transaction.loan_margin_shortfall = loan_margin_shortfall_name
        if is_for_interest:
            loan_transaction.is_for_interest = is_for_interest

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
            self.check_for_shortfall()

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
        for i in self.items:
            i.amount = i.price * i.pledged_quantity
            self.total_collateral_value += i.amount

        drawing_power = round(
            (self.total_collateral_value * (self.allowable_ltv / 100)), 2
        )
        self.drawing_power = (
            drawing_power
            if drawing_power <= self.sanctioned_limit
            else self.sanctioned_limit
        )

    def get_collateral_list(self, group_by_psn=False, where_clause=""):
        # sauce: https://stackoverflow.com/a/23827026/9403680
        sql = """
			SELECT
				cl.loan, cl.isin, cl.psn,
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
			GROUP BY cl.isin{group_by_psn_clause};
		""".format(
            loan=self.name,
            where_clause=where_clause if where_clause else "",
            group_by_psn_clause=" ,cl.psn" if group_by_psn else "",
        )

        return frappe.db.sql(sql, as_dict=1)

    def update_items(self):
        check = False

        collateral_list = self.get_collateral_list()
        collateral_list_map = {i.isin: i for i in collateral_list}
        # updating existing and
        # setting check flag
        for i in self.items:
            curr = collateral_list_map.get(i.isin)
            # print(check, i.price, curr.price, not check or i.price != curr.price)
            if not check or i.price != curr.price:
                check = True

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

    def check_for_shortfall(self):
        check = False
        customer = self.get_customer()
        old_total_collateral_value = self.total_collateral_value

        securities_price_map = lms.get_security_prices([i.isin for i in self.items])
        check = self.update_items()

        if check:
            self.fill_items()
            self.save(ignore_permissions=True)

            loan_margin_shortfall = self.get_margin_shortfall()
            old_shortfall_action = loan_margin_shortfall.margin_shortfall_action
            loan_margin_shortfall.fill_items()
            if old_shortfall_action:
                loan_margin_shortfall.set_deadline(old_shortfall_action)

            if loan_margin_shortfall.is_new():
                # if loan_margin_shortfall.margin_shortfall_action:
                if loan_margin_shortfall.shortfall_percentage > 0:
                    loan_margin_shortfall.insert(ignore_permissions=True)
                    if frappe.utils.now_datetime() > loan_margin_shortfall.deadline:
                        loan_margin_shortfall.status = "Sell Triggered"
                        loan_margin_shortfall.save(ignore_permissions=True)
            else:
                # if not loan_margin_shortfall.margin_shortfall_action:
                if loan_margin_shortfall.status == "Pending":
                    loan_margin_shortfall.timer_start_stop_fcm()
                if loan_margin_shortfall.shortfall_percentage == 0:
                    loan_margin_shortfall.status = "Resolved"
                    loan_margin_shortfall.action_time = frappe.utils.now_datetime()
                if (
                    loan_margin_shortfall.shortfall_percentage > 0
                    and frappe.utils.now_datetime() > loan_margin_shortfall.deadline
                ):
                    loan_margin_shortfall.status = "Sell Triggered"
                loan_margin_shortfall.save(ignore_permissions=True)

            # alerts comparison with percentage and amount
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
        margin_shortfall_name = frappe.db.get_value(
            "Loan Margin Shortfall", {"loan": self.name, "status": "Pending"}, "name"
        )
        if not margin_shortfall_name:
            margin_shortfall = frappe.new_doc("Loan Margin Shortfall")
            margin_shortfall.loan = self.name
            return margin_shortfall

        return frappe.get_doc("Loan Margin Shortfall", margin_shortfall_name)

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
        virtual_interest_doc = self.add_virtual_interest(input_date)

        # Now, check if additional interest applicable
        add_intrst = self.check_for_additional_interest(input_date)

        # check if penal interest applicable
        penal_intrst = self.add_penal_interest(input_date)

    def add_virtual_interest(self, input_date=None):
        interest_cofiguration = frappe.db.get_value(
            "Interest Configuration",
            {
                "lender": self.lender,
                "from_amount": ["<=", self.balance],
                "to_amount": [">=", self.balance],
            },
            ["name", "base_interest", "rebait_interest"],
            as_dict=1,
        )

        if input_date:
            input_date = datetime.strptime(input_date, "%Y-%m-%d") - timedelta(days=1)
        else:
            input_date = frappe.utils.now_datetime() - timedelta(days=1)

        # get no of days in month
        num_of_days_in_month = (
            (input_date.replace(day=1) + timedelta(days=32)).replace(day=1)
            - timedelta(days=1)
        ).day

        # calculate daily base interest
        base_interest_daily = (
            interest_cofiguration["base_interest"] / num_of_days_in_month
        )
        base_amount = self.balance * base_interest_daily / 100

        # calculate daily rebate interest
        rebate_interest_daily = (
            interest_cofiguration["rebait_interest"] / num_of_days_in_month
        )
        rebate_amount = self.balance * rebate_interest_daily / 100

        frappe.db.begin()
        virtual_interest_doc = frappe.get_doc(
            {
                "doctype": "Virtual Interest",
                "lender": self.lender,
                "loan": self.name,
                "time": input_date.replace(
                    hour=23, minute=59, second=59, microsecond=999999
                ),
                "base_interest": interest_cofiguration["base_interest"],
                "rebate_interest": interest_cofiguration["rebait_interest"],
                "base_amount": round(base_amount, 2),
                "rebate_amount": round(rebate_amount, 2),
                "loan_balance": self.balance,
                "interest_configuration": interest_cofiguration["name"],
            }
        )
        virtual_interest_doc.save(ignore_permissions=True)
        frappe.db.commit()
        return virtual_interest_doc.as_dict()

    def check_for_additional_interest(self, input_date=None):
        # daily scheduler - executes at start of day i.e 00:00
        if input_date:
            current_date = datetime.strptime(input_date, "%Y-%m-%d")
        else:
            current_date = frappe.utils.now_datetime()

        job_date = (current_date - timedelta(days=1)).replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
        last_day_of_prev_month = job_date.replace(day=1) - timedelta(days=1)
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

                if job_date > transaction_time:
                    # Sum of rebate amounts
                    rebate_interest_sum = frappe.db.sql(
                        "select sum(rebate_amount) as amount from `tabVirtual Interest` where loan = '{}' and lender = '{}' and DATE_FORMAT(time, '%Y') = {} and DATE_FORMAT(time, '%m') = {}".format(
                            self.name, self.lender, prev_month_year, prev_month
                        ),
                        as_dict=1,
                    )

                    frappe.db.begin()
                    # Additional Interest Entry
                    additional_interest_transaction = frappe.get_doc(
                        {
                            "doctype": "Loan Transaction",
                            "loan": self.name,
                            "lender": self.lender,
                            "transaction_type": "Additional Interest",
                            "record_type": "DR",
                            "amount": rebate_interest_sum[0]["amount"],
                            "unpaid_interest": rebate_interest_sum[0]["amount"],
                            "time": transaction_time.replace(
                                hour=23, minute=59, second=59, microsecond=999999
                            ),
                        }
                    )
                    additional_interest_transaction.insert(ignore_permissions=True)
                    additional_interest_transaction.transaction_id = (
                        additional_interest_transaction.name
                    )
                    additional_interest_transaction.status = "Approved"
                    additional_interest_transaction.workflow_state = "Approved"
                    additional_interest_transaction.docstatus = 1
                    additional_interest_transaction.save(ignore_permissions=True)

                    # Update booked interest entry
                    booked_interest_transaction_doc = frappe.get_doc(
                        "Loan Transaction", booked_interest[0]["name"]
                    )
                    booked_interest_transaction_doc.db_set(
                        "additional_interest", additional_interest_transaction.name
                    )

                    # Mark as booked for rebate
                    frappe.db.sql(
                        "update `tabVirtual Interest` set is_booked_for_rebate = 1 where loan = '{}' and is_booked_for_rebate = 0 and DATE_FORMAT(time, '%Y') = {} and DATE_FORMAT(time, '%m') = {}".format(
                            self.name, prev_month_year, prev_month
                        )
                    )

                    # Mark loan as 'is_irregular'
                    # self.is_irregular = 1
                    # self.save(ignore_permissions=True)

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

                    return additional_interest_transaction.as_dict()

    def book_virtual_interest_for_month(self, input_date=None):
        if input_date:
            current_date = datetime.strptime(input_date, "%Y-%m-%d")
        else:
            current_date = frappe.utils.now_datetime()

        job_date = (current_date - timedelta(days=1)).replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
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

            frappe.db.begin()
            loan_transaction = frappe.get_doc(
                {
                    "doctype": "Loan Transaction",
                    "loan": self.name,
                    "lender": self.lender,
                    "amount": virtual_interest_sum[0]["amount"],
                    "unpaid_interest": virtual_interest_sum[0]["amount"],
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
            frappe.db.commit()

            doc = frappe.get_doc("User KYC", self.get_customer().choice_kyc).as_dict()
            doc["loan_name"] = self.name
            doc["transaction_type"] = loan_transaction.transaction_type

            frappe.enqueue_doc("Notification", "Interest Due", method="send", doc=doc)

    def add_penal_interest(self, input_date=None):
        # daily scheduler - executes at start of day i.e 00:00
        # get not paid booked interest
        if input_date:
            current_date = datetime.strptime(input_date, "%Y-%m-%d")
        else:
            current_date = frappe.utils.now_datetime()

        job_date = (current_date - timedelta(days=1)).replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
        last_day_of_prev_month = job_date.replace(day=1) - timedelta(days=1)
        num_of_days_in_prev_month = last_day_of_prev_month.day
        prev_month = last_day_of_prev_month.month
        prev_month_year = last_day_of_prev_month.year

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
                if job_date > transaction_time:
                    # if yes, apply penalty interest
                    # calculate daily penalty interest
                    default_interest = int(self.get_default_interest())
                    if default_interest:
                        default_interest_daily = (
                            default_interest / num_of_days_in_prev_month
                        )
                        amount = self.balance * default_interest_daily / 100

                        frappe.db.begin()
                        # Penal Interest Entry
                        penal_interest_transaction = frappe.get_doc(
                            {
                                "doctype": "Loan Transaction",
                                "loan": self.name,
                                "lender": self.lender,
                                "transaction_type": "Penal Interest",
                                "record_type": "DR",
                                "amount": amount,
                                "unpaid_interest": amount,
                                "time": job_date,
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

                        # Mark loan as 'is_penalize'
                        # self.is_penalize = 1
                        # self.save(ignore_permissions=True)

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

                        return penal_interest_transaction.as_dict()

    def before_save(self):
        self.total_collateral_value_str = lms.amount_formatter(
            self.total_collateral_value
        )
        self.drawing_power_str = lms.amount_formatter(self.drawing_power)
        self.sanctioned_limit_str = lms.amount_formatter(self.sanctioned_limit)
        self.balance_str = lms.amount_formatter(self.balance)

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
        max_topup_amount = (
            self.total_collateral_value * (self.allowable_ltv / 100)
        ) - self.sanctioned_limit

        # show available top up amount only if topup amount is greater than 10% of sanctioned limit
        if max_topup_amount > (self.sanctioned_limit * 0.1):
            if max_topup_amount > 1000:
                max_topup_amount = lms.round_down_amount_to_nearest_thousand(
                    max_topup_amount
                )
            # else:
            #     max_topup_amount = round(max_topup_amount, 1)
        else:
            max_topup_amount = 0

        return round(max_topup_amount, 2)

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
        minimum_collateral_value = (100 / self.allowable_ltv) * self.balance
        maximum_unpledge_amount = self.total_collateral_value - minimum_collateral_value

        return {
            "minimum_collateral_value": minimum_collateral_value
            if minimum_collateral_value > 0
            else 0.0,
            "maximum_unpledge_amount": round(maximum_unpledge_amount, 2)
            if maximum_unpledge_amount > 0
            else 0.0,
        }

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

        return frappe.get_doc("Unpledge Application", unpledge_application_name) if unpledge_application_name else None

    # def validate(self):
    #     #remove row from items if pledge quantity is 0
    #     for i in self.items:
    #         if i.pledged_quantity == 0:
    #             self.items.remove(i)


def check_loans_for_shortfall(loans):
    for loan_name in loans:
        frappe.enqueue_doc("Loan", loan_name, method="check_for_shortfall")


@frappe.whitelist()
def check_all_loans_for_shortfall():
    chunks = lms.chunk_doctype(doctype="Loan", limit=50)

    for start in chunks.get("chunks"):
        loan_list = frappe.db.get_all(
            "Loan", limit_page_length=chunks.get("limit"), limit_start=start
        )

        frappe.enqueue(
            method="lms.lms.doctype.loan.loan.check_loans_for_shortfall",
            loans=[i.name for i in loan_list],
            queue="long",
        )


# @frappe.whitelist()
# def check_single_loan_for_shortfall(loan_name):
#     loan = frappe.get_doc("Loan",loan_name)
#     loan.check_for_shortfall()


@frappe.whitelist()
def daily_cron_job(loan_name, input_date=None):
    frappe.enqueue_doc(
        "Loan",
        loan_name,
        method="calculate_virtual_and_additional_interest",
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
