frappe.listview_settings["Security Price"] = {
  onload: function (listview) {
    if (false == true) {
      listview.page.add_inner_button(__("Update Prices"), function () {
        frappe.call({
          method:
            "lms.lms.doctype.security_price.security_price.update_all_security_prices",
          freeze: true,
        });
      });
    }
  },
};
