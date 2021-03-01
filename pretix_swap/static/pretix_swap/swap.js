const typeSelect = document.querySelector("#id_swap_type")
const swapMethodSelect = document.querySelector("#id_swap_method")
const cancelMethodSelect = document.querySelector("#id_cancel_method")
const positionChoices = Array.from(document.querySelector("#id_position").options)

const visibilities = {  // Type, Method
    "s,f": ["#id_swap_method"],  // swap, free: neither swap code nor cancel code visible
    "s,s": ["#id_swap_method", "#id_swap_code"],  // swap, specific: swap code visible
    "c,f": ["#id_cancel_method"],  // cancel, free: neither swap code nor cancel code visible
    "c,s": ["#id_cancel_method", "#id_cancel_code"],  // cancel, specific: cancel code visible
}

const updateVisibility = () => {
    const type = typeSelect ? typeSelect.value : "s"  // gotta have some default, let's use swap
    const currentMethodSelect = type == "s" ? swapMethodSelect : cancelMethodSelect
    const method = currentMethodSelect ? currentMethodSelect.value : "f"  // gotta have some default, let's use free

    const visible = visibilities[`${type},${method}`]
    const fields = ["#id_cancel_code", "#id_swap_code", "#id_cancel_method", "#id_swap_method"]
    fields.forEach(e => {visible.includes(e) ? $(e).parent().show() : $(e).parent().hide()})

    const currentChoice = document.querySelector("#id_position").value
    positionChoices.forEach(choice => {
        if ((choice.value !== currentChoice) || (type === "c") || (method === "s")) {
            $(`#id_position_choice_${choice.value}`).parent().hide()
        } else {
            const el = document.querySelector(`#id_position_choice_${choice.value}`)
            if (el.options.length > 2) {$(el).parent().show()} else {$(el).parent().hide()}
        }
    })
}

if (typeSelect) typeSelect.addEventListener("change", updateVisibility)
if (swapMethodSelect) swapMethodSelect.addEventListener("change", updateVisibility)
if (cancelMethodSelect) cancelMethodSelect.addEventListener("change", updateVisibility)
document.querySelector("#id_position").addEventListener("change", updateVisibility)
updateVisibility()


const hideIfUseless = ["#id_swap_type"]
hideIfUseless.forEach(e => {
    el = document.querySelector(e)
    if (el && el.options.length === 1) $(el).parent().hide()
})
