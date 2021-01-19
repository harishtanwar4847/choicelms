var pledgor_boid = "1206690000000027";
var file_id = null;
var token = null;
var cart_name = null;
var loan_app_name = null;
var loan_name = null;
var extra_token = null;
var extra_cart_name = null;
var extra_loan_app_name = null;
var extra_loan_name = null;

context("Esign", () => {
  before(() => {
    cy.delete_user(Cypress.config("dummy_user").email);
    cy.register_user(Cypress.config("dummy_user")).then((res) => {
      Cypress.config("token", res.body.data.token);
      cy.valid_user_kyc_hit(Cypress.config("token"));
    });
    cy.delete_extra_user(Cypress.config("extra_user").email);
    cy.register_extra_user(Cypress.config("extra_user")).then((res) => {
      Cypress.config("extra_token", res.body.data.token);
      cy.valid_user_kyc_hit(Cypress.config("extra_token"));
    });
  });

  it("only post http method should be allowed", () => {
    cy.api_call("lms.loan.esign", {}, "GET", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      expect(res.status).to.eq(405);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Method not allowed");
      cy.screenshot();
    });
  });

  it("auth method", () => {
    cy.api_call("lms.loan.esign", {}, "POST").then((res) => {
      expect(res.status).to.eq(403);
      cy.screenshot();
    });
  });

  it("loan application not found", () => {
    cy.api_call(
      "lms.loan.esign",
      { loan_application_name: "this_loan_app_does_not_exist" },
      "POST",
      {
        Authorization: Cypress.config("token"),
      }
    ).then((res) => {
      expect(res.status).to.eq(404);
      // expect(res.body).to.eq({});
      cy.screenshot();
    });
  });

  it("Field empty loan application name", () => {
    cy.api_call("lms.loan.esign", { loan_application_name: "" }, "POST", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      expect(res.status).to.eq(422);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Validation Error");
      cy.screenshot();
    });
  });

  it("valid hit esign", () => {
    var cart_name = null;
    cy.api_call("lms.user.securities", {}, "GET", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      var securities = res.body.data;
      var approved_securities = securities.filter(
        (x) => x.Is_Eligible && x.Quantity >= 2 && x.Depository == "CDSL"
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
        { Authorization: Cypress.config("token") }
      ).then((res) => {
        cart_name = res.body.data.cart.name;
        // expect(res.body).to.eq({})
        cy.api_call(
          "lms.cart.process_dummy",
          { cart_name: cart_name },
          "POST",
          {
            Authorization: Cypress.config("token"),
          }
        ).then((res) => {
          loan_app_name = res.body.message;
          // expect(res.body).to.eq({});
          cy.api_call(
            "lms.loan.esign",
            { loan_application_name: loan_app_name },
            "POST",
            {
              Authorization: Cypress.config("token"),
            }
          );
          expect(res.status).to.eq(200);
          cy.screenshot();
        });
      });
    });
  });

  it("use your own loan appplication", () => {
    cy.api_call(
      "lms.loan.esign",
      { loan_application_name: loan_app_name },
      "POST",
      {
        Authorization: Cypress.config("extra_token"),
      }
    ).then((res) => {
      expect(res.status).to.eq(403);
      cy.screenshot();
    });
  });
});

context("Esign done", () => {
  before(() => {
    cy.delete_user(Cypress.config("dummy_user").email);
    cy.register_user(Cypress.config("dummy_user")).then((res) => {
      Cypress.config("token", res.body.data.token);
      cy.valid_user_kyc_hit(Cypress.config("token"));
    });
  });

  it("only post http method should be allowed", () => {
    cy.api_call("lms.loan.esign", {}, "GET", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      cy.screenshot();
    });
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
        Authorization: Cypress.config("token"),
      }
    ).then((res) => {
      expect(res.status).to.eq(422);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Validation Error");
      cy.screenshot();
    });
  });

  it("Field empty loan application name", () => {
    var cart_name = null;
    cy.api_call("lms.user.securities", {}, "GET", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      var securities = res.body.data;
      var approved_securities = securities.filter(
        (x) => x.Is_Eligible && x.Quantity >= 2 && x.Depository == "CDSL"
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
        { Authorization: Cypress.config("token") }
      ).then((res) => {
        cart_name = res.body.data.cart.name;
        // expect(res.body).to.eq({})
        cy.api_call(
          "lms.cart.process_dummy",
          { cart_name: cart_name },
          "POST",
          {
            Authorization: Cypress.config("token"),
          }
        ).then((res) => {
          loan_app_name = res.body.message;
          // expect(res.body).to.eq({});
          cy.api_call(
            "lms.loan.esign",
            { loan_application_name: loan_app_name },
            "POST",
            {
              Authorization: Cypress.config("token"),
            }
          ).then((res) => {
            file_id = res.body.data.file_id;
            cy.api_call(
              "lms.loan.esign_done",
              { loan_application_name: "", file_id: file_id },
              "POST",
              {
                Authorization: Cypress.config("token"),
              }
            ).then((res) => {
              // expect(res.body).to.eq({});
              expect(res.status).to.eq(422);
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
    var cart_name = null;
    cy.api_call("lms.user.securities", {}, "GET", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      var securities = res.body.data;
      var approved_securities = securities.filter(
        (x) => x.Is_Eligible && x.Quantity >= 2 && x.Depository == "CDSL"
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
        { Authorization: Cypress.config("token") }
      ).then((res) => {
        cart_name = res.body.data.cart.name;
        // expect(res.body).to.eq({})
        cy.api_call(
          "lms.cart.process_dummy",
          { cart_name: cart_name },
          "POST",
          {
            Authorization: Cypress.config("token"),
          }
        ).then((res) => {
          loan_app_name = res.body.message;
          // expect(res.body).to.eq({});
          cy.api_call(
            "lms.loan.esign",
            { loan_application_name: loan_app_name },
            "POST",
            {
              Authorization: Cypress.config("token"),
            }
          ).then((res) => {
            file_id = res.body.data.file_id;
            cy.api_call(
              "lms.loan.esign_done",
              {
                loan_application_name: "this_loan_app_does_not_exist",
                file_id: file_id,
              },
              "POST",
              {
                Authorization: Cypress.config("token"),
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
    var cart_name = null;
    cy.api_call("lms.user.securities", {}, "GET", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      var securities = res.body.data;
      var approved_securities = securities.filter(
        (x) => x.Is_Eligible && x.Quantity >= 2 && x.Depository == "CDSL"
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
        { Authorization: Cypress.config("token") }
      ).then((res) => {
        cart_name = res.body.data.cart.name;
        // expect(res.body).to.eq({})
        cy.api_call(
          "lms.cart.process_dummy",
          { cart_name: cart_name },
          "POST",
          {
            Authorization: Cypress.config("token"),
          }
        ).then((res) => {
          loan_app_name = res.body.message;
          // expect(res.body).to.eq({});
          cy.api_call(
            "lms.loan.esign",
            { loan_application_name: loan_app_name },
            "POST",
            {
              Authorization: Cypress.config("token"),
            }
          ).then((res) => {
            file_id = res.body.data.file_id;
            cy.api_call(
              "lms.loan.esign_done",
              { loan_application_name: loan_app_name, file_id: file_id },
              "POST",
              {
                Authorization: Cypress.config("token"),
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

context("upload file and Approve loan application", () => {
  it("upload pdf file and approve", () => {
    cy.lender_login();
    cy.go_to_form("Loan Application", loan_app_name);
    cy.wait(2000);
    cy.screenshot();
    cy.get_field("lender_esigned_document", "Attach").click({ force: true });
    cy.get_open_dialog()
      .get(".file-uploader .file-upload-area")
      .attachFile("test.pdf", { subjectType: "drag-n-drop" });
    cy.get_open_dialog()
      .get("button.btn.btn-primary:contains('Upload')")
      .click();
    // cy.wait(2000);
    cy.screenshot();
    cy.contains("Actions").click();
    // cy.wait(3000);
    cy.contains("Approve").click();
    // cy.wait(3000);
    cy.screenshot();
    cy.contains("Settings").click();
    cy.contains("Logout").click();
  });
});

context.skip("upload file and Reject loan application", () => {
  before(() => {
    cy.delete_user(Cypress.config("dummy_user").email);
    cy.register_user(Cypress.config("dummy_user")).then((res) => {
      Cypress.config("token", res.body.data.token);
      cy.valid_user_kyc_hit(Cypress.config("token"));
    });
  });

  it("Reject loan application", () => {
    cy.api_call("lms.user.securities", {}, "GET", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      var securities = res.body.data;
      var approved_securities = securities.filter(
        (x) => x.Is_Eligible && x.Quantity >= 2 && x.Depository == "CDSL"
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
        { Authorization: Cypress.config("token") }
      ).then((res) => {
        cart_name = res.body.data.cart.name;
        // expect(res.body).to.eq({})
        cy.api_call(
          "lms.cart.process_dummy",
          { cart_name: cart_name },
          "POST",
          {
            Authorization: Cypress.config("token"),
          }
        ).then((res) => {
          loan_app_name = res.body.message;
          // expect(res.body).to.eq({});
          cy.api_call(
            "lms.loan.esign",
            { loan_application_name: loan_app_name },
            "POST",
            {
              Authorization: Cypress.config("token"),
            }
          ).then((res) => {
            file_id = res.body.data.file_id;
            cy.api_call(
              "lms.loan.esign_done",
              { loan_application_name: loan_app_name, file_id: file_id },
              "POST",
              {
                Authorization: Cypress.config("token"),
              }
            ).then((res) => {
              expect(res.status).to.eq(200);
              // expect(res.body).to.eq({});
              cy.lender_login();
              cy.go_to_form("Loan Application", loan_app_name);
              cy.wait(2000);
              cy.screenshot();
              cy.contains("Actions").click();
              cy.contains("Reject").click();
              // cy.wait(2000);
              cy.screenshot();
              cy.contains("Settings").click();
              cy.contains("Logout").click();
            });
          });
        });
      });
    });
  });
});

context("Loan details", () => {
  // before(() => {
  //   cy.delete_user(Cypress.config("dummy_user").email);
  //   cy.register_user(Cypress.config("dummy_user")).then((res) => {
  //     Cypress.config("token", res.body.data.token);
  //     cy.valid_user_kyc_hit(Cypress.config("token"));
  //   });
  //   cy.delete_extra_user(Cypress.config("extra_user").email);
  //   cy.register_extra_user(Cypress.config("extra_user")).then((res) => {
  //     Cypress.config("extra_token", res.body.data.token);
  //     cy.valid_user_kyc_hit(Cypress.config("extra_token"));
  //   });
  // });

  it("only get http method should be allowed", () => {
    cy.api_call("lms.loan.loan_details", {}, "POST", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      expect(res.status).to.eq(405);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Method not allowed");
      cy.screenshot();
    });
  });

  it("auth method", () => {
    cy.api_call("lms.loan.loan_details", {}, "GET").then((res) => {
      expect(res.status).to.eq(403);
      cy.screenshot();
    });
  });

  it("loan not found", () => {
    cy.api_call(
      "lms.loan.loan_details",
      { loan_name: "this_loan_does_not_exist" },
      "GET",
      {
        Authorization: Cypress.config("token"),
      }
    ).then((res) => {
      expect(res.status).to.eq(404);
      // expect(res.body).to.eq({});
      cy.screenshot();
    });
  });

  it("Field empty loan name", () => {
    cy.api_call("lms.loan.loan_details", { loan_name: "" }, "GET", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      expect(res.status).to.eq(422);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Validation Error");
      cy.screenshot();
    });
  });

  it("valid hit loan details", () => {
    cy.api_call("lms.user.securities", {}, "GET", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      var securities = res.body.data;
      var approved_securities = securities.filter(
        (x) => x.Is_Eligible && x.Quantity >= 2 && x.Depository == "CDSL"
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
        { Authorization: Cypress.config("token") }
      ).then((res) => {
        cart_name = res.body.data.cart.name;
        // expect(res.body).to.eq({})
        cy.api_call(
          "lms.cart.process_dummy",
          { cart_name: cart_name },
          "POST",
          {
            Authorization: Cypress.config("token"),
          }
        ).then((res) => {
          loan_app_name = res.body.message;
          // expect(res.body).to.eq({});
          cy.api_call(
            "lms.loan.esign",
            { loan_application_name: loan_app_name },
            "POST",
            {
              Authorization: Cypress.config("token"),
            }
          ).then((res) => {
            file_id = res.body.data.file_id;
            cy.api_call(
              "lms.loan.esign_done",
              { loan_application_name: loan_app_name, file_id: file_id },
              "POST",
              {
                Authorization: Cypress.config("token"),
              }
            ).then((res) => {
              expect(res.status).to.eq(200);
              // expect(res.body).to.eq({});
              cy.lender_login();
              cy.go_to_form("Loan Application", loan_app_name);
              cy.wait(5000);
              cy.screenshot();
              cy.get_field("lender_esigned_document", "Attach").click({
                force: true,
              });
              cy.get_open_dialog()
                .get(".file-uploader .file-upload-area")
                .attachFile("test.pdf", { subjectType: "drag-n-drop" });
              cy.get_open_dialog()
                .get("button.btn.btn-primary:contains('Upload')")
                .click();
              cy.wait(5000);
              cy.screenshot();
              cy.contains("Actions").click();
              cy.wait(3000);
              cy.contains("Approve").click();
              cy.wait(3000);
              cy.screenshot();
              cy.contains("Actions").click();
              // cy.wait(3000);
              cy.contains("Approve").click();
              // cy.wait(3000);
              cy.screenshot();
              cy.contains("Settings").click();
              cy.contains("Logout").click();
              cy.admin_api_call("frappe.client.get_list", {
                doctype: "Loan",
              }).then((res) => {
                loan_name = res.body.message[0];
                cy.api_call(
                  "lms.loan.loan_details",
                  { loan_name: loan_name },
                  "GET",
                  {
                    Authorization: Cypress.config("token"),
                  }
                ).then((res) => {
                  expect(res.status).to.eq(200);
                  // expect(res.body).to.eq({});
                  cy.screenshot();
                });
              });
            });
          });
        });
      });
    });
  });

  it("use your own loan", () => {
    cy.api_call("lms.loan.loan_details", { loan_name: loan_name }, "GET", {
      Authorization: Cypress.config("extra_token"),
    }).then((res) => {
      expect(res.status).to.eq(403);
      cy.screenshot();
    });
  });
});

context("Request Loan withdraw OTP", () => {
  it("only post http method should be allowed", () => {
    cy.api_call("lms.loan.request_loan_withdraw_otp", {}, "GET", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      cy.screenshot();
    });
  });

  it("auth method", () => {
    cy.api_call("lms.loan.request_loan_withdraw_otp", {}, "POST").then(
      (res) => {
        expect(res.status).to.eq(403);
        cy.screenshot();
      }
    );
  });

  it("valid hit Loan withdraw OTP", () => {
    // cy.valid_user_kyc_hit(Cypress.config("token"));
    cy.api_call("lms.loan.request_loan_withdraw_otp", {}, "POST", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      expect(res.status).to.eq(200);
      cy.screenshot();
    });
  });
});

context("Loan withdraw Request", () => {
  // before(() => {
  //   cy.delete_user(Cypress.config("dummy_user").email);
  //   cy.register_user(Cypress.config("dummy_user")).then((res) => {
  //     Cypress.config("token", res.body.data.token);
  //     cy.valid_user_kyc_hit(Cypress.config("token"));
  //   });
  //   cy.delete_extra_user(Cypress.config("extra_user").email);
  //   cy.register_extra_user(Cypress.config("extra_user")).then((res) => {
  //     Cypress.config("extra_token", res.body.data.token);
  //     cy.valid_user_kyc_hit(Cypress.config("extra_token"));
  //   });
  // });

  it("only post http method should be allowed", () => {
    cy.api_call("lms.loan.loan_withdraw_request", {}, "GET", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      cy.screenshot();
    });
  });

  it("auth method", () => {
    cy.api_call("lms.loan.loan_withdraw_request", {}, "POST").then((res) => {
      expect(res.status).to.eq(403);
      cy.screenshot();
    });
  });

  it("field empty loan name", () => {
    cy.api_call(
      "lms.loan.loan_withdraw_request",
      { loan_name: "", amount: 1, bank_account_name: "anything", otp: 1111 },
      "POST",
      {
        Authorization: Cypress.config("token"),
      }
    ).then((res) => {
      expect(res.status).to.eq(422);
      // expect(res.body).to.eq({});
      cy.screenshot();
    });
  });

  it("field empty bank account", () => {
    cy.api_call(
      "lms.loan.loan_withdraw_request",
      {
        loan_name: "any_loan_name",
        amount: 1,
        bank_account_name: "",
        otp: 1111,
      },
      "POST",
      {
        Authorization: Cypress.config("token"),
      }
    ).then((res) => {
      expect(res.status).to.eq(422);
      // expect(res.body).to.eq({});
      cy.screenshot();
    });
  });

  it("field empty otp", () => {
    cy.api_call(
      "lms.loan.loan_withdraw_request",
      {
        loan_name: "any_loan_name",
        amount: 1,
        bank_account_name: "bank_name",
        otp: "",
      },
      "POST",
      {
        Authorization: Cypress.config("token"),
      }
    ).then((res) => {
      expect(res.status).to.eq(422);
      // expect(res.body).to.eq({});
      cy.screenshot();
    });
  });

  it("loan not found", () => {
    cy.api_call("lms.loan.request_loan_withdraw_otp", {}, "POST", {
      Authorization: Cypress.config("token"),
    });
    cy.admin_api_call("frappe.client.get_list", {
      doctype: "User Token",
      fields: ["token"],
      filters: {
        entity: "0000000000",
        token_type: "Withdraw OTP",
        used: 0,
      },
    }).then((res) => {
      // expect(res.body).to.eq({});
      var withdraw_otp = res.body.message[0].token;
      cy.api_call(
        "lms.loan.loan_withdraw_request",
        {
          loan_name: "this_loan_does_not_exist",
          amount: 1,
          bank_account_name: "anything",
          otp: withdraw_otp,
        },
        "POST",
        {
          Authorization: Cypress.config("token"),
        }
      ).then((res) => {
        expect(res.status).to.eq(404);
        // expect(res.body).to.eq({});
        cy.screenshot();
      });
    });
  });

  it("bank account not found", () => {
    cy.api_call("lms.user.securities", {}, "GET", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      var securities = res.body.data;
      var approved_securities = securities.filter(
        (x) => x.Is_Eligible && x.Quantity >= 2 && x.Depository == "CDSL"
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
        { Authorization: Cypress.config("token") }
      ).then((res) => {
        cart_name = res.body.data.cart.name;
        // expect(res.body).to.eq({})
        cy.api_call(
          "lms.cart.process_dummy",
          { cart_name: cart_name },
          "POST",
          {
            Authorization: Cypress.config("token"),
          }
        ).then((res) => {
          loan_app_name = res.body.message;
          // expect(res.body).to.eq({});
          cy.api_call(
            "lms.loan.esign",
            { loan_application_name: loan_app_name },
            "POST",
            {
              Authorization: Cypress.config("token"),
            }
          ).then((res) => {
            file_id = res.body.data.file_id;
            cy.api_call(
              "lms.loan.esign_done",
              { loan_application_name: loan_app_name, file_id: file_id },
              "POST",
              {
                Authorization: Cypress.config("token"),
              }
            ).then((res) => {
              expect(res.status).to.eq(200);
              // expect(res.body).to.eq({});
              cy.lender_login();
              cy.go_to_form("Loan Application", loan_app_name);
              cy.wait(5000);
              cy.screenshot();
              cy.get_field("lender_esigned_document", "Attach").click({
                force: true,
              });
              cy.get_open_dialog()
                .get(".file-uploader .file-upload-area")
                .attachFile("test.pdf", { subjectType: "drag-n-drop" });
              cy.get_open_dialog()
                .get("button.btn.btn-primary:contains('Upload')")
                .click();
              cy.wait(5000);
              cy.screenshot();
              cy.contains("Actions").click();
              cy.wait(3000);
              cy.contains("Approve").click();
              cy.wait(3000);
              cy.screenshot();
              cy.contains("Settings").click();
              cy.contains("Logout").click();
              cy.admin_api_call("frappe.client.get_list", {
                doctype: "Loan",
              }).then((res) => {
                loan_name = res.body.message[0];
                cy.api_call("lms.loan.request_loan_withdraw_otp", {}, "POST", {
                  Authorization: Cypress.config("token"),
                });
                cy.admin_api_call("frappe.client.get_list", {
                  doctype: "User Token",
                  fields: ["token"],
                  filters: {
                    entity: "0000000000",
                    token_type: "Withdraw OTP",
                    used: 0,
                  },
                }).then((res) => {
                  // expect(res.body).to.eq({});
                  var withdraw_otp = res.body.message[0].token;
                  cy.api_call(
                    "lms.loan.loan_withdraw_request",
                    {
                      loan_name: loan_name,
                      amount: 1,
                      bank_account_name: "anything",
                      otp: withdraw_otp,
                    },
                    "POST",
                    {
                      Authorization: Cypress.config("token"),
                    }
                  ).then((res) => {
                    expect(res.status).to.eq(404);
                    // expect(res.body).to.eq({});
                    cy.screenshot();
                  });
                });
              });
            });
          });
        });
      });
    });
  });

  it("invalid otp", () => {
    cy.api_call("lms.user.securities", {}, "GET", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      var securities = res.body.data;
      var approved_securities = securities.filter(
        (x) => x.Is_Eligible && x.Quantity >= 2 && x.Depository == "CDSL"
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
        { Authorization: Cypress.config("token") }
      ).then((res) => {
        cart_name = res.body.data.cart.name;
        // expect(res.body).to.eq({})
        cy.api_call(
          "lms.cart.process_dummy",
          { cart_name: cart_name },
          "POST",
          {
            Authorization: Cypress.config("token"),
          }
        ).then((res) => {
          loan_app_name = res.body.message;
          // expect(res.body).to.eq({});
          cy.api_call(
            "lms.loan.esign",
            { loan_application_name: loan_app_name },
            "POST",
            {
              Authorization: Cypress.config("token"),
            }
          ).then((res) => {
            file_id = res.body.data.file_id;
            cy.api_call(
              "lms.loan.esign_done",
              { loan_application_name: loan_app_name, file_id: file_id },
              "POST",
              {
                Authorization: Cypress.config("token"),
              }
            ).then((res) => {
              expect(res.status).to.eq(200);
              // expect(res.body).to.eq({});
              cy.lender_login();
              cy.go_to_form("Loan Application", loan_app_name);
              cy.wait(2000);
              cy.screenshot();
              cy.get_field("lender_esigned_document", "Attach").click({
                force: true,
              });
              cy.get_open_dialog()
                .get(".file-uploader .file-upload-area")
                .attachFile("test.pdf", { subjectType: "drag-n-drop" });
              cy.get_open_dialog()
                .get("button.btn.btn-primary:contains('Upload')")
                .click();
              cy.wait(2000);
              cy.screenshot();
              cy.contains("Actions").click();
              cy.wait(3000);
              cy.contains("Approve").click();
              // cy.wait(3000);
              cy.screenshot();
              cy.contains("Actions").click();
              // cy.wait(3000);
              cy.contains("Approve").click();
              // cy.wait(3000);
              cy.screenshot();
              cy.contains("Settings").click();
              cy.contains("Logout").click();
              cy.admin_api_call("frappe.client.get_list", {
                doctype: "Loan",
              }).then((res) => {
                loan_name = res.body.message[0];
                cy.api_call("lms.loan.request_loan_withdraw_otp", {}, "POST", {
                  Authorization: Cypress.config("token"),
                });
                cy.api_call(
                  "lms.loan.loan_withdraw_request",
                  {
                    loan_name: loan_name,
                    amount: 1,
                    bank_account_name: "anything",
                    otp: 1111,
                  },
                  "POST",
                  {
                    Authorization: Cypress.config("token"),
                  }
                ).then((res) => {
                  expect(res.status).to.eq(422);
                  // expect(res.body).to.eq({});
                  cy.screenshot();
                });
              });
            });
          });
        });
      });
    });
  });

  it("invalid otp length", () => {
    cy.api_call("lms.user.securities", {}, "GET", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      var securities = res.body.data;
      var approved_securities = securities.filter(
        (x) => x.Is_Eligible && x.Quantity >= 2 && x.Depository == "CDSL"
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
        { Authorization: Cypress.config("token") }
      ).then((res) => {
        cart_name = res.body.data.cart.name;
        // expect(res.body).to.eq({})
        cy.api_call(
          "lms.cart.process_dummy",
          { cart_name: cart_name },
          "POST",
          {
            Authorization: Cypress.config("token"),
          }
        ).then((res) => {
          loan_app_name = res.body.message;
          // expect(res.body).to.eq({});
          cy.api_call(
            "lms.loan.esign",
            { loan_application_name: loan_app_name },
            "POST",
            {
              Authorization: Cypress.config("token"),
            }
          ).then((res) => {
            file_id = res.body.data.file_id;
            cy.api_call(
              "lms.loan.esign_done",
              { loan_application_name: loan_app_name, file_id: file_id },
              "POST",
              {
                Authorization: Cypress.config("token"),
              }
            ).then((res) => {
              expect(res.status).to.eq(200);
              // expect(res.body).to.eq({});
              cy.lender_login();
              cy.go_to_form("Loan Application", loan_app_name);
              cy.wait(2000);
              cy.screenshot();
              cy.get_field("lender_esigned_document", "Attach").click({
                force: true,
              });
              cy.get_open_dialog()
                .get(".file-uploader .file-upload-area")
                .attachFile("test.pdf", { subjectType: "drag-n-drop" });
              cy.get_open_dialog()
                .get("button.btn.btn-primary:contains('Upload')")
                .click();
              cy.wait(2000);
              cy.screenshot();
              cy.contains("Actions").click();
              cy.wait(3000);
              cy.contains("Approve").click();
              // cy.wait(3000);
              cy.screenshot();
              cy.contains("Settings").click();
              cy.contains("Logout").click();
              cy.admin_api_call("frappe.client.get_list", {
                doctype: "Loan",
              }).then((res) => {
                loan_name = res.body.message[0];
                cy.api_call("lms.loan.request_loan_withdraw_otp", {}, "POST", {
                  Authorization: Cypress.config("token"),
                });
                cy.api_call(
                  "lms.loan.loan_withdraw_request",
                  {
                    loan_name: loan_name,
                    amount: 1,
                    bank_account_name: "anything",
                    otp: 11111,
                  },
                  "POST",
                  {
                    Authorization: Cypress.config("token"),
                  }
                ).then((res) => {
                  expect(res.status).to.eq(422);
                  // expect(res.body).to.eq({});
                  cy.screenshot();
                });
              });
            });
          });
        });
      });
    });
  });

  it("valid hit loan withdraw request", () => {
    cy.api_call("lms.user.securities", {}, "GET", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      var securities = res.body.data;
      var approved_securities = securities.filter(
        (x) => x.Is_Eligible && x.Quantity >= 2 && x.Depository == "CDSL"
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
        { Authorization: Cypress.config("token") }
      ).then((res) => {
        cart_name = res.body.data.cart.name;
        // expect(res.body).to.eq({})
        cy.api_call(
          "lms.cart.process_dummy",
          { cart_name: cart_name },
          "POST",
          {
            Authorization: Cypress.config("token"),
          }
        ).then((res) => {
          loan_app_name = res.body.message;
          // expect(res.body).to.eq({});
          cy.api_call(
            "lms.loan.esign",
            { loan_application_name: loan_app_name },
            "POST",
            {
              Authorization: Cypress.config("token"),
            }
          ).then((res) => {
            file_id = res.body.data.file_id;
            cy.api_call(
              "lms.loan.esign_done",
              { loan_application_name: loan_app_name, file_id: file_id },
              "POST",
              {
                Authorization: Cypress.config("token"),
              }
            ).then((res) => {
              expect(res.status).to.eq(200);
              // expect(res.body).to.eq({});
              cy.lender_login();
              cy.go_to_form("Loan Application", loan_app_name);
              cy.wait(2000);
              cy.screenshot();
              cy.get_field("lender_esigned_document", "Attach").click({
                force: true,
              });
              cy.get_open_dialog()
                .get(".file-uploader .file-upload-area")
                .attachFile("test.pdf", { subjectType: "drag-n-drop" });
              cy.get_open_dialog()
                .get("button.btn.btn-primary:contains('Upload')")
                .click();
              cy.wait(2000);
              cy.screenshot();
              cy.contains("Actions").click();
              cy.wait(3000);
              cy.contains("Approve").click();
              // cy.wait(3000);
              cy.screenshot();
              cy.contains("Settings").click();
              cy.contains("Logout").click();
              cy.admin_api_call("frappe.client.get_list", {
                doctype: "Loan",
              }).then((res) => {
                loan_name = res.body.message[0];
                cy.api_call("lms.loan.request_loan_withdraw_otp", {}, "POST", {
                  Authorization: Cypress.config("token"),
                });
                cy.admin_api_call("frappe.client.get_list", {
                  doctype: "User Token",
                  fields: ["token"],
                  filters: {
                    entity: "0000000000",
                    token_type: "Withdraw OTP",
                    used: 0,
                  },
                }).then((res) => {
                  // expect(res.body).to.eq({});
                  var withdraw_otp = res.body.message[0].token;
                  cy.valid_user_kyc_hit(Cypress.config("token")).then((res) => {
                    var bank_name = res.body.data.user_kyc.bank_account[0].name;
                    // expect(res.body).to.eq({bank_name});
                    cy.api_call(
                      "lms.loan.loan_withdraw_request",
                      {
                        loan_name: loan_name,
                        amount: 1,
                        bank_account_name: bank_name,
                        otp: withdraw_otp,
                      },
                      "POST",
                      {
                        Authorization: Cypress.config("token"),
                      }
                    ).then((res) => {
                      expect(res.status).to.eq(200);
                      cy.screenshot();
                    });
                  });
                });
              });
            });
          });
        });
      });
    });
  });
});

context("Loan withdraw details", () => {
  // before(() => {
  //   cy.delete_user(Cypress.config("dummy_user").email);
  //   cy.register_user(Cypress.config("dummy_user")).then((res) => {
  //     Cypress.config("token", res.body.data.token);
  //     cy.valid_user_kyc_hit(Cypress.config("token"));
  //   });
  //   cy.delete_extra_user(Cypress.config("extra_user").email);
  //   cy.register_extra_user(Cypress.config("extra_user")).then((res) => {
  //     Cypress.config("extra_token", res.body.data.token);
  //     cy.valid_user_kyc_hit(Cypress.config("extra_token"));
  //   });
  // });

  it("only get http method should be allowed", () => {
    cy.api_call("lms.loan.loan_withdraw_details", {}, "POST", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      expect(res.status).to.eq(405);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Method not allowed");
      cy.screenshot();
    });
  });

  it("auth method", () => {
    cy.api_call("lms.loan.loan_withdraw_details", {}, "GET").then((res) => {
      expect(res.status).to.eq(403);
      cy.screenshot();
    });
  });

  it("loan not found", () => {
    cy.api_call(
      "lms.loan.loan_withdraw_details",
      { loan_name: "this_loan_does_not_exist" },
      "GET",
      {
        Authorization: Cypress.config("token"),
      }
    ).then((res) => {
      expect(res.status).to.eq(404);
      // expect(res.body).to.eq({});
      cy.screenshot();
    });
  });

  it("Field empty loan name", () => {
    cy.api_call("lms.loan.loan_withdraw_details", { loan_name: "" }, "GET", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      expect(res.status).to.eq(422);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Validation Error");
      cy.screenshot();
    });
  });

  it("valid hit loan withdraw details", () => {
    cy.api_call("lms.user.securities", {}, "GET", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      var securities = res.body.data;
      var approved_securities = securities.filter(
        (x) => x.Is_Eligible && x.Quantity >= 2 && x.Depository == "CDSL"
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
        { Authorization: Cypress.config("token") }
      ).then((res) => {
        cart_name = res.body.data.cart.name;
        // expect(res.body).to.eq({})
        cy.api_call(
          "lms.cart.process_dummy",
          { cart_name: cart_name },
          "POST",
          {
            Authorization: Cypress.config("token"),
          }
        ).then((res) => {
          loan_app_name = res.body.message;
          // expect(res.body).to.eq({});
          cy.api_call(
            "lms.loan.esign",
            { loan_application_name: loan_app_name },
            "POST",
            {
              Authorization: Cypress.config("token"),
            }
          ).then((res) => {
            file_id = res.body.data.file_id;
            cy.api_call(
              "lms.loan.esign_done",
              { loan_application_name: loan_app_name, file_id: file_id },
              "POST",
              {
                Authorization: Cypress.config("token"),
              }
            ).then((res) => {
              expect(res.status).to.eq(200);
              // expect(res.body).to.eq({});
              cy.lender_login();
              cy.go_to_form("Loan Application", loan_app_name);
              cy.wait(2000);
              cy.screenshot();
              cy.get_field("lender_esigned_document", "Attach").click({
                force: true,
              });
              cy.get_open_dialog()
                .get(".file-uploader .file-upload-area")
                .attachFile("test.pdf", { subjectType: "drag-n-drop" });
              cy.get_open_dialog()
                .get("button.btn.btn-primary:contains('Upload')")
                .click();
              cy.wait(2000);
              cy.screenshot();
              cy.contains("Actions").click();
              cy.wait(3000);
              cy.contains("Approve").click();
              // cy.wait(3000);
              cy.screenshot();
              cy.contains("Settings").click();
              cy.contains("Logout").click();
              cy.admin_api_call("frappe.client.get_list", {
                doctype: "Loan",
              }).then((res) => {
                loan_name = res.body.message[0];
                cy.api_call(
                  "lms.loan.loan_withdraw_details",
                  { loan_name: loan_name },
                  "GET",
                  {
                    Authorization: Cypress.config("token"),
                  }
                ).then((res) => {
                  expect(res.status).to.eq(200);
                  // expect(res.body).to.eq({});
                  cy.screenshot();
                });
              });
            });
          });
        });
      });
    });
  });

  it("use your own loan", () => {
    cy.api_call(
      "lms.loan.loan_withdraw_details",
      { loan_name: loan_name },
      "GET",
      {
        Authorization: Cypress.config("extra_token"),
      }
    ).then((res) => {
      expect(res.status).to.eq(403);
      cy.screenshot();
    });
  });
});

context("Request Loan withdraw OTP", () => {
  // before(() => {
  //   cy.delete_user(Cypress.config("dummy_user").email);
  //   cy.register_user(Cypress.config("dummy_user")).then((res) => {
  //     Cypress.config("token", res.body.data.token);
  //     cy.valid_user_kyc_hit(Cypress.config("token"));
  //   });
  //   cy.delete_extra_user(Cypress.config("extra_user").email);
  //   cy.register_extra_user(Cypress.config("extra_user")).then((res) => {
  //     Cypress.config("extra_token", res.body.data.token);
  //     cy.valid_user_kyc_hit(Cypress.config("extra_token"));
  //   });
  // });

  it("only post http method should be allowed", () => {
    cy.api_call("lms.loan.loan_payment", {}, "GET", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      cy.screenshot();
    });
  });

  it("auth method", () => {
    cy.api_call("lms.loan.loan_payment", {}, "POST").then((res) => {
      expect(res.status).to.eq(403);
      cy.screenshot();
    });
  });
});
