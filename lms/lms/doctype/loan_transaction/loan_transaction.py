# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from frappe.model.document import Document

import lms
from lms.firebase import FirebaseAdmin


class LoanTransaction(Document):
    loan_transaction_map = {
        "Withdrawal": "DR",
        "Payment": "CR",
        "Debit Note": "DR",
        "Credit Note": "CR",
        "Processing Fees": "DR",
        "Stamp Duty": "DR",
        "Documentation Charges": "DR",
        "Mortgage Charges": "DR",
        # "Sell Collateral": "DR",  # confirm
        "Sell Collateral": "CR",  # confirm
        "Invoke Pledge": "DR",  # confirm
        "Interest": "DR",
        "Additional Interest": "DR",
        "Penal Interest": "DR",
        "Other Charges": "DR",
        "Legal Charges": "DR",
        "DP Reimbursement(Unpledge)": "DR",
        "DP Reimbursement(Sell)": "DR",
        "Sell Collateral Charges": "DR",
        "Renewal Charges": "DR",
    }

    def autoname(self):
        latest_transaction = frappe.db.sql(
            "select name from `tabLoan Transaction` where loan='{loan}' and name like '{loan}-%' order by creation desc limit 1".format(
                loan=self.loan
            ),
            as_dict=True,
        )

        if len(latest_transaction) == 0:
            self.name = "{}-00001".format(self.loan)
        else:
            latest_transaction_id = latest_transaction[0].name.split("-")[1]
            self.name = "{}-".format(self.loan) + (
                "%05d" % (int(latest_transaction_id) + 1)
            )

    def validate_withdrawal_amount(self):
        if self.amount <= 0:
            frappe.throw("Please fix the amount.")
        if self.transaction_type == "Withdrawal":
            loan = self.get_loan()
            maximum_withdrawable_amount = loan.maximum_withdrawable_amount()
            if self.amount > maximum_withdrawable_amount:
                frappe.throw(
                    "Can not withdraw more than {}".format(maximum_withdrawable_amount)
                )

    def set_record_type(self):
        self.record_type = self.loan_transaction_map.get(self.transaction_type, "DR")

    def get_loan(self):
        return frappe.get_doc("Loan", self.loan)

    def get_lender(self):
        return frappe.get_doc("Lender", self.lender)

    def before_insert(self):
        if not self.time:
            self.time = frappe.utils.now_datetime()
        self.set_record_type()
        self.validate_withdrawal_amount()
        # set customer
        loan = self.get_loan()
        # update opening balance
        self.opening_balance = loan.balance
        self.customer = loan.customer
        self.customer_name = loan.customer_name
        # check for user roles and permissions before adding transactions
        user_roles = frappe.db.get_values(
            "Has Role", {"parent": frappe.session.user, "parenttype": "User"}, ["role"]
        )
        if not user_roles:
            frappe.throw(_("Invalid User"))
        user_roles = [role[0] for role in user_roles]

        # loan_cust_transaction_list = ["Withdrawal", "Payment", "Sell Collateral"]
        loan_cust_transaction_list = ["Withdrawal", "Payment"]
        lender_team_transaction_list = [
            "Debit Note",
            "Credit Note",
            "Processing Fees",
            "Stamp Duty",
            "Documentation Charges",
            "Mortgage Charges",
            "Invoke Pledge",
            "Interests",
            "Additional Interests",
            "Other Charges",
            "Sell Collateral",
            "Legal Charges",
            "DP Reimbursement(Unpledge)",
            "DP Reimbursement(Sell)",
            "Sell Collateral Charges",
            "Renewal Charges",
        ]

        if "System Manager" not in user_roles:
            if self.transaction_type in loan_cust_transaction_list and (
                "Loan Customer" not in user_roles
            ):
                frappe.throw(_("You are not permitted to perform this action"))
            elif self.transaction_type in lender_team_transaction_list and (
                "Lender" not in user_roles
            ):
                frappe.throw(_("You are not permitted to perform this action"))

    def on_submit(self):
        check_for_shortfall = True
        if self.transaction_type in [
            "Processing Fees",
            "Stamp Duty",
            "Documentation Charges",
            "Mortgage Charges",
        ]:
            check_for_shortfall = False
            lender = self.get_lender()
            if self.transaction_type == "Processing Fees":
                sharing_amount = lender.lender_processing_fees_sharing
                sharing_type = lender.lender_processing_fees_sharing_type
                # transaction_type = "Processing Fees"
            elif self.transaction_type == "Stamp Duty":
                sharing_amount = lender.stamp_duty_sharing
                sharing_type = lender.stamp_duty_sharing_type
                # transaction_type = "Stamp Duty"
            elif self.transaction_type == "Documentation Charges":
                sharing_amount = lender.documentation_charges_sharing
                sharing_type = lender.documentation_charge_sharing_type
                # transaction_type = "Documentation Charges"
            elif self.transaction_type == "Mortgage Charges":
                sharing_amount = lender.mortgage_charges_sharing
                sharing_type = lender.mortgage_charge_sharing_type
                # transaction_type = "Mortgage Charges"

            lender_sharing_amount = sharing_amount
            # loan_transaction_type = transaction_type
            if sharing_type == "Percentage":
                lender_sharing_amount = (lender_sharing_amount / 100) * self.amount
            spark_sharing_amount = self.amount - lender_sharing_amount

            loan = self.get_loan()
            # customer_name = loan.customer_name
            self.create_lender_ledger(
                lender_sharing_amount,
                spark_sharing_amount,
            )

        loan = self.get_loan()

        # Mark loan as 'is_irregular' and 'is_penalize
        if self.transaction_type == "Additional Interest":
            loan.is_irregular = 1
        elif self.transaction_type == "Penal Interest":
            loan.is_penalize = 1
        negative_balance = loan.balance
        loan.update_loan_balance(check_for_shortfall=check_for_shortfall)
        if self.record_type == "CR":
            negative_balance = loan.balance

        if self.transaction_type == "Payment":
            doc = frappe.get_doc("User KYC", self.get_customer().choice_kyc).as_dict()
            doc["payment"] = {
                "status": self.status,
                "loan": self.loan,
                "amount": self.amount,
                "balance": loan.balance,
                "date_time": datetime.strptime(
                    self.time, "%Y-%m-%d %H:%M:%S.%f"
                ).strftime("%d-%m-%Y %H:%M")
                if type(self.time) == str
                else (self.time).strftime("%d-%m-%Y %H:%M"),
            }
            frappe.enqueue_doc("Notification", "Payment", method="send", doc=doc)
            msg = "Dear Customer,\nYou loan account {}  has been credited by payment of Rs. {} . Your loan balance is Rs. {}. {} Spark Loans".format(
                self.loan,
                self.amount,
                loan.balance,
                datetime.strptime(self.time, "%Y-%m-%d %H:%M:%S.%f").strftime(
                    "%d-%m-%Y %H:%M"
                )
                if type(self.time) == str
                else (self.time).strftime("%d-%m-%Y %H:%M"),
            )
            fcm_notification = frappe.get_doc(
                "Spark Push Notification", "Payment credited to account", fields=["*"]
            )
            lms.send_spark_push_notification(
                fcm_notification=fcm_notification,
                message=fcm_notification.message.format(
                    loan=self.loan,
                    amount=self.amount,
                    loan_balance=loan.balance,
                    datetime=datetime.strptime(
                        self.time, "%Y-%m-%d %H:%M:%S.%f"
                    ).strftime("%d-%m-%Y %H:%M")
                    if type(self.time) == str
                    else (self.time).strftime("%d-%m-%Y %H:%M"),
                ),
                loan=self.loan,
                customer=self.get_customer(),
            )

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

        if self.transaction_type == "Withdrawal":
            mess = ""
            doc = frappe.get_doc("User KYC", self.get_customer().choice_kyc).as_dict()
            doc["withdrawal"] = {
                "status": self.status,
                "requested_amt": self.requested,
                "disbursed_amt": self.disbursed,
                "amount": self.amount,
                "balance": loan.balance,
                "date_time": datetime.strptime(
                    self.time, "%Y-%m-%d %H:%M:%S.%f"
                ).strftime("%d-%m-%Y %H:%M")
                if type(self.time) == str
                else (self.time).strftime("%d-%m-%Y %H:%M"),
            }
            frappe.enqueue_doc("Notification", "Withdrawal", method="send", doc=doc)
            if self.requested == self.disbursed:
                mess = "Dear Customer,\nYour withdrawal request has been executed and Rs. {amount}  transferred to your designated bank account. Your loan account has been debited for Rs. {disbursed} . Your loan balance is Rs. {balance}. {date_time}. If this is not you report immediately on 'Contact Us' in the app -Spark Loans".format(
                    amount=self.amount,
                    disbursed=self.disbursed,
                    balance=loan.balance,
                    date_time=datetime.strptime(
                        self.time, "%Y-%m-%d %H:%M:%S.%f"
                    ).strftime("%d-%m-%Y %H:%M")
                    if type(self.time) == str
                    else (self.time).strftime("%d-%m-%Y %H:%M"),
                )

                fcm_notification = frappe.get_doc(
                    "Spark Push Notification", "Withdrawal successful", fields=["*"]
                )
                message = fcm_notification.message.format(amount=self.amount)

            elif self.disbursed < self.requested:
                mess = "Dear Customer,\nYour withdrawal request for Rs. {requested}  has been partially executed and Rs. {disbursed}  transferred to your designated bank account. Your loan account has been debited for Rs. {disbursed} . If this is not you report immediately on 'Contact Us' in the app -Spark Loans".format(
                    requested=self.requested, disbursed=self.disbursed
                )

                fcm_notification = frappe.get_doc(
                    "Spark Push Notification",
                    "Partial withdrawal successful",
                    fields=["*"],
                )
                message = fcm_notification.message.format(
                    requested=self.requested, disbursed=self.disbursed
                )

            from frappe.core.doctype.sms_settings.sms_settings import send_sms

            if mess:
                frappe.enqueue(
                    method=send_sms, receiver_list=[self.get_customer().phone], msg=mess
                )

            if fcm_notification:
                lms.send_spark_push_notification(
                    fcm_notification=fcm_notification,
                    message=message,
                    loan=self.loan,
                    customer=self.get_customer(),
                )

        if self.loan_margin_shortfall:
            loan_margin_shortfall = frappe.get_doc(
                "Loan Margin Shortfall", self.loan_margin_shortfall
            )
            loan_margin_shortfall.fill_items()
            # if not loan_margin_shortfall.margin_shortfall_action:
            if loan_margin_shortfall.shortfall_percentage == 0:
                if self.transaction_type == "Payment":
                    loan_margin_shortfall.status = "Paid Cash"
                elif self.transaction_type == "Sell Collateral":
                    loan_margin_shortfall.status = "Sell Off"

                loan_margin_shortfall.action_time = frappe.utils.now_datetime()

            # if shortfall is not recoverd then margin shortfall status will change from request pending to pending
            under_process_la = frappe.get_all(
                "Loan Application",
                filters={
                    "loan": self.loan,
                    "status": ["not IN", ["Approved", "Rejected", "Pledge Failure"]],
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

        if self.is_for_interest or negative_balance < 0:
            self.pay_for_interest(negative_balance)

        # Update Interest Details fields in loan Doctype
        if self.transaction_type in [
            "Interest",
            "Additional Interest",
            "Penal Interest",
            "Payment",
        ]:
            self.update_interest_summary_values(loan)
            loan.reload()

        # update closing balance
        frappe.db.set_value(
            self.doctype,
            self.name,
            "closing_balance",
            loan.balance,
            update_modified=False,
        )

    def pay_for_interest(self, negative_balance):
        # fetch all interest transaction which are not paid
        # sauce: https://stackoverflow.com/a/25433139/9403680
        not_paid_interests = frappe.db.sql(
            """select name, amount, time, unpaid_interest, transaction_type from `tabLoan Transaction` where loan=%s and transaction_type in ('Interest', 'Additional Interest', 'Penal Interest') and unpaid_interest > 0 order by field(transaction_type, "Penal Interest", "Additional Interest", "Interest")""",
            self.loan,
            as_dict=1,
        )

        if not_paid_interests:
            if negative_balance < 0 and not self.is_for_interest:
                total_interest_amt_paid = abs(negative_balance)
                transaction_name = ""
            else:
                total_interest_amt_paid = self.amount
                transaction_name = self.name

            for interest in not_paid_interests:
                interest_pay_log_amt = unpaid_interest = 0

                if interest["unpaid_interest"] > total_interest_amt_paid:
                    interest_pay_log_amt = total_interest_amt_paid
                    unpaid_interest = (
                        interest["unpaid_interest"] - total_interest_amt_paid
                    )
                    total_interest_amt_paid = 0

                if interest["unpaid_interest"] <= total_interest_amt_paid:
                    interest_pay_log_amt = interest["unpaid_interest"]
                    unpaid_interest = 0
                    total_interest_amt_paid = (
                        total_interest_amt_paid - interest["unpaid_interest"]
                    )

                # Add 'Interest pay log' entry and also Update 'unpaid_interest'
                interest_doc = frappe.get_doc("Loan Transaction", interest["name"])
                interest_doc.append(
                    "items",
                    {
                        "amount": interest_pay_log_amt,
                        "payment_transaction": transaction_name,
                    },
                )
                interest_doc.save(ignore_permissions=True)
                interest_doc.db_set("unpaid_interest", unpaid_interest)

                if total_interest_amt_paid <= 0:
                    break

    def create_lender_ledger(
        self,
        lender_share,
        spark_share,
    ):
        frappe.get_doc(
            {
                "doctype": "Lender Ledger",
                "loan": self.loan,
                "customer_name": self.customer_name,
                "loan_transaction": self.name,
                "lender": self.lender,
                "transaction_type": self.transaction_type,
                "amount": self.amount,
                "lender_share": lender_share,
                "spark_share": spark_share,
            }
        ).insert(ignore_permissions=True)

    def before_submit(self):
        if not self.transaction_id:
            frappe.throw("Kindly add transaction id before approving")

        if self.transaction_type == "Withdrawal":
            self.amount = self.disbursed

            if self.amount <= 0:
                frappe.throw("Amount should be more than 0.")

            # amount should be less than equal requsted
            if self.amount > self.requested:
                frappe.throw("Amount should be less than or equal to requested amount")

            # check if allowable is greater than amount
            if self.amount > self.allowable:
                frappe.throw("Amount should be less than or equal to allowable amount")

    def on_update(self):
        if self.transaction_type == "Withdrawal":
            customer = self.get_loan().get_customer()
            if self.status == "Rejected":
                mess = "Dear Customer,\nSorry! Your withdrawal request has been rejected by our lending partner for technical reasons. We regret the inconvenience caused. Please try again after sometime or reach out to us through 'Contact Us' on the app  -Spark Loans"

                from frappe.core.doctype.sms_settings.sms_settings import send_sms

                doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
                doc["withdrawal"] = {"status": self.status}
                frappe.enqueue_doc("Notification", "Withdrawal", method="send", doc=doc)
                frappe.enqueue(
                    method=send_sms, receiver_list=[customer.phone], msg=mess
                )
                fcm_notification = frappe.get_doc(
                    "Spark Push Notification", "Withdrawal rejected", fields=["*"]
                )
                lms.send_spark_push_notification(
                    fcm_notification=fcm_notification, loan=self.loan, customer=customer
                )

        if self.loan_margin_shortfall:
            if self.status == "Rejected":
                # if shortfall is not recoverd then margin shortfall status will change from request pending to pending
                loan_margin_shortfall = frappe.get_doc(
                    "Loan Margin Shortfall", self.loan_margin_shortfall
                )
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

        # if rejected then opening balance = closing balance
        if self.status == "Rejected":
            frappe.db.set_value(
                self.doctype,
                self.name,
                "closing_balance",
                self.opening_balance,
                update_modified=False,
            )

    def get_customer(self):
        return frappe.get_doc("Loan Customer", self.customer)

    def update_interest_summary_values(self, loan):
        """
        total interest = interest + additional interest + penal interest
        where unpaid interest > 0
        """
        total_interest_incl_penal_due = frappe.db.sql(
            "select sum(unpaid_interest) as total_amount from `tabLoan Transaction` where loan = '{}' and transaction_type in ('Interest', 'Additional Interest', 'Penal Interest') and unpaid_interest >0 ".format(
                self.loan
            ),
            as_dict=1,
        )[0]["total_amount"]
        # day_past_due = frappe.db.sql(
        #     "select sum(unpaid_interest) as total_amount, DATEDIFF('{}', time) as dpd from `tabLoan Transaction` where loan = '{}' and transaction_type = 'Interest' and unpaid_interest >0 order by creation asc".format(
        #         current_date, self.loan
        #     ),
        #     as_dict=True,
        # )
        # if day_past_due[0]["total_amount"]:
        #     loan.day_past_due = day_past_due[0]["dpd"]
        # else:
        #     loan.day_past_due = 0
        loan.total_interest_incl_penal_due = (
            total_interest_incl_penal_due if total_interest_incl_penal_due else 0.0
        )
        """On Full Payment Done of Interest
        day past due will reset to 0
        """
        if total_interest_incl_penal_due == None:
            loan.day_past_due = 0
        """Sum of unpaid interest in loan transaction of transaction type Penal Interest """
        if self.transaction_type in ["Penal Interest", "Payment"]:
            penal_interest_charges = frappe.db.sql(
                "select sum(unpaid_interest) as unpaid_interest from `tabLoan Transaction` where loan = '{}' and transaction_type = 'Penal Interest' and unpaid_interest >0 ".format(
                    self.loan
                ),
                as_dict=1,
            )
            loan.penal_interest_charges = (
                penal_interest_charges[0]["unpaid_interest"]
                if penal_interest_charges
                else 0.0
            )

        """Sum of unpaid interest in loan transaction of transaction type Interest of last month"""
        if self.transaction_type in ["Interest", "Payment"]:
            # interest_due = frappe.db.sql(
            #     "select sum(unpaid_interest) as unpaid_interest from `tabLoan Transaction` where loan = '{}' and transaction_type = 'Interest' and unpaid_interest >0 ".format(
            #         self.loan
            #     ),
            #     as_dict=1,
            # )[0]["unpaid_interest"]
            # input_date = frappe.utils.now_datetime()
            # calculation_date = (input_date).replace(
            #     day=1, hour=23, minute=59, second=59, microsecond=999999
            # ) - timedelta(days=1)
            # prev_month = calculation_date.month
            # prev_month_year = calculation_date.year
            interest_due = frappe.db.sql(
                "select unpaid_interest from `tabLoan Transaction` where loan = '{}' and transaction_type = 'Interest' and unpaid_interest > 0 order by time desc ".format(
                    self.loan
                ),
                as_dict=1,
            )
            loan.interest_due = (
                interest_due[0]["unpaid_interest"] if interest_due else 0.0
            )
            if self.transaction_type == "Interest":
                loan.base_interest_amount = 0.0

        """
        Sum of unpaid interest in loan transaction of transaction type Additional Interest till now and
        set interest due to 0.0
        """
        if self.transaction_type in ["Additional Interest", "Payment"]:
            interest_overdue = frappe.db.sql(
                "select sum(unpaid_interest) as unpaid_interest from `tabLoan Transaction` where loan = '{}' and transaction_type in ('Interest', 'Additional Interest') and unpaid_interest >0 ".format(
                    self.loan
                ),
                as_dict=1,
            )
            loan.interest_overdue = (
                interest_overdue[0]["unpaid_interest"] if interest_overdue else 0.0
            )
            if interest_overdue:
                loan.interest_due = 0.0
        if self.transaction_type == "Payment":
            import lms.lms.doctype.loan.loan as Loan

            current_date = frappe.utils.now_datetime()
            loan.day_past_due = Loan.Loan.calculate_day_past_due(loan, current_date)
        loan.save(ignore_permissions=True)

    def before_save(self):
        if (
            self.transaction_type == "Withdrawal"
            and self.allowable > self.requested
            and self.status == "Ready for Approval"
        ):
            frappe.throw("Allowable amount could not be greater than requested amount")
