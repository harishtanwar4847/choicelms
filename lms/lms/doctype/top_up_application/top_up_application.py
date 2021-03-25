# -*- coding: utf-8 -*-
# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

from datetime import datetime

import frappe
from frappe.model.document import Document
from num2words import num2words


class TopupApplication(Document):
    def get_customer(self):
        return frappe.get_doc("Loan Customer", self.customer)

    def on_update(self):
        loan = frappe.get_doc("Loan", self.loan)
        if self.status == "Approved":
            loan.drawing_power += self.top_up_amount
            loan.sanctioned_limit += self.top_up_amount
            loan.save(ignore_permissions=True)
            frappe.db.commit()
            self.map_loan_agreement_file(loan)

        self.notify_customer()

    def get_loan(self):
        return frappe.get_doc("Loan", self.loan)

    def before_save(self):
        if self.status == "Approved" and not self.lender_esigned_document:
            frappe.throw("Please upload Lender Esigned Document")

        if self.status == "Approved":
            loan = self.get_loan()
            updated_top_up_amt = loan.max_topup_amount()
            if updated_top_up_amt < self.top_up_amount:
                frappe.throw("Top up not available")
            if self.top_up_amount <= 0:
                frappe.throw("Top up can not be approved with Amount Rs. 0")

    def get_lender(self):
        return frappe.get_doc("Lender", self.get_loan().lender)

    def create_tnc_file(self):
        lender = self.get_lender()
        customer = self.get_customer()
        user_kyc = customer.get_kyc()
        loan = self.get_loan()

        doc = {
            "esign_date": "__________",
            "loan_application_number": self.name,
            "borrower_name": user_kyc.investor_name,
            "borrower_address": user_kyc.address,
            "sanctioned_amount": self.top_up_amount,
            "sanctioned_amount_in_words": num2words(
                self.top_up_amount, lang="en_IN"
            ).title(),
            "old_sanctioned_amount": loan.sanctioned_limit,
            "old_sanctioned_amount_in_words": num2words(
                loan.sanctioned_limit, lang="en_IN"
            ).title(),
            "rate_of_interest": lender.rate_of_interest,
            "default_interest": lender.default_interest,
            "account_renewal_charges": lender.account_renewal_charges,
            "documentation_charges": lender.documentation_charges,
            # "stamp_duty_charges": (lender.stamp_duty / 100)
            # * self.drawing_power,  # CR loan agreement changes
            "processing_fee": lender.lender_processing_fees,
            "transaction_charges_per_request": lender.transaction_charges_per_request,
            "security_selling_share": lender.security_selling_share,
            "cic_charges": lender.cic_charges,
            "total_pages": lender.total_pages,
        }

        loan = self.get_loan()
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

    def esign_request(self):
        customer = self.get_customer()
        user = frappe.get_doc("User", customer.user)
        user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
        lender = self.get_lender()
        loan = self.get_loan()

        doc = {
            "esign_date": datetime.now().strftime("%d-%m-%Y"),
            "loan_application_number": self.name,
            "borrower_name": user_kyc.investor_name,
            "borrower_address": user_kyc.address,
            "sanctioned_amount": self.top_up_amount,
            "sanctioned_amount_in_words": num2words(
                self.top_up_amount, lang="en_IN"
            ).title(),
            "old_sanctioned_amount": loan.sanctioned_limit,
            "old_sanctioned_amount_in_words": num2words(
                loan.sanctioned_limit, lang="en_IN"
            ).title(),
            "rate_of_interest": lender.rate_of_interest,
            "default_interest": lender.default_interest,
            "account_renewal_charges": lender.account_renewal_charges,
            "documentation_charges": lender.documentation_charges,
            # "stamp_duty_charges": (lender.stamp_duty / 100)
            # * self.drawing_power,  # CR loan agreement changes
            "processing_fee": lender.lender_processing_fees,
            "transaction_charges_per_request": lender.transaction_charges_per_request,
            "security_selling_share": lender.security_selling_share,
            "cic_charges": lender.cic_charges,
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

        customer = self.get_customer()
        user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
        doc = frappe.get_doc("User", customer.user).as_dict()
        doc["top_up_application"] = {
            "status": self.status,
            "loan": self.loan,
            "top_up_amount": self.top_up_amount,
        }
        # frappe.enqueue_doc("Notification", "Top up Application", method="send", doc=doc)
        mess = ""
        if doc.get("top_up_application").get("status") == "Pending":
            mess = "Your request has been successfully received. You will be notified when your new OD limit is approved by our banking partner."

        if doc.get("top_up_application").get("status") == "Approved":
            mess = "Congratulations! Your Top up application for Loan {} is Approved.".format(
                doc.get("top_up_application").get("loan")
            )

        if doc.get("top_up_application").get("status") == "Rejected":
            mess = "Sorry! Your Top up application was turned down. We regret the inconvenience caused."

        if mess:
            receiver_list = list(
                set([str(customer.phone), str(user_kyc.mobile_number)])
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

        loan_agreement_file_url = frappe.utils.get_files_path(
            loan_agreement_file_name, is_private=is_private
        )

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
