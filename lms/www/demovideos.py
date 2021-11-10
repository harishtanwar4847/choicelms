import frappe
import utils

import lms


@frappe.whitelist(allow_guest=True)
def get_videos_list(page_no, latest_video="", search_key=""):
    if latest_video == "true":
        limit = 3
    else:
        limit = 6

    offset = (int(page_no) - 1) * limit

    if len(search_key.strip()) > 0:
        where = "where video_title LIKE '%{search_key}%' or video_description LIKE '%{search_key}%'".format(
            search_key=search_key
        )
    else:
        where = ""

    if latest_video == "true":
        page_limit = "limit {}".format(limit)
    else:
        page_limit = "limit {},{}".format(offset, limit)

    videos_list = frappe.db.sql(
        "select * from `tabYoutube Id` {} order by creation desc {}".format(
            where, page_limit
        ),
        as_dict=True,
    )
    all_video_count = frappe.db.count("Youtube Id")
    response = {
        "videos_list_response": videos_list,
        "page_no": page_no,
        "all_video_count": all_video_count,
    }

    return utils.respondWithSuccess(data=response)
