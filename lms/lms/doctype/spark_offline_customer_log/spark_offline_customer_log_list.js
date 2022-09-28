frappe.listview_settings["Spark Offline Customer Log"] = {
  get_indicator: function (doc) {
    var colors = {
      Success: "green",
      "Partial Success": "orange",
      Failure: "red",
    };
    let status = doc.status;
    return [__(status), colors[status], "status,=," + doc.status];
  },
  hide_name_column: true,
};
