# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import base64
import json
from datetime import datetime, timedelta

import frappe
import razorpay
import requests
from frappe import _
from frappe.model.document import Document

import lms
from lms import convert_sec_to_hh_mm_ss
from lms.firebase import FirebaseAdmin
from lms.lms.doctype.user_token.user_token import send_sms


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
        "DP Reimbursement(Unpledge) Charges": "DR",
        "DP Reimbursement(Sell) Charges": "DR",
        "Sell Collateral Charges": "DR",
        "Account Renewal Charges": "DR",
        "Lien Charges": "DR",  # MF
        "Invoke Charges": "DR",  # MF
        "Revoke Charges": "DR",  # MF
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
        user_roles = frappe.db.get_values(
            "Has Role", {"parent": frappe.session.user, "parenttype": "User"}, ["role"]
        )
        if "Loan Customer" in user_roles:
            self.validate_withdrawal_amount()
        # set customer
        loan = self.get_loan()
        # update opening balance
        customer = frappe.get_doc("Loan Customer", loan.customer)
        user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
        for i in user_kyc.bank_account:
            if i.is_default == 1:
                bank = i.bank
                account_number = i.account_number
                ifsc = i.ifsc
        self.opening_balance = loan.balance
        self.customer = loan.customer
        self.customer_name = loan.customer_name
        if (
            self.transaction_type == "Withdrawal"
            and not self.allowable
            and not self.requested
            and "Loan Customer" not in user_roles
        ):
            self.requested = self.amount
            self.allowable = loan.maximum_withdrawable_amount()
            self.bank = bank
            self.account_number = account_number
            self.ifsc = ifsc

        # if there is interest for loan, mark is_for_interest=True for loan transaction with record type CR
        if self.record_type == "CR":
            interest_entry = frappe.get_value(
                "Loan Transaction",
                {
                    "loan": self.loan,
                    "transaction_type": "Interest",
                    "unpaid_interest": [">", 0],
                },
                "name",
            )
            if interest_entry and not self.is_for_interest:
                self.is_for_interest = True

        # check for user roles and permissions before adding transactions
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
            "DP Reimbursement(Unpledge) Charges",
            "DP Reimbursement(Sell) Charges",
            "Sell Collateral Charges",
            "Account Renewal Charges",
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
        loan = self.get_loan()
        lender = self.get_lender()
        if self.transaction_type in [
            "Processing Fees",
            "Stamp Duty",
            "Documentation Charges",
            "Mortgage Charges",
        ]:
            check_for_shortfall = False
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

            # customer_name = loan.customer_name
            self.create_lender_ledger(
                lender_sharing_amount,
                spark_sharing_amount,
            )

        if self.transaction_type in [
            "Processing Fees",
            "Stamp Duty",
            "Documentation Charges",
            "Mortgage Charges",
            "Sell Collateral Charges",
            "Account Renewal Charges",
            "DP Reimbursement(Unpledge) Charges",
            "DP Reimbursement(Sell) Charges",
            "Lien Charges",
            "Invocation Charges",
            "Revocation Charges",
        ]:
            self.gst_on_charges(loan, lender)

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
                receiver_list = [str(self.get_customer().phone)]
                if self.get_customer().get_kyc().mob_num:
                    receiver_list.append(str(self.get_customer().get_kyc().mob_num))
                if self.get_customer().get_kyc().choice_mob_no:
                    receiver_list.append(
                        str(self.get_customer().get_kyc().choice_mob_no)
                    )

                receiver_list = list(set(receiver_list))

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
                    "razorpay_event": ["not in", ["", "Failed", "Payment Cancelled"]],
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
            "Sell Collateral",
        ]:
            loan.reload()
            self.update_interest_summary_values(loan)
            # loan.reload()

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

        # if self.transaction_type == "Payment" and self.settlement_status != "Processed":
        #     frappe.throw(
        #         "Can not approve this Payment transaction as its Settlement status is not Processed"
        #     )

    def on_update(self):
        if self.transaction_type == "Withdrawal":
            customer = self.get_loan().get_customer()
            if self.status == "Rejected":
                mess = "Dear Customer,\nSorry! Your withdrawal request has been rejected by our lending partner for technical reasons. We regret the inconvenience caused. Please try again after sometime or reach out to us through 'Contact Us' on the app  -Spark Loans"

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
                        "razorpay_event": [
                            "not in",
                            ["", "Failed", "Payment Cancelled"],
                        ],
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

        loan.total_interest_incl_penal_due = (
            total_interest_incl_penal_due if total_interest_incl_penal_due else 0.0
        )
        """On Full Payment Done of Interest
        day past due will reset to 0
        """
        if total_interest_incl_penal_due == None:
            loan.day_past_due = 0
        """Sum of unpaid interest in loan transaction of transaction type Penal Interest """
        if self.transaction_type in ["Penal Interest", "Payment", "Sell Collateral"]:
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
        if self.transaction_type in ["Interest", "Payment", "Sell Collateral"]:
            interest_due = frappe.db.sql(
                "select unpaid_interest from `tabLoan Transaction` where loan = '{}' and additional_interest IS NULL and transaction_type = 'Interest' and unpaid_interest > 0 order by time desc ".format(
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
        if self.transaction_type in [
            "Additional Interest",
            "Payment",
            "Sell Collateral",
        ]:
            # Fresh interest entry for interest_due field i.e additional_interest field IS NULL
            interest_due = frappe.db.sql(
                "select unpaid_interest from `tabLoan Transaction` where loan = '{}' and transaction_type = 'Interest' and additional_interest IS NULL and unpaid_interest > 0 order by time desc ".format(
                    self.loan
                ),
                as_dict=1,
            )
            loan.interest_due = (
                interest_due[0]["unpaid_interest"] if interest_due else 0.0
            )

            interest_overdue = frappe.db.sql(
                "select sum(unpaid_interest) as unpaid_interest from `tabLoan Transaction` where loan = '{loan}' and transaction_type in ('Interest', 'Additional Interest') and unpaid_interest > 0".format(
                    loan=self.loan
                ),
                as_dict=1,
            )
            if interest_overdue[0]["unpaid_interest"]:
                loan.interest_overdue = (
                    interest_overdue[0]["unpaid_interest"] - loan.interest_due
                )
            else:
                loan.interest_overdue = 0

        if self.transaction_type in ["Payment", "Sell Collateral"]:
            loan.day_past_due = loan.calculate_day_past_due(frappe.utils.now_datetime())
        loan.save(ignore_permissions=True)

    def before_save(self):
        loan = self.get_loan()
        self.lender = loan.lender
        self.instrument_type = loan.instrument_type
        self.scheme_type = loan.scheme_type
        if (
            self.transaction_type == "Withdrawal"
            and self.allowable > self.requested
            and self.status == "Ready for Approval"
        ):
            frappe.throw("Allowable amount could not be greater than requested amount")

        if self.transaction_type == "Amount Write Off" and self.amount > (
            loan.balance * -1
        ):
            frappe.throw("Amount input cannot be Greater than credit loan balance")

    def gst_on_charges(self, loan, lender):
        lender = lender.as_dict()
        customer = frappe.get_doc("Loan Customer", loan.customer)
        user_kyc = customer.get_kyc()
        address = frappe.get_doc("Customer Address Details", user_kyc.address_details)
        if address.perm_state.lower() == "maharashtra":
            # CGST
            transac_cgst = "CGST on " + self.transaction_type
            trans_cgst = (
                transac_cgst.lower().replace(" ", "_").replace("(", "").replace(")", "")
            )
            if lender.get(trans_cgst) > 0:
                cgst = self.amount * (lender.get(trans_cgst) / 100)
                if cgst > 0:
                    loan.create_loan_transaction(
                        transaction_type=transac_cgst,
                        amount=cgst,
                        gst_percent=lender.get(trans_cgst),
                        charge_reference=self.name,
                        approve=True,
                    )
            # SGST
            transac_sgst = "SGST on " + self.transaction_type
            trans_sgst = (
                transac_sgst.lower().replace(" ", "_").replace("(", "").replace(")", "")
            )
            if lender.get(trans_sgst) > 0:
                sgst = self.amount * (lender.get(trans_sgst) / 100)
                if sgst > 0:
                    loan.create_loan_transaction(
                        transaction_type=transac_sgst,
                        amount=sgst,
                        gst_percent=lender.get(trans_sgst),
                        charge_reference=self.name,
                        approve=True,
                    )
        else:
            # IGST
            transac_igst = "IGST on " + self.transaction_type
            trans_igst = (
                transac_igst.lower().replace(" ", "_").replace("(", "").replace(")", "")
            )
            if lender.get(trans_igst) > 0:
                igst = self.amount * (lender.get(trans_igst) / 100)
                if igst > 0:
                    loan.create_loan_transaction(
                        transaction_type=transac_igst,
                        amount=igst,
                        gst_percent=lender.get(trans_igst),
                        charge_reference=self.name,
                        approve=True,
                    )


@frappe.whitelist()
def reject_blank_transaction_and_settlement_recon_api():
    data = ""
    try:
        blank_rzp_event_transaction = frappe.get_all(
            "Loan Transaction",
            {
                "transaction_type": "Payment",
                "razorpay_event": "",
                "status": "Pending",
            },
        )
        if blank_rzp_event_transaction:
            for single_transaction in blank_rzp_event_transaction:
                single_transaction = frappe.get_doc(
                    "Loan Transaction", single_transaction.name
                )
                data = single_transaction.name
                if single_transaction.creation < frappe.utils.now_datetime():
                    hours_difference = convert_sec_to_hh_mm_ss(
                        abs(
                            frappe.utils.now_datetime() - single_transaction.creation
                        ).total_seconds()
                    )
                    if int(hours_difference.split(":")[0]) >= 24:
                        single_transaction.workflow_state = "Rejected"
                        single_transaction.status = "Rejected"
                        single_transaction.save(ignore_permissions=True)
                        frappe.db.commit()
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback() + "\nPayment details:\n" + data,
            title=_("Blank Payment Reject Error"),
        )
    if frappe.utils.now_datetime().hour > 15:
        settlement_recon_api()


@frappe.whitelist()
def settlement_recon_api(input_date=None):
    try:
        if input_date:
            input_date = datetime.strptime(input_date, "%Y-%m-%d")
        else:
            input_date = frappe.utils.now_datetime().date()

        loan_transaction_name = ""
        # get rzp key secret from las settings
        razorpay_key_secret = frappe.get_single("LAS Settings").razorpay_key_secret
        if razorpay_key_secret:
            # split rzp key secret and store in id and secret for auth of single settlement api
            id, secret = razorpay_key_secret.split(":")
            client = razorpay.Client(auth=(id, secret))

            # Basic auth for settlement recon api
            razorpay_key_secret_auth = "Basic " + base64.b64encode(
                bytes(razorpay_key_secret, "utf-8")
            ).decode("ascii")

            # query parameters for settlement recon api
            params = {
                "year": input_date.year,
                "month": input_date.month,
                "day": input_date.day,
            }

            las_settings = frappe.get_single("LAS Settings")
            raw_res = requests.get(
                las_settings.settlement_recon_api,
                headers={"Authorization": razorpay_key_secret_auth},
                params=params,
            )
            # get json response from raw response
            res = raw_res.json()

            # create log for settlement recon api
            log = {
                "request": params,
                "response": res,
            }
            lms.create_log(log, "settlement_recon_api_log")

            if res["count"] and res["items"]:
                # iterate through all settled items
                for settled_items in res["items"]:
                    try:
                        loan_transaction_name = frappe.get_value(
                            "Loan Transaction",
                            {
                                "order_id": settled_items["order_id"],
                                "transaction_id": settled_items["entity_id"],
                                "loan": json.loads(settled_items["notes"])["loan_name"],
                                "razorpay_event": "Captured",
                            },
                            "name",
                        )
                        if loan_transaction_name:
                            # call settlement api with id
                            settle_res = client.settlement.fetch(
                                settled_items["settlement_id"]
                            )
                            lms.create_log(
                                {
                                    "settle_res": settle_res,
                                    "loan_transaction_name": loan_transaction_name,
                                },
                                "settlement_api_id_log",
                            )

                            loan_transaction = frappe.get_doc(
                                "Loan Transaction", loan_transaction_name
                            )
                            # update settlement status in loan transaction
                            if settle_res["status"] == "created":
                                settlement_status = "Created"
                            elif settle_res["status"] == "processed":
                                settlement_status = "Processed"
                            elif settle_res["status"] == "failed":
                                settlement_status = "Failed"

                            # update settlement id in loan transaction
                            if loan_transaction.status == "Pending":
                                loan_transaction.settlement_status = settlement_status
                                loan_transaction.settlement_id = settled_items[
                                    "settlement_id"
                                ]
                                loan_transaction.save(ignore_permissions=True)
                                frappe.db.commit()
                            else:
                                if loan_transaction.settlement_status != "Processed":
                                    loan_transaction.db_set(
                                        "settlement_status", settlement_status
                                    )
                                    loan_transaction.db_set(
                                        "settlement_id", settled_items["settlement_id"]
                                    )

                    except Exception:
                        frappe.log_error(
                            message=frappe.get_traceback()
                            + "\nSettlement details:\n"
                            + json.dumps(settled_items)
                            + loan_transaction_name,
                            title=_("Payment Settlement Error"),
                        )
    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback() + "\nSettlement details:\n" + str(e.args),
            title=_("Payment Settlement Error"),
        )
