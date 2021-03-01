const typeSelect = document.querySelector("#id_swap_type")

if (typeSelect) {
    const updateVisibility = () => {
        if (typeSelect.value === "s") {
            $("#id_cancel_code").parent().hide()
            $("#id_swap_code").parent().show()
        } else {
            $("#id_cancel_code").parent().show()
            $("#id_swap_code").parent().hide()
        }
    }

    typeSelect.addEventListener("change", updateVisibility)
    updateVisibility()
}
