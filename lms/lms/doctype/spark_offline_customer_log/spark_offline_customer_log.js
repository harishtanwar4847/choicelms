// Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Spark Offline Customer Log", {
  refresh: function (frm) {
    if (frm.doc.user_status == "Success") {
      frm.set_df_property("first_name", "read_only", 1);
      frm.set_df_property("last_name", "read_only", 1);
      frm.set_df_property("mobile_no", "read_only", 1);
      frm.set_df_property("email_id", "read_only", 1);
    }
    if (frm.doc.customer_status == "Success") {
      frm.set_df_property("customer_first_name", "read_only", 1);
      frm.set_df_property("customer_last_name", "read_only", 1);
      frm.set_df_property("customer_mobile", "read_only", 1);
      frm.set_df_property("customer_email", "read_only", 1);
    }
    if (frm.doc.ckyc_status == "Success") {
      frm.set_df_property("pan_no", "read_only", 1);
      frm.set_df_property("dob", "read_only", 1);
      frm.set_df_property("ckyc_no", "read_only", 1);
    }
    if (frm.doc.bank_status == "Success") {
      frm.set_df_property("bank", "read_only", 1);
      frm.set_df_property("branch", "read_only", 1);
      frm.set_df_property("account_no", "read_only", 1);
      frm.set_df_property("ifsc", "read_only", 1);
      frm.set_df_property("city", "read_only", 1);
      frm.set_df_property("account_holder_name", "read_only", 1);
      frm.set_df_property("bank_address", "read_only", 1);
      frm.set_df_property("account_type", "read_only", 1);
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
