from datetime import datetime

import frappe
import utils


# import lms
def get_context(context):
    context.blogs = frappe.get_all(
        "News and Blog", fields=["*"], page_length=6, order_by="creation desc"
    )
    for blog in context.blogs:
        blog.publishing_date = (blog.publishing_date).strftime("%d %B, %Y")


@frappe.whitelist(allow_guest=True)
def fetch_blogs(page_no, latest_post="", trending_post="", search_key=""):
    limit = 6
    offset = (int(page_no) - 1) * limit
    if latest_post == "true":
        if len(search_key.strip()) > 0:
            where = "where nb.title LIKE %(txt)s and nb.is_latest=true"
            where_extras = {"txt": "%{}%".format(search_key)}
            blogs_all = frappe.db.sql(
                "select nb.*, DATE_FORMAT(nb.publishing_date, %(format)s) as publishing_date, Group_CONCAT(bt.website_tags) as website_tags from `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent =   nb. name) {} group by nb.name order by creation desc limit {},{}".format(
                    where, offset, limit
                ),
                {"format": "%d %M, %Y"},
                where_extras,
                as_dict=True,
                debug=True,
            )
        else:
            where = "where nb.is_latest=true"
            blogs_all = frappe.db.sql(
                "select nb.*, DATE_FORMAT(nb.publishing_date, %(format)s) as publishing_date,Group_CONCAT(bt.website_tags) as website_tags from    `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent = nb. name) {} group by nb.name order by creation desc limit {},{}".format(
                    where, offset, limit
                ),
                {"format": "%d %M, %Y"},
                as_dict=True,
                debug=True,
            )
        response = {"blogs_all": blogs_all, "page_no": page_no}
    elif trending_post == "true":
        if len(search_key.strip()) > 0:
            where = "where nb.title LIKE %(txt)s and nb.is_trending=true"
            where_extras = {"txt": "%{}%".format(search_key)}
            blogs_all = frappe.db.sql(
                "select nb.*, DATE_FORMAT(nb.publishing_date, %(format)s) as publishing_date, Group_CONCAT(bt.website_tags) as website_tags from `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent =   nb. name) {} group by nb.name order by creation desc limit {},{}".format(
                    where, offset, limit
                ),
                {"format": "%d %M, %Y"},
                where_extras,
                as_dict=True,
                debug=True,
            )
        else:
            where = "where nb.is_trending=true"
            blogs_all = frappe.db.sql(
                "select nb.*, DATE_FORMAT(nb.publishing_date, %(format)s) as publishing_date, Group_CONCAT(bt.website_tags) as website_tags from    `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent = nb. name) {} group by nb.name order by creation desc limit {},{}".format(
                    where, offset, limit
                ),
                {"format": "%d %M, %Y"},
                as_dict=True,
                debug=True,
            )
        response = {"blogs_all": blogs_all, "page_no": page_no}
    else:
        if len(search_key.strip()) > 0:
            where = "where nb.title LIKE %(txt)s"
            where_extras = {"txt": "%{}%".format(search_key)}
            blogs_all = frappe.db.sql(
                "select nb.*, DATE_FORMAT(nb.publishing_date, %(format)s) as publishing_date, Group_CONCAT(bt.website_tags) as website_tags from    `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent =   nb. name) {} group by nb.name order by creation desc limit {},{}".format(
                    where, offset, limit
                ),
                {"format": "%d %M, %Y"},
                where_extras,
                as_dict=True,
                debug=True,
            )
        else:
            blogs_all = frappe.db.sql(
                "select nb.*, DATE_FORMAT(nb.publishing_date, %(format)s) as publishing_date, Group_CONCAT(bt.website_tags) as website_tags from    `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent =   nb. name) group by nb.name order by creation desc limit {},{}".format(
                    offset, limit
                ),
                {"format": "%d %M, %Y"},
                as_dict=True,
                debug=True,
            )

        response = {"blogs_all": blogs_all, "page_no": page_no}
    return utils.respondWithSuccess(data=response)
