// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Loan Application', {
	refresh: function(frm) {
		// if(['Esign Done', 'Approved'].includes(frm.doc.status)) {
		// 	if(frm.doc.customer_esigned_document) {
		// 		frm.set_df_property('customer_esigned_document', 'disabled', 1)
		// 	}
		// }
	}
});
