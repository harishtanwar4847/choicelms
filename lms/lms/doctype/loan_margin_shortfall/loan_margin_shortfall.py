# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import json
import math
from datetime import date, datetime, timedelta

import frappe
from frappe import _
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from frappe.model.document import Document

import lms
from lms.firebase import FirebaseAdmin
from lms.user import convert_sec_to_hh_mm_ss, holiday_list


class LoanMarginShortfall(Document):
    def before_save(self):
        self.fill_items()

    def fill_items(self):
        loan = frappe.get_doc("Loan", self.loan)
        self.total_collateral_value = loan.total_collateral_value
        self.allowable_ltv = loan.allowable_ltv
        self.drawing_power = loan.drawing_power
        self.customer_name = loan.customer_name
        self.loan_balance = loan.balance
        self.time_remaining = "00:00:00"
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
            loan = self.get_loan()
            # self.notify_customer()

            # creation = datetime.strptime(self.creation, "%Y-%m-%d %H:%M:%S.%f")
            # deadline = self.deadline
            # hrs_difference = deadline - frappe.utils.now_datetime()
            # margin_shortfall_action = self.get_shortfall_action()
            # if margin_shortfall_action.sell_off_after_hours:
            #     date_array = set(
            #         creation.date() + timedelta(days=x)
            #         for x in range(
            #             0,
            #             (deadline.date() - creation.date()).days + 1,
            #         )
            #     )
            #     holidays = date_array.intersection(set(holiday_list()))
            #     hrs_difference = (
            #         deadline
            #         - frappe.utils.now_datetime()
            #         - timedelta(days=(len(holidays) if holidays else 0))
            #     )

            # try:
            #     fa = FirebaseAdmin()
            #     fa.send_data(
            #         data={
            #             "event": "timer start",
            #             "condition": "after insert",
            #             "time": convert_sec_to_hh_mm_ss(
            #                 abs(hrs_difference).total_seconds()
            #             ),
            #             "loan_name": loan.name,
            #             "margin_shortfall_doc": self.as_json(),
            #         },
            #         tokens=lms.get_firebase_tokens(loan.get_customer().user),
            #     )
            # except Exception:
            #     pass
            # finally:
            #     fa.delete_app()
            # try:
            #     fa = FirebaseAdmin()
            #     fa.send_data(
            #         data={
            #             "event": "timer stop",
            #             "condition": "after insert",
            #             "time": "00:00:00",
            #             "loan_name": loan.name,
            #             "margin_shortfall_doc": self.as_json(),
            #         },
            #         tokens=lms.get_firebase_tokens(loan.get_customer().user),
            #     )
            # except Exception:
            #     pass
            # finally:
            #     fa.delete_app()

        # TODO: notify customer even if not set margin shortfall action

    def get_loan(self):
        return frappe.get_doc("Loan", self.loan)

    def get_shortfall_action(self):
        if self.margin_shortfall_action:
            return frappe.get_doc(
                "Margin Shortfall Action", self.margin_shortfall_action
            )

    def notify_customer(self):
        margin_shortfall_action = self.get_shortfall_action()
        # mess = ""
        # if margin_shortfall_action.sell_off_after_hours:
        #     mess = "Dear Customer,\nURGENT ACTION REQUIRED. There is a margin shortfall in your loan account {}. Please check the app and take an appropriate action within {} hours; else sale will be triggered. Spark Loans".format(
        #         self.loan, margin_shortfall_action.sell_off_after_hours
        #     )
        # elif margin_shortfall_action.sell_off_deadline_eod:
        #     eod_sell_off = frappe.get_all(
        #         "Margin Shortfall Action",
        #         filters={"sell_off_after_hours": ("!=", 0)},
        #         fields=["max_threshold"],
        #     )

        #     mess = "Dear Customer,\nURGENT ACTION REQUIRED. There is a margin shortfall in your loan account {} which exceeds {}% of portfolio value. Please check the app and take an appropriate action by {} Today; else sale will be triggered. Spark Loans".format(
        #         self.loan,
        #         eod_sell_off[0].max_threshold,
        #         datetime.strptime(
        #             str(margin_shortfall_action.sell_off_deadline_eod), "%H"
        #         ).strftime("%I:%M%P"),
        #     )

        # doc = frappe.get_doc(
        #     "User KYC", self.get_loan().get_customer().choice_kyc
        # ).as_dict()
        # doc["loan_margin_shortfall"] = {
        #     "loan": self.loan,
        #     "margin_shortfall_action": margin_shortfall_action,
        # }
        # frappe.enqueue_doc("Notification", "Margin Shortfall", method="send", doc=doc)
        # if mess:
        #     frappe.enqueue(
        #         method=send_sms,
        #         receiver_list=[self.get_loan().get_customer().phone],
        #         msg=mess,
        #     )

        # if margin_shortfall_action:
        #     customer = self.get_loan().get_customer()
        #     mess = _(
        #         "Your Loan {0} has been marked for margin shortfall. Please take action"
        #     ).format(self.loan)

        #     # if margin_shortfall_action.sms:
        #     #     frappe.enqueue(
        #     #         method=send_sms, receiver_list=[customer.phone], msg=mess
        #     #     )

        #     if margin_shortfall_action.email:
        #         frappe.enqueue(
        #             method=frappe.sendmail,
        #             recipients=[customer.user],
        #             sender=None,
        #             subject="Margin Shortfall Notification",
        #             message=mess,
        #         )

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

    # def timer_start_stop_fcm(self):
    #     loan = self.get_loan()
    #     now = frappe.utils.now_datetime()
    #     tomorrow = datetime.strptime(
    #         frappe.utils.today(), "%Y-%m-%d"
    #     ).date() + timedelta(days=1)

    #     if (
    #         now.hour == 23
    #         and now.minute >= 00
    #         and now.second >= 00
    #         and now.microsecond >= 0
    #     ):
    #         if tomorrow in holiday_list() and (self.deadline).date() >= tomorrow:
    #             try:
    #                 fa = FirebaseAdmin()
    #                 fa.send_data(
    #                     data={
    #                         "event": "timer stop",
    #                         "condition": "if tomorrow bank holiday",
    #                         "time": convert_sec_to_hh_mm_ss(
    #                             abs(
    #                                 self.deadline
    #                                 - frappe.utils.now_datetime().replace(
    #                                     hour=23,
    #                                     minute=59,
    #                                     second=59,
    #                                     microsecond=999999,
    #                                 )
    #                                 - timedelta(days=1)
    #                             ).total_seconds()
    #                         ),
    #                         "loan_name": loan.name,
    #                         "margin_shortfall_doc": self.as_json(),
    #                     },
    #                     tokens=lms.get_firebase_tokens(loan.get_customer().user),
    #                 )
    #             except Exception:
    #                 pass
    #             finally:
    #                 fa.delete_app()

    #         if (
    #             datetime.strptime(frappe.utils.today(), "%Y-%m-%d").date()
    #             in holiday_list()
    #             and tomorrow not in holiday_list()
    #         ):
    #             try:
    #                 fa = FirebaseAdmin()
    #                 fa.send_data(
    #                     data={
    #                         "event": "timer start",
    #                         "condition": "if tomorrow no bank holiday",
    #                         "time": convert_sec_to_hh_mm_ss(
    #                             abs(
    #                                 self.deadline
    #                                 - frappe.utils.now_datetime().replace(
    #                                     hour=23,
    #                                     minute=59,
    #                                     second=59,
    #                                     microsecond=999999,
    #                                 )
    #                                 - timedelta(days=1)
    #                             ).total_seconds()
    #                         ),
    #                         "loan_name": loan.name,
    #                         "margin_shortfall_doc": self.as_json(),
    #                     },
    #                     tokens=lms.get_firebase_tokens(loan.get_customer().user),
    #                 )
    #             except Exception:
    #                 pass
    #             finally:
    #                 fa.delete_app()

    def on_update(self):
        loan = self.get_loan()
        loan.margin_shortfall_amount = self.shortfall_c
        loan.save(ignore_permissions=True)
        frappe.db.commit()
        self.notify_customer()
        # TODO : manage 'Sell Triggered' Notify Customer and Update Deadline Scenario - with scheduler/any
        """
        # if (
        #     self.shortfall_percentage > 0
        #     and frappe.utils.now_datetime()
        #     > datetime.strptime(self.deadline, "%Y-%m-%d %H:%M:%S.%f")
        # ):
        #     frappe.db.set_value(
        #         self.doctype,
        #         self.name,
        #         "status",
        #         "Sell Triggered",
        #     )
        #     frappe.db.commit()
        #     mess = "Dear Customer,\nURGENT NOTICE. A sale has been triggered in your loan account {} due to inaction on your part to mitigate margin shortfall.The lender will sell required collateral and deposit the proceeds in your loan account to fulfill the shortfall. Kindly check the app for details. Spark Loans".format(
        #         self.loan
        #     )
        #     frappe.enqueue(
        #         method=send_sms,
        #         receiver_list=[self.get_customer().phone],
        #         msg=mess,
        #     )
        """

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


@frappe.whitelist()
def set_timer(loan_margin_shortfall_name):
    try:
        if not loan_margin_shortfall_name:
            all_margin_shortfall = frappe.get_all("Loan Margin Shortfall")
            for loan_margin_shortfall_name in all_margin_shortfall:
                loan_margin_shortfall = frappe.get_doc(
                    "Loan Margin Shortfall", loan_margin_shortfall_name
                )
                if loan_margin_shortfall.status in ["Pending", "Request Pending"]:
                    timer = convert_sec_to_hh_mm_ss(
                        abs(
                            loan_margin_shortfall.deadline - frappe.utils.now_datetime()
                        ).total_seconds()
                    )
                else:
                    timer = "00:00:00"

                frappe.db.set_value(
                    "Loan Margin Shortfall",
                    loan_margin_shortfall_name,
                    "time_remaining",
                    timer,
                    update_modified=False,
                )
        else:
            loan_margin_shortfall = frappe.get_doc(
                "Loan Margin Shortfall", loan_margin_shortfall_name
            )
            if loan_margin_shortfall.status in ["Pending", "Request Pending"]:
                timer = convert_sec_to_hh_mm_ss(
                    abs(
                        loan_margin_shortfall.deadline - frappe.utils.now_datetime()
                    ).total_seconds()
                )
            else:
                timer = "00:00:00"

            frappe.db.set_value(
                "Loan Margin Shortfall",
                loan_margin_shortfall_name,
                "time_remaining",
                timer,
                update_modified=False,
            )
    except Exception as e:
        # To log exception errors into Frappe Error Log
        frappe.log_error(
            frappe.get_traceback()
            + "\nMargin Shortfall Info:\n"
            + json.dumps(loan_margin_shortfall_name),
            e.args,
        )
