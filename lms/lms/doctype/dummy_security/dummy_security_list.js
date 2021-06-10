frappe.listview_settings["Dummy Security"] = {
  refresh: function (listview) {
    listview.page.add_inner_button(__("Upload CSV"), function () {
      let d = new frappe.ui.Dialog({
        title: "Enter details",
        fields: [
          {
            label: "Upload CSV",
            fieldname: "file",
            fieldtype: "Attach",
          },
        ],
        primary_action_label: "Submit",
        primary_action(values) {
          console.log(values);
          frappe.call({
            method: "lms.lms.doctype.dummy_security.dummy_security.process_csv",
            args: {
              upload_file: values.file,
            },
            freeze: true,
          });
          d.hide();
        },
      });

      d.show();
    });
  },
};
