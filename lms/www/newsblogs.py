import frappe
import utils

# import lms


@frappe.whitelist(allow_guest=True)
def fetch_blogs(page_no, search_key=""):
    limit = 3
    offset = (int(page_no) - 1) * limit

    if len(search_key.strip()) > 0:
        where = "where nb.title LIKE %(txt)s"
        where_extras = {"txt": "%{}%".format(search_key)}
        blogs_all = frappe.db.sql(
            "select nb.*, Group_CONCAT(bt.website_tags) as website_tags from `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent = nb. name) {} group by nb.name order by creation desc limit {},{}".format(
                where, offset, limit
            ),
            where_extras,
            as_dict=True,
            debug=True,
        )
    else:
        blogs_all = frappe.db.sql(
            "select nb.*, Group_CONCAT(bt.website_tags) as website_tags from `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent = nb. name) group by nb.name order by creation desc limit {},{}".format(
                offset, limit
            ),
            as_dict=True,
            debug=True,
        )

    response = {"blogs_all": blogs_all, "page_no": page_no}
    return utils.respondWithSuccess(data=response)
