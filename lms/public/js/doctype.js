$(document).on('app_ready', function () {
    $.each(["Virtual Interest", "Loan Transaction", "Loan Margin Shortfall", "Top up application", "Collateral Ledger"], function (i, doctype) {
        frappe.ui.form.on(doctype, "refresh", function (frm) {
            frappe.db.get_doc('Loan', frm.doc.loan).then((doc) => {
                var data = "";
                data +=
                    "<style>" +
                    "table {" +
                    "border-collapse:separate;border:solid black 2px;border-radius:6px;-moz-border-radius:6px;background-color:white;width:100%" +
                    "}" +
                    "td,th {" +
                    "border-left:solid black 2px;border-top:solid black 2px;text-align: center;color:black;padding:6px 4px;" +
                    "}" +
                    "th {" +
                    "border-top: none;" +
                    "}" +
                    "td:first-child, th:first-child {" +
                    " border-left: none;" +
                    "}" +
                    "</style>" +
                    "<table>" +
                    "<tr>" +
                    "<th> Loan Account No </th>" +
                    "<th> Customer Name </th>" +
                    "<th> Loan Balance </th>" +
                    "<th> Virtual interest not booked </th>" +
                    "<th> Drawing Power </th>" +
                    "<th> Sanctioned limit </th>" +
                    "<th> Lender name </th>" +
                    "<th> Margin shortfall </th>" +
                    "<th> Interest due </th>" +
                    "<th> Interest overdue </th>" +
                    "<th> DPD(days past due) </th>" +
                    "<th> Collateral value </th>" +
                    "</tr>" +
                    "<tr>" +
                    "<td>" +
                    doc.name +
                    "</td>" +
                    "<td>" +
                    doc.customer_name +
                    "</td>" +
                    "<td>" +
                    doc.balance +
                    "</td>" +
                    "<td>" +
                    doc.base_interest_amount +
                    "</td>" +
                    "<td>" +
                    doc.drawing_power +
                    "</td>" +
                    "<td>" +
                    doc.sanctioned_limit +
                    "</td>" +
                    "<td>" +
                    doc.lender +
                    "</td>" +
                    "<td>" +
                    doc.margin_shortfall_amount +
                    "</td>" +
                    "<td>" +
                    "-" +
                    "</td>" +
                    "<td>" +
                    "-" +
                    "</td>" +
                    "<td>" +
                    "-" +
                    "</td>" +
                    "<td>" +
                    doc.total_collateral_value +
                    "</td>" +
                    "</tr>";
                "</table>";
                frm.set_intro(data);
            });
            document.getElementsByClassName("form-message")[0].style.background ="#f9fafa";
            document.getElementsByClassName("form-message")[0].style.padding = "0px";
        });
    });
});
