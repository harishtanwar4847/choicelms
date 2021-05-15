// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Loan Application", {
  refresh: function (frm) {
    frm.set_df_property("items", "read_only", 1);
    frm.attachments.parent.hide();
    if (["Esign Done", "Approved"].includes(frm.doc.status)) {
      if (frm.doc.customer_esigned_document) {
        frm
          .get_field("customer_esigned_document")
          .$input_wrapper.find("[data-action=clear_attachment]")
          .hide();
      }
      if (frm.doc.lender_esigned_document) {
        frm
          .get_field("lender_esigned_document")
          .$input_wrapper.find("[data-action=clear_attachment]")
          .hide();
      }
    }

    if (false == false) {
      if (frm.doc.status == "Waiting to be pledged") {
        frm.add_custom_button(__("Process Pledge"), function () {
          frappe.call({
            method:
              "lms.lms.doctype.loan_application.loan_application.process_pledge",
            freeze: true,
            args: {
              loan_application_name: frm.doc.name,
            },
          });
        });
      }
    }

    if (frm.doc.status == "Pledge executed") {
        frm.add_custom_button(__("Approve All ISIN"), function () {
          frappe.call({
            method:
              "lms.lms.doctype.loan_application.loan_application.approve_all_isin_button",
            freeze: true,
            args: {
              loan_application_name: frm.doc.name,
            },
          });
        }, __("Select All ISIN"));

        frm.add_custom_button(__("Reject All ISIN"), function () {
          frappe.call({
            method:
              "lms.lms.doctype.loan_application.loan_application.reject_all_isin_button",
            freeze: true,
            args: {
              loan_application_name: frm.doc.name,
            },
          });
        }, __("Select All ISIN"));

        frm.add_custom_button(__("Undo Select All ISIN"), function () {
          frappe.call({
            method:
              "lms.lms.doctype.loan_application.loan_application.undo_select_all_isin_button",
            freeze: true,
            args: {
              loan_application_name: frm.doc.name,
            },
          });
        }, __("Select All ISIN"));
      }

    if (
      frm.doc.workflow_state == "Approved" ||
      frm.doc.workflow_state == "Rejected"
    ) {
      var df = frappe.meta.get_docfield(
        "Loan Application Item",
        "lender_approval_status",
        cur_frm.doc.name
      );
      df.read_only = 1;
    }
  },
});
