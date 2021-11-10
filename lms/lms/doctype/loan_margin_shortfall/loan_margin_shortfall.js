// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Loan Margin Shortfall", {
  refresh: function (frm) {
    frappe.call({
      type: "POST",
      method:
        "lms.lms.doctype.loan_margin_shortfall.loan_margin_shortfall.set_timer",
      args: { loan_margin_shortfall_name: frm.doc.name },
    });
  },
});
