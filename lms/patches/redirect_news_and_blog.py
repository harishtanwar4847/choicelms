import frappe


def execute():
    frappe.get_doc(
        {
            "doctype": "Website Route Redirect",
            "source": "newsblog",
            "target": "/news-and-blogs",
            "parent": "Website Settings",
            "parenttype": "Website Settings",
            "parentfield": "route_redirects",
        }
    ).insert()
    frappe.db.commit()
