import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Loan", force=True)
    loan_list = frappe.get_all("Loan", fields=["*"])
    for i in loan_list:
        try:
            loan = frappe.get_doc("Loan", i.name)
            if loan.loan_agreement and "http:" not in loan.loan_agreement:
                agreement = loan.loan_agreement
                lfile_name = agreement.split("files/", 1)
                l_file = lfile_name[1]
                sanction_letter_esign_document = frappe.utils.get_url(
                    "files/{}".format(l_file)
                )
                frappe.db.set_value(
                    "Loan", i.name, "loan_agreement", sanction_letter_esign_document
                )
        except Exception:
            frappe.log_error(
                title="Update loan agreement url patch error",
                message=frappe.get_traceback() + "\n\nLoan name :" + str(i.name),
            )
