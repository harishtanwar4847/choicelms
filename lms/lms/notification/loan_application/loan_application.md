<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=0">
<title>Mailer</title>

<style rel="stylesheet" type="text/css">
    @media only screen and (max-width: 600px) {
		table table.table1{ width:95% !important}
        table { width: 100% !important; }

        .column {width: 100% !important; display: block !important; text-align:center  }
    }
</style>

</head>

<body>
<table width="800" border="0" align="center" cellpadding="0" cellspacing="0" style="background:#fff">
  <tr>
    <td bgcolor="#e7e7e8" height="138"><table class="table1" width="700" border="0" align="center" cellpadding="0" cellspacing="0" style="width:95% !important">
        <tr>
          <td><a href="#"><img src="{{ frappe.utils.get_url('/assets/lms/mail_images/logo.png') }}" width="138" height="138" style="border:0;height:138px"/></a></td>
        </tr>
      </table></td>
  </tr>
  <tr>
    <td><table class="table1" width="700" border="0" align="center" cellpadding="0" cellspacing="0" style="width:95% !important">
        <tr>
          <td height="25">&nbsp;</td>
        </tr>
        <tr>
          <td><strong><span style="font-family:Arial, Helvetica, sans-serif; font-size:16px; color:#2c2a2b">Dear {{ doc.investor_name or "" }},</span></strong></td>
        </tr>
        <tr>
          <td>&nbsp;</td>
        </tr>
        <tr>
            <td>
                <span style="font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:150%; color:#2c2a2b">
                    {% if doc.get("loan_application").get("status") == "Pledge accepted by Lender" and not doc.get("loan_margin_shortfall") %}
                        <strong>Congratulations!!</strong><br />
                        <br />
                        Your loan application has been accepted.<br />
                        Kindly check the app for details under e-sign banner on the dashboard. Please e-sign the loan agreement to avail the loan now.<br />
                        <br />
                        For any help on e-sign please view our tutorial videos or you can reach to us through 'Contact Us' on the app.<br />
                        We look forward to serve you soon.<br />
                        <br />
                    {% endif %}
                    {% if doc.get("loan_application").get("status") == "Pledge Failure" %}
                        Sorry! Your loan application was turned down since the pledge was not successful due to technical reasons.<br />
                        <br />
                        We regret the inconvenience caused.<br />
                        <br />
                        Please try again after sometime or you can reach to us through 'Contact Us' on the app.<br />
                        We look forward to serve you soon.<br />
                        <br />
                    {% endif %}
                    {% if doc.get("loan_application").get("status") == "Approved" and not doc.get("loan_margin_shortfall") %}
                        Your loan account is now open!<br />
                        <br />
                        You may now withdraw funds as per your convenience.<br />
                        <br />
                        You can reach to us through 'Contact Us' on the app.
                        We look forward to serve you soon.<br />
                        <br />
                    {% endif %}
                    {% if doc.get("loan_application").get("status") == "Rejected" and not doc.get("loan_margin_shortfall") %}
                        Sorry! Your loan application was turned down due to technical reasons.<br />
                        <br />
                        We regret the inconvenience caused.<br />
                        <br />
                        Please try again after sometime or you can reach to us through 'Contact Us' on the app.
                        We look forward to serve you soon.<br />
                        <br />
                    {% endif %}
                    {% if ((doc.get("loan_application").get("pledge_status") == "Partial Success") or (doc.get("loan_application").get("current_total_collateral_value") < doc.get("loan_application").get("requested_total_collateral_value"))) and doc.get("loan_application").get("status") == "Pledge accepted by Lender" and not doc.get("loan_margin_shortfall") %}
                        Congratulations!<br />
                        <br />
                        Your pledge request was successfully considered and was partially accepted for Rs. {{doc.get("loan_application").get("current_total_collateral_value")}} due to
                        technical reasons.<br />
                        <br />
                        Kindly check the app for details under e-sign banner on the dashboard. Please e-sign the loan
                        agreement to avail the loan now.<br />
                        <br />
                        Please go to spark.loans application for more details.<br />
                        <br />
                        You can reach to us through 'Contact Us' on the app.<br />
                        We look forward to serve you soon.<br />
                        <br />
                    {% endif %}
                </span>
            </td>
        </tr>
        <tr>
          <td>&nbsp;</td>
        </tr>
        <tr>
          <td><span style="font-family:Arial, Helvetica, sans-serif; font-size:14px;">Thanks,<br />
            <br />
            The Spark.Loans Team</span></td>
        </tr>
        <tr>
          <td height="25">&nbsp;</td>
        </tr>
      </table></td>
  </tr>
  <tr>
    <td height="138" bgcolor="#ff6565"><table width="700" border="0" align="center" cellpadding="0" cellspacing="0">
        <tr>
          <td class="column" align="center" width="100%" style="padding-bottom:10px"><span style="font-family:Arial, Helvetica, sans-serif; font-size:16px; color:#fff;width: 100% !important; display: block !important; text-align:center">© 2021 Spark Financial Technologies Private Limited</span></td>
          </tr>
          <tr>
          <td class="column" align="center" width="100%" style="width: 100% !important; display: block !important; text-align:center"><a href="https://www.facebook.com/Spark-Loans-102197685496313/"><img src="{{ frappe.utils.get_url('/assets/lms/mail_images/fb-icon.png') }}" width="36" height="35" style="border:0"/></a>&nbsp;  <a href="https://www.instagram.com/spark.loans/"><img src="{{ frappe.utils.get_url('/assets/lms/mail_images/inst-icon.png') }}" width="36" height="35" style="border:0"/></a>&nbsp; <a href="https://www.linkedin.com/company/74991731/"><img src="{{ frappe.utils.get_url('/assets/lms/mail_images/lin-icon.png') }}" width="36" height="35" style="border:0"/></a></td>
        </tr>
      </table></td>
  </tr>
  <tr>
    <td>&nbsp;</td>
  </tr>
</table>
</body>
</html>
