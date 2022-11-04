// Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Spark Loan Renewal Application", {
  refresh: function (frm) {
    if (frm.doc.status == "Pending") {
      frm.add_custom_button(__("Notify Customer"), function () {
        frappe.call({
          method:
            "lms.lms.doctype.loan_application.loan_application.actions_on_isin",
          freeze: true,
          args: {
            loan_application: frm.doc,
          },
        });
      });
    }
  },
});
