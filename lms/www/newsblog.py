import frappe
import utils

import lms


@frappe.whitelist(allow_guest=True)
def fetch_related_articles(blog_route, page_no):
    blog_name = frappe.db.sql(
        """select name from `tabNews and Blog` where route = '{}' """.format(
            blog_route
        ),
        as_dict=True,
    )[0]["name"]
    blog_details = frappe.get_doc("News and Blog", blog_name)
    tags_list = [i.website_tags for i in blog_details.blog_tags]
    limit = 3
    offset = (int(page_no) - 1) * limit
    # all_blog = frappe.db.sql("select count(*) as all_post from `tabNews and Blog`", as_dict=True)[0]["all_post"]
    related_articles = frappe.db.sql(
        "select nb.name, nb.title, DATE_FORMAT(nb.publishing_date, %(format)s) as publishing_date, GROUP_CONCAT(bt.website_tags) as website_tags, nb.for_banner_view from `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent = nb.name) where nb.name in (Select nb.name from `tabNews and Blog` nb, `tabBlog Tags` bt where bt.parent=nb.name AND nb.name <> '{}' AND bt.website_tags in {} group by nb.name) group by nb.name order by nb.creation desc limit {}, 3;".format(
            blog_name, lms.convert_list_to_tuple_string(tags_list), offset
        ),
        {"format": "%d %M, %Y"},
        as_dict=True,
    )
    all_blog = len(
        frappe.db.sql(
            "select count(*) from `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent = nb.name) where nb.name in (Select nb.name from `tabNews and Blog` nb, `tabBlog Tags` bt where bt.parent=nb.name AND nb.name <> '{}' AND bt.website_tags in {} group by nb.name) group by nb.name order by nb.creation desc;".format(
                blog_name, lms.convert_list_to_tuple_string(tags_list)
            ),
            {"format": "%d %M, %Y"},
            as_dict=True,
        )
    )
    response = {
        "related_articles": related_articles,
        "page_no": page_no,
        "all_blog": all_blog,
    }
    return utils.respondWithSuccess(data=response)


@frappe.whitelist(allow_guest=True)
def page_update(blog_route):
    blog_name = frappe.db.sql(
        """select name from `tabNews and Blog` where route = '{}' """.format(
            blog_route
        ),
        as_dict=True,
    )[0]["name"]
    previous_page = frappe.db.sql(
        "SELECT route, (SELECT route FROM `tabNews and Blog` nb1 WHERE nb1.creation < nb.creation ORDER BY creation DESC LIMIT 1) as previous_name  FROM `tabNews and Blog` nb WHERE name = '{}'".format(
            blog_name
        ),
        as_dict=True,
    )[0]["previous_name"]
    next_page = frappe.db.sql(
        "SELECT route, (SELECT route FROM `tabNews and Blog` nb2 WHERE nb2.creation > nb.creation ORDER BY creation ASC LIMIT 1) as next_name FROM `tabNews and Blog` nb WHERE name = '{}'".format(
            blog_name
        ),
        as_dict=True,
    )[0]["next_name"]
    response = {"previous_page": previous_page, "next_page": next_page}
    return utils.respondWithSuccess(data=response)


@frappe.whitelist(allow_guest=True)
def website_ads():
    website_ads = frappe.db.sql(
        """select * from `tabWebsite Ads` order by creation desc limit 1""",
        as_dict=True,
    )[0]
    response = {"website_ads": website_ads}
    return utils.respondWithSuccess(data=response)
