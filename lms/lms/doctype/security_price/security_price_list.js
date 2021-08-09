frappe.listview_settings["Security Price"] = {
  onload: function (listview) {
    frappe.db.get_single_value("LAS Settings", "debug_mode").then((res) => {
      if (res) {
        listview.page.add_inner_button(__("Update Prices"), function () {
          frappe.call({
            method:
              "lms.lms.doctype.security_price.security_price.update_all_security_prices",
            freeze: true,
          });
        });
      }
    });
  },
};
