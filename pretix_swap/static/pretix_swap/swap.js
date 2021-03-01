const typeSelect = document.querySelector("#id_swap_type")
const swapMethodSelect = document.querySelector("#id_swap_method")
const cancelMethodSelect = document.querySelector("#id_cancel_method")

const visibilities = {  // Type, Method
    "s,f": ["#id_swap_method"],  // swap, free: neither swap code nor cancel code visible
    "s,s": ["#id_swap_method", "#id_swap_code"],  // swap, specific: swap code visible
    "c,f": ["#id_cancel_method"],  // cancel, free: neither swap code nor cancel code visible
    "c,s": ["#id_cancel_method", "#id_cancel_code"],  // cancel, specific: cancel code visible
}

const updateCodeVisibility = () => {
    if (!typeSelect) return
    const currentMethodSelect = typeSelect == "s" ? swapMethodSelect : cancelMethodSelect

    const method = currentMethodSelect ? currentMethodSelect.value : "s"  // gotta have some default, let's use swap
    const type = typeSelect ? typeSelect.value : "f"  // free is always allowed

    const visible = visibilities[`${type},${method}`]
    const fields = ["#id_cancel_code", "#id_swap_code", "#id_cancel_method", "#id_swap_method"]
    fields.forEach(e => {visible.includes(e) ? $(e).parent().show() : $(e).parent().hide()})
}

if (typeSelect) typeSelect.addEventListener("change", updateCodeVisibility)
if (swapMethodSelect) swapMethodSelect.addEventListener("change", updateCodeVisibility)
if (cancelMethodSelect) cancelMethodSelect.addEventListener("change", updateCodeVisibility)
updateCodeVisibility()


const positionChoices = Array.from(document.querySelector("#id_position").options)

const hidePositionChoices = () => {
    const currentChoice = document.querySelector("#id_position").value
    const type = typeSelect ? typeSelect.value : "s"
    positionChoices.forEach(choice => {
        if ((choice.value !== currentChoice) || (type === "c")) {
            $(`#id_position_choice_${choice.value}`).parent().hide()
        } else {
            const el = document.querySelector(`#id_position_choice_${choice.value}`)
            if (el.options.length > 2) {$(el).parent().show()} else {$(el).parent().hide()}
        }
    })
}
document.querySelector("#id_position").addEventListener("change", hidePositionChoices)
if (typeSelect) typeSelect.addEventListener("change", hidePositionChoices)
hidePositionChoices()


const hideIfUseless = ["#id_swap_type"]
hideIfUseless.forEach(e => {
    el = document.querySelector(e)
    if (el && el.options.length === 1) $(el).parent().hide()
})
