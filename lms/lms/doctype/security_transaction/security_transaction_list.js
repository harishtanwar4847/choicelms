frappe.listview_settings["Security Transaction"] = {
  onload: function (listview) {
    frappe.db.get_single_value("LAS Settings", "debug_mode").then((res) => {
      if (res) {
        listview.page.add_inner_button(
          __("Update Security Transaction"),
          function () {
            frappe.call({
              method:
                "lms.lms.doctype.security_transaction.security_transaction.security_transaction",
              freeze: true,
            });
          }
        );
      }
    });
  },
};
