# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import math
from datetime import date, datetime, timedelta

import frappe
from frappe import _
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from frappe.model.document import Document

import lms
from lms import convert_sec_to_hh_mm_ss, holiday_list
from lms.firebase import FirebaseAdmin


class LoanMarginShortfall(Document):
    def before_save(self):
        self.fill_items()

    def fill_items(self):
        loan = frappe.get_doc("Loan", self.loan)

        self.total_collateral_value = loan.total_collateral_value
        self.allowable_ltv = loan.allowable_ltv
        self.drawing_power = loan.drawing_power

        self.loan_balance = loan.balance
        # self.ltv = (self.loan_balance / self.total_collateral_value) * 100
        # Zero division error - handling
        self.ltv = (
            (self.loan_balance / self.total_collateral_value) * 100
            if self.total_collateral_value > 0
            else loan.allowable_ltv
        )

        self.surplus_margin = 100 - self.ltv
        self.minimum_collateral_value = (100 / self.allowable_ltv) * self.loan_balance

        self.shortfall = math.ceil(
            (self.minimum_collateral_value - self.total_collateral_value)
            if self.loan_balance > self.drawing_power
            else 0
        )
        self.shortfall_c = math.ceil(
            ((self.loan_balance - self.drawing_power) * 2)
            if self.loan_balance > self.drawing_power
            else 0
        )
        self.shortfall_percentage = (
            ((self.loan_balance - self.drawing_power) / self.loan_balance) * 100
            if self.loan_balance > self.drawing_power
            else 0
        )

        self.minimum_pledge_amount = self.shortfall_c
        self.advisable_pledge_amount = self.minimum_pledge_amount * 1.1
        self.minimum_cash_amount = (self.allowable_ltv / 100) * self.shortfall_c
        self.advisable_cash_amount = self.minimum_cash_amount * 1.1

        self.set_shortfall_action()

    def set_shortfall_action(self):
        self.margin_shortfall_action = None

        action_list = frappe.get_all(
            "Margin Shortfall Action",
            filters={"max_threshold": (">=", self.shortfall_percentage)},
            order_by="max_threshold asc",
            page_length=1,
        )
        if len(action_list):
            self.margin_shortfall_action = action_list[0].name

    def after_insert(self):
        if self.status == "Pending":
            self.set_deadline()

    def get_loan(self):
        return frappe.get_doc("Loan", self.loan)

    def get_shortfall_action(self):
        if self.margin_shortfall_action:
            return frappe.get_doc(
                "Margin Shortfall Action", self.margin_shortfall_action
            )

    def set_deadline(self, old_shortfall_action=None):
        margin_shortfall_action = self.get_shortfall_action()
        mess = ""

        if (
            margin_shortfall_action
            and old_shortfall_action != margin_shortfall_action.name
        ):
            if old_shortfall_action:
                old_shortfall_action = frappe.get_doc(
                    "Margin Shortfall Action", old_shortfall_action
                ).sell_off_deadline_eod

            """suppose mg shortfall deadline was after 72 hours and suddenly more shortfall happens the deadline will be
            EOD and before EOD security values increased and margin shortfall percentage gone below 20% then deadline should be 72 hrs which was started at initial stage"""
            if old_shortfall_action and margin_shortfall_action.sell_off_after_hours:
                # self.deadline = self.creation + timedelta(
                #     hours=margin_shortfall_action.sell_off_after_hours
                # )
                self.update_deadline_based_on_holidays()

            elif (
                margin_shortfall_action.sell_off_after_hours
                and not margin_shortfall_action.sell_off_deadline_eod
            ):
                # sell off after 72 hours
                # self.deadline = frappe.utils.now_datetime() + timedelta(
                #     hours=margin_shortfall_action.sell_off_after_hours
                # )
                self.update_deadline_based_on_holidays(frappe.utils.now_datetime())

            elif (
                not margin_shortfall_action.sell_off_after_hours
                and margin_shortfall_action.sell_off_deadline_eod
            ):
                # sell off at EOD
                self.deadline = frappe.utils.now_datetime().replace(
                    hour=margin_shortfall_action.sell_off_deadline_eod,
                    minute=0,
                    second=0,
                    microsecond=0,
                )

            elif (
                not margin_shortfall_action.sell_off_after_hours
                and not margin_shortfall_action.sell_off_deadline_eod
            ):
                # sell off immediately
                self.deadline = frappe.utils.now_datetime()
                hrs_sell_off = frappe.get_all(
                    "Margin Shortfall Action",
                    filters={"sell_off_deadline_eod": ("!=", 0)},
                    fields=["max_threshold"],
                )
                doc = frappe.get_doc(
                    "User KYC", self.get_loan().get_customer().choice_kyc
                ).as_dict()
                doc["loan_margin_shortfall"] = {
                    "loan": self.loan,
                    "margin_shortfall_action": margin_shortfall_action,
                    "hrs_sell_off": hrs_sell_off[0].max_threshold,
                }
                # if self.status in ["Pending", "Approved", "Rejected"]:
                frappe.enqueue_doc(
                    "Notification", "Sale Triggered", method="send", doc=doc
                )
                mess = "Dear Customer,\nURGENT NOTICE. There is a margin shortfall in your loan account which exceeds {}% of portfolio value. Therefore sale has been triggered in your loan account {}.The lender will sell required collateral and deposit the proceeds in your loan account to fulfill the shortfall. Kindly check the app for details. Spark Loans".format(
                    hrs_sell_off[0].max_threshold, self.loan
                )
                fcm_notification = frappe.get_doc(
                    "Spark Push Notification", "Sale triggerred immediate", fields=["*"]
                )
                message = fcm_notification.message.format(
                    max_threshold=hrs_sell_off[0].max_threshold
                )
            if margin_shortfall_action.sell_off_after_hours:
                mess = "Dear Customer,\nURGENT ACTION REQUIRED. There is a margin shortfall in your loan account {}. Please check the app and take an appropriate action within {} hours; else sale will be triggered. Spark Loans".format(
                    self.loan, margin_shortfall_action.sell_off_after_hours
                )
                fcm_notification = frappe.get_doc(
                    "Spark Push Notification",
                    "Margin shortfall – Action required after hours",
                    fields=["*"],
                )
                message = fcm_notification.message.format(
                    loan=self.loan,
                    shortfall_action=margin_shortfall_action.sell_off_after_hours,
                )

            elif margin_shortfall_action.sell_off_deadline_eod:
                eod_sell_off = frappe.get_all(
                    "Margin Shortfall Action",
                    filters={"sell_off_after_hours": ("!=", 0)},
                    fields=["max_threshold"],
                )

                mess = "Dear Customer,\nURGENT ACTION REQUIRED. There is a margin shortfall in your loan account {} which exceeds {}% of portfolio value. Please check the app and take an appropriate action by {} Today; else sale will be triggered. Spark Loans".format(
                    self.loan,
                    eod_sell_off[0].max_threshold,
                    datetime.strptime(
                        str(margin_shortfall_action.sell_off_deadline_eod), "%H"
                    ).strftime("%I:%M%P"),
                )
                fcm_notification = frappe.get_doc(
                    "Spark Push Notification",
                    "Margin shortfall – Action required at eod",
                    fields=["*"],
                )
                message = fcm_notification.message.format(
                    loan=self.loan,
                    max_threshold=eod_sell_off[0].max_threshold,
                    eod_time=datetime.strptime(
                        str(margin_shortfall_action.sell_off_deadline_eod), "%H"
                    ).strftime("%I:%M%P"),
                )

            if (
                margin_shortfall_action.sell_off_after_hours
                or margin_shortfall_action.sell_off_deadline_eod
            ):
                doc = frappe.get_doc(
                    "User KYC", self.get_loan().get_customer().choice_kyc
                ).as_dict()
                doc["loan_margin_shortfall"] = {
                    "loan": self.loan,
                    "margin_shortfall_action": margin_shortfall_action,
                }
                frappe.enqueue_doc(
                    "Notification", "Margin Shortfall", method="send", doc=doc
                )

            if mess:
                frappe.enqueue(
                    method=send_sms,
                    receiver_list=[self.get_loan().get_customer().phone],
                    msg=mess,
                )

            if fcm_notification:
                lms.send_spark_push_notification(
                    fcm_notification=fcm_notification,
                    message=message,
                    loan=self.loan,
                    customer=self.get_loan().get_customer(),
                )

            self.save(ignore_permissions=True)
            frappe.db.commit()

    def update_deadline_based_on_holidays(self, input_datetime=None):
        margin_shortfall_action = self.get_shortfall_action()
        if margin_shortfall_action.sell_off_after_hours:
            total_hrs = []
            if input_datetime:
                creation_date = input_datetime.date() + timedelta(days=1)
                creation_datetime = input_datetime
            else:
                creation_date = (
                    datetime.strptime(str(self.creation), "%Y-%m-%d %H:%M:%S.%f")
                ).date() + timedelta(days=1)

                creation_datetime = datetime.strptime(
                    str(self.creation), "%Y-%m-%d %H:%M:%S.%f"
                )

            counter = 1
            max_days = int(margin_shortfall_action.sell_off_after_hours / 24)
            while counter <= max_days:
                if creation_date not in holiday_list():
                    total_hrs.append(creation_date)
                    creation_date += timedelta(hours=24)
                    counter += 1
                else:
                    creation_date += timedelta(hours=24)

            date_of_deadline = datetime.strptime(
                total_hrs[-1].strftime("%Y-%m-%d %H:%M:%S.%f"), "%Y-%m-%d %H:%M:%S.%f"
            )
            self.deadline = date_of_deadline.replace(
                hour=creation_datetime.hour,
                minute=creation_datetime.minute,
                second=creation_datetime.second,
                microsecond=creation_datetime.microsecond,
            )
            fcm_notification = frappe.get_doc(
                "Spark Push Notification",
                "Margin shortfall – Action required after hours",
                fields=["*"],
            )
