import frappe
import utils


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
    date_format = "DATE_FORMAT(nb.publishing_date, %(format)s) as publishing_date,"
    if len(search_key.strip()) > 0:
        where = "where nb.title LIKE %(txt)s"
        if latest_post == "true":
            where += " and nb.is_latest=true"
        elif trending_post == "true":
            where += " and nb.is_trending=true"

        where_extras = {"format": "%d %M, %Y", "txt": "%{}%".format(search_key)}

        blogs_all = frappe.db.sql(
            "select nb.name,nb.title,nb.for_banner_view, nb.creation, {} Group_CONCAT(bt.website_tags) as website_tags from `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent = nb.name) {} group by nb.name order by creation desc limit {},{}".format(
                date_format, where, offset, limit
            ),
            where_extras,
            as_dict=True,
        )

    else:
        where = ""
        if latest_post == "true":
            where += "where nb.is_latest=true"
        elif trending_post == "true":
            where += "where nb.is_trending=true"

        blogs_all = frappe.db.sql(
            "select nb.name,nb.title,nb.for_banner_view,nb.creation, {} Group_CONCAT(bt.website_tags) as website_tags from `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent = nb.name) {} group by nb.name order by creation desc limit {},{}".format(
                date_format, where, offset, limit
            ),
            {"format": "%d %M, %Y"},
            as_dict=True,
        )
    response = {"blogs_all": blogs_all, "page_no": page_no}
    return utils.respondWithSuccess(data=response)
