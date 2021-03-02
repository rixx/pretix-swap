document.querySelectorAll(".copyable").forEach(e => {
    e.style.cursor = "pointer"
    e.addEventListener("click", e => {
        var $temp = $("<input>")
        $("body").append($temp)
        const $target = $(e.target)
        $temp.val($target.data("destination")).select()
        document.execCommand("copy")
        $temp.remove()
        const previousTitle = e.target.dataset["originalTitle"]
        e.target.title = "Copied!"
        e.target.dataset["originalTitle"] = "Copied!"
        $target.tooltip('show')
        window.setTimeout(() => {
          e.target.title = previousTitle
          e.target.dataset["originalTitle"] = previousTitle
            $target.tooltip('hide')
        }, 600)
    })
})

document.querySelectorAll(".secret").forEach(e => {
    e.style.color = "transparent";
    e.style.textShadow = "0 0 5px rgba(0,0,0,1.2)";
    e.style.filter = "blur(5px)"
    e.style.margin = "0px 8px"
    e.addEventListener("mouseenter", ev => {
        const e = ev.target
        e.style.filter = ""
        e.style.textShadow = ""
        e.style.color = "black"
    })
    e.addEventListener("mouseleave", ev => {
        const e = ev.target
        e.style.filter = "blur(5px)";
        e.style.textShadow = "0 0 5px rgba(0,0,0,1.2)";
        e.style.color = "transparent"
    })
})
