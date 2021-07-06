import frappe
import pymysql
import utils

import lms


@frappe.whitelist(allow_guest=True)
def fetch_blogs_all(page_no):
    limit = 6
    offset = (int(page_no) - 1) * limit
    blogs_all = frappe.db.sql(
        "select nb.*, Group_CONCAT(bt.website_tags) as website_tags from `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent = nb. name) group by nb.name limit {},6".format(
            offset
        ),
        as_dict=True,
        debug=True,
    )
    response = {"blogs_all": blogs_all, "page_no": page_no}
    return utils.respondWithSuccess(data=response)


@frappe.whitelist(allow_guest=True)
def search_blog(search_content, page_no):
    limit = 6
    offset = (int(page_no) - 1) * limit
    if search_content != "":
        print(search_content)
        print("first fucntion called")
        searched_blogs = frappe.db.sql(
            "select nb.*, Group_CONCAT(bt.website_tags) as website_tags from `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent = nb.name) where nb.title LIKE %(txt)s  group by nb.name limit {},6".format(
                offset
            ),
            {
                "txt": "%{}%".format(search_content),
            },
            as_dict=True,
            debug=True,
        )

        response = {"searched_blogs": searched_blogs, "page_no": page_no}
    else:
        print("second fucntion called")
        searched_blogs = frappe.db.sql(
            "select nb.*, Group_CONCAT(bt.website_tags) as website_tags from `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent = nb.name) group by nb.name limit {},6".format(
                offset
            ),
            as_dict=True,
            debug=True,
        )

        response = {"searched_blogs": searched_blogs, "page_no": page_no}

    return utils.respondWithSuccess(data=response)
