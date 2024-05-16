import re
import threading
import time
import os

import openai
from flask import Flask, render_template, abort, request
from selenium import webdriver
from selenium.common.exceptions import *
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

driver = None

app = Flask(__name__)

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OpenAI API key not found. Please set the OPENAI_API_KEY environment variable.")
openai_client = openai.OpenAI(api_key=api_key)

valid_systems = ["SISBAJUD"]


def wait_for_page_load(driver, url: str = None, timeout: int = 30):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    if url is not None and not driver.current_url.startswith(url):
        raise AssertionError("Reached different page.")


def wait_for_element(driver, identifier: str, timeout: int = 10, id_type: str = By.XPATH):
    return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((id_type, identifier)))


def wait_for_element_invisible(driver, identifier: str, timeout: int = 10, id_type: str = By.XPATH):
    WebDriverWait(driver, timeout).until(EC.invisibility_of_element_located((id_type, identifier)))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/action/queued")
def queued():
    return render_template("queued.html")


@app.route("/action/<system>")
def action(system):
    if system.upper() not in valid_systems:
        abort(404)
    return render_template(f"{system.lower()}/start.html", system=system)


@app.route("/action/<system>/extract", methods=["POST"])
def extract(system):
    if system.upper() not in valid_systems:
        abort(404)
    mandado_content = request.form["mandado_content"]
    print(f"[EXTRACT] [{system}] mandado_content={mandado_content}")
    data = None
    if system.lower() == "sisbajud":
        prompt = (
            "Você deve extrair as seguintes informações do mandado a seguir no seguinte formato (os valores são apenas exemplos com instruções). Caso você não encontre algum dos valores, não inclua a chave (caso seja uma lista, deixe a lista vazia)."
            "{"
            "   \"vara\": \"1ª VARA DO TRABALHO DE CIDADE\","
            "   \"numero_mandado\": \"012345-67.8901.2.34.5678\","
            "   \"autor\": \"NOME DO AUTOR (COMO NO CABEÇALHO)\","
            # "   \"executado\": \"NOME DO EXECUTADO (COMO NO CABEÇALHO)\","
            "   \"pesquisados\": ["
            "       {"
            # "           \"nome\": \"NOME DO EXECUTADO A SER PESQUISADO\","
            "           \"cpf_cnpj\": \"012.345.678-90 ou 01.234.567/0001-89\""
            "       }"
            "   ],"
            "   \"valor_pesquisa\": \"R$ 1.234,56\""
            "}")
        print(f"[EXTRACT] [{system}] preparing openai request")
        openai_response = openai_client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user",
                 "content": f"Texto do Mandado:\n{mandado_content}\nRetorne o resultado no formato JSON."}
            ]
        )
        print(f"[EXTRACT] [{system}] openai request responded")
        extracted_data = openai_response.choices[0].message.content
        data = eval(extracted_data)
    print(f"[EXTRACT] [{system}] extracted_data={data}")
    if data is None:
        abort(500)
    return render_template(f"{system.lower()}/confirm.html", data=data, system=system)


@app.route("/action/<system>/execute", methods=["POST"])
def execute(system):
    if system.upper() not in valid_systems:
        abort(404)
    cb = None
    if system.lower() == "sisbajud":
        cb = sisbajud
    if cb is None:
        print(f"[EXECUTE] [{system}] failed to queue")
        abort(404)
    print(f"[EXECUTE] [{system}] reading body...")
    data = request.get_json(force=True)
    print(f"[EXECUTE] [{system}] data={data}")
    action_thread = threading.Thread(target=cb, args=[data])
    print(f"[EXECUTE] [{system}] queued")
    action_thread.start()
    print(f"[EXECUTE] [{system}] started")
    return f"Action {system} initiated successfully."


def sisbajud(data):
    if not re.match(r"^\d.*$", data["vara"]):
        data["vara"] = "1ª " + data["vara"]

    driver.get("https://sisbajud.cloud.pje.jus.br/minuta")
    try:
        wait_for_page_load(driver, "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/auth?")
        wait_for_element(driver, '//*[@id="username"]').send_keys(data["login"])
        wait_for_element(driver, '//*[@id="password"]').send_keys(data["senha"])
        wait_for_element(driver, '//*[@id="kc-login"]').click()
    except AssertionError:
        pass
    wait_for_page_load(driver, "https://sisbajud.cloud.pje.jus.br/minuta")
    wait_for_element(driver,
                     '/html/body/sisbajud-root/uikit-layout/mat-sidenav-container/mat-sidenav-content/sisbajud-pesquisa-minuta/div[1]/div/div[1]/button[1]').click()
    wait_for_page_load(driver, "https://sisbajud.cloud.pje.jus.br/minuta/cadastrar")
    wait_for_element(driver, '//*[@id="mat-input-6"]').send_keys(data["juiz"])
    wait_for_element(driver, '/html/body/div[3]/div/div/div/mat-option/span').click()
    wait_for_element(driver,
                     '/html/body/sisbajud-root/uikit-layout/mat-sidenav-container/mat-sidenav-content/sisbajud-cadastro-minuta/div/div[2]/mat-card[3]/mat-card-content/div[1]/div[3]/mat-form-field/div/div[1]/div/mat-select/div').click()
    wait_for_element(driver,
                     '/html/body/div[3]/div[2]/div/div/div/mat-option[1]/span/ngx-mat-select-search/div/input').send_keys(
        f" - {data['vara']}")
    wait_for_element(driver, '/html/body/div[3]/div[2]/div/div/div/mat-option[2]/span').click()
    wait_for_element(driver, '//*[@id="mat-input-1"]').send_keys(data["numero_mandado"])
    wait_for_element(driver,
                     '/html/body/sisbajud-root/uikit-layout/mat-sidenav-container/mat-sidenav-content/sisbajud-cadastro-minuta/div/div[2]/mat-card[3]/mat-card-content/div[2]/div[2]/mat-form-field/div/div[1]/div').click()
    wait_for_element(driver, '/html/body/div[3]/div[2]/div/div/div/mat-option[3]/span').click()
    wait_for_element(driver, '//*[@id="mat-input-3"]').send_keys(data["autor"])
    for executed in data["pesquisados"]:
        keys = re.sub(r"[^\d]", "", executed["cpf_cnpj"])
        for key in keys:
            wait_for_element(driver, '//*[@id="mat-input-4"]').send_keys(key)
            time.sleep(0.05)
        wait_for_element(driver,
                         '/html/body/sisbajud-root/uikit-layout/mat-sidenav-container/mat-sidenav-content/sisbajud-cadastro-minuta/div/div[2]/div[2]/mat-card/mat-card-content/div/div[1]/div/div[2]/button').click()
        wait_for_element_invisible(driver, '/html/body/sisbajud-root/sisbajud-spinner/div')
        try:
            wait_for_element(driver,
                             '/html/body/div[3]/div/div/snack-bar-container/sisbajud-snack-messenger/div/div[2]/button',
                             1).click()
        except TimeoutException:
            pass
    wait_for_element(driver, '//*[@id="mat-input-5"]').send_keys(data["valor_pesquisa"])
    wait_for_element(driver,
                     '/html/body/sisbajud-root/uikit-layout/mat-sidenav-container/mat-sidenav-content/sisbajud-cadastro-minuta/div/div[2]/div[2]/mat-card/mat-card-content/div/div[2]/div/div[2]/div/button').click()
    # table = wait_for_element(driver, '/html/body/sisbajud-root/uikit-layout/mat-sidenav-container/mat-sidenav-content/sisbajud-cadastro-minuta/div/div[2]/div[2]/div/table')
    # for row in table.find_elements_by_tag_name("tr"):
    #     cells = row.find_elements_by_tag_name("td")
    #     relationship_cell = cells[2]
    #     relationship_count = relationship_cell.find_element_by_tag_name("span").text
    #     if relationship_count == 0:
    #         options_cell = cells[-1]
    #         options_cell.find_element_by_tag_name("button").click()
    #         options_menu = wait_for_element(driver, "cdk-overlay-pane", id_type=By.CLASS_NAME)
    #         options_menu.find_elements_by_tag_name("span")[-1].click()
    print(f"[EXECUTE] [sisbajud] finished successfully")


if __name__ == "__main__":
    driver = webdriver.Firefox()
    app.run(port=80)
