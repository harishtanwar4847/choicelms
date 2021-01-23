frappe.listview_settings["Loan"] = {
  onload: function (listview) {
    if (false == true) {
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
  },
};
