// Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Spark Offline Customer Log", {
  refresh: function (frm) {
    if (frm.doc.status == "Success") {
      frm.set_df_property("doc_status_section", "read_only", 1);
      frm.set_df_property("user_details_section", "read_only", 1);
      frm.set_df_property("customer_details_section", "read_only", 1);
      frm.set_df_property("ckyc_details_section", "read_only", 1);
      frm.set_df_property("bank_details_section", "read_only", 1);
    }

    if (frm.doc.status != "Success") {
      frm.add_custom_button("Retry Process", () => {
        frappe.call({
          method:
            "lms.lms.doctype.spark_offline_customer_log.spark_offline_customer_log.retry_process",
          freeze: true,
          args: { doc_name: frm.doc.name },
        });
      });
    }
  },
});
