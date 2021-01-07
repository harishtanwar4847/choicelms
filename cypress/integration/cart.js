context("Cart API", () => {
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
  it("only post http method should be allowed", () => {
    cy.api_call("lms.cart.upsert", {}, "GET", { Authorization: token }).then(
      (res) => {
        expect(res.status).to.eq(405);
        expect(res.body).to.have.property("message", "Method not allowed");
        expect(res.body.message).to.be.a("string");
        cy.screenshot();
      }
    );
  });
  it("Securities required in upsert cart", () => {
    cy.api_call(
      "lms.cart.upsert",
      { pledgor_boid: "1206690000000027" },
      "POST",
      { Authorization: token }
    ).then((res) => {
      expect(res.status).to.eq(422);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body.message).to.be.a("string");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("securities");
      expect(res.body.errors.securities).to.be.a("string");
      cy.screenshot();
    });
  });
  it("Field empty Pledgor boid", () => {
    cy.api_call("lms.cart.upsert", { pledgor_boid: "" }, "POST", {
      Authorization: token,
    }).then((res) => {
      expect(res.status).to.eq(422);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body.message).to.be.a("string");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("pledgor_boid");
      expect(res.body.errors.pledgor_boid).to.be.a("string");
      cy.screenshot();
    });
  });
  it("ISIN not found", () => {
    cy.api_call(
      "lms.cart.upsert",
      {
        securities: { list: [{ isin: "INE280" }, { isin: "" }] },
        pledgor_boid: "1206690000000027",
      },
      "POST",
      { Authorization: token }
    ).then((res) => {
      expect(res.status).to.eq(422);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body.message).to.be.a("string");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("securities");
      expect(res.body.errors.securities).to.be.a("string");
      cy.screenshot();
    });
  });
  it("valid hit upsert cart", () => {
    cy.api_call(
      "lms.cart.upsert",
      {
        securities: {
          list: [
            { isin: "INE280A01028", quantity: 1 },
            { isin: "INE101A01026", quantity: 1 },
          ],
        },
        pledgor_boid: "1206690000000027",
      },
      "POST",
      { Authorization: token }
    ).then((res) => {
      expect(res.status).to.eq(200);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Success");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });

  it("only post http method should be allowed req pledge otp", () => {
    cy.api_call("lms.cart.request_pledge_otp", {}, "GET", {
      Authorization: token,
    }).then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });
  it("Kyc not found in req pledge otp", () => {
    cy.admin_api_call("frappe.client.get_list", {
      doctype: "Customer",
      username: "0000000000@example.com",
    });
    cy.api_call(
      "lms.user.kyc",
      { pan_no: "ABCD2795", birth_date: "12-12-1999", accept_terms: true },
      "GET",
      { Authorization: token }
    );
    cy.api_call("lms.cart.request_pledge_otp", {}, "POST", {
      Authorization: token,
    }).then((res) => {
      expect(res.status).to.eq(404);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "User KYC not found");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });
  it("valid hit req pledge otp", () => {
    cy.admin_api_call("frappe.client.get_list", {
      doctype: "Customer",
      username: "0000000000@example.com",
    });
    cy.api_call(
      "lms.user.kyc",
      { pan_no: "AAKHR7426K", birth_date: "01-01-1970", accept_terms: true },
      "GET",
      { Authorization: token }
    );
    cy.api_call("lms.cart.request_pledge_otp", {}, "POST", {
      Authorization: token,
    }).then((res) => {
      expect(res.status).to.eq(200);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Pledge OTP sent");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });
});
