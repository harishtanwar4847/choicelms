frappe.listview_settings["Loan"] = {
  onload: function (listview) {
    frappe.db.get_single_value("LAS Settings", "debug_mode").then((res) => {
      if (res) {
        listview.page.add_inner_button(
          __("Check for Margin Shortfall"),
          function () {
            frappe.call({
              method: "lms.lms.doctype.loan.loan.check_all_loans_for_shortfall",
              freeze: true,
            });
          }
        );
      }
    });
  },
  hide_name_column: true,
};
