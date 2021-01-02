// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("User KYC", {
  refresh: function (frm) {
    frm.disable_save();
  },
});
