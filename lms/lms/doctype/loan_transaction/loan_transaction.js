// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Loan Transaction", {
  refresh: function (frm) {
    let is_allowed = frappe.user_roles.includes("System Manager");
    frm.toggle_enable(["transaction_type", "amount"], is_allowed);
    if (
      frm.doc.status == "Ready for Approval" &&
      frappe.user_roles.includes("Spark Transaction Approver")
    ) {
      console.log("in function");
      frm.set_df_property("allowable", "read_only", 0);
    }
    // else {
    //   frm.set_df_property("allowable","read_only", 0);
    // }
  },
});
// eval:frappe.user_roles.includes("[System Manager"])
