// Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Spark Loan Renewal Application", {
  refresh: function (frm) {
    if (frm.doc.status == "Pending") {
      frm.add_custom_button(__("Notify Customer"), function () {
        frappe.call({
          method:
            "lms.lms.doctype.spark_loan_renewal_application.spark_loan_renewal_application.customer_reminder",
          freeze: true,
          args: {
            doc_name: frm.doc.name,
          },
        });
      });
    }
    frappe.call({
      type: "POST",
      method:
        "lms.lms.doctype.spark_loan_renewal_application.spark_loan_renewal_application.renewal_timer",
      args: { loan_renewal_name: frm.doc.name },
    });
  },
});
