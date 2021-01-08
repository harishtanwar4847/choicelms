var cart_name = null;
var token = null;

context("Cart Upsert", () => {
  var pledgor_boid = "1206690000000027";
  before(() => {
    cy.delete_dummy_user();
    cy.register_dummy_user().then((res) => {
      token = res.body.data.token;
      cy.valid_user_kyc_hit(token);
    });
  });

  it("only post http method should be allowed", () => {
    cy.api_call("lms.cart.upsert", {}, "GET", { Authorization: token }).then(
      (res) => {
        expect(res.status).to.eq(405);
        expect(res.body).to.have.property("message", "Method not allowed");
        cy.screenshot();
      }
    );
  });

  it("auth method", () => {
    cy.api_call("lms.cart.upsert", {}, "POST").then((res) => {
      expect(res.status).to.eq(403);
      cy.screenshot();
    });
  });

  it("Securities required in upsert cart", () => {
    cy.api_call("lms.cart.upsert", { pledgor_boid: pledgor_boid }, "POST", {
      Authorization: token,
    }).then((res) => {
      expect(res.status).to.eq(422);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Validation Error");
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
        pledgor_boid: pledgor_boid,
      },
      "POST",
      { Authorization: token }
    ).then((res) => {
      expect(res.status).to.eq(422);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("securities");
      expect(res.body.errors.securities).to.be.a("string");
      cy.screenshot();
    });
  });

  it("valid hit upsert cart", () => {
    cy.api_call("lms.user.securities", {}, "GET", {
      Authorization: token,
    }).then((res) => {
      var securities = res.body.data;
      var approved_securities = securities.filter(
        (x) => x.Is_Eligible && x.Quantity >= 1 && x.Depository == "CDSL"
      );
      var securities_list = [];
      if (approved_securities.length >= 1) {
        securities_list.push({
          isin: approved_securities[0].ISIN,
          quantity: 1,
        });
      }
      if (approved_securities.length >= 2) {
        securities_list.push({
          isin: approved_securities[1].ISIN,
          quantity: 1,
        });
      }
      cy.api_call(
        "lms.cart.upsert",
        {
          securities: {
            list: securities_list,
          },
          pledgor_boid: pledgor_boid,
        },
        "POST",
        { Authorization: token }
      ).then((res) => {
        cart_name = res.body.data.cart.name;
        expect(res.status).to.eq(200);
        // expect(res.body).to.eq({});
        expect(res.body).to.have.property("message", "Success");
        cy.screenshot();
      });
    });
  });
});

context("Get TnC", () => {
  // var token = null;
  // before(() => {
  //   cy.delete_dummy_user();
  //   cy.register_dummy_user().then((res) => {
  //     token = res.body.data.token;
  //   });
  //   cy.valid_user_kyc_hit(token);
  // });

  it("only get http method should be allowed", () => {
    cy.api_call("lms.cart.get_tnc", {}, "POST", {
      Authorization: token,
    }).then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      cy.screenshot();
    });
  });

  it("auth method", () => {
    cy.api_call("lms.cart.get_tnc", {}, "GET").then((res) => {
      expect(res.status).to.eq(403);
      cy.screenshot();
    });
  });

  it("cart name required", () => {
    cy.api_call("lms.cart.get_tnc", {}, "GET", {
      Authorization: token,
    }).then((res) => {
      expect(res.status).to.eq(422);
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("cart_name");
      expect(res.body.errors.cart_name).to.be.a("string");
      cy.screenshot();
    });
  });

  it("valid hit get tnc", () => {
    cy.valid_user_kyc_hit(token);
    cy.api_call("lms.cart.get_tnc", { cart_name: cart_name }, "GET", {
      Authorization: token,
    }).then((res) => {
      expect(res.status).to.eq(200);
      expect(res.body).to.have.property("message", "Success");
      cy.screenshot();
    });
  });
});

context("Request Pledge OTP", () => {
  var token = null;
  before(() => {
    cy.delete_dummy_user();
    cy.register_dummy_user().then((res) => {
      token = res.body.data.token;
    });
    cy.valid_user_kyc_hit(token);
  });

  it("only post http method should be allowed", () => {
    cy.api_call("lms.cart.request_pledge_otp", {}, "GET", {
      Authorization: token,
    }).then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      cy.screenshot();
    });
  });

  it("auth method", () => {
    cy.api_call("lms.cart.request_pledge_otp", {}, "POST").then((res) => {
      expect(res.status).to.eq(403);
      cy.screenshot();
    });
  });

  it("Kyc not found in req pledge otp", () => {
    cy.api_call("lms.cart.request_pledge_otp", {}, "POST", {
      Authorization: token,
    }).then((res) => {
      expect(res.status).to.eq(404);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "User KYC not found");
      cy.screenshot();
    });
  });

  it("valid hit req pledge otp", () => {
    cy.valid_user_kyc_hit(token);
    cy.api_call("lms.cart.request_pledge_otp", {}, "POST", {
      Authorization: token,
    }).then((res) => {
      expect(res.status).to.eq(200);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Pledge OTP sent");
      cy.screenshot();
    });
  });
});
