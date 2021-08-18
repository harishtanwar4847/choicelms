# -*- coding: utf-8 -*-
# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

from datetime import datetime, timedelta

import frappe
from frappe.model.document import Document
from num2words import num2words


class TopupApplication(Document):
    def get_customer(self):
        return frappe.get_doc("Loan Customer", self.customer)

    def get_loan(self):
        return frappe.get_doc("Loan", self.loan)

    def on_submit(self):
        loan = self.get_loan()

        # apply loan charges
        self.apply_loan_charges(loan)
        loan.reload()

        loan.drawing_power += self.top_up_amount
        loan.sanctioned_limit += self.top_up_amount
        loan.expiry_date = self.expiry_date
        loan.save(ignore_permissions=True)
        frappe.db.commit()

        self.map_loan_agreement_file(loan)
        # self.notify_customer()

    def apply_loan_charges(self, loan):
        lender = loan.get_lender()

        # renewal charges
        import calendar

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
                * loan.sanctioned_limit
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
                * self.top_up_amount
                / days_in_year
                * days_left_to_expiry
            )
            processing_fees = loan.validate_loan_charges_amount(
                lender,
                amount,
                "lender_processing_minimum_amount",
                "lender_processing_maximum_amount",
            )

        if processing_fees > 0:
            loan.create_loan_transaction(
                "Processing Fees",
                processing_fees,
                approve=True,
            )

        # Stamp Duty
        stamp_duty = lender.stamp_duty
        if lender.stamp_duty_type == "Percentage":
            amount = (stamp_duty / 100) * self.top_up_amount
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
            amount = (documentation_charges / 100) * self.top_up_amount
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

    def on_update(self):
        if self.status == "Esign Done" and self.lender_esigned_document != None:
            return
        self.notify_customer()

    def before_submit(self):
        if not self.lender_esigned_document:
            frappe.throw("Please upload Lender Esigned Document")

        loan = self.get_loan()
        updated_top_up_amt = loan.max_topup_amount()
        if updated_top_up_amt < (loan.sanctioned_limit * 0.1):
            frappe.throw("Top up not available")
        if self.top_up_amount <= 0:
            frappe.throw("Top up can not be approved with Amount Rs. 0")

    def get_lender(self):
        return frappe.get_doc("Lender", self.get_loan().lender)

    # def create_tnc_file(self):
    #     lender = self.get_lender()
    #     customer = self.get_customer()
    #     user_kyc = customer.get_kyc()
    #     loan = self.get_loan()

    #     doc = {
    #         "esign_date": "__________",
    #         "loan_application_number": self.loan,
    #         "borrower_name": user_kyc.investor_name,
    #         "borrower_address": user_kyc.address,
    #         # "sanctioned_amount": self.top_up_amount,
    #         # "sanctioned_amount_in_words": num2words(
    #         #     self.top_up_amount, lang="en_IN"
    #         # ).title(),
    #         "sanctioned_amount": (self.top_up_amount + loan.sanctioned_limit),
    #         "sanctioned_amount_in_words": num2words(
    #             (self.top_up_amount + loan.sanctioned_limit), lang="en_IN"
    #         ).title(),
    #         "old_sanctioned_amount": loan.sanctioned_limit,
    #         "old_sanctioned_amount_in_words": num2words(
    #             loan.sanctioned_limit, lang="en_IN"
    #         ).title(),
    #         "rate_of_interest": lender.rate_of_interest,
    #         "default_interest": lender.default_interest,
    #         "account_renewal_charges": lender.account_renewal_charges,
    #         "documentation_charges": lender.documentation_charges,
    #         # "stamp_duty_charges": (lender.stamp_duty / 100)
    #         # * self.sanctioned_limit,  # CR loan agreement changes
    #         "processing_fee": lender.lender_processing_fees,
    #         "transaction_charges_per_request": lender.transaction_charges_per_request,
    #         "security_selling_share": lender.security_selling_share,
    #         "cic_charges": lender.cic_charges,
    #         "total_pages": lender.total_pages,
    #     }

    #     agreement_template = lender.get_loan_enhancement_agreement_template()

    #     agreement = frappe.render_template(
    #         agreement_template.get_content(), {"doc": doc}
    #     )

    #     from frappe.utils.pdf import get_pdf

    #     agreement_pdf = get_pdf(agreement)

    #     tnc_dir_path = frappe.utils.get_files_path("tnc")
    #     import os

    #     if not os.path.exists(tnc_dir_path):
    #         os.mkdir(tnc_dir_path)
    #     tnc_file = "tnc/{}.pdf".format(self.loan)
    #     tnc_file_path = frappe.utils.get_files_path(tnc_file)

    #     with open(tnc_file_path, "wb") as f:
    #         f.write(agreement_pdf)
    #     f.close()

    def esign_request(self):
        customer = self.get_customer()
        user = frappe.get_doc("User", customer.user)
        user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
        lender = self.get_lender()
        loan = self.get_loan()

        doc = {
            "esign_date": frappe.utils.now_datetime().strftime("%d-%m-%Y"),
            "loan_application_number": self.name,
            "borrower_name": user_kyc.investor_name,
            "borrower_address": user_kyc.address,
            # "sanctioned_amount": self.top_up_amount,
            # "sanctioned_amount_in_words": num2words(
            #     self.top_up_amount, lang="en_IN"
            # ).title(),
            "sanctioned_amount": int(self.top_up_amount + loan.sanctioned_limit),
            "sanctioned_amount_in_words": num2words(
                (self.top_up_amount + loan.sanctioned_limit), lang="en_IN"
            ).title(),
            "old_sanctioned_amount": int(loan.sanctioned_limit),
            "old_sanctioned_amount_in_words": num2words(
                loan.sanctioned_limit, lang="en_IN"
            ).title(),
            "rate_of_interest": lender.rate_of_interest,
            "default_interest": lender.default_interest,
            "rebait_threshold": lender.rebait_threshold,
            "renewal_charges": lender.renewal_charges,
            "renewal_charge_type": lender.renewal_charge_type,
            "renewal_charge_in_words": num2words(
                lender.renewal_charges, lang="en_IN"
            ).title(),
            "renewal_min_amt": int(lender.renewal_minimum_amount),
            "renewal_max_amt": int(lender.renewal_maximum_amount),
            "documentation_charge": lender.documentation_charges,
            "documentation_charge_type": lender.documentation_charge_type,
            "documentation_charge_in_words": num2words(
                lender.documentation_charges, lang="en_IN"
            ).title(),
            "documentation_min_amt": int(lender.lender_documentation_minimum_amount),
            "documentation_max_amt": int(lender.lender_documentation_maximum_amount),
            "lender_processing_fees_type": lender.lender_processing_fees_type,
            "processing_charge": lender.lender_processing_fees,
            "processing_charge_in_words": num2words(
                lender.lender_processing_fees, lang="en_IN"
            ).title(),
            "processing_min_amt": int(lender.lender_processing_minimum_amount),
            "processing_max_amt": int(lender.lender_processing_maximum_amount),
            # "stamp_duty_charges": int(lender.lender_stamp_duty_minimum_amount),
            # "documentation_charges": lender.documentation_charges,
            # "stamp_duty_charges": (lender.stamp_duty / 100)
            # * self.sanctioned_limit,  # CR loan agreement changes
            "transaction_charges_per_request": int(
                lender.transaction_charges_per_request
            ),
            "security_selling_share": lender.security_selling_share,
            "cic_charges": int(lender.cic_charges),
            "total_pages": lender.total_pages,
        }

        agreement_template = lender.get_loan_enhancement_agreement_template()
        loan_agreement_file = "loan-enhancement-aggrement.pdf"
        coordinates = lender.enhancement_coordinates.split(",")
        esign_page = lender.enhancement_esign_page
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

    def notify_customer(self):
        from frappe.core.doctype.sms_settings.sms_settings import send_sms

        doc = frappe.get_doc("User KYC", self.get_customer().choice_kyc).as_dict()
        doc["top_up_application"] = {
            "status": self.status,
            "loan": self.loan,
            "top_up_amount": self.top_up_amount,
        }
        # if self.status in ["Pending", "Approved", "Rejected"]:
        frappe.enqueue_doc("Notification", "Top up Application", method="send", doc=doc)
        mess = ""
        if doc.get("top_up_application").get("status") == "Pending":
            # mess = "Your request has been successfully received. You will be notified when your new OD limit is approved by our banking partner."
            mess = 'Dear Customer,\nCongratulations! Your Top Up application has been accepted. Kindly check the app for details under e-sign banner on the dashboard. Please e-sign the loan agreement to avail the loan now. For any help on e-sign please view our tutorial videos or reach out to us under "Contact Us" on the app -Spark Loans'

        if doc.get("top_up_application").get("status") == "Approved":
            mess = "Dear Customer,\nCongratulations! Your loan account has been topped up. Please check the app for details. -Spark Loans"
            # mess = "Congratulations! Your Top up application for Loan {} is Approved.".format(
            #     doc.get("top_up_application").get("loan")
            # )

        if doc.get("top_up_application").get("status") == "Rejected":
            # mess = "Sorry! Your Top up application was turned down. We regret the inconvenience caused."

            mess = "Dear Customer,\nSorry! Your top up request could not be executed due to technical reasons. We regret the inconvenience caused.Please try again after sometime or reach out to us through 'Contact Us' on the app  -Spark Loans"

        if mess:
            receiver_list = list(
                set([str(self.get_customer().phone), str(doc.mobile_number)])
            )

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=mess)

    def map_loan_agreement_file(self, loan):
        file_name = frappe.db.get_value(
            "File", {"file_url": self.lender_esigned_document}
        )

        loan_agreement = frappe.get_doc("File", file_name)

        loan_agreement_file_name = "{}-loan-enhancement-aggrement.pdf".format(loan.name)
        event = "Top up"

        is_private = 0

        # loan_agreement_file_url = frappe.utils.get_files_path(
        #     loan_agreement_file_name, is_private=is_private
        # )

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


def only_pdf_upload(doc, method):
    if doc.attached_to_doctype == "Top up Application":
        if doc.file_name.split(".")[-1].lower() != "pdf":
            frappe.throw("Kindly upload PDF files only.")
