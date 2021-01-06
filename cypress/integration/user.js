context("User API", () => {
  var token = null;
  it("only get http method should be allowed", () => {
    cy.apicall(
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
      // expect(res.body).to.eq({})
      cy.apicall("lms.user.kyc", {}, "POST", { Authorization: token }).then(
        (res) => {
          expect(res.status).to.eq(405);
          expect(res.body).to.have.property("message", "Method not allowed");
          expect(res.body.message).to.be.a("string");
          cy.screenshot();
        }
      );
    });
  });
  it("KYC not found", () => {
    cy.apicall(
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
    cy.apicall(
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
    cy.apicall(
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
    cy.apicall(
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
    cy.apicall(
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
});
