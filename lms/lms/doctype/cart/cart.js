// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Cart', {
	refresh: function(frm) {
		if (!frm.doc.is_processed) {
			frm.add_custom_button(__('Process dummy cart'), function() {
				frappe.call({
					method: 'lms.cart.process_dummy',
					args: {
						cart_name: frm.doc.name
					},
					callback: function(r) {
						frappe.set_route("Form", 'Loan Application', r.message);
					},
					freeze: true
				})
			});
		}
	}
});
