<h3>Dear {{ doc.investor_name or "" }},</h3>
{% if doc.transaction_type == "Interest" %}
<p>Your interest for Loan Account {{doc.loan_name}} is due for payment. Please take action<p>
{% endif %}

{% if doc.transaction_type == "Additional Interest" %}
<p>You have been charged Additional interest of INR {{doc.unpaid_interest}} for {{doc.loan_name}}<p>
{% endif %}

{% if doc.transaction_type == "Penal Interest" %}
<p>You have been charged Penal interest of INR {{doc.unpaid_interest}} for {{doc.loan_name}}<p>
{% endif %}

<p>Thanks,</p>
<p>The Spark Team	</p>
