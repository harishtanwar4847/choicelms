// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Loan Transaction", {
  refresh: function (frm) {
    let is_allowed = frappe.user_roles.includes("System Manager");
    frm.toggle_enable(["transaction_type", "amount"], is_allowed);
  },
});
