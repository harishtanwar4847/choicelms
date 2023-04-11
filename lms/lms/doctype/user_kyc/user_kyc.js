// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("User KYC", {
  refresh: function (frm) {
    // frm.disable_save();
    if (window.location.href.includes("https://spark.loans")) {
      frm.set_df_property("pan_no", "read_only", 1);
      frm.set_df_property("date_of_birth", "read_only", 1);
    } else {
      frm.set_df_property("pan_no", "read_only", 0);
      frm.set_df_property("date_of_birth", "read_only", 0);
    }
  },
});
