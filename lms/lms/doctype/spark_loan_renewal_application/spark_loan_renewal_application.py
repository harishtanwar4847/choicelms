# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import os
from datetime import date, datetime, time, timedelta

import frappe
import pandas as pd
from frappe import _
from frappe.model.document import Document
from PyPDF2 import PdfReader, PdfWriter

import lms
from lms import send_spark_push_notification
from lms.lms.doctype.user_token.user_token import send_sms


class SparkLoanRenewalApplication(Document):
    def before_save(self):
        self.two_days_grace_period()
        las_settings = frappe.get_single("LAS Settings")
        loan = frappe.get_doc("Loan", self.loan)
        if self.lender_esigned_document and self.status == "Esign Done":
            file_name = frappe.db.get_value(
                "File", {"file_url": self.lender_esigned_document}
            )
            file_ = frappe.get_doc("File", file_name)
            if file_.is_private:
                file_.is_private = 0
                file_.save(ignore_permissions=True)
                frappe.db.commit()
                file_.reload()
            self.lender_esigned_document = file_.file_url
        msg = ""
        current_year = int(frappe.utils.now_datetime().strftime("%Y"))
        if (
            (current_year % 400 == 0)
            or (current_year % 100 != 0)
            and (current_year % 4 == 0)
        ):
            no_of_days = 366
        # Else it is not a leap year
        else:
            no_of_days = 365

        if (
            self.status == "Approved"
            and not self.expiry_date
            and not self.lender_esigned_document
        ):
            frappe.throw(_("Please upload Lender esigned document."))

        remarks = self.remarks
        remarks_trim = remarks.replace(" ", "") if remarks else ""
        if self.status == "Rejected" and not remarks_trim:
            frappe.throw(_("Remarks field cannot be empty."))
        if self.status == "Rejected" and not self.remarks:
            frappe.throw(_("Remarks field cannot be empty."))
        if self.custom_base_interest:
            self.base_interest = self.custom_base_interest

        if self.custom_rebate_interest:
            self.rebate_interest = self.custom_rebate_interest

        if self.custom_base_interest <= float(
            0
        ) or self.custom_rebate_interest <= float(0):
            frappe.throw("Base interest and Rebate Interest should be greater than 0")

        if (
            self.status == "Loan Renewal accepted by Lender"
            and self.base_interest == 0
            and self.rebate_interest == 0
        ):
            frappe.throw(_("Please enter the base interest and rebate interest"))

        if self.loan_balance > 0 and self.is_default == 1:
            interest_configuration = frappe.db.get_value(
                "Interest Configuration",
                {
                    "lender": self.lender,
                    "from_amount": ["<=", self.loan_balance],
                    "to_amount": [">=", self.loan_balance],
                },
                ["name", "base_interest", "rebait_interest"],
                as_dict=1,
            )
            self.base_interest = interest_configuration["base_interest"]
            self.rebate_interest = interest_configuration["rebait_interest"]
        try:
            loan = frappe.get_doc("Loan", self.loan)
            customer = frappe.get_doc("Loan Customer", self.customer)

            doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
            doc["loan_renewal_application"] = {
                "status": self.status,
                "lr_accepted_by_lender": self.lr_accepted_by_lender,
            }

            if self.status in [
                "Loan Renewal accepted by Lender",
                "Esign Done",
                "Rejected",
            ]:
                frappe.enqueue_doc(
                    "Notification", "Loan Renewal Application", method="send", doc=doc
                )
            # elif self.status == "Approved":
            #     self.sanction_letter(check=loan.name)
            #     loan_email_message = frappe.db.sql(
            #         "select message from `tabNotification` where name ='Loan Renewal Application Approved';"
            #     )[0][0]
            #     loan_email_message = loan_email_message.replace(
            #         "fullname", doc.fullname
            #     )
            #     loan_email_message = loan_email_message.replace(
            #         "fullname", doc.fullname
            #     )
            #     loan_email_message = loan_email_message.replace(
            #         "logo_file",
            #         frappe.utils.get_url("/assets/lms/mail_images/logo.png"),
            #     )
            #     loan_email_message = loan_email_message.replace(
            #         "fb_icon",
            #         frappe.utils.get_url("/assets/lms/mail_images/fb-icon.png"),
            #     )
            #     # loan_email_message = loan_email_message.replace("tw_icon",frappe.utils.get_url("/assets/lms/mail_images/tw-icon.png"),)
            #     loan_email_message = loan_email_message.replace(
            #         "inst_icon",
            #         frappe.utils.get_url("/assets/lms/mail_images/inst-icon.png"),
            #     )
            #     loan_email_message = loan_email_message.replace(
            #         "lin_icon",
            #         frappe.utils.get_url("/assets/lms/mail_images/lin-icon.png"),
            #     )
            #     attachments = ""
            #     attachments = self.create_attachment()
            #     frappe.enqueue(
            #         method=frappe.sendmail,
            #         recipients=[customer.user],
            #         sender=None,
            #         subject="Loan Renewal Application",
            #         message=loan_email_message,
            #         attachments=attachments,
            #     )

            if (
                self.status == "Loan Renewal accepted by Lender"
                and not self.lr_accepted_by_lender
            ):
                self.lr_accepted_by_lender = 1
                msg = """Dear Customer,
Congratulations! Your loan renewal application has been accepted. Kindly check the app for details under e-sign banner on the dashboard. Please e-sign the loan agreement. For any help on e-sign, please view our tutorial videos or reach out to us under "Contact Us" on the app - {link} - Spark Loans""".format(
                    link=las_settings.contact_us
                )

                fcm_notification = frappe.get_doc(
                    "Spark Push Notification",
                    "Loan Renewal accepted",
                    fields=["*"],
                )
                send_spark_push_notification(
                    fcm_notification=fcm_notification,
                    loan=loan.name,
                    customer=customer,
                )
                self.sanction_letter()

            elif self.status == "Esign Done" and self.lender_esigned_document == None:
                msg = """Dear Customer,
Your E-sign process is completed. You shall soon receive a confirmation of loan renew approval. Thank you for your patience. - Spark Loans"""

                fcm_notification = frappe.get_doc(
                    "Spark Push Notification",
                    "Loan Renewal E-signing was successful",
                    fields=["*"],
                )
                send_spark_push_notification(
                    fcm_notification=fcm_notification,
                    loan=loan.name,
                    customer=customer,
                )

            elif self.status == "Approved":
                self.expiry_date = (
                    loan.expiry_date + timedelta(days=no_of_days) - timedelta(days=1)
                )
                self.sanction_letter(check=loan.name)

            elif self.status == "Rejected":
                if (
                    self.lr_accepted_by_lender == 1
                    and not self.customer_esigned_document
                ):
                    msg = """Dear Customer,
Your loan renew application was turned down, as per your request. Please try again or you can reach to us through 'Contact Us' on the app- ({link})-Spark Loans""".format(
                        link=las_settings.contact_us
                    )

                    fcm_notification = frappe.get_doc(
                        "Spark Push Notification",
                        "Loan Renewal rejected(in accepted by lender state)",
                        fields=["*"],
                    )
                    send_spark_push_notification(
                        fcm_notification=fcm_notification,
                        loan=loan.name,
                        customer=customer,
                    )

                else:
                    msg = """Dear Customer,
Sorry! Your loan renewal application was turned down. We regret the inconvenience caused. Please try again after sometime or reach out to us through 'Contact Us' on the app  - {link}- Spark Loans""".format(
                        link=las_settings.contact_us
                    )

                    fcm_notification = frappe.get_doc(
                        "Spark Push Notification",
                        "Loan Renewal rejected",
                        fields=["*"],
                    )
                    send_spark_push_notification(
                        fcm_notification=fcm_notification,
                        loan=loan.name,
                        customer=customer,
                    )

                existing_renewal_doc = frappe.get_all(
                    "Spark Loan Renewal Application",
                    filters={
                        "name": ["!=", self.name],
                        "loan": loan.name,
                        "status": ["not IN", ["Approved", "Rejected"]],
                    },
                    fields=["name"],
                )
                if (
                    loan.expiry_date > frappe.utils.now_datetime().date()
                    and not existing_renewal_doc
                    and self.remarks
                    != "Rejected due to Approval of Top-up/Increase Loan Application"
                ):
                    self.tnc_complete = 0
                    self.updated_kyc_status = ""
                    if self.new_kyc_name:
                        kyc_doc = frappe.get_doc("User KYC", self.new_kyc_name)
                        kyc_doc.updated_kyc = 0
                        kyc_doc.save(ignore_permissions=True)
                    wef_date = loan.wef_date
                    if type(wef_date) is str:
                        wef_date = datetime.strptime(str(wef_date), "%Y-%m-%d").date()
                    if (
                        wef_date >= frappe.utils.now_datetime().date()
                        and self.is_default == 0
                    ) or (
                        self.old_is_default == 0
                        and wef_date >= frappe.utils.now_datetime().date()
                    ):
                        custom_base_interest = loan.old_interest
                        custom_rebate_interest = loan.old_rebate_interest
                    else:
                        custom_base_interest = loan.custom_base_interest
                        custom_rebate_interest = loan.custom_rebate_interest

                    frappe.get_doc(
                        dict(
                            doctype="Spark Loan Renewal Application",
                            loan=loan.name,
                            lender=loan.lender,
                            custom_base_interest=custom_base_interest,
                            custom_rebate_interest=custom_rebate_interest,
                            is_default=loan.is_default,
                            old_kyc_name=customer.choice_kyc,
                            total_collateral_value=loan.total_collateral_value,
                            sanctioned_limit=loan.sanctioned_limit,
                            drawing_power=loan.drawing_power,
                            customer=customer.name,
                            customer_name=customer.full_name,
                        )
                    ).insert(ignore_permissions=True)
                    frappe.db.commit()
                if loan.expiry_date < frappe.utils.now_datetime().date():
                    renewal_list_expiring = frappe.get_all(
                        "Spark Loan Renewal Application",
                        filters={"loan": loan.name},
                        fields=["*"],
                    )
                    status_list = [i["status"] for i in renewal_list_expiring]
                    if status_list.count("Rejected") >= 2:
                        self.is_expired = 1

                    if (
                        status_list.count("Rejected") >= 2
                        and (self.creation.date() + timedelta(days=7))
                        == frappe.utils.now_datetime().date()
                    ):
                        self.is_expired = 1

            if msg:
                receiver_list = [str(customer.phone)]
                if customer.get_kyc().mob_num:
                    receiver_list.append(str(customer.get_kyc().mob_num))
                if customer.get_kyc().choice_mob_no:
                    receiver_list.append(str(customer.get_kyc().choice_mob_no))

                receiver_list = list(set(receiver_list))

                frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)
        except Exception as e:
            frappe.log_error(
                message=frappe.get_traceback()
                + "\n Loan Renewal Application : {}".format(self.name),
                title=_("Loan Renewal Application - Customer Notification "),
            )

    def on_update(self):
        if self.status == "Approved":
            las_settings = frappe.get_single("LAS Settings")
            lender = frappe.get_doc("Lender", self.lender)
            loan = self.get_loan()
            loan_renewal_charges = lender.renewal_charges
            customer = frappe.get_doc("Loan Customer", self.customer)
            doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
            doc["loan_renewal_application"] = {
                "status": self.status,
                "lr_accepted_by_lender": self.lr_accepted_by_lender,
            }

            if lender.renewal_charge_type == "Percentage":
                amount = (loan_renewal_charges / 100) * self.drawing_power
                loan_renewal_charges = loan.validate_loan_charges_amount(
                    lender,
                    amount,
                    "renewal_minimum_amount",
                    "renewal_maximum_amount",
                )
            loan.create_loan_transaction(
                transaction_type="Account Renewal Charges",
                amount=loan_renewal_charges,
                approve=True,
            )
            frappe.db.commit()
            loan_email_message = frappe.db.sql(
                "select message from `tabNotification` where name ='Loan Renewal Application Approved';"
            )[0][0]
            loan_email_message = loan_email_message.replace("fullname", doc.fullname)
            loan_email_message = loan_email_message.replace("fullname", doc.fullname)
            loan_email_message = loan_email_message.replace(
                "logo_file",
                frappe.utils.get_url("/assets/lms/mail_images/logo.png"),
            )
            loan_email_message = loan_email_message.replace(
                "fb_icon",
                frappe.utils.get_url("/assets/lms/mail_images/fb-icon.png"),
            )
            # loan_email_message = loan_email_message.replace("tw_icon",frappe.utils.get_url("/assets/lms/mail_images/tw-icon.png"),)
            loan_email_message = loan_email_message.replace(
                "inst_icon",
                frappe.utils.get_url("/assets/lms/mail_images/inst-icon.png"),
            )
            loan_email_message = loan_email_message.replace(
                "lin_icon",
                frappe.utils.get_url("/assets/lms/mail_images/lin-icon.png"),
            )
            attachments = self.create_attachment()
            frappe.enqueue(
                method=frappe.sendmail,
                recipients=[customer.user],
                sender=None,
                subject="Loan Renewal Application",
                message=loan_email_message,
                attachments=attachments,
            )
            current_year = int(frappe.utils.now_datetime().strftime("%Y"))
            if (
                (current_year % 400 == 0)
                or (current_year % 100 != 0)
                and (current_year % 4 == 0)
            ):
                no_of_days = 366
            # Else it is not a leap year
            else:
                no_of_days = 365

            expiry_date = (
                loan.expiry_date + timedelta(days=no_of_days) - timedelta(days=1)
            )
            loan.reload()
            # loan.expiry_date = loan.expiry_date + timedelta(days=no_of_days)
            # loan.base_interest = self.base_interest
            # loan.rebate_interest = self.rebate_interest
            # loan.wef_date = frappe.utils.now_datetime().date()
            # loan.save(ignore_permissions=True)
            # frappe.db.commit()
            frappe.db.set_value(
                "Loan",
                self.loan,
                {
                    "expiry_date": expiry_date,
                    "base_interest": self.base_interest,
                    "rebate_interest": self.rebate_interest,
                    "wef_date": frappe.utils.now_datetime().date(),
                    "old_interest": loan.base_interest,
                    "old_rebate_interest": loan.rebate_interest,
                },
            )
            msg = """Dear Customer,
Congratulations! Your loan renewal process is completed. Please visit the spark.loans app for details  - {link} -Spark Loans""".format(
                link=las_settings.app_login_dashboard
            )
            fcm_notification = frappe.get_doc(
                "Spark Push Notification",
                "Loan Renewal approved",
                fields=["*"],
            )
            send_spark_push_notification(
                fcm_notification=fcm_notification,
                loan=loan.name,
                customer=customer,
            )
            if msg:
                receiver_list = [str(customer.phone)]
                if customer.get_kyc().mob_num:
                    receiver_list.append(str(customer.get_kyc().mob_num))
                if customer.get_kyc().choice_mob_no:
                    receiver_list.append(str(customer.get_kyc().choice_mob_no))

                receiver_list = list(set(receiver_list))

                frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

    def create_attachment(self):
        attachments = []
        doc_name = self.lender_esigned_document
        fname = doc_name.split("files/", 1)
        file = fname[1].split(".", 1)
        file_name = file[0]
        log_file = frappe.utils.get_files_path("{}.pdf".format(file_name))
        with open(log_file, "rb") as fileobj:
            filedata = fileobj.read()

        sanction_letter = {"fname": fname[1], "fcontent": filedata}
        attachments.append(sanction_letter)
        return attachments

    def esign_request(self, increase_loan):
        try:
            customer = self.get_customer()
            user = frappe.get_doc("User", customer.user)
            user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
            lender = self.get_lender()
            logo_file_path_1 = lender.get_lender_logo_file()
            logo_file_path_2 = lender.get_lender_address_file()
            diff = self.drawing_power
            if self.loan:
                loan = self.get_loan()
                # increased_sanctioned_limit = lms.round_down_amount_to_nearest_thousand(
                #     (self.total_collateral_value + loan.total_collateral_value)
                #     * self.allowable_ltv
                #     / 100
                # )
                # actual_dp = lms.round_down_amount_to_nearest_thousand(
                #     loan.actual_drawing_power
                # )
                # increased_sanctioned_limit = lms.round_down_amount_to_nearest_thousand(
                #     actual_dp + self.drawing_power
                # )
                # new_increased_sanctioned_limit = (
                #     increased_sanctioned_limit
                #     if increased_sanctioned_limit < lender.maximum_sanctioned_limit
                #     else lender.maximum_sanctioned_limit
                # )
                # frappe.db.set_value(
                #     self.doctype,
                #     self.name,
                #     "increased_sanctioned_limit",
                #     new_increased_sanctioned_limit,
                #     update_modified=False,
                # )
                diff = self.sanctioned_limit

            if user_kyc.address_details:
                address_details = frappe.get_doc(
                    "Customer Address Details", user_kyc.address_details
                )
                address = (
                    (
                        (str(address_details.perm_line1) + ", ")
                        if address_details.perm_line1
                        else ""
                    )
                    + (
                        (str(address_details.perm_line2) + ", ")
                        if address_details.perm_line2
                        else ""
                    )
                    + (
                        (str(address_details.perm_line3) + ", ")
                        if address_details.perm_line3
                        else ""
                    )
                    + str(address_details.perm_city)
                    + ", "
                    + str(address_details.perm_dist)
                    + ", "
                    + str(address_details.perm_state)
                    + ", "
                    + str(address_details.perm_country)
                    + ", "
                    + str(address_details.perm_pin)
                )
            else:
                address = ""

            if user_kyc.address_details:
                address_details = frappe.get_doc(
                    "Customer Address Details", user_kyc.address_details
                )

                line1 = str(address_details.perm_line1)
                if line1:
                    addline1 = "{},<br/>".format(line1)
                else:
                    addline1 = ""

                line2 = str(address_details.perm_line2)
                if line2:
                    addline2 = "{},<br/>".format(line2)
                else:
                    addline2 = ""

                line3 = str(address_details.perm_line3)
                if line3:
                    addline3 = "{},<br/>".format(line3)
                else:
                    addline3 = ""

                perm_city = str(address_details.perm_city)
                perm_dist = str(address_details.perm_dist)
                perm_state = str(address_details.perm_state)
                perm_pin = str(address_details.perm_pin)

            else:
                address_details = ""

            interest_config = frappe.get_value(
                "Interest Configuration",
                {
                    "to_amount": [
                        ">=",
                        lms.validate_rupees(float(self.sanctioned_limit)),
                    ],
                },
                order_by="to_amount asc",
            )

            int_config = frappe.get_doc("Interest Configuration", interest_config)
            roi_ = round((self.base_interest * 12), 2)
            charges = lms.charges_for_apr(
                lender.name,
                lms.validate_rupees(float(diff)),
            )
            # apr = lms.calculate_apr(
            #     self.name,
            #     roi_,
            #     12,
            #     int(lms.validate_rupees(float(self.sanctioned_limit))),
            #     charges.get("total"),
            # )
            annual_default_interest = lender.default_interest * 12
            # sanctionlimit = (
            #     new_increased_sanctioned_limit
            #     if self.loan and not self.loan_margin_shortfall
            #     else self.drawing_power
            # )
            interest_charges_in_amount = int(
                lms.validate_rupees(float(self.sanctioned_limit))
            ) * (roi_ / 100)
            interest_per_month = float(interest_charges_in_amount / 12)
            final_payment = float(interest_per_month) + self.sanctioned_limit
            apr = lms.calculate_irr(
                name_=self.name,
                sanction_limit=float(
                    self.increased_sanctioned_limit
                    if self.increased_sanctioned_limit
                    else self.drawing_power
                ),
                interest_per_month=interest_per_month,
                final_payment=final_payment,
                charges=charges.get("total"),
            )
            doc = {
                "esign_date": frappe.utils.now_datetime().strftime("%d-%m-%Y"),
                "loan_account_number": loan.name if self.loan else "",
                "loan_application_number": self.name,
                "borrower_name": customer.full_name,
                "borrower_address": address,
                "addline1": addline1,
                "addline2": addline2,
                "addline3": addline3,
                "city": perm_city,
                "district": perm_dist,
                "state": perm_state,
                "pincode": perm_pin,
                "logo_file_path_1": logo_file_path_1.file_url
                if logo_file_path_1
                else "",
                "logo_file_path_2": logo_file_path_2.file_url
                if logo_file_path_2
                else "",
                # "sanctioned_amount": frappe.utils.fmt_money(float(self.drawing_power)),
                "sanctioned_amount": frappe.utils.fmt_money(
                    float(self.sanctioned_limit)
                ),
                "sanctioned_amount_in_words": lms.number_to_word(
                    lms.validate_rupees(float(self.sanctioned_limit))
                ).title(),
                "roi": roi_,
                "apr": apr,
                "documentation_charges_kfs": frappe.utils.fmt_money(
                    charges.get("documentation_charges")
                ),
                "processing_charges_kfs": frappe.utils.fmt_money(
                    charges.get("processing_fees")
                ),
                "net_disbursed_amount": frappe.utils.fmt_money(
                    float(self.sanctioned_limit) - charges.get("total")
                ),
                "total_amount_to_be_paid": frappe.utils.fmt_money(
                    float(self.sanctioned_limit)
                    + charges.get("total")
                    + interest_charges_in_amount
                ),
                "loan_application_no": self.name,
                "rate_of_interest": self.base_interest,
                "rebate_interest": self.rebate_interest,
                "default_interest": annual_default_interest,
                "rebait_threshold": lender.rebait_threshold,
                "penal_charges": lender.renewal_penal_interest
                if lender.renewal_penal_interest
                else "",
                "documentation_charges_kfs": frappe.utils.fmt_money(
                    charges.get("documentation_charges")
                ),
                "processing_charges_kfs": frappe.utils.fmt_money(
                    charges.get("processing_fees")
                ),
                "interest_charges_in_amount": frappe.utils.fmt_money(
                    interest_charges_in_amount
                ),
                "interest_per_month": frappe.utils.fmt_money(interest_per_month),
                "final_payment": frappe.utils.fmt_money(final_payment),
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
                "documentation_charge": lms.validate_rupees(
                    lender.documentation_charges
                )
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
                "lien_initiate_charge_type": lender.lien_initiate_charge_type,
                "invoke_initiate_charge_type": lender.invoke_initiate_charge_type,
                "revoke_initiate_charge_type": lender.revoke_initiate_charge_type,
                "lien_initiate_charge_minimum_amount": lms.validate_rupees(
                    lender.lien_initiate_charge_minimum_amount
                ),
                "lien_initiate_charge_maximum_amount": lms.validate_rupees(
                    lender.lien_initiate_charge_maximum_amount
                ),
                "lien_initiate_charges": lms.validate_rupees(
                    lender.lien_initiate_charges
                )
                if lender.lien_initiate_charge_type == "Fix"
                else lms.validate_percent(lender.lien_initiate_charges),
                "invoke_initiate_charges_minimum_amount": lms.validate_rupees(
                    lender.invoke_initiate_charges_minimum_amount
                ),
                "invoke_initiate_charges_maximum_amount": lms.validate_rupees(
                    lender.invoke_initiate_charges_maximum_amount
                ),
                "invoke_initiate_charges": lms.validate_rupees(
                    lender.invoke_initiate_charges
                )
                if lender.invoke_initiate_charge_type == "Fix"
                else lms.validate_percent(lender.invoke_initiate_charges),
                "revoke_initiate_charges_minimum_amount": lms.validate_rupees(
                    lender.revoke_initiate_charges_minimum_amount
                ),
                "revoke_initiate_charges_maximum_amount": lms.validate_rupees(
                    lender.revoke_initiate_charges_maximum_amount
                ),
                "revoke_initiate_charges": lms.validate_rupees(
                    lender.revoke_initiate_charges
                )
                if lender.revoke_initiate_charge_type == "Fix"
                else lms.validate_percent(lender.revoke_initiate_charges),
            }

            if increase_loan:
                doc["old_sanctioned_amount"] = frappe.utils.fmt_money(
                    loan.sanctioned_limit
                )
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

            # from frappe.utils.pdf import get_pdf

            agreement_pdf = lms.get_pdf(agreement)
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
        except Exception:
            frappe.log_error(
                title="Esign Request Loan Doc",
                message=frappe.get_traceback() + "\n\nLoan name \n" + str(self.name),
            )

    def get_customer(self):
        return frappe.get_doc("Loan Customer", self.customer)

    def get_lender(self):
        return frappe.get_doc("Lender", self.lender)

    def get_loan(self):
        return frappe.get_doc("Loan", self.loan)

    def sanction_letter(self, check=None):
        try:
            customer = self.get_customer()
            user = frappe.get_doc("User", customer.user)
            user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
            lender = self.get_lender()
            if user_kyc.address_details:
                address_details = frappe.get_doc(
                    "Customer Address Details", user_kyc.address_details
                )

                line1 = str(address_details.perm_line1)
                if line1:
                    addline1 = "{},<br/>".format(line1)
                else:
                    addline1 = ""

                line2 = str(address_details.perm_line2)
                if line2:
                    addline2 = "{},<br/>".format(line2)
                else:
                    addline2 = ""

                line3 = str(address_details.perm_line3)
                if line3:
                    addline3 = "{},<br/>".format(line3)
                else:
                    addline3 = ""

                perm_city = str(address_details.perm_city)
                perm_dist = str(address_details.perm_dist)
                perm_state = str(address_details.perm_state)
                perm_pin = str(address_details.perm_pin)

            else:
                address_details = ""

            diff = self.drawing_power
            if self.loan:
                loan = self.get_loan()
                increased_sanctioned_limit = loan.sanctioned_limit
                # new_increased_sanctioned_limit = (
                #     increased_sanctioned_limit
                #     if increased_sanctioned_limit < lender.maximum_sanctioned_limit
                #     else lender.maximum_sanctioned_limit
                # )
                diff = self.sanctioned_limit
            interest_config = frappe.get_value(
                "Interest Configuration",
                {
                    "to_amount": [
                        ">=",
                        lms.validate_rupees(
                            float(
                                loan.sanctioned_limit
                                # self.increased_sanctioned_limit
                                # if self.increased_sanctioned_limit
                                # else self.drawing_power
                            )
                        ),
                    ],
                },
                order_by="to_amount asc",
            )

            int_config = frappe.get_doc("Interest Configuration", interest_config)
            # sanctionlimit = (
            #     new_increased_sanctioned_limit
            #     if self.loan and not self.loan_margin_shortfall
            #     else self.drawing_power
            # )
            roi_ = round((self.base_interest * 12), 2)
            charges = lms.charges_for_apr(
                lender.name,
                lms.validate_rupees(float(diff)),
            )
            interest_charges_in_amount = int(
                lms.validate_rupees(
                    float(
                        self.sanctioned_limit
                        # self.increased_sanctioned_limit
                        # if self.increased_sanctioned_limit
                        # else self.drawing_power
                    )
                )
            ) * (roi_ / 100)
            # apr = lms.calculate_apr(
            #     self.name,
            #     roi_,
            #     12,
            #     int(
            #         lms.validate_rupees(
            #             float(
            #                 loan.sanctioned_limit
            #                 # self.increased_sanctioned_limit
            #                 # if self.increased_sanctioned_limit
            #                 # else self.drawing_power
            #             )
            #         )
            #     ),
            #     charges.get("total"),
            # )
            interest_per_month = float(interest_charges_in_amount / 12)
            final_payment = float(interest_per_month) + self.sanctioned_limit
            apr = lms.calculate_irr(
                name_=self.name,
                sanction_limit=float(
                    self.increased_sanctioned_limit
                    if self.increased_sanctioned_limit
                    else self.drawing_power
                ),
                interest_per_month=interest_per_month,
                final_payment=final_payment,
                charges=charges.get("total"),
            )

            loan_name = ""
            if not check and self.loan:
                loan_name = loan.name
            elif check:
                loan_name = check
            annual_default_interest = lender.default_interest * 12
            if self.status != "Approved":
                doc = {
                    "esign_date": "",
                    "loan_account_number": loan_name,
                    "loan_application_no": self.name,
                    "borrower_name": customer.full_name,
                    "addline1": addline1,
                    "addline2": addline2,
                    "addline3": addline3,
                    "city": perm_city,
                    "district": perm_dist,
                    "state": perm_state,
                    "pincode": perm_pin,
                    # "sanctioned_amount": frappe.utils.fmt_money(float(self.drawing_power)),
                    "sanctioned_amount": frappe.utils.fmt_money(
                        loan.sanctioned_limit
                        # self.increased_sanctioned_limit
                        # if self.increased_sanctioned_limit
                        # else self.drawing_power
                    ),
                    "sanctioned_amount_in_words": lms.number_to_word(
                        lms.validate_rupees(
                            float(
                                loan.sanctioned_limit
                                # self.increased_sanctioned_limit
                                # if self.increased_sanctioned_limit
                                # else self.drawing_power
                            )
                        )
                    ).title(),
                    "roi": roi_,
                    "apr": apr,
                    "documentation_charges_kfs": frappe.utils.fmt_money(
                        charges.get("documentation_charges")
                    ),
                    "processing_charges_kfs": frappe.utils.fmt_money(
                        charges.get("processing_fees")
                    ),
                    "net_disbursed_amount": frappe.utils.fmt_money(
                        float(
                            loan.sanctioned_limit
                            # self.increased_sanctioned_limit
                            # if self.increased_sanctioned_limit
                            # else self.drawing_power
                        )
                        - charges.get("total")
                    ),
                    "total_amount_to_be_paid": frappe.utils.fmt_money(
                        float(
                            loan.sanctioned_limit
                            # self.increased_sanctioned_limit
                            # if self.increased_sanctioned_limit
                            # else self.drawing_power
                        )
                        + charges.get("total")
                        + interest_charges_in_amount
                    ),
                    "loan_application_no": self.name,
                    "rate_of_interest": self.base_interest,
                    "rebate_interest": self.rebate_interest,
                    "default_interest": annual_default_interest,
                    "rebait_threshold": lender.rebait_threshold,
                    "penal_charges": lender.renewal_penal_interest
                    if lender.renewal_penal_interest
                    else "",
                    "interest_charges_in_amount": frappe.utils.fmt_money(
                        interest_charges_in_amount
                    ),
                    "interest_per_month": frappe.utils.fmt_money(interest_per_month),
                    "final_payment": frappe.utils.fmt_money(final_payment),
                    "renewal_charges": lms.validate_rupees(lender.renewal_charges)
                    if lender.renewal_charge_type == "Fix"
                    else lms.validate_percent(lender.renewal_charges),
                    "renewal_charge_type": lender.renewal_charge_type,
                    "renewal_charge_in_words": lms.number_to_word(
                        lms.validate_rupees(lender.renewal_charges)
                    ).title()
                    if lender.renewal_charge_type == "Fix"
                    else "",
                    "renewal_min_amt": lms.validate_rupees(
                        lender.renewal_minimum_amount
                    ),
                    "renewal_max_amt": lms.validate_rupees(
                        lender.renewal_maximum_amount
                    ),
                    "documentation_charge": lms.validate_rupees(
                        lender.documentation_charges
                    )
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
                    "processing_charge": lms.validate_rupees(
                        lender.lender_processing_fees
                    )
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
                    "lien_initiate_charge_type": lender.lien_initiate_charge_type,
                    "invoke_initiate_charge_type": lender.invoke_initiate_charge_type,
                    "revoke_initiate_charge_type": lender.revoke_initiate_charge_type,
                    "lien_initiate_charge_minimum_amount": lms.validate_rupees(
                        lender.lien_initiate_charge_minimum_amount
                    ),
                    "lien_initiate_charge_maximum_amount": lms.validate_rupees(
                        lender.lien_initiate_charge_maximum_amount
                    ),
                    "lien_initiate_charges": lms.validate_rupees(
                        lender.lien_initiate_charges
                    )
                    if lender.lien_initiate_charge_type == "Fix"
                    else lms.validate_percent(lender.lien_initiate_charges),
                    "invoke_initiate_charges_minimum_amount": lms.validate_rupees(
                        lender.invoke_initiate_charges_minimum_amount
                    ),
                    "invoke_initiate_charges_maximum_amount": lms.validate_rupees(
                        lender.invoke_initiate_charges_maximum_amount
                    ),
                    "invoke_initiate_charges": lms.validate_rupees(
                        lender.invoke_initiate_charges
                    )
                    if lender.invoke_initiate_charge_type == "Fix"
                    else lms.validate_percent(lender.invoke_initiate_charges),
                    "revoke_initiate_charges_minimum_amount": lms.validate_rupees(
                        lender.revoke_initiate_charges_minimum_amount
                    ),
                    "revoke_initiate_charges_maximum_amount": lms.validate_rupees(
                        lender.revoke_initiate_charges_maximum_amount
                    ),
                    "revoke_initiate_charges": lms.validate_rupees(
                        lender.revoke_initiate_charges
                    )
                    if lender.revoke_initiate_charge_type == "Fix"
                    else lms.validate_percent(lender.revoke_initiate_charges),
                }
                # doc_d = str(frappe.utils.now_datetime())
                # doc_da = doc_d.replace(" ","_")
                # doc_date = doc_da.replace(".",":")
                sanctioned_letter_pdf_file = "{}-sanctioned_letter.pdf".format(
                    self.name
                )
                sll_name = sanctioned_letter_pdf_file

                sanctioned_leter_pdf_file_path = frappe.utils.get_files_path(
                    sanctioned_letter_pdf_file
                )
                sanction_letter_template = lender.get_sanction_letter_template()

                # sanction_letter = frappe.render_template(
                #     sanction_letter_template.get_content(), {"doc": doc}
                # )

                s_letter = frappe.render_template(
                    sanction_letter_template.get_content(), {"doc": doc}
                )

                pdf_file = open(sanctioned_leter_pdf_file_path, "wb")

                # /from frappe.utils.pdf import get_pdf

                pdf = lms.get_pdf(s_letter)

                pdf_file.write(pdf)
                pdf_file.close()
                sL_letter = frappe.utils.get_url(
                    "files/{}".format(sanctioned_letter_pdf_file)
                )
            if not check:
                if not self.sanction_letter_logs:
                    sl = frappe.get_doc(
                        dict(
                            doctype="Sanction Letter and CIAL Log",
                            loan_application=self.name,
                        ),
                    ).insert(ignore_permissions=True)
                    frappe.db.commit()
                    self.sanction_letter_logs = sl.name
                    sanction_letter_table = frappe.get_all(
                        "Sanction Letter Entries",
                        filters={"renewal_application": self.name},
                        fields=["*"],
                    )
                    if not sanction_letter_table:
                        sll = frappe.get_doc(
                            {
                                "doctype": "Sanction Letter Entries",
                                "parent": sl.name,
                                "parentfield": "sl_table",
                                "parenttype": "Sanction Letter and CIAL Log",
                                "sanction_letter": sL_letter,
                                "renewal_application": self.name,
                                "date_of_acceptance": frappe.utils.now_datetime().date(),
                                "base_interest": self.base_interest,
                                "rebate_interest": self.rebate_interest,
                            }
                        ).insert(ignore_permissions=True)
                        frappe.db.commit()

            if self.status == "Approved":
                lender_esign_file = self.lender_esigned_document
                if self.lender_esigned_document:
                    lfile_name = lender_esign_file.split("files/", 1)
                    l_file = lfile_name[1]
                    pdf_file_path = frappe.utils.get_files_path(
                        l_file,
                    )
                    file_base_name = pdf_file_path.replace(".pdf", "")
                    reader = PdfReader(pdf_file_path)
                    pages = [
                        23,
                        24,
                        25,
                        26,
                        27,
                        28,
                        29,
                        30,
                    ]  # page 1, 3, 5
                    pdfWriter = PdfWriter()
                    for page_num in pages:
                        pdfWriter.add_page(reader.pages[page_num])
                    sanction_letter_esign = "Sanction_letter_{0}.pdf".format(self.name)
                    sanction_letter_esign_path = frappe.utils.get_files_path(
                        sanction_letter_esign
                    )
                    if os.path.exists(sanction_letter_esign_path):
                        os.remove(sanction_letter_esign_path)
                    sanction_letter_esign_document = frappe.utils.get_url(
                        "files/{}".format(sanction_letter_esign)
                    )
                    sanction_letter_esign = frappe.utils.get_files_path(
                        sanction_letter_esign
                    )

                    with open(sanction_letter_esign, "wb") as f:
                        pdfWriter.write(f)
                        f.close()
                    sl = frappe.get_all(
                        "Sanction Letter Entries",
                        filters={"renewal_application": self.name},
                        fields=["*"],
                    )
                    # loan_name = ""
                    # if not check and self.loan:
                    #     loan_name = loan.name
                    # elif check:
                    #     loan_name = check
                    # frappe.db.set_value(
                    #     "Sanction Letter and CIAL Log", self.sl_entries, "loan", loan_name
                    # )
                    if sl:
                        sll = frappe.get_doc("Sanction Letter Entries", sl[0].name)
                        sll.sanction_letter = sanction_letter_esign_document
                        sll.save()
                        frappe.db.commit()
            return
        except Exception:
            frappe.log_error(
                message=frappe.get_traceback(),
                title=(_("Sanction Letter failed in Loan Renewal")),
            )

    def two_days_grace_period(self):
        try:
            updated_kyc = ""
            if self.new_kyc_name:
                updated_kyc = frappe.get_doc("User KYC", self.new_kyc_name)
            if updated_kyc and updated_kyc.kyc_status == "Approved":
                loan = frappe.get_doc("Loan", self.loan)
                # exp = datetime.strptime(str(loan.expiry_date), "%Y-%m-%d").date()
                is_expired_date = datetime.strptime(
                    str(loan.expiry_date), "%Y-%m-%d"
                ) + timedelta(days=14)
                if type(is_expired_date) is str:
                    is_expired_date = datetime.strptime(
                        str(loan.expiry_date), "%Y-%m-%d"
                    )

                if type(loan.expiry_date) is str:
                    date_1 = datetime.strptime(
                        self.kyc_approval_date, "%Y-%m-%d %H:%M:%S"
                    )
                else:
                    date_1 = self.kyc_approval_date

                if date_1.date() > is_expired_date.date():
                    extended_two_days = date_1 + timedelta(days=2)
                    seconds = abs(
                        extended_two_days - frappe.utils.now_datetime()
                    ).total_seconds()
                    # seconds = abs(extended_two_days).total_seconds()
                    renewal_timer = lms.convert_sec_to_hh_mm_ss(
                        seconds, is_for_days=True
                    )
                    self.time_remaining = renewal_timer

        except Exception:
            frappe.log_error(
                message=frappe.get_traceback()
                + "Loan Renewal Application : {}".format(self.name),
                title=(_("Two_days_grace_period")),
            )


@frappe.whitelist()
def customer_reminder(doc_name):
    try:
        las_settings = frappe.get_single("LAS Settings")
        renewal_doc = frappe.get_doc("Spark Loan Renewal Application", doc_name)
        loan = frappe.get_doc("Loan", renewal_doc.loan)
        try:
            customer = frappe.get_doc("Loan Customer", renewal_doc.customer)
        except Exception as e:
            frappe.log_error(
                message=frappe.get_traceback(),
                title=(_("Loan Customer {} not found".format(renewal_doc.customer))),
            )
        doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
        doc["loan_renewal_application"] = {"status": renewal_doc.status}

        if renewal_doc.status == "Pending":
            kyc_doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
            email_expiry = frappe.db.sql(
                "select message from `tabNotification` where name='Loan Renewal Reminder';"
            )[0][0]
            exp = datetime.strptime(str(loan.expiry_date), "%Y-%m-%d").strftime(
                "%d-%m-%Y"
            )
            expiry = exp.replace("-", "/")
            email_expiry = email_expiry.replace("loan_name", str(loan.name))
            email_expiry = email_expiry.replace("expiry_date", str(expiry))
            email_expiry = email_expiry.replace(
                "dlt_link", las_settings.app_login_dashboard
            )
            frappe.enqueue(
                method=frappe.sendmail,
                recipients=[customer.user],
                sender=None,
                subject="Loan Renewal Reminder",
                message=email_expiry,
                queue="short",
                delayed=False,
                job_name="Loan Renewal Reminder",
            )
            msg = """Dear Customer,
Your loan account number {loan_name} is due for renewal on or before {expiry_date}. Click on the link {link} to submit your request - Spark Loans
""".format(
                loan_name=renewal_doc.loan,
                expiry_date=loan.expiry_date,
                link=las_settings.app_login_dashboard,
            )
            fcm_notification = frappe.get_doc(
                "Spark Push Notification",
                "Loan Renewal Reminder",
                fields=["*"],
            )
            send_spark_push_notification(
                fcm_notification=fcm_notification,
                loan=loan.name,
                customer=customer,
            )
            if msg:
                receiver_list = [str(customer.phone)]
                if customer.get_kyc().mob_num:
                    receiver_list.append(str(customer.get_kyc().mob_num))
                if customer.get_kyc().choice_mob_no:
                    receiver_list.append(str(customer.get_kyc().choice_mob_no))

                receiver_list = list(set(receiver_list))

                frappe.enqueue(
                    method=send_sms,
                    receiver_list=receiver_list,
                    msg=msg,
                )
    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=_("Loan Renewal Application - Notify Customer"),
        )


@frappe.whitelist()
def all_loans_renewal_update_doc():
    try:
        loans = frappe.get_all("Loan", fields=["name"])
        for loan_name in loans:
            frappe.enqueue(
                method="lms.lms.doctype.spark_loan_renewal_application.spark_loan_renewal_application.loan_renewal_update_doc",
                queue="long",
                loan_name=loan_name,
                job_name="{}-Loan Renewal Update Doc".format(loan_name),
            )
            frappe.enqueue(
                method="lms.lms.doctype.spark_loan_renewal_application.spark_loan_renewal_application.renewal_penal_interest",
                queue="long",
                loan_name=loan_name,
                job_name="{}-Renewal Penal Interest".format(loan_name),
            )
        frappe.enqueue(
            method="lms.lms.doctype.spark_loan_renewal_application.spark_loan_renewal_application.renewal_timer",
            queue="long",
            job_name="Renewal Timer",
        )
        # frappe.enqueue(
        #     method="lms.lms.doctype.spark_loan_renewal_application.spark_loan_renewal_application.renewal_doc_for_selected_customer",
        #     queue="long",
        #     job_name="Renewal doc for Selected Customer",
        # )

    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=_("All Loans Renewal Update Doc Error"),
        )


@frappe.whitelist()
def renewal_penal_interest(loan_name):
    try:
        loan = frappe.get_doc("Loan", loan_name)
        pending_renewal_doc_list = frappe.get_all(
            "Spark Loan Renewal Application",
            filters={"loan": loan.name, "status": "Pending"},
            fields=["*"],
        )
        try:
            customer = frappe.get_doc("Loan Customer", loan.customer)
        except Exception:
            customer = ""
            frappe.log_error(
                message=frappe.get_traceback(),
                title=(_("Loan Customer {} not found".format(loan.customer))),
            )

        user_kyc_approved = ""
        user_kyc = ""
        if customer:
            user_kyc = frappe.get_all(
                "User KYC",
                filters={
                    "user": customer.user,
                    "updated_kyc": 1,
                    "kyc_status": "Pending",
                },
                fields=["*"],
            )

            user_kyc_approved = frappe.get_all(
                "User KYC",
                filters={
                    "user": customer.user,
                    "updated_kyc": 1,
                    "kyc_status": "Approved",
                },
                fields=["*"],
            )
        applications = []

        current_date = frappe.utils.now_datetime().date()
        exp = datetime.strptime(str(loan.expiry_date), "%Y-%m-%d").date()
        greater_than_7 = exp + timedelta(days=7)
        more_than_7 = greater_than_7 + timedelta(days=7)
        is_expired_date = datetime.strptime(
            str(loan.expiry_date), "%Y-%m-%d"
        ) + timedelta(days=14)

        if (
            (pending_renewal_doc_list and not user_kyc and not user_kyc_approved)
            or (user_kyc_approved and pending_renewal_doc_list)
        ) and (
            (
                greater_than_7 > current_date
                or more_than_7 > current_date
                or (
                    user_kyc_approved
                    and pending_renewal_doc_list
                    and pending_renewal_doc_list[0].kyc_approval_date < is_expired_date
                )
            )
            and (exp + timedelta(days=1)) < current_date
            and loan.balance > 0
        ):
            top_up_application = frappe.get_all(
                "Top up Application",
                filters={
                    "loan": loan.name,
                    "status": ["IN", ["Pending", "Esign Done"]],
                },
                fields=["name"],
            )
            for i in top_up_application:
                applications.append(i)
            loan_application = frappe.get_all(
                "Loan Application",
                filters={
                    "loan": loan.name,
                    "status": ["not IN", ["Rejected", "Approved"]],
                },
                fields=["name"],
            )
            for i in loan_application:
                applications.append(i)
            if not top_up_application and not loan_application:
                current_year = frappe.utils.now_datetime().strftime("%Y")
                current_year = int(current_year)
                if (
                    (current_year % 400 == 0)
                    or (current_year % 100 != 0)
                    and (current_year % 4 == 0)
                ):
                    no_of_days = 366
                # Else it is not a leap year
                else:
                    no_of_days = 365
                renewal_penal_interest = frappe.get_doc("Lender", loan.lender)
                daily_penal_interest = (
                    float(renewal_penal_interest.renewal_penal_interest) / no_of_days
                )
                amount = loan.balance * (daily_penal_interest / 100)
                penal_interest_transaction = frappe.get_doc(
                    {
                        "doctype": "Loan Transaction",
                        "loan": loan.name,
                        "lender": loan.lender,
                        "transaction_type": "Penal Interest",
                        "record_type": "DR",
                        "amount": round(amount, 2),
                        "unpaid_interest": round(amount, 2),
                        "time": current_date,
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
                frappe.db.commit()

        pending_renewal_doc_list = frappe.get_all(
            "Spark Loan Renewal Application",
            filters={"loan": loan.name, "status": "Pending"},
            fields=["*"],
        )
        is_expired_date = exp + timedelta(days=7)
        if pending_renewal_doc_list:
            for renewal_doc in pending_renewal_doc_list:
                doc = frappe.get_doc("Spark Loan Renewal Application", renewal_doc.name)

                if (
                    not user_kyc
                    and not user_kyc_approved
                    and is_expired_date < frappe.utils.now_datetime().date()
                ) or (
                    user_kyc_approved
                    and not user_kyc
                    and is_expired_date < frappe.utils.now_datetime().date()
                    and (is_expired_date + timedelta(days=7))
                    > frappe.utils.now_datetime().date()
                    and doc.status == "Pending"
                ):
                    doc.status = "Rejected"
                    doc.workflow_state = "Rejected"
                    doc.remarks = "Is Expired"
                if (
                    doc.new_kyc_name
                    and doc.kyc_approval_date
                    and frappe.utils.now_datetime() > doc.kyc_approval_date
                    and doc.tnc_show == 0
                    and (is_expired_date + timedelta(days=7))
                    < frappe.utils.now_datetime().date()
                ):
                    doc.tnc_show = 1
                doc.save(ignore_permissions=True)
                frappe.db.commit()

    except Exception:
        frappe.log_error(
            message=frappe.get_traceback()
            + "\nLoan Renewal Application Name : {}".format(loan.name),
            title=_("Loan Renewal Penal Interest Error"),
        )


@frappe.whitelist()
def renewal_timer(loan_renewal_name=None):
    try:
        if loan_renewal_name:
            renewal_doc = frappe.get_doc(
                "Spark Loan Renewal Application", loan_renewal_name
            )
            loan = frappe.get_doc("Loan", renewal_doc.loan)
            try:
                customer = frappe.get_doc("Loan Customer", loan.customer)
            except Exception:
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=(_("Loan Customer {} not found".format(loan.customer))),
                )
            if type(loan.expiry_date) is str:
                exp = datetime.strptime(str(loan.expiry_date), "%Y-%m-%d").date()
            else:
                exp = loan.expiry_date
            loan_expiry = datetime.combine(exp, time.min)

            # user_kyc = frappe.get_all(
            #     "User KYC",
            #     filters={
            #         "user": customer.user,
            #         "updated_kyc": 1,
            #     },
            #     fields=["*"],
            # )
            user_kyc_pending = frappe.get_all(
                "User KYC",
                filters={
                    "user": customer.user,
                    "updated_kyc": 1,
                    "kyc_status": "Pending",
                },
                fields=["*"],
            )
            top_up_application = frappe.get_all(
                "Top up Application",
                filters={"loan": loan.name, "status": "Pending"},
                fields=["name"],
            )

            loan_application = frappe.get_all(
                "Loan Application",
                filters={
                    "loan": loan.name,
                    "status": ["not IN", ["Approved", "Rejected"]],
                },
                fields=["name"],
            )
            if top_up_application or loan_application:
                action_status = "Pending"
            else:
                action_status = ""
            frappe.db.set_value(
                "Spark Loan Renewal Application",
                renewal_doc.name,
                "action_status",
                action_status,
                update_modified=False,
            )
            date_7after_expiry = loan_expiry + timedelta(days=8)
            if (
                frappe.utils.now_datetime().date() > exp
                and frappe.utils.now_datetime().date() <= (exp + timedelta(days=7))
                and renewal_doc.status not in ["Approved", "Rejected"]
            ):
                seconds = abs(
                    date_7after_expiry - frappe.utils.now_datetime()
                ).total_seconds()
                renewal_timer = lms.convert_sec_to_hh_mm_ss(seconds, is_for_days=True)
                frappe.db.set_value(
                    "Spark Loan Renewal Application",
                    renewal_doc.name,
                    "time_remaining",
                    renewal_timer,
                    update_modified=False,
                )

            elif (
                frappe.utils.now_datetime().date()
                > (renewal_doc.creation.date() + timedelta(days=7))
                and frappe.utils.now_datetime().date()
                < (renewal_doc.creation.date() + timedelta(days=14))
                and renewal_doc.status not in ["Approved", "Rejected"]
            ):
                date_time = datetime.combine(renewal_doc.creation, time.min)
                date_7after_expiry = date_time + timedelta(days=14)
                seconds = abs(
                    date_7after_expiry - frappe.utils.now_datetime()
                ).total_seconds()
                renewal_timer = lms.convert_sec_to_hh_mm_ss(seconds, is_for_days=True)
                frappe.db.set_value(
                    "Spark Loan Renewal Application",
                    renewal_doc.name,
                    "time_remaining",
                    renewal_timer,
                    update_modified=False,
                )
            elif (
                frappe.utils.now_datetime().date() > (exp + timedelta(days=7))
                and frappe.utils.now_datetime().date() <= (exp + timedelta(days=14))
                and user_kyc_pending
            ):
                seconds = abs(
                    (date_7after_expiry + timedelta(days=7))
                    - frappe.utils.now_datetime()
                ).total_seconds()
                renewal_timer = lms.convert_sec_to_hh_mm_ss(seconds, is_for_days=True)
                frappe.db.set_value(
                    "Spark Loan Renewal Application",
                    renewal_doc.name,
                    "time_remaining",
                    renewal_timer,
                    update_modified=False,
                )

            elif renewal_doc and renewal_doc.new_kyc_name:
                updated_kyc = frappe.get_doc("User KYC", renewal_doc.new_kyc_name)
                if updated_kyc and updated_kyc.kyc_status == "Approved":
                    loan = frappe.get_doc("Loan", renewal_doc.loan)
                    # exp = datetime.strptime(str(loan.expiry_date), "%Y-%m-%d").date()
                    is_expired_date = datetime.strptime(
                        str(loan.expiry_date), "%Y-%m-%d"
                    ) + timedelta(days=14)
                    date_1 = renewal_doc.kyc_approval_date.date()
                    extended_two_days = renewal_doc.kyc_approval_date + timedelta(
                        days=2
                    )
                    if (
                        date_1 > is_expired_date.date()
                        and frappe.utils.now_datetime() < extended_two_days
                    ):
                        seconds = abs(
                            extended_two_days - frappe.utils.now_datetime()
                        ).total_seconds()
                        # seconds = abs(extended_two_days).total_seconds()
                        renewal_timer = lms.convert_sec_to_hh_mm_ss(
                            seconds, is_for_days=True
                        )
                        frappe.db.set_value(
                            "Spark Loan Renewal Application",
                            renewal_doc.name,
                            "time_remaining",
                            renewal_timer,
                            update_modified=False,
                        )
                    else:
                        seconds = 0
                        renewal_timer = lms.convert_sec_to_hh_mm_ss(
                            seconds, is_for_days=True
                        )
                        frappe.db.set_value(
                            "Spark Loan Renewal Application",
                            renewal_doc.name,
                            {"time_remaining": renewal_timer, "tnc_show": 1},
                            update_modified=False,
                        )

            else:
                seconds = 0
                renewal_timer = lms.convert_sec_to_hh_mm_ss(seconds, is_for_days=True)
                frappe.db.set_value(
                    "Spark Loan Renewal Application",
                    renewal_doc.name,
                    {"time_remaining": renewal_timer, "tnc_show": 1},
                    update_modified=False,
                )

        else:
            loans = frappe.get_all("Loan", fields=["*"])
            for loan in loans:
                try:
                    customer = frappe.get_doc("Loan Customer", loan.customer)
                except Exception:
                    frappe.log_error(
                        message=frappe.get_traceback(),
                        title=(_("Loan Customer {} not found".format(loan.customer))),
                    )
                # user_kyc = frappe.get_all(
                #     "User KYC",
                #     filters={
                #         "user": customer.user,
                #         "updated_kyc": 1,
                #     },
                #     fields=["*"],
                # )
                top_up_application = frappe.get_all(
                    "Top up Application",
                    filters={
                        "loan": loan.name,
                        "status": [
                            "IN",
                            ["Pending", "Esign Done"],
                        ],
                    },
                    fields=["name"],
                )

                loan_application = frappe.get_all(
                    "Loan Application",
                    filters={
                        "loan": loan.name,
                        "application_type": [
                            "IN",
                            ["Increase Loan", "Pledge More", "Margin Shortfall"],
                        ],
                    },
                    fields=["name"],
                )

                renewal_doc_list = frappe.get_all(
                    "Spark Loan Renewal Application",
                    filters={
                        "loan": loan.name,
                        "status": ["NOT IN", ["Approved", "Rejected"]],
                    },
                    fields=["*"],
                )
                if top_up_application or loan_application and renewal_doc_list:
                    action_status = "Pending"
                else:
                    action_status = ""

                if renewal_doc_list:
                    renewal_doc = frappe.get_doc(
                        "Spark Loan Renewal Application", renewal_doc_list[0].name
                    )

                    frappe.db.set_value(
                        "Spark Loan Renewal Application",
                        renewal_doc.name,
                        "action_status",
                        action_status,
                        update_modified=False,
                    )

                user_kyc_pending = frappe.get_all(
                    "User KYC",
                    filters={
                        "user": customer.user,
                        "updated_kyc": 1,
                        "kyc_status": "Pending",
                    },
                    fields=["*"],
                )
                renewal_doc_pending_list = frappe.get_all(
                    "Spark Loan Renewal Application",
                    filters={"loan": loan.name, "status": "Pending"},
                    fields=["*"],
                )

                if type(loan.expiry_date) is str:
                    exp = datetime.strptime(str(loan.expiry_date), "%Y-%m-%d").date()
                else:
                    exp = loan.expiry_date

                loan_expiry = datetime.combine(exp, time.min)
                date_7after_expiry = loan_expiry + timedelta(days=8)

                if (
                    frappe.utils.now_datetime().date() > loan.expiry_date
                    and frappe.utils.now_datetime().date()
                    <= (loan.expiry_date + timedelta(days=7))
                    and renewal_doc_list
                ):
                    seconds = abs(
                        date_7after_expiry - frappe.utils.now_datetime()
                    ).total_seconds()
                    renewal_timer = lms.convert_sec_to_hh_mm_ss(
                        seconds, is_for_days=True
                    )

                    frappe.db.set_value(
                        "Spark Loan Renewal Application",
                        renewal_doc.name,
                        "time_remaining",
                        renewal_timer,
                        update_modified=False,
                    )

                elif (
                    frappe.utils.now_datetime().date()
                    > (loan.expiry_date + timedelta(days=7))
                    and frappe.utils.now_datetime().date()
                    <= (loan.expiry_date + timedelta(days=14))
                    and user_kyc_pending
                    and renewal_doc_pending_list
                ):
                    seconds = abs(
                        (date_7after_expiry + timedelta(days=7))
                        - frappe.utils.now_datetime()
                    ).total_seconds()
                    renewal_timer = lms.convert_sec_to_hh_mm_ss(
                        seconds, is_for_days=True
                    )
                    renewal_doc = frappe.get_doc(
                        "Spark Loan Renewal Application",
                        renewal_doc_pending_list[0].name,
                    )

                    frappe.db.set_value(
                        "Spark Loan Renewal Application",
                        renewal_doc.name,
                        "time_remaining",
                        renewal_timer,
                        update_modified=False,
                    )

    except Exception:
        frappe.log_error(
            message=frappe.get_traceback()
            + "loan renewal application : {}".format(
                loan_renewal_name if loan_renewal_name else ""
            ),
            title=_("Loan Renewal Application  - Timer Function"),
        )


def loan_renewal_update_doc(loan_name):
    try:
        loan = frappe.get_doc("Loan", loan_name)
        las_settings = frappe.get_single("LAS Settings")
        str_exp = datetime.strptime(str(loan.expiry_date), "%Y-%m-%d").strftime(
            "%d/%m/%Y"
        )
        renewal_doc_list = frappe.get_all(
            "Spark Loan Renewal Application",
            filters={"loan": loan.name, "status": ["not in", ["Rejected", "Approved"]]},
            fields=["name"],
        )
        msg = ""
        fcm_notification = {}

        for i in renewal_doc_list:
            doc = frappe.get_doc("Spark Loan Renewal Application", i.name)
            exp = datetime.strptime(str(loan.expiry_date), "%Y-%m-%d").date()
            if (exp < frappe.utils.now_datetime().date() and doc.is_expired == 0) or (
                doc.creation.date() + timedelta(days=7)
                == frappe.utils.now_datetime().date()
                and doc.is_expired == 0
            ):
                doc.is_expired = 1
                doc.save(ignore_permissions=True)
                frappe.db.commit()

        existing_renewal_doc_list = frappe.get_all(
            "Spark Loan Renewal Application",
            filters={"loan": loan.name, "status": "Pending"},
            fields=["*"],
        )

        try:
            customer = frappe.get_doc("Loan Customer", loan.customer)
        except Exception:
            customer = ""
            frappe.log_error(
                message=frappe.get_traceback() + "\nLoan Name : {}".format(loan.name),
                title=(_("Loan Customer {} not found".format(loan.customer))),
            )
        user_kyc = ""
        if customer:
            user_kyc = frappe.get_all(
                "User KYC",
                filters={
                    "user": customer.user,
                    "updated_kyc": 1,
                    "kyc_status": ["in", ["Pending", "Approved"]],
                },
                fields=["name"],
            )

        expiry_date = frappe.utils.now_datetime().date() + timedelta(days=29)
        if type(loan.expiry_date) == str:
            exp = datetime.strptime(loan.expiry_date, "%Y-%m-%d").date()
        else:
            exp = loan.expiry_date

        if (
            existing_renewal_doc_list
            and exp < frappe.utils.now_datetime().date()
            and frappe.utils.now_datetime().date() < exp + timedelta(days=2)
        ) or (
            existing_renewal_doc_list
            and user_kyc
            and (exp + timedelta(days=7)) < frappe.utils.now_datetime().date()
            and frappe.utils.now_datetime().date() < exp + timedelta(days=9)
        ):
            # if frappe.utils.now_datetime().date() < exp + timedelta(days=2):
            #     expiry = exp
            # else:
            #     expiry = exp + timedelta(days=7)

            email_expiry = frappe.db.sql(
                "select message from `tabNotification` where name='Loan Renewal Extension';"
            )[0][0]
            email_expiry = email_expiry.replace("loan_name", loan.name)
            email_expiry = email_expiry.replace("expiry_date", str_exp)
            email_expiry = email_expiry.replace(
                "dlt_link", las_settings.app_login_dashboard
            )
            frappe.enqueue(
                method=frappe.sendmail,
                recipients=[customer.user],
                subject="Loan Renewal Extension",
                message=email_expiry,
                queue="short",
                job_name="Loan Renewal Extension",
            )
            msg = """Dear Customer,
You have received a loan renewal extension of 7 days from the current expiry date: {expiry_date}. Click here to continue {link} - Spark Loan""".format(
                expiry_date=str_exp,
                link=las_settings.app_login_dashboard,
            )

            fcm_notification = frappe.get_doc(
                "Spark Push Notification",
                "Loan Renewal Extension",
                fields=["*"],
            )
            # send_spark_push_notification(
            #     fcm_notification=fcm_notification,
            #     loan=loan.name,
            #     customer=customer,
            # )
            # if msg:
            #     receiver_list = [str(customer.phone)]
            #     if customer.get_kyc().mob_num:
            #         receiver_list.append(str(customer.get_kyc().mob_num))
            #     if customer.get_kyc().choice_mob_no:
            #         receiver_list.append(str(customer.get_kyc().choice_mob_no))

            #     receiver_list = list(set(receiver_list))
            #     frappe.enqueue(
            #         method=send_sms,
            #         receiver_list=receiver_list,
            #         msg=msg,
            #     )

        if (
            exp == expiry_date
            and loan.total_collateral_value > 0
            and len(loan.items) > 0
        ):
            wef_date = loan.wef_date
            if type(wef_date) is str:
                wef_date = datetime.strptime(str(wef_date), "%Y-%m-%d").date()
            if (
                wef_date >= frappe.utils.now_datetime().date() and loan.is_default == 0
            ) or (
                loan.old_is_default == 0
                and wef_date >= frappe.utils.now_datetime().date()
            ):
                custom_base_interest = loan.old_interest
                custom_rebate_interest = loan.old_rebate_interest
            else:
                custom_base_interest = loan.custom_base_interest
                custom_rebate_interest = loan.custom_rebate_interest
            renewal_doc = frappe.get_doc(
                dict(
                    doctype="Spark Loan Renewal Application",
                    loan=loan.name,
                    lender=loan.lender,
                    old_kyc_name=customer.choice_kyc,
                    total_collateral_value=loan.total_collateral_value,
                    sanctioned_limit=loan.sanctioned_limit,
                    drawing_power=loan.drawing_power,
                    customer=customer.name,
                    customer_name=customer.full_name,
                    custom_base_interest=custom_base_interest,
                    custom_rebate_interest=custom_rebate_interest,
                    remarks="",
                )
            ).insert(ignore_permissions=True)
            frappe.db.commit()
            email_expiry = frappe.db.sql(
                "select message from `tabNotification` where name='Loan Renewal Reminder';"
            )[0][0]
            email_expiry = email_expiry.replace("loan_name", str(loan.name))
            email_expiry = email_expiry.replace("expiry_date", str_exp)
            email_expiry = email_expiry.replace(
                "dlt_link", str(las_settings.app_login_dashboard)
            )
            frappe.enqueue(
                method=frappe.sendmail,
                recipients=[customer.user],
                subject="Loan Renewal Reminder",
                message=email_expiry,
                queue="short",
                job_name="Loan Renewal Reminder",
            )
            msg = """Dear Customer,
Your loan account number {loan_name} is due for renewal on or before {expiry_date}. Click on the link {link} to submit your request - Spark Loans""".format(
                loan_name=loan.name,
                expiry_date=str_exp,
                link=las_settings.app_login_dashboard,
            )
            fcm_notification = frappe.get_doc(
                "Spark Push Notification",
                "Loan Renewal Reminder",
                fields=["*"],
            )
            # send_spark_push_notification(
            #     fcm_notification=fcm_notification,
            #     loan=loan.name,
            #     customer=customer,
            # )
            # if msg:
            #     receiver_list = [str(customer.phone)]
            #     if customer.get_kyc().mob_num:
            #         receiver_list.append(str(customer.get_kyc().mob_num))
            #     if customer.get_kyc().choice_mob_no:
            #         receiver_list.append(str(customer.get_kyc().choice_mob_no))

            #     receiver_list = list(set(receiver_list))
            #     frappe.enqueue(
            #         method=send_sms,
            #         receiver_list=receiver_list,
            #         msg=msg,
            #     )

            renewal_doc.reminders = 1
            renewal_doc.save(ignore_permissions=True)
            frappe.db.commit()

        for doc in existing_renewal_doc_list:
            if (
                exp == frappe.utils.now_datetime().date() + timedelta(days=19)
                and doc.reminders == 1
            ):
                renewal_doc = frappe.get_doc("Spark Loan Renewal Application", doc.name)
                email_expiry = frappe.db.sql(
                    "select message from `tabNotification` where name='Loan Renewal Reminder';"
                )[0][0]
                email_expiry = email_expiry.replace("loan_name", str(loan.name))
                email_expiry = email_expiry.replace("expiry_date", str_exp)
                email_expiry = email_expiry.replace(
                    "dlt_link", str(las_settings.app_login_dashboard)
                )
                frappe.enqueue(
                    method=frappe.sendmail,
                    recipients=[customer.user],
                    sender=None,
                    subject="Loan Renewal Reminder",
                    message=email_expiry,
                    queue="short",
                    delayed=False,
                    job_name="Loan Renewal Reminder",
                )
                msg = """Dear Customer,
Your loan account number {loan_name} is due for renewal on or before {expiry_date}. Click on the link {link} to submit your request - Spark Loans""".format(
                    loan_name=loan.name,
                    expiry_date=str_exp,
                    link=las_settings.app_login_dashboard,
                )
                fcm_notification = frappe.get_doc(
                    "Spark Push Notification",
                    "Loan Renewal Reminder",
                    fields=["*"],
                )
                # send_spark_push_notification(
                #     fcm_notification=fcm_notification,
                #     loan=loan.name,
                #     customer=customer,
                # )
                # if msg:
                #     receiver_list = [str(customer.phone)]
                #     if customer.get_kyc().mob_num:
                #         receiver_list.append(str(customer.get_kyc().mob_num))
                #     if customer.get_kyc().choice_mob_no:
                #         receiver_list.append(str(customer.get_kyc().choice_mob_no))

                #     receiver_list = list(set(receiver_list))

                #     frappe.enqueue(
                #         method=send_sms,
                #         receiver_list=receiver_list,
                #         msg=msg,
                #     )

                renewal_doc.reminders = 2
                renewal_doc.save(ignore_permissions=True)
                frappe.db.commit()

            elif (
                exp == frappe.utils.now_datetime().date() + timedelta(days=9)
                and doc.reminders == 2
            ):
                renewal_doc = frappe.get_doc("Spark Loan Renewal Application", doc.name)
                email_expiry = frappe.db.sql(
                    "select message from `tabNotification` where name='Loan Renewal Reminder';"
                )[0][0]
                email_expiry = email_expiry.replace("loan_name", str(loan.name))
                email_expiry = email_expiry.replace("expiry_date", str_exp)
                email_expiry = email_expiry.replace(
                    "dlt_link", str(las_settings.app_login_dashboard)
                )
                frappe.enqueue(
                    method=frappe.sendmail,
                    recipients=[customer.user],
                    sender=None,
                    subject="Loan Renewal Reminder",
                    message=email_expiry,
                    queue="short",
                    delayed=False,
                    job_name="Loan Renewal Reminder",
                )
                msg = """Dear Customer,
Your loan account number {loan_name} is due for renewal on or before {expiry_date}. Click on the link {link} to submit your request - Spark Loans""".format(
                    loan_name=loan.name,
                    expiry_date=str_exp,
                    link=las_settings.app_login_dashboard,
                )
                fcm_notification = frappe.get_doc(
                    "Spark Push Notification",
                    "Loan Renewal Reminder",
                    fields=["*"],
                )
                # send_spark_push_notification(
                #     fcm_notification=fcm_notification,
                #     loan=loan.name,
                #     customer=customer,
                # )
                # if msg:
                #     receiver_list = [str(customer.phone)]
                #     if customer.get_kyc().mob_num:
                #         receiver_list.append(str(customer.get_kyc().mob_num))
                #     if customer.get_kyc().choice_mob_no:
                #         receiver_list.append(str(customer.get_kyc().choice_mob_no))

                #     receiver_list = list(set(receiver_list))

                #     frappe.enqueue(
                #         method=send_sms,
                #         receiver_list=receiver_list,
                #         msg=msg,
                #     )

                renewal_doc.reminders = 3
                renewal_doc.save(ignore_permissions=True)
                frappe.db.commit()

            elif (
                exp == frappe.utils.now_datetime().date() + timedelta(days=2)
                and doc.reminders == 3
            ):
                renewal_doc = frappe.get_doc("Spark Loan Renewal Application", doc.name)
                email_expiry = frappe.db.sql(
                    "select message from `tabNotification` where name='Loan Renewal Reminder';"
                )[0][0]
                email_expiry = email_expiry.replace("loan_name", str(loan.name))
                email_expiry = email_expiry.replace("expiry_date", str_exp)
                email_expiry = email_expiry.replace(
                    "dlt_link", str(las_settings.app_login_dashboard)
                )
                frappe.enqueue(
                    method=frappe.sendmail,
                    recipients=[customer.user],
                    sender=None,
                    subject="Loan Renewal Reminder",
                    message=email_expiry,
                    queue="short",
                    delayed=False,
                    job_name="Loan Renewal Reminder",
                )
                msg = """Dear Customer,
Your loan account number {loan_name} is due for renewal on or before {expiry_date}. Click on the link {link} to submit your request - Spark Loans""".format(
                    loan_name=loan.name,
                    expiry_date=str_exp,
                    link=las_settings.app_login_dashboard,
                )

                fcm_notification = frappe.get_doc(
                    "Spark Push Notification",
                    "Loan Renewal Reminder",
                    fields=["*"],
                )
                # send_spark_push_notification(
                #     fcm_notification=fcm_notification,
                #     loan=loan.name,
                #     customer=customer,
                # )
                # if msg:
                #     receiver_list = [str(customer.phone)]
                #     if customer.get_kyc().mob_num:
                #         receiver_list.append(str(customer.get_kyc().mob_num))
                #     if customer.get_kyc().choice_mob_no:
                #         receiver_list.append(str(customer.get_kyc().choice_mob_no))

                #     receiver_list = list(set(receiver_list))

                #     frappe.enqueue(
                #         method=send_sms,
                #         receiver_list=receiver_list,
                #         msg=msg,
                #     )

                renewal_doc.reminders = 4
                renewal_doc.save(ignore_permissions=True)
                frappe.db.commit()

        if fcm_notification and msg:
            send_spark_push_notification(
                fcm_notification=fcm_notification,
                loan=loan.name,
                customer=customer,
            )
            receiver_list = [str(customer.phone)]
            if customer.get_kyc().mob_num:
                receiver_list.append(str(customer.get_kyc().mob_num))
            if customer.get_kyc().choice_mob_no:
                receiver_list.append(str(customer.get_kyc().choice_mob_no))

            receiver_list = list(set(receiver_list))

            frappe.enqueue(
                method=send_sms,
                receiver_list=receiver_list,
                msg=msg,
            )
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback() + "Loan Name : {}".format(loan_name),
            title=_("Loan Renewal Application - Update Doc"),
        )


# def renewal_doc_for_selected_customer():
#     try:
#         loan_name_list = ["SL000004", "SL000026"]
#         las_settings = frappe.get_single("LAS Settings")
#         for i in loan_name_list:
#             loan = frappe.get_doc("Loan", str(i))
#             # las_settings = frappe.get_single("LAS Settings")
#             # str_exp = datetime.strptime(str(loan.expiry_date), "%Y-%m-%d").strftime(
#             #     "%d/%m/%Y"
#             # )
#             # renewal_doc_list = frappe.get_all(
#             #     "Spark Loan Renewal Application",
#             #     filters={"loan": loan.name, "status": ["!=", "Rejected"]},
#             #     fields=["name"],
#             # )
#             pending_renewal_doc_list = frappe.get_all(
#                 "Spark Loan Renewal Application",
#                 filters={"loan": loan.name, "status": "Pending"},
#                 fields=["*"],
#             )
#             try:
#                 customer = frappe.get_doc("Loan Customer", loan.customer)
#             except Exception:
#                 frappe.log_error(
#                     message=frappe.get_traceback(),
#                     title=(_("Loan Customer {} not found".format(loan.customer))),
#                 )
#             user_kyc = frappe.get_all(
#                 "User KYC",
#                 filters={
#                     "user": customer.user,
#                     "updated_kyc": 1,
#                     "kyc_status": "Pending",
#                 },
#                 fields=["*"],
#             )
#             user_kyc_approved = frappe.get_all(
#                 "User KYC",
#                 filters={
#                     "user": customer.user,
#                     "updated_kyc": 1,
#                     "kyc_status": "Approved",
#                 },
#                 fields=["*"],
#             )
#             existing_renewal_doc = frappe.get_all(
#                 "Spark Loan Renewal Application", filters={"loan": i}
#             )
#             if not existing_renewal_doc and len(loan.items) > 0:
#                 wef_date = loan.wef_date
#                 if type(wef_date) is str:
#                     wef_date = datetime.strptime(str(wef_date), "%Y-%m-%d").date()
#                 custom_base_interest = (
#                     loan.old_interest
#                     if wef_date >= frappe.utils.now_datetime().date()
#                     else loan.custom_base_interest
#                 )
#                 custom_rebate_interest = (
#                     loan.old_rebate_interest
#                     if wef_date >= frappe.utils.now_datetime().date()
#                     else loan.custom_rebate_interest
#                 )
#                 renewal_doc = frappe.get_doc(
#                     dict(
#                         doctype="Spark Loan Renewal Application",
#                         loan=loan.name,
#                         lender=loan.lender,
#                         old_kyc_name=customer.choice_kyc,
#                         total_collateral_value=loan.total_collateral_value,
#                         sanctioned_limit=loan.sanctioned_limit,
#                         drawing_power=loan.drawing_power,
#                         customer=customer.name,
#                         customer_name=customer.full_name,
#                         custom_base_interest=custom_base_interest,
#                         custom_rebate_interest=custom_rebate_interest,
#                         remarks="",
#                     )
#                 ).insert(ignore_permissions=True)
#                 frappe.db.commit()
#                 str_exp = "18/04/2023"
#                 email_expiry = frappe.db.sql(
#                     "select message from `tabNotification` where name='Loan Renewal Reminder';"
#                 )[0][0]
#                 email_expiry = email_expiry.replace("loan_name", str(loan.name))
#                 email_expiry = email_expiry.replace("expiry_date", str_exp)
#                 email_expiry = email_expiry.replace(
#                     "dlt_link", str(las_settings.app_login_dashboard)
#                 )
#                 frappe.enqueue(
#                     method=frappe.sendmail,
#                     recipients=[customer.user],
#                     sender=None,
#                     subject="Loan Renewal Reminder",
#                     message=email_expiry,
#                     queue="short",
#                     delayed=False,
#                     job_name="Loan Renewal Reminder",
#                 )
#                 msg = """Dear Customer,
# Your loan account number {loan_name} is due for renewal on or before {expiry_date}. Click on the link {link} to submit your request - Spark Loans""".format(
#                     loan_name=loan.name,
#                     expiry_date=str_exp,
#                     link=las_settings.app_login_dashboard,
#                 )
#                 fcm_notification = frappe.get_doc(
#                     "Spark Push Notification",
#                     "Loan Renewal Reminder",
#                     fields=["*"],
#                 )
#                 send_spark_push_notification(
#                     fcm_notification=fcm_notification,
#                     loan=loan.name,
#                     customer=customer,
#                 )
#                 if msg:
#                     receiver_list = [str(customer.phone)]
#                     if customer.get_kyc().mob_num:
#                         receiver_list.append(str(customer.get_kyc().mob_num))
#                     if customer.get_kyc().choice_mob_no:
#                         receiver_list.append(str(customer.get_kyc().choice_mob_no))

#                     receiver_list = list(set(receiver_list))

#                     frappe.enqueue(
#                         method=send_sms,
#                         receiver_list=receiver_list,
#                         msg=msg,
#                     )

#             else:
#                 renewal_doc = frappe.get_doc(
#                     "Spark Loan Renewal Application", existing_renewal_doc[0].name
#                 )

#             # grace_7days = datetime.strftime(frappe.utils.now_datetime().date(), "%Y-%m-%d")

#             if type(renewal_doc.creation) == str:
#                 grace_7th = datetime.strptime(
#                     renewal_doc.creation, "%Y-%m-%d %H:%M:%S.%f"
#                 )
#             else:
#                 grace_7th = renewal_doc.creation

#             current_date = frappe.utils.now_datetime().date()
#             exp = grace_7th.date()
#             greater_than_7 = exp + timedelta(days=7)
#             more_than_7 = greater_than_7 + timedelta(days=7)
#             applications = []

#             # grace_7th_expiry = datetime.strftime(grace_7th_expiry, "%Y-%m-%d") + timedelta(days=7)
#             if (
#                 current_date > greater_than_7
#                 and current_date < more_than_7
#                 and (
#                     (
#                         pending_renewal_doc_list
#                         and not user_kyc
#                         and not user_kyc_approved
#                     )
#                     or (user_kyc_approved and pending_renewal_doc_list)
#                 )
#             ):
#                 top_up_application = frappe.get_all(
#                     "Top up Application",
#                     filters={
#                         "loan": loan.name,
#                         "status": ["IN", ["Pending", "Esign Done"]],
#                     },
#                     fields=["name"],
#                 )
#                 for i in top_up_application:
#                     applications.append(i)
#                 loan_application = frappe.get_all(
#                     "Loan Application",
#                     filters={
#                         "loan": loan.name,
#                     },
#                     fields=["name"],
#                 )
#                 for i in loan_application:
#                     applications.append(i)
#                 if not top_up_application and not loan_application:
#                     current_year = frappe.utils.now_datetime().strftime("%Y")
#                     current_year = int(current_year)
#                     if (
#                         (current_year % 400 == 0)
#                         or (current_year % 100 != 0)
#                         and (current_year % 4 == 0)
#                     ):
#                         no_of_days = 366
#                     # Else it is not a leap year
#                     else:
#                         no_of_days = 365
#                     renewal_penal_interest = frappe.get_doc("Lender", loan.lender)
#                     daily_penal_interest = (
#                         float(renewal_penal_interest.renewal_penal_interest)
#                         / no_of_days
#                     )
#                     amount = loan.balance * (daily_penal_interest / 100)
#                     penal_interest_transaction = frappe.get_doc(
#                         {
#                             "doctype": "Loan Transaction",
#                             "loan": loan.name,
#                             "lender": loan.lender,
#                             "transaction_type": "Penal Interest",
#                             "record_type": "DR",
#                             "amount": round(amount, 2),
#                             "unpaid_interest": round(amount, 2),
#                             "time": current_date,
#                         }
#                     )
#                     penal_interest_transaction.insert(ignore_permissions=True)
#                     penal_interest_transaction.transaction_id = (
#                         penal_interest_transaction.name
#                     )
#                     penal_interest_transaction.status = "Approved"
#                     penal_interest_transaction.workflow_state = "Approved"
#                     penal_interest_transaction.docstatus = 1
#                     penal_interest_transaction.save(ignore_permissions=True)
#                     frappe.db.commit()
#     except Exception:
#         frappe.log_error(
#             message=frappe.get_traceback() + "\n loan name : {}".format(str(loan.name)),
#             title=_("Loan Renewal Application - Update Doc"),
#         )
