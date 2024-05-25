function populateForm(formElement, data) {
    const entries = Object.entries(data)
    console.log(formElement, entries)
    entries.forEach(([key, value]) => {
        const el = formElement.querySelector(`[name="${key}"], #${key}`)
        if (!el) return
        const tag = el.tagName.toLowerCase()
        console.log(key, tag)
        if (tag === "input" || tag === "select" || tag === "textarea")
            el.value = value
        else if (tag === "ul" && Array.isArray(value)) {
            value.forEach(v => {
                formElement.querySelector(`button[data-list-add='${el.id}']`).click()
                const items = el.querySelectorAll("li")
                populateForm(items[items.length - 1], v)
            })
        }
    })
}

function implementFormButtons(formElement, onSubmit) {
    formElement.addEventListener("submit", onSubmit)

    const listAddButtons = formElement.querySelectorAll("button[data-list-add]")
    listAddButtons.forEach(button => {
        button.addEventListener("click", (e) => {
            e.preventDefault()
            const list = formElement.querySelector(`#${button.dataset.listAdd}`)
            list.appendChild(list.querySelector("template").content.cloneNode(true))
        })
    })

    const lists = formElement.querySelectorAll("ul")
    lists.forEach(list => {
        list.addEventListener("click", (e) => {
            e.preventDefault()
            if (e.target.dataset.hasOwnProperty("listRemove")) {
                let el = e.target;
                while (el !== undefined) {
                    if (el.tagName.toLowerCase() === "li") {
                        el.remove()
                        break;
                    }
                    el = el.parentElement;
                }
            }
        })
    })
}

function formToJson(form) {
    const formData = new FormData(form);
    const json = {};

    formData.forEach((value, key) => {
        if (json[key]) {
            if (!Array.isArray(json[key]))
                json[key] = [json[key]]
            json[key].push(value)
        } else json[key] = value
    });

    const nestedElements = form.querySelectorAll("ul[id]");
    nestedElements.forEach(ul => {
        const ulId = ul.id;
        json[ulId] = [];
        ul.querySelectorAll("li").forEach(li => {
            const liJson = {}
            li.querySelectorAll("input, select, textarea").forEach(input =>
                liJson[input.name] = input.value)
            json[ulId].push(liJson);
        });
    });

    return json
}

function formHelper(dataStr, system) {

    document.addEventListener("DOMContentLoaded", () => {
        let extractedData = {}
        try {
            extractedData = JSON.parse(dataStr.replaceAll("&#39;", "\""))
        } catch (err) {
            console.error("Failed to parse extracted data", err)
        }
        const savedData = JSON.parse(localStorage.getItem(`${system}-saved`) || "{}")
        const data = {...savedData, ...extractedData}
        const form = document.querySelector("form")

        implementFormButtons(form, (e) => {
            e.preventDefault()

            const savedData = {}
            form.querySelectorAll("[data-save]").forEach(el => {
                if (!el.name || !el.value) return
                savedData[el.name] = el.value
            })
            localStorage.setItem(`${system}-saved`, JSON.stringify(savedData))

            const json = formToJson(form)

            fetch(`/action/${system}/execute`, {
                method: "POST",
                headers: {"content-type": "application/json"},
                body: JSON.stringify(json)
            })
                .catch(err => console.log(err))
                .finally(() => window.location.href = "/action/queued")
        })
        populateForm(form, data)
    })
}