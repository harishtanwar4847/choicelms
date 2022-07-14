frappe.listview_settings["Interest Calculation"] = {
  onload: function (listview) {
    frappe.db.get_single_value("LAS Settings", "debug_mode").then((res) => {
      if (res) {
        listview.page.add_inner_button(
          __("Update Interest Calculation"),
          function () {
            frappe.call({
              method:
                "lms.lms.doctype.interest_calculation.interest_calculation.interest_calculation_enqueue",
              freeze: true,
            });
          }
        );
      }
    });
  },
  hide_name_column: true,
};
