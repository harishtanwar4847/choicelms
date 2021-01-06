context("User API", () => {
  var token = null;
  before(() => {
    cy.admin_api_call("frappe.client.delete", {
      doctype: "User",
      name: "0000000000@example.com",
    });
    cy.api_call(
      "lms.auth.register",
      {
        first_name: "abcd",
        last_name: "efgh",
        mobile: "0000000000",
        email: "0000000000@example.com",
        firebase_token: "asdf",
      },
      "POST"
    ).then((res) => {
      token = res.body.data.token;
    });
  });
  it("only get http method should be allowed(KYC)", () => {
    cy.api_call("lms.user.kyc", {}, "POST", { Authorization: token }).then(
      (res) => {
        expect(res.status).to.eq(405);
        expect(res.body).to.have.property("message", "Method not allowed");
        expect(res.body.message).to.be.a("string");
        cy.screenshot();
      }
    );
  });
  it("KYC not found", () => {
    cy.api_call(
      "lms.user.kyc",
      { pan_no: "ABCD2795", birth_date: "12-12-1999", accept_terms: true },
      "GET",
      { Authorization: token }
    ).then((res) => {
      expect(res.status).to.eq(404);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "User KYC not found");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });
  it("field empty pan no", () => {
    cy.api_call(
      "lms.user.kyc",
      { pan_no: "", birth_date: "12-12-1999", accept_terms: true },
      "GET",
      { Authorization: token }
    ).then((res) => {
      expect(res.status).to.eq(422);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body.message).to.be.a("string");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("pan_no");
      expect(res.body.errors.pan_no).to.be.a("string");
      cy.screenshot();
    });
  });
  it("field empty birth date", () => {
    cy.api_call(
      "lms.user.kyc",
      { pan_no: "ABCD2795", birth_date: "", accept_terms: true },
      "GET",
      { Authorization: token }
    ).then((res) => {
      expect(res.status).to.eq(422);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body.message).to.be.a("string");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("birth_date");
      expect(res.body.errors.birth_date).to.be.a("string");
      cy.screenshot();
    });
  });
  it("accept terms false", () => {
    cy.api_call(
      "lms.user.kyc",
      { pan_no: "ABCD2795", birth_date: "12-12-1999", accept_terms: false },
      "GET",
      { Authorization: token }
    ).then((res) => {
      expect(res.status).to.eq(401);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property(
        "message",
        "Please accept Terms and Conditions."
      );
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });
  it("Valid User KYC hit", () => {
    cy.api_call(
      "lms.user.kyc",
      { pan_no: "AAKHR7426K", birth_date: "01-01-1970", accept_terms: true },
      "GET",
      { Authorization: token }
    ).then((res) => {
      expect(res.status).to.eq(200);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Success");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });
  it("only get http method should be allowed(securities)", () => {
    cy.api_call("lms.user.securities", {}, "POST", {
      Authorization: token,
    }).then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });
  it("Valid Securities hit", () => {
    cy.api_call("lms.user.securities", {}, "GET", {
      Authorization: token,
    }).then((res) => {
      expect(res.status).to.eq(200);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Success");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });
});
