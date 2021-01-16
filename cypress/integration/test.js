context("upload file", () => {
  it("upload pdf file", () => {
    cy.lender_login();
    cy.go_to_form("Loan Application", "LA000263");
    cy.screenshot();
    cy.get_field("lender_esigned_document", "Attach").click({ force: true });
    // cy.screenshot();
    cy.get_open_dialog()
      .get(".file-uploader .file-upload-area")
      .attachFile("test.pdf", { subjectType: "drag-n-drop" });
    cy.get_open_dialog()
      .get("button.btn.btn-primary:contains('Upload')")
      .click();
    cy.screenshot();
    cy.contains("Actions").click();
    cy.contains("Approve").click();
    cy.wait(2000);
    cy.screenshot();
  });
});
