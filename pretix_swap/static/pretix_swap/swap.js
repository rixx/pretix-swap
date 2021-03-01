const typeSelect = document.querySelector("#id_swap_type")

if (typeSelect) {
    const updateVisibility = () => {
        const mode = document.querySelector("#id_swap_method").value
        if (typeSelect.value === "s") {
            if (mode === "s") {
                $("#id_cancel_code").parent().hide()
                $("#id_swap_code").parent().show()
            } else {
                $("#id_cancel_code").parent().hide()
                $("#id_swap_code").parent().hide()
            }
        } else {
            if (mode === "s") {
                $("#id_cancel_code").parent().show()
                $("#id_swap_code").parent().hide()
            } else {
                $("#id_cancel_code").parent().hide()
                $("#id_swap_code").parent().hide()
            }
        } 
    }

    typeSelect.addEventListener("change", updateVisibility)
    document.querySelector("#id_swap_method").addEventListener("change", updateVisibility)
    updateVisibility()
}


const positionChoices = Array.from(document.querySelector("#id_position").options)

const hidePositionChoices = () => {
    const currentChoice = document.querySelector("#id_position").value
    positionChoices.forEach(choice => {
        if (choice.value === currentChoice) {
            const el = document.querySelector(`#id_position_choice_${choice.value}`)
            if (el.options.length > 2) {$(el).parent().show()} else {$(el).parent().hide()}
        } else {
            $(`#id_position_choice_${choice.value}`).parent().hide()
        }
    })
}
document.querySelector("#id_position").addEventListener("change", hidePositionChoices)
hidePositionChoices()
