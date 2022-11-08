# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from lms import send_spark_push_notification
from lms.lms.doctype.user_token.user_token import send_sms


class SparkLoanRenewalApplication(Document):
    def notify_renewal_customer(self):
        try:
            loan = frappe.get_doc("Loan", self.loan)
            customer = frappe.get_doc("Loan Customer", self.customer)

            doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
            doc["loan_renewal_application"] = {
                "status": self.status,
            }

            if self.status in [
                "Loan Renewal accepted by Lender",
                "Esign Done" "Approved",
                "Rejected",
            ]:
                frappe.enqueue_doc(
                    "Notification", "Loan Renewal Application", method="send", doc=doc
                )

            if doc.status == "Loan Renewal accepted by Lender":
                doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()

                msg = 'Dear Customer,\nCongratulations! Your loan renewal application has been accepted.\nKindly check the app for details under e-sign banner on the dashboard. Please e-sign the loan agreement.\nFor any help on e-sign, please view our tutorial videos or reach out to us under "Contact Us" on the app\n-Spark Loans'
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

            elif doc.status == "Esign Done":
                doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()

                msg = "Dear Customer,\nYour E-sign process is completed. You shall soon receive a confirmation of loan renew approval.\nThank you for your patience.\n-Spark Loans"

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

            elif doc.status == "Approved":
                doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()

                msg = "Dear Customer,\nCongratulations! Your loan renewal process is completed. Kindly check the app.\n-Spark Loans"

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

            elif doc.status == "Rejected":
                doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()

                msg = "Dear Customer,\nSorry! Your loan renewal application was turned down. We regret the inconvenience caused. Please try again after sometime or reach out to us through 'Contact Us' on the app.\n-SparkLoans"

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
                message=frappe.get_traceback(),
                title=_("Loan Renewal Application - Notify Customer"),
            )


@frappe.whitelist()
def customer_reminder(document):
    try:
        loan = frappe.get_doc("Loan", document.loan)
        customer = frappe.get_doc("Loan Customer", document.customer)

        doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
        doc["loan_renewal_application"] = {"status": document.status}

        if document.status in [
            "Loan Renewal accepted by Lender",
            "Esign Done" "Approved",
            "Rejected",
        ]:
            frappe.enqueue_doc(
                "Notification", "Loan Renewal Application", method="send", doc=doc
            )

        if document.status == "Pending":
            kyc_doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
            email_expiry = frappe.db.sql(
                "select message from `tabNotification` where name='Loan Renewal Reminder';"
            )[0][0]
            email_expiry = email_expiry.replace("expiry_date", loan.expiry_date)
            frappe.enqueue_doc(
                method=frappe.sendmail,
                recipients=[customer.email],
                sender=None,
                subject="Loan Renewal Reminder",
                message=email_expiry,
                queue="short",
                delayed=False,
                job_name="Loan Renewal Reminder",
            )
            msg = "Dear Customer,\nYour expiry date is due on {}.\nPlease renew your loan before it expires.\n-Spark Loans"
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
        elif document.status == "Loan Renewal accepted by Lender":
            kyc_doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
            msg = 'Dear Customer,\nCongratulations! Your loan renewal application has been accepted.\nKindly check the app for details under e-sign banner on the dashboard. Please e-sign the loan agreement.\nFor any help on e-sign, please view our tutorial videos or reach out to us under "Contact Us" on the app\n-Spark Loans'
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
        elif document.status == "Esign Done":
            kyc_doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()

            msg = "Dear Customer,\nYour E-sign process is completed. You shall soon receive a confirmation of loan renew approval.\nThank you for your patience.\n-Spark Loans"

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
            message=frappe.get_traceback(),
            title=_("Loan Renewal Application - Notify Customer"),
        )
