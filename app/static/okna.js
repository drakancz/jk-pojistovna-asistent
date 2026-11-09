// Potvrzovací okna: tlačítko s data-otevri="id" otevře <dialog id="id">,
// tlačítko s data-zavri ho zavře. Soubor jde z naší adresy, CSP ho pustí.
document.addEventListener("click", (udalost) => {
  const cil = udalost.target instanceof Element ? udalost.target : null;
  const otevri = cil?.closest("[data-otevri]");
  if (otevri) {
    document.getElementById(otevri.getAttribute("data-otevri"))?.showModal();
    return;
  }
  const zavri = cil?.closest("[data-zavri]");
  if (zavri) zavri.closest("dialog")?.close();
});
