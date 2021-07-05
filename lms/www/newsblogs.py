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
    # if search_content:
    # search_content = pymysql.escape_string("'")
    print(search_content)
    searched_blogs = frappe.db.sql(
        """select nb.*, Group_CONCAT(bt.website_tags) as website_tags from `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent = nb.name) where nb.title = '{}' group by nb.name limit {},6""".format(
            str(search_content), offset
        ),
        as_dict=True,
        debug=True,
    )

    response = {"searched_blogs": searched_blogs, "page_no": page_no}
    # else:
    #     searched_blogs = frappe.db.sql(
    #     "select nb.*, Group_CONCAT(bt.website_tags) as website_tags from `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent = nb.name) group by nb.name limit {},6".format(offset),
    #     as_dict=True,
    #     debug=True,
    #     )
    #     response = {"searched_blogs": searched_blogs, "page_no": page_no}

    return utils.respondWithSuccess(data=response)
