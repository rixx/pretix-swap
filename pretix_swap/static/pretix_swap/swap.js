const swapMethodSelect = document.querySelector("#id_details-swap_method")
const swapCode = document.querySelector("#id_details-swap_code")
const cancelCode = document.querySelector("#id_details-cancel_code")

const updateVisibility = () => {
    if (swapMethodSelect.value === "f") {
        if (swapCode) $(swapCode).parent().parent().hide()
        if (cancelCode) $(cancelCode).parent().parent().hide()
    } else {
        if (swapCode) $(swapCode).parent().parent().show()
        if (cancelCode) $(cancelCode).parent().parent().show()
    }
}

if (swapMethodSelect) swapMethodSelect.addEventListener("change", updateVisibility)
updateVisibility()
