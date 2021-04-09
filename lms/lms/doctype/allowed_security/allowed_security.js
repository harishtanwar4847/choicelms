// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Allowed Security", {
  refresh: function (frm) {
    frm.set_df_property("lender", "hidden", true);
  },
});
