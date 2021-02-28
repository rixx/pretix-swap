const updateActiveBoxes = () => {
    if (document.querySelector("#id_swap_orderpositions").checked) {
        document.querySelector("#id_swap_orderpositions_specific").disabled = false
        document.querySelector("label[for=id_swap_orderpositions_specific]").parentElement.classList.remove("text-muted")
    } else {
        document.querySelector("#id_swap_orderpositions_specific").disabled = true
        document.querySelector("label[for=id_swap_orderpositions_specific]").parentElement.classList.add("text-muted")
    }

    if (document.querySelector("#id_cancel_orderpositions").checked) {
        document.querySelector("#id_cancel_orderpositions_specific").disabled = false
        document.querySelector("label[for=id_cancel_orderpositions_specific]").parentElement.classList.remove("text-muted")
    } else {
        document.querySelector("#id_cancel_orderpositions_specific").disabled = true
        document.querySelector("label[for=id_cancel_orderpositions_specific]").parentElement.classList.add("text-muted")
    }
}

document.querySelectorAll("input[type=checkbox]").forEach(e => e.addEventListener("change", updateActiveBoxes))

updateActiveBoxes()
