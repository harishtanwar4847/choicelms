# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import json
from datetime import datetime, timedelta

import frappe
import requests
import utils
from frappe import _
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from frappe.model.document import Document
from num2words import num2words

import lms
from lms.exceptions import PledgeSetupFailureException
from lms.firebase import FirebaseAdmin
from lms.lms.doctype.collateral_ledger.collateral_ledger import CollateralLedger


class LoanApplication(Document):
    def get_lender(self):
        return frappe.get_doc("Lender", self.lender)

    def get_customer(self):
        return frappe.get_doc("Loan Customer", self.customer)

    def get_loan(self):
        return frappe.get_doc("Loan", self.loan)

    def esign_request(self, increase_loan):
        customer = self.get_customer()
        user = frappe.get_doc("User", customer.user)
        user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
        lender = self.get_lender()
        if self.loan:
            loan = self.get_loan()
            increased_sanctioned_limit = lms.round_down_amount_to_nearest_thousand(
                (self.total_collateral_value + loan.total_collateral_value)
                * self.allowable_ltv
                / 100
            )
            new_increased_sanctioned_limit = (
                increased_sanctioned_limit
                if increased_sanctioned_limit < lender.maximum_sanctioned_limit
                else lender.maximum_sanctioned_limit
            )
            frappe.db.set_value(
                self.doctype,
                self.name,
                "increased_sanctioned_limit",
                new_increased_sanctioned_limit,
                update_modified=False,
            )

        doc = {
            "esign_date": frappe.utils.now_datetime().strftime("%d-%m-%Y"),
            "loan_application_number": self.name,
            "borrower_name": user_kyc.investor_name,
            "borrower_address": user_kyc.address,
            "sanctioned_amount": lms.validate_rupees(
                new_increased_sanctioned_limit
                if self.loan and not self.loan_margin_shortfall
                else self.drawing_power
            ),
            "sanctioned_amount_in_words": lms.number_to_word(
                lms.validate_rupees(
                    new_increased_sanctioned_limit
                    if self.loan and not self.loan_margin_shortfall
                    else self.drawing_power,
                )
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
            # "stamp_duty_charges": int(lender.lender_stamp_duty_minimum_amount),
            "transaction_charges_per_request": lms.validate_rupees(
                lender.transaction_charges_per_request
            ),
            "security_selling_share": lender.security_selling_share,
            "cic_charges": lms.validate_rupees(lender.cic_charges),
            "total_pages": lender.total_pages,
        }

        if increase_loan:
            doc["old_sanctioned_amount"] = lms.validate_rupees(loan.sanctioned_limit)
            doc["old_sanctioned_amount_in_words"] = lms.number_to_word(
                lms.validate_rupees(loan.sanctioned_limit)
            ).title()
            agreement_template = lender.get_loan_enhancement_agreement_template()
            loan_agreement_file = "loan-enhancement-aggrement.pdf"
            coordinates = lender.enhancement_coordinates.split(",")
            esign_page = lender.enhancement_esign_page
        else:
            agreement_template = lender.get_loan_agreement_template()
            loan_agreement_file = "loan-aggrement.pdf"
            coordinates = lender.coordinates.split(",")
            esign_page = lender.esign_page

        agreement = frappe.render_template(
            agreement_template.get_content(), {"doc": doc}
        )

        from frappe.utils.pdf import get_pdf

        agreement_pdf = get_pdf(agreement)

        las_settings = frappe.get_single("LAS Settings")
        headers = {"userId": las_settings.choice_user_id}
        files = {"file": (loan_agreement_file, agreement_pdf)}

        return {
            "file_upload_url": "{}{}".format(
                las_settings.esign_host, las_settings.esign_upload_file_uri
            ),
            "headers": headers,
            "files": files,
            "esign_url_dict": {
                "x": coordinates[0],
                "y": coordinates[1],
                "page_number": esign_page,
            },
            "esign_url": "{}{}".format(
                las_settings.esign_host, las_settings.esign_request_uri
            ),
        }

    def before_save(self):
        lender = self.get_lender()
        self.minimum_sanctioned_limit = lender.minimum_sanctioned_limit
        self.maximum_sanctioned_limit = lender.maximum_sanctioned_limit
        values1 = {"value": "{} Inside before save outside if line 177".format(lender)}
        lms.create_log(values1, "status_pledge_accepted_by_lender")
        frappe.logger().info(values1)
        if (
            self.status == "Approved"
            and not self.lender_esigned_document
            and not self.loan_margin_shortfall
            and not self.application_type == "Pledge More"
        ):
            values2 = {
                "value": (
                    self.status,
                    self.lender_esigned_document,
                    self.loan_margin_shortfall,
                    self.application_type,
                    "inside if line 185",
                )
            }
            lms.create_log(values2, "status_pledge_accepted_by_lender ")
            frappe.logger().info(values2)
            frappe.throw("Please upload Lender Esigned Document")
        elif self.status == "Approved":
            values3 = {"value": (self.status, "inside elif2 before save line 189")}
            lms.create_log(values3, "status_pledge_accepted_by_lender ")
            frappe.logger().info(values3)
            current = frappe.utils.now_datetime()
            expiry = frappe.utils.add_years(current, 1) - timedelta(days=1)
            self.expiry_date = datetime.strftime(expiry, "%Y-%m-%d")
        elif self.status == "Pledge accepted by Lender":
            values4 = {"value": (self.status, "inside elif2 before save line 195")}
            lms.create_log(values4, "status_pledge_accepted_by_lender")
            frappe.logger().info(values4)

            if self.pledge_status == "Failure":
                values5 = {
                    "value": (
                        self.pledge_status,
                        "inside elif's if before save line 199",
                    )
                }
                lms.create_log(values5, "status_pledge_accepted_by_lender")
                frappe.logger().info(values5)
                frappe.throw("Sorry! Pledge for this Loan Application is failed.")

            total_approved = 0
            total_collateral_value = 0

            values6 = {"value": ("outside for before save line 206")}
            lms.create_log(values6, "status_pledge_accepted_by_lender")
            frappe.logger().info(values6)

            for i in self.items:
                values7 = {"value": (i, "inside for before save line210")}
                lms.create_log(values7, "status_pledge_accepted_by_lender")
                frappe.logger().info(values7)

                if i.get("pledge_status") == "Failure" and i.lender_approval_status in [
                    "Approved",
                    "Rejected",
                ]:
                    values8 = {
                        "value": (
                            i.get("pledge_status"),
                            (i.lender_approval_status),
                            "inside for's if before save line217",
                        )
                    }
                    lms.create_log(values8, "status_pledge_accepted_by_lender")
                    frappe.logger().info(values8)
                    frappe.throw(
                        "Pledge failed for ISIN - {}, can't Approve or Reject".format(
                            i.isin
                        )
                    )

                elif i.get("pledge_status") == "Success":
                    values9 = {
                        "value": (
                            i.get("pledge_status"),
                            "inside for's elif before save line226",
                        )
                    }
                    lms.create_log(values9, "status_pledge_accepted_by_lender")
                    frappe.logger().info(values9)

                    if i.lender_approval_status == "Pledge Failure":
                        values10 = {
                            "value": (
                                (i.lender_approval_status),
                                "inside for's elif's if before save line230",
                            )
                        }
                        lms.create_log(values10, "status_pledge_accepted_by_lender")
                        frappe.logger().info(values10)

                        frappe.throw(
                            "Already pledge success for {}, not allowed to set Pledge Failure.".format(
                                i.isin
                            )
                        )

                    elif i.lender_approval_status == "":
                        values11 = {
                            "value": (
                                (i.lender_approval_status),
                                "inside for's elif if before save line240",
                            )
                        }
                        frappe.logger().info(values11)
                        lms.create_log(values11, "status_pledge_accepted_by_lender")
                        frappe.throw("Please Approve/Reject {}".format(i.isin))

                    if i.lender_approval_status == "Approved":
                        values31 = {
                            "value": (
                                (i.lender_approval_status),
                                "inside for's elif's if before save line245",
                            )
                        }
                        lms.create_log(values31, "status_pledge_accepted_by_lender")
                        frappe.logger().info(values31)
                        total_approved += 1
                        total_collateral_value += i.amount

            if total_approved == 0:
                values12 = {
                    "value": ((total_approved), "inside if before save line251")
                }
                lms.create_log(values12, "status_pledge_accepted_by_lender")
                frappe.logger().info(values12)
                frappe.throw(
                    "Please Approve atleast one item or Reject the Loan Application"
                )

            # TODO : manage loan application and its item's as per lender approval
            self.total_collateral_value = round(total_collateral_value, 2)
            drawing_power = round(
                lms.round_down_amount_to_nearest_thousand(
                    (self.allowable_ltv / 100) * self.total_collateral_value
                ),
                2,
            )
            self.drawing_power = (
                drawing_power
                if drawing_power < self.maximum_sanctioned_limit
                else self.maximum_sanctioned_limit
            )

            # TODO : if increase loan drawing power is less than 10k the loan application wont be proceed
            loan_total_collateral_value = 0
            if self.loan:
                loan_total_collateral_value = frappe.get_doc(
                    "Loan", self.loan
                ).total_collateral_value

            # Use increased sanctioned limit field for this validation
            drawing_power = round(
                lms.round_down_amount_to_nearest_thousand(
                    (self.total_collateral_value + loan_total_collateral_value)
                    * (self.allowable_ltv / 100)
                ),
                2,
            )

            if self.application_type in ["New Loan", "Increase Loan"]:
                values13 = {
                    "value": ((self.application_type), "inside if before save line288")
                }
                lms.create_log(values13, "status_pledge_accepted_by_lender")
                frappe.logger().info(values13)

                if drawing_power < self.minimum_sanctioned_limit:
                    values14 = {
                        "value": (
                            drawing_power,
                            self.minimum_sanctioned_limit,
                            "inside if before save line292",
                        )
                    }
                    lms.create_log(values14, "status_pledge_accepted_by_lender")
                    frappe.logger().info(values14)
                    frappe.throw(
                        "Sorry! This Loan Application can not be Approved as its Drawing power is less than Minimum Sanctioned Limit."
                    )

        if self.status == "Pledge executed":
            total_collateral_value = 0
            values15 = {"value": (self.status, "inside if before save line300")}
            lms.create_log(values15, "status_pledge_accepted_by_lender")
            frappe.logger().info(values15)
            for i in self.items:
                values16 = {"value": (i, "inside if before save line303")}
                lms.create_log(values16, "status_pledge_accepted_by_lender")
                frappe.logger().info(values16)

                if i.pledge_status == "Success" or i.pledge_status == "":
                    values17 = {
                        "value": (
                            i.pledge_status,
                            "inside second for's if before save line307",
                        )
                    }
                    lms.create_log(values17, "status_pledge_accepted_by_lender")
                    frappe.logger().info(values17)
                    if (
                        i.lender_approval_status == "Approved"
                        or i.lender_approval_status == ""
                    ):
                        values18 = {
                            "value": (
                                i.lender_approval_status,
                                "inside 2nd for's if before save line313",
                            )
                        }
                        lms.create_log(values18, "status_pledge_accepted_by_lender")
                        frappe.logger().info(values18)
                        total_collateral_value += i.amount
                        self.total_collateral_value = round(total_collateral_value, 2)
                        drawing_power = round(
                            lms.round_down_amount_to_nearest_thousand(
                                (self.allowable_ltv / 100) * self.total_collateral_value
                            ),
                            2,
                        )
                        self.drawing_power = (
                            drawing_power
                            if drawing_power < self.maximum_sanctioned_limit
                            else self.maximum_sanctioned_limit
                        )
                        values19 = {
                            "value": (
                                total_collateral_value,
                                self.total_collateral_value,
                                self.drawing_power,
                                "inside 2nd for's if before save line328",
                            )
                        }
                        lms.create_log(values19, "status_pledge_accepted_by_lender")
                        frappe.logger().info(values19)

                    # elif (
                    #     i.lender_approval_status == "Rejected"
                    #     or i.lender_approval_status == "Pledge Failure"
                    # ):
                    #     if (
                    #         total_collateral_value > 0
                    #         and total_collateral_value >= i.amount
                    #     ):
                    #         total_collateral_value -= i.amount
                    #     self.total_collateral_value = round(total_collateral_value, 2)
                    #     self.drawing_power = round(
                    #         lms.round_down_amount_to_nearest_thousand(
                    #             (self.allowable_ltv / 100) * self.total_collateral_value
                    #         ),
                    #         2,
                    #     )

        # On loan application rejection mark lender approvel status as rejected in loan application items
        if self.status == "Rejected":
            values20 = {"value": (self.status, "inside if before save line350")}
            lms.create_log(values20, "status_pledge_accepted_by_lender")
            frappe.logger().info(values20)
            for i in self.items:
                values21 = {"value": (i, "inside if before save")}
                lms.create_log(values21, "status_pledge_accepted_by_lender line354")
                frappe.logger().info(values21)
                i.lender_approval_status = "Rejected"

        self.total_collateral_value_str = lms.amount_formatter(
            self.total_collateral_value
        )
        self.drawing_power_str = lms.amount_formatter(self.drawing_power)
        self.pledged_total_collateral_value_str = lms.amount_formatter(
            self.pledged_total_collateral_value
        )

    def on_update(self):
        print("print")
        if self.status == "Approved":
            if not self.loan:
                values21 = {"value": (self.status, "inside if on update line368")}
                lms.create_log(values21, "status_pledge_accepted_by_lender")
                frappe.logger().info(values21)
                loan = self.create_loan()
            else:
                values21 = {"value": (self.status, "inside else on update line372")}
                lms.create_log(values21, "status_pledge_accepted_by_lender")
                frappe.logger().info(values21)
                loan = self.update_existing_loan()
            frappe.db.commit()

            if not self.loan:
                # new loan agreement mapping
                values22 = {"value": (self.loan, "inside 2nd if  on update line379")}
                lms.create_log(values22, "status_pledge_accepted_by_lender")
                frappe.logger().info(values22)
                self.map_loan_agreement_file(loan)
            elif (
                self.loan
                and self.lender_esigned_document
                and not self.loan_margin_shortfall
            ):
                values23 = {
                    "value": (
                        self.loan,
                        self.lender_esigned_document,
                        self.loan_margin_shortfall,
                        "inside elif on update line387",
                    )
                }
                lms.create_log(values23, "status_pledge_accepted_by_lender")
                frappe.logger().info(values23)
                # increase loan agreement mapping
                self.map_loan_agreement_file(loan, increase_loan=True)

            if self.loan_margin_shortfall:
                # if shortfall is not recoverd then margin shortfall status will change from request pending to pending
                values24 = {
                    "value": (
                        self.loan_margin_shortfall,
                        "inside if 3rd on update line394",
                    )
                }
                lms.create_log(values24, "status_pledge_accepted_by_lender")
                frappe.logger().info(values24)

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

                values25 = {
                    "value": (
                        loan_margin_shortfall,
                        under_process_la,
                        pending_loan_transaction,
                        pending_sell_collateral_application,
                        "inside if 3rd on update line433",
                    )
                }
                lms.create_log(values25, "status_pledge_accepted_by_lender")
                frappe.logger().info(values25)
                if (
                    (
                        not pending_loan_transaction
                        and not pending_sell_collateral_application
                        and not under_process_la
                    )
                    and loan_margin_shortfall.status == "Request Pending"
                    and loan_margin_shortfall.shortfall_percentage > 0
                ):
                    values26 = {
                        "value": (
                            loan_margin_shortfall,
                            under_process_la,
                            pending_loan_transaction,
                            pending_sell_collateral_application,
                            "inside if 3rd on update line444",
                        )
                    }
                    lms.create_log(values26, "status_pledge_accepted_by_lender")
                    frappe.logger().info(values26)

                    loan_margin_shortfall.status = "Pending"
                    loan_margin_shortfall.save(ignore_permissions=True)
                    frappe.db.commit()

        elif self.status == "Pledge accepted by Lender":
            approved_isin_list = []
            rejected_isin_list = []
            values27 = {"value": (self.status, "inside elif 3rd on update line454")}
            lms.create_log(values27, "status_pledge_accepted_by_lender")
            frappe.logger().info(values27)
            for i in self.items:
                values27 = {"value": (i, "inside if 3rd on update line457")}
                lms.create_log(values27, "status_pledge_accepted_by_lender")
                frappe.logger().info(values27)
                if i.lender_approval_status == "Approved":
                    values28 = {
                        "value": (
                            i.lender_approval_status,
                            "inside for's if 3rd on update line460",
                        )
                    }
                    lms.create_log(values28, "status_pledge_accepted_by_lender")
                    frappe.logger().info(values28)
                    approved_isin_list.append(i.isin)
                elif i.lender_approval_status == "Rejected":
                    values28 = {
                        "value": (
                            i.lender_approval_status,
                            "inside elif 3rd on update line464",
                        )
                    }
                    lms.create_log(values28, "status_pledge_accepted_by_lender")
                    frappe.logger().info(values28)
                    rejected_isin_list.append(i.isin)

            if len(approved_isin_list) > 0:
                values29 = {
                    "value": (approved_isin_list, "inside len if 3rd on update line469")
                }
                lms.create_log(values29, "status_pledge_accepted_by_lender")
                frappe.logger().info(values29)
                self.update_collateral_ledger(
                    {"lender_approval_status": "Approved"},
                    "application_doctype = 'Loan Application' and application_name = '{}' and isin IN {}".format(
                        self.name, lms.convert_list_to_tuple_string(approved_isin_list)
                    ),
                )

            if len(rejected_isin_list) > 0:
                values29 = {
                    "value": (
                        rejected_isin_list,
                        "inside len len if 3rd on update line479",
                    )
                }
                lms.create_log(values29, "status_pledge_accepted_by_lender")
                frappe.logger().info(values29)
                self.update_collateral_ledger(
                    {"lender_approval_status": "Rejected"},
                    "application_doctype = 'Loan Application' and application_name = '{}' and isin IN {}".format(
                        self.name, lms.convert_list_to_tuple_string(rejected_isin_list)
                    ),
                )
            try:
                fa = FirebaseAdmin()
                fa.send_data(
                    data={
                        "event": "Esign Pending",
                    },
                    tokens=lms.get_firebase_tokens(self.get_customer().user),
                )
                values30 = {"value": (fa, "inside len len if 3rd on update line495")}
                lms.create_log(values30, "status_pledge_accepted_by_lender")
                frappe.logger().info(values30)
            except Exception:
                pass
            finally:
                fa.delete_app()

        elif self.status == "Rejected":
            if self.loan_margin_shortfall:
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
                values30 = {
                    "value": (
                        loan_margin_shortfall,
                        pending_sell_collateral_application,
                        pending_loan_transaction,
                        "inside len len if 3rd on update line540",
                    )
                }
                lms.create_log(values30, "status_pledge_accepted_by_lender")
                frappe.logger().info(values30)
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

            if not self.loan and not self.loan_margin_shortfall:
                values30 = {"value": ("True inside len len if 3rd on update line556")}
                lms.create_log(values30, "status_pledge_accepted_by_lender")
                customer = self.get_customer()
                if customer.pledge_securities:
                    customer.pledge_securities = 0
                    customer.save(ignore_permissions=True)
                    frappe.db.commit()
                    values30 = {
                        "value": (
                            customer.pledge_securities,
                            "inside len len if 3rd on update line495",
                        )
                    }
                    lms.create_log(values30, "status_pledge_accepted_by_lender")

            # On loan application rejection mark lender approvel status as rejected in collateral ledger as well 23-09-2021 Poonam
            loan_application_isin_list = [i.isin for i in self.items]
            values30 = {
                "value": (
                    loan_application_isin_list,
                    "inside len len if 3rd on update line495",
                )
            }
            lms.create_log(values30, "status_pledge_accepted_by_lender")
            frappe.logger().info(values30)

            self.update_collateral_ledger(
                {"lender_approval_status": "Rejected"},
                "application_doctype = 'Loan Application' and application_name = '{}' and isin IN {}".format(
                    self.name,
                    lms.convert_list_to_tuple_string(loan_application_isin_list),
                ),
            )
        self.notify_customer()

    def create_loan(self):
        items = []

        for item in self.items:
            if item.lender_approval_status == "Approved":
                temp = frappe.get_doc(
                    {
                        "doctype": "Loan Item",
                        "isin": item.isin,
                        "security_name": item.security_name,
                        "security_category": item.security_category,
                        "pledged_quantity": item.pledged_quantity,
                        "price": item.price,
                        "amount": item.amount,
                    }
                )

                items.append(temp)

        loan = frappe.get_doc(
            {
                "doctype": "Loan",
                "total_collateral_value": self.total_collateral_value,
                "drawing_power": self.drawing_power,
                "sanctioned_limit": self.drawing_power,
                "expiry_date": self.expiry_date,
                "allowable_ltv": self.allowable_ltv,
                "customer": self.customer,
                "customer_name": self.customer_name,
                "lender": self.lender,
                "items": items,
                "is_eligible_for_interest": 1,
            }
        )
        loan.insert(ignore_permissions=True)
        loan.create_loan_charges()
        # self.map_loan_agreement_file(loan)

        # File code here #S

        customer = frappe.get_doc("Loan Customer", self.customer)
        if not customer.loan_open:
            customer.loan_open = 1
            customer.save(ignore_permissions=True)

        self.update_collateral_ledger(
            {"loan": loan.name},
            "application_doctype = 'Loan Application' and application_name = '{}'".format(
                self.name,
            ),
        )

        loan.reload()
        loan.update_items()
        loan.fill_items()
        loan.save(ignore_permissions=True)

        # customer = frappe.db.get_value("Loan Customer", {"name": self.customer}, "user")
        """changes as per latest email notification list-sent by vinayak - email verification final 2.0"""
        # doc = frappe.get_doc("User KYC", self.get_customer().choice_kyc)
        # frappe.enqueue_doc("Notification", "Loan Sanction", method="send", doc=doc)

        # mobile = frappe.db.get_value("Loan Customer", {"name": self.customer}, "phone")
        # mess = _(
        #     "Dear "
        #     + doc.investor_name
        #     + ", Congratulations! Your loan account is active now! Current available limit - "
        #     + str(loan.drawing_power)
        #     + "."
        # )
        # mess = _(
        #     "Congratulations! Your loan account is active now! Current available limit - "
        #     + str(loan.drawing_power)
        #     + "."
        # )
        # frappe.enqueue(method=send_sms, receiver_list=[doc.mobile_number], msg=mess)

        return loan

    def map_loan_agreement_file(self, loan, increase_loan=False):
        file_name = frappe.db.get_value(
            "File", {"file_url": self.lender_esigned_document}
        )

        loan_agreement = frappe.get_doc("File", file_name)

        event = "New loan"
        if increase_loan:
            loan_agreement_file_name = "{}-loan-enhancement-aggrement.pdf".format(
                loan.name
            )
            event = "Increase loan"
        else:
            loan_agreement_file_name = "{}-loan-aggrement.pdf".format(loan.name)

        is_private = 0
        loan_agreement_file_url = frappe.utils.get_files_path(
            loan_agreement_file_name, is_private=is_private
        )

        frappe.db.begin()
        loan_agreement_file = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": loan_agreement_file_name,
                "content": loan_agreement.get_content(),
                "attached_to_doctype": "Loan",
                "attached_to_name": loan.name,
                "attached_to_field": "loan_agreement",
                "folder": "Home",
                # "file_url": loan_agreement_file_url,
                "is_private": is_private,
            }
        )
        loan_agreement_file.insert(ignore_permissions=True)
        frappe.db.commit()

        frappe.db.set_value(
            "Loan",
            loan.name,
            "loan_agreement",
            loan_agreement_file.file_url,
            update_modified=False,
        )
        # save loan sanction history
        loan.save_loan_sanction_history(loan_agreement_file.name, event)

    def update_existing_loan(self):
        self.update_collateral_ledger(
            {"loan": self.loan},
            "application_doctype = 'Loan Application' and application_name = '{}'".format(
                self.name
            ),
        )

        loan = frappe.get_doc("Loan", self.loan)
        loan.update_items()
        loan.fill_items()

        loan.drawing_power = (loan.allowable_ltv / 100) * loan.total_collateral_value
        loan.save(ignore_permissions=True)

        if self.application_type == "Increase Loan":
            # apply processing fees on new sanctioned limit(loan application drawing power)
            # apply renewal charges on existing loan sanctioned limit
            self.apply_renewal_charges(loan)
            loan.reload()
            # TODO : manage expiry date
            loan.expiry_date = self.expiry_date

            loan.sanctioned_limit = (
                self.maximum_sanctioned_limit
                if self.increased_sanctioned_limit > self.maximum_sanctioned_limit
                else self.increased_sanctioned_limit
            )
            if loan.drawing_power > loan.sanctioned_limit:
                loan.drawing_power = loan.sanctioned_limit
            # loan.sanctioned_limit = loan.drawing_power
            loan.save(ignore_permissions=True)
            loan_margin_shortfall = loan.get_margin_shortfall()
            if not loan_margin_shortfall.is_new() and loan_margin_shortfall.status in [
                "Pending",
                "Request Pending",
            ]:
                loan_margin_shortfall.fill_items()
                if loan_margin_shortfall.shortfall_percentage == 0:
                    loan_margin_shortfall.status = "Resolved"
                loan_margin_shortfall.save(ignore_permissions=True)

        if self.application_type in ["Margin Shortfall", "Pledge More"]:
            if loan.drawing_power > loan.sanctioned_limit:
                loan.drawing_power = loan.sanctioned_limit

            loan.save(ignore_permissions=True)
            if self.loan_margin_shortfall:
                loan_margin_shortfall = frappe.get_doc(
                    "Loan Margin Shortfall", self.loan_margin_shortfall
                )
                loan_margin_shortfall.fill_items()
                # if not loan_margin_shortfall.margin_shortfall_action:
                if loan_margin_shortfall.shortfall_percentage == 0:
                    loan_margin_shortfall.status = "Pledged Securities"
                    loan_margin_shortfall.action_time = frappe.utils.now_datetime()
                loan_margin_shortfall.save(ignore_permissions=True)

        return loan

    def apply_renewal_charges(self, loan):
        lender = loan.get_lender()

        # renewal charges
        import calendar

        # new sanctioned_limit > old sanctioned_limit
        # -> apply processing fee on (new - old)
        # -> apply renewal on loan sanctioned
        # new sanctioned_limit < old sanctioned_limit
        # -> no processing fee
        # -> renewal on new sanctioned
        # new sanctioned_limit = old sanctioned_limit
        # -> no processing fee
        # -> renewal on new sanctioned
        # new sanctioned limit = lms.round_down_amount_to_nearest_thousand((new total coll + old total coll) / 2)
        new_sanctioned_limit = self.increased_sanctioned_limit

        renewal_sanctioned_limit, processing_sanctioned_limit = (
            (loan.sanctioned_limit, (new_sanctioned_limit - loan.sanctioned_limit))
            if new_sanctioned_limit > loan.sanctioned_limit
            else (new_sanctioned_limit, 0)
        )

        date = frappe.utils.now_datetime()
        days_in_year = 366 if calendar.isleap(date.year) else 365
        renewal_charges = lender.renewal_charges
        if lender.renewal_charge_type == "Percentage":
            la_expiry_date = (
                (datetime.strptime(self.expiry_date, "%Y-%m-%d")).date()
                if type(self.expiry_date) == str
                else self.expiry_date
            )
            loan_expiry_date = loan.expiry_date + timedelta(days=1)
            days_left_to_expiry = (la_expiry_date - loan_expiry_date).days + 1

            amount = (
                (renewal_charges / 100)
                * renewal_sanctioned_limit
                / days_in_year
                * days_left_to_expiry
            )
            renewal_charges = loan.validate_loan_charges_amount(
                lender, amount, "renewal_minimum_amount", "renewal_maximum_amount"
            )

        if renewal_charges > 0:
            loan.create_loan_transaction(
                "Renewal Charges", renewal_charges, approve=True
            )

        # Processing fees
        processing_fees = lender.lender_processing_fees
        if lender.lender_processing_fees_type == "Percentage":
            days_left_to_expiry = days_in_year

            amount = (
                (processing_fees / 100)
                * processing_sanctioned_limit
                / days_in_year
                * days_left_to_expiry
            )
            processing_fees = loan.validate_loan_charges_amount(
                lender,
                amount,
                "lender_processing_minimum_amount",
                "lender_processing_maximum_amount",
            )

        if processing_fees > 0 and processing_sanctioned_limit > 0:
            loan.create_loan_transaction(
                "Processing Fees",
                processing_fees,
                approve=True,
            )

        # Stamp Duty
        stamp_duty = lender.stamp_duty
        if lender.stamp_duty_type == "Percentage":
            amount = (stamp_duty / 100) * self.drawing_power
            stamp_duty = loan.validate_loan_charges_amount(
                lender,
                amount,
                "lender_stamp_duty_minimum_amount",
                "lender_stamp_duty_maximum_amount",
            )

        if stamp_duty > 0:
            loan.create_loan_transaction(
                "Stamp Duty",
                stamp_duty,
                approve=True,
            )

        # Documentation Charges
        documentation_charges = lender.documentation_charges
        if lender.documentation_charge_type == "Percentage":
            amount = (documentation_charges / 100) * self.drawing_power
            documentation_charges = loan.validate_loan_charges_amount(
                lender,
                amount,
                "lender_documentation_minimum_amount",
                "lender_documentation_maximum_amount",
            )

        if documentation_charges > 0:
            loan.create_loan_transaction(
                "Documentation Charges",
                documentation_charges,
                approve=True,
            )

        # Mortgage Charges
        mortgage_charges = lender.mortgage_charges
        if lender.mortgage_charge_type == "Percentage":
            amount = (mortgage_charges / 100) * self.drawing_power
            mortgage_charges = loan.validate_loan_charges_amount(
                lender,
                amount,
                "lender_mortgage_minimum_amount",
                "lender_mortgage_maximum_amount",
            )

        if mortgage_charges > 0:
            loan.create_loan_transaction(
                "Mortgage Charges",
                mortgage_charges,
                approve=True,
            )

    def update_collateral_ledger(self, set_values={}, where=""):
        set_values_str = ""
        last_col = sorted(set_values.keys())[-1]
        if len(set_values.keys()) == len(set_values.values()):
            for col, val in set_values.items():
                set_values_str += "{} = '{}'".format(col, val)
                if len(set_values.keys()) > 0 and col != last_col:
                    set_values_str += ", "

        sql = """update `tabCollateral Ledger` set {} """.format(set_values_str)

        if len(where) > 0:
            sql += " where {}".format(where)

        frappe.db.sql(sql)

    # hit pledge request as per batch items
    def pledge_request(self, security_list):
        las_settings = frappe.get_single("LAS Settings")
        API_URL = "{}{}".format(las_settings.cdsl_host, las_settings.pledge_setup_uri)

        prf_number = lms.random_token(length=12)
        securities_array = []
        for i in self.items:
            if i.isin in security_list:
                # set prf_number to LA item
                i.prf_number = prf_number
                j = {
                    "ISIN": i.isin,
                    "Quantity": str(float(i.pledged_quantity)),
                    "Value": str(float(i.price)),
                }
                securities_array.append(j)
        self.save(ignore_permissions=True)

        payload = {
            "PledgorBOID": self.pledgor_boid,
            "PledgeeBOID": self.pledgee_boid,
            "PRFNumber": prf_number,
            "ExpiryDate": self.expiry_date.strftime("%d%m%Y"),
            "ISINDTLS": securities_array,
        }

        headers = las_settings.cdsl_headers()

        return {"url": API_URL, "headers": headers, "payload": payload}

    # dummy pledge response for pledge
    def dummy_pledge_response(self, security_list):
        import random

        error_flag = 0
        # error_flag = bool(random.getrandbits(1))
        if error_flag:
            return {
                "Success": False,
                "PledgeSetupResponse": {
                    "ErrorId": "ERR007",
                    "ErrorMessage": "Invalid Pledgor BOID.",
                },
            }
        else:
            ISINstatusDtls = []
            flag = 0
            for item in security_list:
                # flag = bool(random.getrandbits(1))
                error_code = ["CIF3065-F", "PLD0152-E", "PLD0125-F"]
                ISINstatusDtls_item = {
                    "ISIN": item.get("ISIN"),
                    "PSN": "" if flag else lms.random_token(7, is_numeric=True),
                    "ErrorCode": random.choice(error_code) if flag else "",
                }
                ISINstatusDtls.append(ISINstatusDtls_item)
            return {
                "Success": True,
                "PledgeSetupResponse": {"ISINstatusDtls": ISINstatusDtls},
            }

    # handle pledge response(process loan application items)
    def process(self, security_list, pledge_response):
        isin_details_ = pledge_response.get("PledgeSetupResponse").get("ISINstatusDtls")

        total_successful_pledge = 0
        if isin_details_:
            isin_details = {}
            for i in isin_details_:
                isin_details[i.get("ISIN")] = i

            total_collateral_value = 0
            for i in self.items:
                if i.get("isin") in security_list:
                    cur = isin_details.get(i.get("isin"))

                    i.pledge_executed = 1

                    success = len(cur.get("PSN")) > 0

                    if success:
                        # TODO : manage individual LA item pledge status
                        i.pledge_status = "Success"
                        total_collateral_value += i.amount
                        total_successful_pledge += 1
                        collateral_ledger_data = {
                            "prf": i.get("prf_number"),
                            "expiry": self.expiry_date,
                            "pledgor_boid": self.pledgor_boid,
                            "pledgee_boid": self.pledgee_boid,
                        }
                        collateral_ledger_input = {
                            "doctype": "Loan Application",
                            "docname": self.name,
                            "request_type": "Pledge",
                            "isin": i.get("isin"),
                            "quantity": i.get("pledged_quantity"),
                            "price": i.get("price"),
                            "security_name": i.get("security_name"),
                            "security_category": i.get("security_category"),
                            "data": collateral_ledger_data,
                            "psn": cur.get("PSN"),
                        }
                        CollateralLedger.create_entry(**collateral_ledger_input)
                    else:
                        i.pledge_status = "Failure"
                        i.lender_approval_status = "Pledge Failure"

            self.total_collateral_value += total_collateral_value
        else:
            ErrorId = pledge_response.get("PledgeSetupResponse").get("ErrorId")
            for i in self.items:
                if i.get("isin") in security_list:
                    i.error_code = ErrorId
                    i.pledge_executed = 1
                    i.pledge_status = "Failure"
                    i.lender_approval_status = "Pledge Failure"

        self.save(ignore_permissions=True)
        return total_successful_pledge

    def notify_customer(self):
        from frappe.core.doctype.sms_settings.sms_settings import send_sms

        doc = frappe.get_doc("User KYC", self.get_customer().choice_kyc).as_dict()
        doc["loan_application"] = {
            "status": self.status,
            "pledge_status": self.pledge_status,
            "current_total_collateral_value": self.total_collateral_value_str,
            "requested_total_collateral_value": self.pledged_total_collateral_value_str,
            "drawing_power": self.drawing_power_str,
        }
        doc["margin_shortfall"] = self.loan_margin_shortfall
        if self.status in [
            "Pledge Failure",
            "Pledge accepted by Lender",
            "Approved",
            "Rejected",
        ]:
            if self.loan and not self.loan_margin_shortfall:
                frappe.enqueue_doc(
                    "Notification", "Increase Loan Application", method="send", doc=doc
                )
            else:
                frappe.enqueue_doc(
                    "Notification", "Loan Application", method="send", doc=doc
                )

        msg = ""
        loan = ""
        fcm_notification = {}
        fcm_message = ""
        if doc.get("loan_application").get("status") == "Pledge Failure":
            msg, fcm_title = (
                (
                    "Dear Customer,\nSorry! Your Increase loan application was turned down since the pledge was not successful due to technical reasons. We regret the inconvenience caused. Please try again after sometime or reach out to us through 'Contact Us' on the app -Spark Loans",
                    "Increase loan application rejected",
                )
                if self.loan and not self.loan_margin_shortfall
                else (
                    "Dear Customer,\nSorry! Your loan application was turned down since the pledge was not successful due to technical reasons. We regret the inconvenience caused. Please try again after sometime or reach out to us through 'Contact Us' on the app  -Spark Loans",
                    "Pledge rejected",
                )
            )
            fcm_notification = frappe.get_doc(
                "Spark Push Notification", fcm_title, fields=["*"]
            )

        elif (
            doc.get("loan_application").get("status") == "Pledge accepted by Lender"
            and not self.loan_margin_shortfall
        ):
            msg, fcm_title = (
                (
                    'Dear Customer,\nCongratulations! Your Increase loan application has been accepted. Kindly check the app for details under e-sign banner on the dashboard. Please e-sign the loan agreement to avail the loan now. For any help on e-sign please view our tutorial videos or reach out to us under "Contact Us" on the app -Spark Loans',
                    "Increase loan application accepted",
                )
                if self.loan and not self.loan_margin_shortfall
                else (
                    'Dear Customer,\nCongratulations! Your loan application has been accepted. Kindly check the app for details under e-sign banner on the dashboard. Please e-sign the loan agreement to avail the loan now. For any help on e-sign please view our tutorial videos or reach out to us under "Contact Us" on the app -Spark Loans',
                    "Pledge accepted",
                )
            )
            fcm_notification = frappe.get_doc(
                "Spark Push Notification", fcm_title, fields=["*"]
            )

        elif (
            doc.get("loan_application").get("status") == "Approved"
            and not self.loan_margin_shortfall
        ):
            msg, fcm_title = (
                (
                    "Dear Customer,\nCongratulations! Your loan limit has been successfully increased. Kindly check the app. You may now withdraw funds as per your convenience. -Spark Loans",
                    "Increase loan application approved",
                )
                if self.loan and not self.loan_margin_shortfall
                else (
                    "Dear Customer,\nCongratulations! Your loan account is open. Kindly check the app. You may now withdraw funds as per your convenience. -Spark Loans",
                    "Loan approved",
                )
            )
            fcm_notification = frappe.get_doc(
                "Spark Push Notification", fcm_title, fields=["*"]
            )

        elif (
            doc.get("loan_application").get("status") == "Rejected"
            and not self.loan_margin_shortfall
        ):
            msg, fcm_title = (
                (
                    "Dear Customer,\nSorry! Your Increase loan application was turned down due to technical reasons. We regret the inconvenience caused. Please try again after sometime or reach out to us through 'Contact Us' on the app  -Spark Loans",
                    "Increase loan application turned down",
                )
                if self.loan and not self.loan_margin_shortfall
                else (
                    "Dear Customer,\nSorry! Your loan application was turned down due to technical reasons. We regret the inconvenience caused. Please try again after sometime or reach out to us through 'Contact Us' on the app  -Spark Loans",
                    "Loan rejected",
                )
            )
            fcm_notification = frappe.get_doc(
                "Spark Push Notification", fcm_title, fields=["*"]
            )

        elif (
            doc.get("loan_application").get("status") == "Esign Done"
            and self.lender_esigned_document == None
            and not self.loan_margin_shortfall
        ):
            msg = "Dear Customer,\nYour E-sign process is completed. You shall soon receive a confirmation of loan approval. Thank you for your patience. - Spark Loans"

            fcm_notification = frappe.get_doc(
                "Spark Push Notification", "E-signing was successful", fields=["*"]
            )

        if (
            (
                (self.pledge_status == "Partial Success")
                or (self.total_collateral_value < self.pledged_total_collateral_value)
            )
            and doc.get("loan_application").get("status") == "Pledge accepted by Lender"
            and not self.loan_margin_shortfall
        ):
            msg = "Dear Customer,\nCongratulations! Your pledge request was successfully considered and was partially accepted for Rs. {} due to technical reasons. Kindly check the app for details under e-sign banner on the dashboard. Please e-sign the loan agreement to avail the loan now. -Spark Loans".format(
                self.total_collateral_value_str
            )
            fcm_notification = frappe.get_doc(
                "Spark Push Notification",
                "Increase loan application partially accepted"
                if self.loan
                else "Pledge partially accepted",
                fields=["*"],
            )
            fcm_message = (
                fcm_notification.message.format(
                    total_collateral_value_str=self.total_collateral_value_str
                )
                if self.loan
                else ""
            )

        if msg:
            receiver_list = list(
                set([str(self.get_customer().phone), str(doc.mobile_number)])
            )
            from frappe.core.doctype.sms_settings.sms_settings import send_sms

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

        if fcm_notification:
            lms.send_spark_push_notification(
                fcm_notification=fcm_notification,
                message=fcm_message,
                loan=self.loan,
                customer=self.get_customer(),
            )

    def validate(self):
        for i, item in enumerate(
            sorted(self.items, key=lambda item: item.security_name), start=1
        ):
            item.idx = i


def check_for_pledge(loan_application_doc):
    # TODO : Workers assigned for this cron can be set in las and we can apply (fetch records)limit as per no. of workers assigned
    frappe.db.begin()
    loan_application_doc.status = "Executing pledge"
    loan_application_doc.workflow_state = "Executing pledge"
    loan_application_doc.total_collateral_value = 0
    loan_application_doc.save(ignore_permissions=True)
    frappe.db.commit()

    customer = loan_application_doc.get_customer()
    count_la_items = frappe.db.count(
        "Loan Application Item", {"parent": loan_application_doc.name}
    )
    no_of_batches = 1
    if count_la_items > 10:
        import math

        no_of_batches = math.ceil(count_la_items / 10)

    # loop as per no of batches
    start = 0
    page_length = 10
    total_successful_pledge = 0
    for b_no in range(no_of_batches):
        frappe.db.begin()
        # fetch loan application items
        if b_no > 0:
            start += page_length

        la_items = frappe.get_all(
            "Loan Application Item",
            fields="*",
            filters={"parent": loan_application_doc.name},
            start=start,
            page_length=page_length,
        )
        la_items_list = [item.isin for item in la_items]

        # TODO : generate prf number and assign to items in batch
        pledge_request = loan_application_doc.pledge_request(la_items_list)
        # TODO : pledge request hit for all batches
        debug_mode = frappe.db.get_single_value("LAS Settings", "debug_mode")
        if debug_mode:
            data = loan_application_doc.dummy_pledge_response(
                pledge_request.get("payload").get("ISINDTLS")
            )
        else:
            try:
                res = requests.post(
                    pledge_request.get("url"),
                    headers=pledge_request.get("headers"),
                    json=pledge_request.get("payload"),
                )
                data = res.json()

                #     # Pledge LOG
                log = {
                    "url": pledge_request.get("url"),
                    "headers": pledge_request.get("headers"),
                    "request": pledge_request.get("payload"),
                    "response": data,
                }
                #     pledge_log_file = frappe.utils.get_files_path("pledge_log.json")
                #     pledge_log = None
                #     if os.path.exists(pledge_log_file):
                #         with open(pledge_log_file, "r") as f:
                #             pledge_log = f.read()
                #         f.close()
                #     pledge_log = json.loads(pledge_log or "[]")
                #     pledge_log.append(log)
                #     with open(pledge_log_file, "w") as f:
                #         f.write(json.dumps(pledge_log))
                #     f.close()
                #     # Pledge LOG end

                lms.create_log(log, "pledge_log")

            except requests.RequestException as e:
                pass

        # TODO : process loan application items in batches
        total_successful_pledge_count = loan_application_doc.process(
            la_items_list, data
        )
        total_successful_pledge += total_successful_pledge_count
        frappe.db.commit()

    frappe.db.begin()
    # manage loan application doc pledge status
    loan_application_doc.status = "Pledge executed"
    pledge_securities = 0
    if total_successful_pledge == len(loan_application_doc.items):
        loan_application_doc.pledge_status = "Success"
        pledge_securities = 1
    elif total_successful_pledge == 0:
        loan_application_doc.reload()
        loan_application_doc.status = "Pledge Failure"
        loan_application_doc.pledge_status = "Failure"
    else:
        loan_application_doc.pledge_status = "Partial Success"
        pledge_securities = 1
    # TODO : once done with all batches, mark LA as Pledge executed
    loan_application_doc.workflow_state = "Pledge executed"

    # TODO : process loan application(handle collateral and eligible amount)
    # loan_application_doc.reload()
    loan_application_doc.total_collateral_value = round(
        loan_application_doc.total_collateral_value, 2
    )
    loan_application_doc.drawing_power = round(
        lms.round_down_amount_to_nearest_thousand(
            (loan_application_doc.allowable_ltv / 100)
            * loan_application_doc.total_collateral_value
        ),
        2,
    )

    loan_application_doc.save(ignore_permissions=True)
    # loan_application_doc.save_collateral_ledger()

    if not customer.pledge_securities:
        # customer.pledge_securities = 1
        customer.pledge_securities = pledge_securities
        customer.save(ignore_permissions=True)

    frappe.db.commit()
    frappe.enqueue(
        method="lms.lms.doctype.loan_application.loan_application.process_pledge"
    )


@frappe.whitelist()
def process_pledge(loan_application_name=""):
    from frappe import utils

    current_hour = int(utils.nowtime().split(":")[0])
    las_settings = frappe.get_single("LAS Settings")
    if (
        las_settings.scheduler_from_time
        <= current_hour
        < las_settings.scheduler_to_time
    ):
        # check if pledge is already in progress
        is_pledge_executing = frappe.get_all(
            "Loan Application",
            fields=["count(name) as count", "status"],
            filters={"status": "Executing pledge"},
        )
        if is_pledge_executing[0].count == 0:
            filters_query = {"status": "Waiting to be pledged"}
            if loan_application_name:
                filters_query["name"] = loan_application_name
            loan_application = frappe.get_all(
                "Loan Application",
                fields="name, creation",
                filters=filters_query,
                order_by="creation asc",
                start=0,
                page_length=1,
            )

            if loan_application:
                loan_application_doc = frappe.get_doc(
                    "Loan Application", loan_application[0].name
                )
                frappe.enqueue(
                    method="lms.lms.doctype.loan_application.loan_application.check_for_pledge",
                    timeout=7200,
                    job_name="loan_application_pledge",
                    loan_application_doc=loan_application_doc,
                )


def only_pdf_upload(doc, method):
    if doc.attached_to_doctype == "Loan Application":
        if doc.file_name.split(".")[-1].lower() != "pdf":
            frappe.throw("Kindly upload PDF files only.")


@frappe.whitelist()
def actions_on_isin(loan_application):
    print("Inside Actions on isin")
    loan_application = json.loads(loan_application)
    loan_application_doc = frappe.get_doc("Loan Application", loan_application["name"])
    if loan_application_doc.status == "Pledge executed":
        total_collateral_value = 0
        drawing_power = 0
        print("inside internal if")
        for i in loan_application["items"]:
            if i["pledge_status"] == "Success" or i["pledge_status"] == "":
                if (
                    i["lender_approval_status"] == "Approved"
                    or i["lender_approval_status"] == ""
                ):
                    total_collateral_value += i["amount"]
                    total_collateral_value = round(total_collateral_value, 2)
                    drawing_power = round(
                        lms.round_down_amount_to_nearest_thousand(
                            (loan_application["allowable_ltv"] / 100)
                            * total_collateral_value
                        ),
                        2,
                    )
                # elif (
                #     i["lender_approval_status"] == "Rejected"
                #     or i["lender_approval_status"] == "Pledge Failure"
                # ):
                #     if (
                #         total_collateral_value > 0
                #         and total_collateral_value >= i["amount"]
                #     ):
                #         total_collateral_value -= i["amount"]
                #     total_collateral_value = round(total_collateral_value, 2)
                #     drawing_power = round(
                #         lms.round_down_amount_to_nearest_thousand(
                #             (loan_application["allowable_ltv"] / 100)
                #             * total_collateral_value
                #         ),
                #         2,
                #     )

        response = {
            "total_collateral_value": total_collateral_value,
            "drawing_power": drawing_power,
            "total_collateral_value_str": lms.amount_formatter(total_collateral_value),
            "drawing_power_str": lms.amount_formatter(drawing_power),
            "pledged_total_collateral_value_str": lms.amount_formatter(
                loan_application["pledged_total_collateral_value"]
            ),
        }
        lms.create_log(response, "status_pledge_accepted_by_lender")
        return response
