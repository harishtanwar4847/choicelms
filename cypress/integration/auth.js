context("Login API", () => {
  it("only post http method should be allowed", () => {
    cy.apicall("lms.auth.login", {}, "GET").then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });

  it("mobile number required", () => {
    cy.apicall("lms.auth.login", {}, "POST").then((res) => {
      expect(res.status).to.eq(422);
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body.message).to.be.a("string");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("mobile");
      expect(res.body.errors.mobile).to.be.a("string");
      cy.screenshot();
    });
  });

  it("valid hit with mobile number", () => {
    cy.apicall(
      "lms.auth.login",
      { mobile: "9876543210", accept_terms: true },
      "POST"
    ).then((res) => {
      expect(res.status).to.eq(200);
      expect(res.body).to.have.property("message", "OTP Sent");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });
});

context("Verify OTP Api", () => {
  it("only post http method should be allowed", () => {
    cy.apicall("lms.auth.verify_otp", {}, "GET").then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });

  it("valid otp", () => {
    cy.apicall(
      "lms.auth.login",
      { mobile: "9876543210", accept_terms: true },
      "POST"
    );
    cy.apicall(
      "frappe.client.get_list",
      { doctype: "User Token", fields: ["token"] },
      "POST",
      {
        Authorization:
          "token " +
          Cypress.config("adminApiKey") +
          ":" +
          Cypress.config("adminApiSecret"),
      }
    ).then((res) => {
      var otp = res.body.message[0].token;
      cy.apicall(
        "lms.auth.verify_otp",
        { mobile: "9876543210", otp: otp, firebase_token: "janabe" },
        "POST"
      ).then((res) => {
        expect(res.status).to.eq(404);
        expect(res.body).to.have.property("message", "User not found.");
        expect(res.body.message).to.be.a("string");
        cy.screenshot();
      });
    });
  });
});
