# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

from datetime import datetime, timedelta

import frappe
from frappe.model.document import Document

import lms
from lms.lms.doctype.loan_transaction.loan_transaction import LoanTransaction


class Loan(Document):
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

        return max_withdraw_amount

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
                "time": datetime.now(),
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
        return frappe.get_doc("Customer", self.customer)

    def update_loan_balance(self):
        summary = self.get_transaction_summary()
        frappe.db.set_value(
            self.doctype,
            self.name,
            "balance",
            round(summary.get("outstanding"), 2),
            update_modified=False,
        )
        frappe.db.set_value(
            self.doctype,
            self.name,
            "balance_str",
            lms.amount_formatter(round(summary.get("outstanding"), 2)),
            update_modified=False,
        )

    def on_update(self):
        frappe.enqueue_doc("Loan", self.name, method="check_for_shortfall")

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

    def check_for_shortfall(self):
        check = False

        securities_price_map = lms.get_security_prices([i.isin for i in self.items])

        for i in self.items:
            if i.price != securities_price_map.get(i.isin):
                check = True
                i.price = securities_price_map.get(i.isin)

        if check:
            self.fill_items()
            self.save(ignore_permissions=True)

            loan_margin_shortfall = self.get_margin_shortfall()

            loan_margin_shortfall.fill_items()

            if loan_margin_shortfall.is_new():
                # if loan_margin_shortfall.margin_shortfall_action:
                if loan_margin_shortfall.shortfall_percentage > 0:
                    loan_margin_shortfall.insert(ignore_permissions=True)
            else:
                # if not loan_margin_shortfall.margin_shortfall_action:
                if loan_margin_shortfall.shortfall_percentage == 0:
                    loan_margin_shortfall.status = "Resolved"
                    loan_margin_shortfall.action_time = datetime.now()
                loan_margin_shortfall.save(ignore_permissions=True)

            # update pending withdraw allowable for this loan
            self.update_pending_withdraw_requests()
            frappe.db.commit()

    def update_pending_withdraw_requests(self):
        all_pending_withdraw_requests = frappe.get_all(
            "Loan Transaction",
            filters={
                "loan": self.name,
                "transaction_type": "Withdrawal",
                "status": "Pending",
                "creation": ("<=", datetime.now()),
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
            input_date = datetime.now() - timedelta(days=1)

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
            current_date = datetime.now()

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
                    self.is_irregular = 1
                    self.save(ignore_permissions=True)

                    frappe.db.commit()
                    # TODO: send notification to user
                    return additional_interest_transaction.as_dict()

    def book_virtual_interest_for_month(self, input_date=None):
        if input_date:
            current_date = datetime.strptime(input_date, "%Y-%m-%d")
        else:
            current_date = datetime.now()

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
            # TODO: send notification to user

    def add_penal_interest(self, input_date=None):
        # daily scheduler - executes at start of day i.e 00:00
        # get not paid booked interest
        if input_date:
            current_date = datetime.strptime(input_date, "%Y-%m-%d")
        else:
            current_date = datetime.now()

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
                        self.is_penalize = 1
                        self.save(ignore_permissions=True)

                        frappe.db.commit()
                        # TODO: send notification to user
                        return penal_interest_transaction.as_dict()

    def before_save(self):
        self.total_collateral_value_str = lms.amount_formatter(
            self.total_collateral_value
        )
        self.drawing_power_str = lms.amount_formatter(self.drawing_power)
        self.sanctioned_limit_str = lms.amount_formatter(self.sanctioned_limit)
        self.balance_str = lms.amount_formatter(self.balance)


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
