<h3>Dear {{ doc.full_name or "" }},</h3>

{% if doc.get("top_up_application").get("status") == "Pending" %}
Your request has been successfully received. You will be notified when your new OD limit is approved by our banking partner.
{% endif %}
{% if doc.get("top_up_application").get("status") == "Approved" %}
Congratulations! Your Top up application for Loan {{doc.get("top_up_application").get("loan")}} is Approved.
{% endif %}
{% if doc.get("top_up_application").get("status") == "Rejected" %}
Sorry! Your Top up application was turned down. We regret the inconvenience caused.
{% endif %}

<p>Thanks,</p>
<p>The Spark Team	</p>
