<h3>Dear {{ doc.investor_name or "" }},</h3>

{% if doc.get("loan_application").get("status") == "Pledge Failure" %}
Sorry! Your loan application was turned down since the Pledge request was not successful.
We regret the inconvenience caused.
{% endif %}
{% if doc.get("loan_application").get("status") == "Pledge accepted by Lender" %}
Congratulations! Your application is being considered favourably by our lending partner
and finally accepted at Rs. {{doc.get("loan_application").get("current_total_collateral_value")}} against the request value of Rs. {{doc.get("loan_application").get("requested_total_collateral_value")}}.
Accordingly the final Drawing power is Rs. {{doc.get("loan_application").get("drawing_power")}}.
Please e-sign the loan agreement to avail the loan now.
{% endif %}
{% if doc.get("loan_application").get("status") == "Approved" %}
Congratulations! Your loan application is Approved.
{% endif %}
{% if doc.get("loan_application").get("status") == "Rejected" %}
Sorry! Your loan application was turned down. We regret the inconvenience caused.
{% endif %}
<p>Thanks,</p>
<p>The Spark Team	</p>
