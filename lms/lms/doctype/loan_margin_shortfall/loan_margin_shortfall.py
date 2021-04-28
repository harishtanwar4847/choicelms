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
from lms.firebase import FirebaseAdmin
from lms.user import convert_sec_to_hh_mm_ss


class LoanMarginShortfall(Document):
    def before_save(self):
        self.fill_items()

    def fill_items(self):
        loan = frappe.get_doc("Loan", self.loan)

        self.total_collateral_value = loan.total_collateral_value
        self.allowable_ltv = loan.allowable_ltv
        self.drawing_power = loan.drawing_power

        self.loan_balance = loan.balance
        self.ltv = (self.loan_balance / self.total_collateral_value) * 100
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
            self.notify_customer()
            # self.set_deadline()
            self.new_fcm_timer_start_stop()
            # self.set_bank_holiday_check()
            # self.timer_start_stop_fcm()

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
        if margin_shortfall_action:
            customer = self.get_loan().get_customer()
            mess = _("Your Loan {0} has been marked for margin shortfall. Please take action").format(
                self.loan
            )

            if margin_shortfall_action.sms:
                frappe.enqueue(
                    method=send_sms, receiver_list=[customer.phone], msg=mess
                )

            if margin_shortfall_action.email:
                frappe.enqueue(
                    method=frappe.sendmail,
                    recipients=[customer.user],
                    sender=None,
                    subject="Margin Shortfall Notification",
                    message=mess,
                )

    def set_deadline(self, old_shortfall_action=None):
        margin_shortfall_action = self.get_shortfall_action()
        print(old_shortfall_action,"old_shortfall_action")
        print(margin_shortfall_action.name,"margin_shortfall_action")
        if margin_shortfall_action:
            if (
                margin_shortfall_action.sell_off_after_hours
                and not margin_shortfall_action.sell_off_deadline_eod
            ):
                # sell off after 72 hours
                if old_shortfall_action != margin_shortfall_action.name:
                    self.deadline = (frappe.utils.now_datetime() + timedelta(hours = margin_shortfall_action.sell_off_after_hours))

            elif not margin_shortfall_action.sell_off_after_hours and margin_shortfall_action.sell_off_deadline_eod:
                # sell off at EOD
                if old_shortfall_action != margin_shortfall_action.name:
                    self.deadline = frappe.utils.now_datetime().replace(hour=margin_shortfall_action.sell_off_deadline_eod,minute=0,second=0,microsecond=0)
                
            elif not margin_shortfall_action.sell_off_after_hours and not margin_shortfall_action.sell_off_deadline_eod:
                # sell off immediately
                if old_shortfall_action != margin_shortfall_action.name:
                    self.deadline = frappe.utils.now_datetime()
            self.save(ignore_permissions=True)
            frappe.db.commit()
        self.set_bank_holiday_check()

    def set_bank_holiday_check(self):
        date_list = []
        tomorrow = date.today() + timedelta(days=1)
        if tomorrow <= (self.deadline).date():
            holiday_list = frappe.get_all("Bank Holiday", "date")
            for i,dates in enumerate(d['date'] for d in holiday_list): 
                date_list.append(dates)
            
            # date_array = (self.creation.date() + timedelta(days=x) for x in range(0, (self.deadline.date()-self.creation.date()).days+1))
            # check_if_holiday = [i for i, j in zip(date_list, date_array) if i == j]
            # if check_if_holiday:
            if tomorrow in date_list:
                self.is_bank_holiday = 1
                # self.deadline = self.deadline + timedelta(hours=24)
            else:
                self.is_bank_holiday = 0
            # self.save(ignore_permissions=True)
            frappe.db.commit()

    def timer_start_stop_fcm(self):
        if self.is_bank_holiday == 1:
            try:
                fa = FirebaseAdmin()
                fa.send_data(
                    data={
                        "timer_start_event": {
                            "condition": "if bank holiday",
                            "time": convert_sec_to_hh_mm_ss(abs(self.deadline - frappe.utils.now_datetime().replace(hour=23, minute=59, second=59, microsecond=999999)).total_seconds()),
                            "loan_name": self.get_loan().name
                    }},
                    tokens=lms.get_firebase_tokens(self.get_loan().get_customer().user),
                )
            except Exception:
                pass
            finally:
                fa.delete_app()
        else:
            try:
                fa = FirebaseAdmin()
                fa.send_data(
                    data={
                        "timer_stop_event": {
                            "condition": "if bank holiday",
                            "time": convert_sec_to_hh_mm_ss(abs(self.deadline - frappe.utils.now_datetime().replace(hour=23, minute=59, second=59, microsecond=999999)).total_seconds()),
                            "loan_name": self.get_loan().name
                    }},
                    tokens=lms.get_firebase_tokens(self.get_loan().get_customer().user),
                )
            except Exception:
                pass
            finally:
                fa.delete_app()

    def on_update(self):
        if self.status == "Pending":
            # self.set_deadline()
            # self.set_bank_holiday_check()
            self.timer_start_stop_fcm()
            # self.save(ignore_permissions=True)
            frappe.db.commit()

    def new_fcm_timer_start_stop(self):
        # if self.deadline > frappe.utils.now_datetime():
        try:
            fa = FirebaseAdmin()
            fa.send_data(
                data={
                    "timer_start_event": {
                    "condition": "after insert",
                    "time": convert_sec_to_hh_mm_ss(abs(self.deadline - frappe.utils.now_datetime()).total_seconds()),
                    "loan_name": self.get_loan().name
                },
                "timer_stop_event": {
                    "condition": "after insert",
                    "time": "00:00:00",
                    "loan_name": self.get_loan().name
                }
                },
                tokens=lms.get_firebase_tokens(self.get_loan().get_customer().user),
            )
        except Exception:
            pass
        finally:
            fa.delete_app()
    
