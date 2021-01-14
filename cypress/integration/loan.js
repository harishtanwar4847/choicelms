var loan_app_name = null;
var cart_name = null;
// var token = null;
var pledgor_boid = "1206690000000027";
var extra_token = null;
var token = null;
var extra_loan_app_name = null;

context("Esign", () => {
  before(() => {
    cy.delete_dummy_user();
    cy.register_dummy_user().then((res) => {
      token = res.body.data.token;
      cy.valid_user_kyc_hit(token);
    });
    cy.delete_extra_user();
    cy.register_extra_user().then((res) => {
      extra_token = res.body.data.token;
    });
    cy.valid_user_kyc_hit(extra_token);
  });

  it("only post http method should be allowed", () => {
    cy.api_call("lms.loan.esign", {}, "GET", { Authorization: token }).then(
      (res) => {
        expect(res.status).to.eq(405);
        // expect(res.body).to.eq({});
        expect(res.body).to.have.property("message", "Method not allowed");
        cy.screenshot();
      }
    );
  });

  it("auth method", () => {
    cy.api_call("lms.loan.esign", {}, "POST").then((res) => {
      expect(res.status).to.eq(403);
      cy.screenshot();
    });
  });

  it("loan application not found", () => {
    cy.api_call("lms.loan.esign", { loan_application_name: "LA111" }, "POST", {
      Authorization: token,
    }).then((res) => {
      expect(res.status).to.eq(404);
      // expect(res.body).to.eq({});
      cy.screenshot();
    });
  });

  it("Field empty loan application name", () => {
    cy.api_call("lms.loan.esign", { loan_application_name: "" }, "POST", {
      Authorization: token,
    }).then((res) => {
      expect(res.status).to.eq(422);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Validation Error");
      cy.screenshot();
    });
  });

  it("use your own loan appplication", () => {
    var cart_name = null;
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
        // expect(res.body).to.eq({})
        cy.api_call(
          "lms.cart.process_dummy",
          { cart_name: cart_name },
          "POST",
          {
            Authorization: token,
          }
        ).then((res) => {
          extra_loan_app_name = res.body.message;
          // expect(res.body).to.eq({});
          cy.api_call(
            "lms.loan.esign",
            { loan_application_name: loan_app_name },
            "POST",
            {
              Authorization: extra_token,
            }
          );
          expect(res.status).to.eq(403);
          cy.screenshot();
        });
      });
    });
  });

  it("valid hit esign", () => {
    var cart_name = null;
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
        // expect(res.body).to.eq({})
        cy.api_call(
          "lms.cart.process_dummy",
          { cart_name: cart_name },
          "POST",
          {
            Authorization: token,
          }
        ).then((res) => {
          loan_app_name = res.body.message;
          // expect(res.body).to.eq({});
          cy.api_call(
            "lms.loan.esign",
            { loan_application_name: loan_app_name },
            "POST",
            {
              Authorization: token,
            }
          ).then((res) => {
            expect(res.status).to.eq(200);
            // expect(res.body).to.eq({})
            cy.screenshot();
          });
        });
      });
    });
  });
});

context("Esign done", () => {
  var token = null;
  before(() => {
    cy.delete_dummy_user();
    cy.register_dummy_user().then((res) => {
      token = res.body.data.token;
      cy.valid_user_kyc_hit(token);
    });
  });

  it("only post http method should be allowed", () => {
    cy.api_call("lms.loan.esign", {}, "GET", { Authorization: token }).then(
      (res) => {
        expect(res.status).to.eq(405);
        expect(res.body).to.have.property("message", "Method not allowed");
        cy.screenshot();
      }
    );
  });

  it("auth method", () => {
    cy.api_call("lms.loan.esign_done", {}, "POST").then((res) => {
      expect(res.status).to.eq(403);
      cy.screenshot();
    });
  });

  it("Field empty file ID", () => {
    cy.api_call(
      "lms.loan.esign_done",
      { loan_application_name: loan_app_name, file_id: "" },
      "POST",
      {
        Authorization: token,
      }
    ).then((res) => {
      expect(res.status).to.eq(422);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Validation Error");
      cy.screenshot();
    });
  });

  it("Field empty loan application name", () => {
    // cy.upsert_cart_process_dummy().then((res) => {
    //   var file_id = res.body.data.file_id
    var cart_name = null;
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
        // expect(res.body).to.eq({})
        cy.api_call(
          "lms.cart.process_dummy",
          { cart_name: cart_name },
          "POST",
          {
            Authorization: token,
          }
        ).then((res) => {
          loan_app_name = res.body.message;
          // expect(res.body).to.eq({});
          cy.api_call(
            "lms.loan.esign",
            { loan_application_name: loan_app_name },
            "POST",
            {
              Authorization: token,
            }
          ).then((res) => {
            var file_id = res.body.data.file_id;
            cy.api_call(
              "lms.loan.esign_done",
              { loan_application_name: "", file_id: file_id },
              "POST",
              {
                Authorization: token,
              }
            ).then((res) => {
              expect(res.status).to.eq(422);
              // expect(res.body).to.eq({});
              expect(res.body).to.have.property("message", "Validation Error");
              cy.screenshot();
            });
          });
        });
      });
      // });
    });
  });

  it("Loan Application not found", () => {
    // cy.upsert_cart_process_dummy().then((res) => {
    //   var file_id = res.body.data.file_id
    var cart_name = null;
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
        // expect(res.body).to.eq({})
        cy.api_call(
          "lms.cart.process_dummy",
          { cart_name: cart_name },
          "POST",
          {
            Authorization: token,
          }
        ).then((res) => {
          loan_app_name = res.body.message;
          // expect(res.body).to.eq({});
          cy.api_call(
            "lms.loan.esign",
            { loan_application_name: loan_app_name },
            "POST",
            {
              Authorization: token,
            }
          ).then((res) => {
            var file_id = res.body.data.file_id;
            cy.api_call(
              "lms.loan.esign_done",
              { loan_application_name: "LA111", file_id: file_id },
              "POST",
              {
                Authorization: token,
              }
            ).then((res) => {
              expect(res.status).to.eq(404);
              // expect(res.body).to.eq({});
              cy.screenshot();
            });
          });
        });
      });
      // });
    });
  });

  it("valid esign done", () => {
    // cy.upsert_cart_process_dummy().then((res) => {
    //   var file_id = res.body.data.file_id
    var cart_name = null;
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
        // expect(res.body).to.eq({})
        cy.api_call(
          "lms.cart.process_dummy",
          { cart_name: cart_name },
          "POST",
          {
            Authorization: token,
          }
        ).then((res) => {
          loan_app_name = res.body.message;
          // expect(res.body).to.eq({});
          cy.api_call(
            "lms.loan.esign",
            { loan_application_name: loan_app_name },
            "POST",
            {
              Authorization: token,
            }
          ).then((res) => {
            var file_id = res.body.data.file_id;
            cy.api_call(
              "lms.loan.esign_done",
              { loan_application_name: loan_app_name, file_id: file_id },
              "POST",
              {
                Authorization: token,
              }
            ).then((res) => {
              expect(res.status).to.eq(200);
              // expect(res.body).to.eq({});
              cy.screenshot();
            });
          });
        });
      });
      // });
    });
  });
});
