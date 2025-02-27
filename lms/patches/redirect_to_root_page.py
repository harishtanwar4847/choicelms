import frappe


def execute():
    source_target_dict = [
        {"source": "index", "target": "/"},
        {"source": "home", "target": "/"},
    ]
    for dict in source_target_dict:
        frappe.get_doc(
            {
                "doctype": "Website Route Redirect",
                "source": dict["source"],
                "target": dict["target"],
                "parent": "Website Settings",
                "parenttype": "Website Settings",
                "parentfield": "route_redirects",
            }
        ).insert()
    frappe.db.commit()
