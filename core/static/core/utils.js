function showTransfer(el) {
    transfer_box = document.getElementById("transfer-box");
    if (el.checked) {
        transfer_box.style.display = "block";
    }
    else {
        transfer_box.style.display = "none";
    }
}

function showInstallments(el) {
    installments_box = document.getElementById("installments");
    installments_box.style.animationDuration = "0.2s";
    installments_box.style.animationPlaystate = "paused";
    installments_box.style.animationFillMode = "forwards";
    if (el.checked) {
        installments_box.style.animationName = "slide-down";
        installments_box.style.animationPlaystate = "running";
        installments_box.style.display = "block";
        installments_box.required = true;
        document.getElementById("monthly").setAttribute("disabled", "");
        document.getElementById("bimonthly").setAttribute("disabled", "");
        document.getElementById("quarterly").setAttribute("disabled", "");
        if (document.getElementById("monthly").checked || document.getElementById("quarterly").checked || document.getElementById("bimonthly").checked) {
            document.getElementById("once").checked = true;
        }
        if (document.getElementById("installments").value > 12) {
            document.getElementById("once").checked = true;
            document.getElementById("yearly").setAttribute("disabled", "");
        }
    } else {
        installments_box.style.animationName = "slide-up";
        installments_box.style.animationPlaystate = "running";
        setTimeout(() => {
            installments_box.style.display = "none";
          }, 200)
        installments_box.required = false;
        document.getElementById("monthly").removeAttribute("disabled");
        document.getElementById("bimonthly").removeAttribute("disabled");
        document.getElementById("quarterly").removeAttribute("disabled");
        document.getElementById("yearly").removeAttribute("disabled");
    }
}

function checkInstallments(el) {
    if (el.value > 12) {
        document.getElementById("once").checked = true;
        document.getElementById("yearly").setAttribute("disabled", "");
    }
    else if (el.value <= 12) {
        document.getElementById("yearly").removeAttribute("disabled");
    }
}

function disableInstallment() {
    el = document.getElementById("has_installments");
    el.setAttribute("disabled", "");
    el.checked = false;
}

function enableInstallment() {
    el = document.getElementById("has_installments");
    el.removeAttribute("disabled");
}

function showMore(id) {
    el_button = document.getElementsByClassName(id)[0];
    el = document.getElementById(id);
    el.style.animationDuration = "0.2s";
    el.style.animationPlaystate = "paused";
    el.style.animationFillMode = "forwards";
    if (el_button.innerHTML == "˅") {
        el_button.innerHTML = "˄";
        el.style.animationName = "slide-down";
        el.style.animationPlaystate = "running";
        el.style.display = "table-row";  
    }
    else {
        el_button.innerHTML = "˅";
        el.style.animationName = "slide-up";
        el.style.animationPlaystate = "running";
        setTimeout(() => {
            el.style.display = "none";
          }, 200)
    }
}

function showTransfer(el) {
    transfer_box = document.getElementById("transfer-box");
    transfer_box.style.animationDuration = "0.2s";
    transfer_box.style.animationPlaystate = "paused";
    transfer_box.style.animationFillMode = "forwards";
    settle_checkbox = document.getElementById("settle")
    if (el.checked) {
        transfer_box.style.animationName = "slide-down";
        transfer_box.style.animationPlaystate = "running";
        transfer_box.style.display = "block";
        settle_checkbox.disabled = true;
        document.getElementById("category").setAttribute("disabled", "");
    }
    else {
        transfer_box.style.animationName = "slide-up";
        transfer_box.style.animationPlaystate = "running";
        setTimeout(() => {
            transfer_box.style.display = "none";
          }, 200)
          settle_checkbox.disabled = false;
        document.getElementById("category").removeAttribute("disabled");
    }
}

function showSettle(el) {
    settle_box = document.getElementById("settle-box");
    settle_box.style.animationDuration = "0.2s";
    settle_box.style.animationPlaystate = "paused";
    settle_box.style.animationFillMode = "forwards";
    transfer_checkbox = document.getElementById("transfer")
    if (el.checked) {
        settle_box.style.animationName = "slide-down";
        settle_box.style.animationPlaystate = "running";
        settle_box.style.display = "block";
        transfer_checkbox.disabled = true;
    }
    else {
        settle_box.style.animationName = "slide-up";
        settle_box.style.animationPlaystate = "running";
        setTimeout(() => {
            settle_box.style.display = "none";
          }, 200)
        transfer_checkbox.disabled = false;
    }
}

function submitForm(img) {
    var form = img.parentNode;
    if (form.tagName === 'FORM') {
        form.submit();
    }
}

function showDeleteConfirmation() {
    document.getElementById("delete").style.display = "none";
    document.getElementById("confirmation").style.display = "initial";
}

// Swap between statement and projection tables
function swap_overview_tab(el) {
    if (el.innerHTML == "Overview") {
        document.getElementById("overview").style.display = "block";
        document.getElementById("projection").style.display = "none";
        document.getElementById("projection-button").removeAttribute("disabled");
        el.setAttribute("disabled", "");
    }
    else {
        document.getElementById("projection").style.display = "block";
        document.getElementById("overview").style.display = "none";
        document.getElementById("overview-button").removeAttribute("disabled");
        el.setAttribute("disabled", "");
    }
}