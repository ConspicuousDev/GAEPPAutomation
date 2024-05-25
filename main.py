import os
import re
import threading
import time
from datetime import datetime

import openai
from flask import Flask, render_template, abort, request
from selenium import webdriver
from selenium.common.exceptions import *
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

webpki_path = "static/webpki.xpi"
firefox_profile_path = os.getenv("FIREFOX_PROFILE_PATH")
driver = None

app = Flask(__name__)

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OpenAI API key not found. Please set the OPENAI_API_KEY environment variable.")
openai_client = openai.OpenAI(api_key=api_key)

valid_systems = ["SISBAJUD", "SERASA_2", "CNIB_INCLUIR", "RENAJUD"]

last_system = None
last_data = None


def wait_for_page_load(driver, url: str = None, timeout: int = 30):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    if url is not None and not driver.current_url.startswith(url):
        raise AssertionError("Reached different page.")


def wait_for_element(driver, identifier: WebElement | str, timeout: int = 10, id_type: str = By.XPATH) -> WebElement:
    if isinstance(identifier, str):
        return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((id_type, identifier)))
    else:
        return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable(identifier))


def wait_for_element_invisible(driver, identifier: WebElement | str, timeout: int = 10, id_type: str = By.XPATH):
    if isinstance(identifier, str):
        return WebDriverWait(driver, timeout).until(EC.invisibility_of_element_located((id_type, identifier)))
    else:
        return WebDriverWait(driver, timeout).until(EC.invisibility_of_element_located(identifier))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/action/queued")
def queued():
    global last_data, last_system
    return render_template("queued.html", last_system=last_system, last_data=last_data)


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
    if mandado_content == "":
        data = {}
    elif system.lower() == "sisbajud":
        prompt = (
            "Você deve extrair as seguintes informações do mandado a seguir no seguinte formato (os valores são apenas exemplos com instruções). Caso você não encontre algum dos valores, não inclua a chave (caso seja uma lista, deixe a lista vazia)."
            "{"
            "   \"vara\": \"1ª VARA DO TRABALHO DE CIDADE\","
            "   \"numero_mandado\": \"012345-67.8901.2.34.5678\","
            "   \"autor\": \"NOME DO AUTOR (COMO NO CABEÇALHO)\","
            "   \"pesquisados\": ["
            "       {"
            "           \"cpf_cnpj\": \"012.345.678-90 ou 01.234.567/0001-89\""
            "       }"
            "   ],"
            "   \"valor_pesquisa\": \"R$ 1.234,56\" (VALOR TOTAL)"
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
    elif system.lower() == "serasa_2":
        prompt = (
            "Você deve extrair as seguintes informações do mandado a seguir no seguinte formato (os valores são apenas exemplos com instruções). Caso você não encontre algum dos valores, não inclua a chave (caso seja uma lista, deixe a lista vazia)."
            "{"
            "   \"numero_mandado\": \"012345-67.8901.2.34.5678\","
            "   \"autor\": \"NOME DO AUTOR (COMO NO CABEÇALHO)\","
            "   \"executado\": \"NOME DO EXECUTADO (COMO NO CABEÇALHO, COM 'E OUTROS X')\","
            "   \"executado_cpf_cnpj\": \"012.345.678-90 ou 01.234.567/0001-89 (DO EXECUTADO PRINCIPAL DO CABEÇALHO)\""
            "   \"pesquisados\": ["
            "       {"
            "           \"nome\": \"NOME DO EXECUTADO A SER PESQUISADO\","
            "           \"cpf_cnpj\": \"012.345.678-90 ou 01.234.567/0001-89\""
            "       }"
            "   ],"
            "   \"valor_pesquisa\": \"R$ 1.234,56\" (VALOR TOTAL)"
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
    elif system.lower() == "cnib_incluir":
        prompt = (
            "Você deve extrair as seguintes informações do mandado a seguir no seguinte formato (os valores são apenas exemplos com instruções). Caso você não encontre algum dos valores, não inclua a chave (caso seja uma lista, deixe a lista vazia)."
            "{"
            "   \"numero_mandado\": \"012345-67.8901.2.34.5678\","
            "   \"executado\": \"NOME DO EXECUTADO (COMO NO CABEÇALHO, COM 'E OUTROS X')\","
            "   \"pesquisados\": ["
            "       {"
            "           \"cpf_cnpj\": \"012.345.678-90 ou 01.234.567/0001-89\""
            "       }"
            "   ],"
            "   \"valor_pesquisa\": \"R$ 1.234,56\" (VALOR TOTAL)"
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
    elif system.lower() == "renajud":
        prompt = (
            "Você deve extrair as seguintes informações do mandado a seguir no seguinte formato (os valores são apenas exemplos com instruções). Caso você não encontre algum dos valores, não inclua a chave (caso seja uma lista, deixe a lista vazia)."
            "{"
            "   \"pesquisados\": ["
            "       {"
            "           \"cpf_cnpj\": \"012.345.678-90 ou 01.234.567/0001-89\""
            "       }"
            "   ],"
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
    global last_data, last_system
    if system.upper() not in valid_systems:
        abort(404)
    cb = None
    if system.lower() == "sisbajud":
        cb = sisbajud
    elif system.lower() == "serasa_2":
        cb = serasa_2
    elif system.lower() == "cnib_incluir":
        cb = cnib_incluir
    elif system.lower() == "renajud":
        cb = renajud
    if cb is None:
        print(f"[EXECUTE] [{system}] failed to queue")
        abort(404)
    data = None
    if "last" in request.args:
        data = last_data
    else:
        print(f"[EXECUTE] [{system}] reading body...")
        data = request.get_json(force=True)
        last_system = system
        last_data = data
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


def serasa_2(data):
    driver.get("https://serasa-judicial.serasaexperian.com.br/login")
    try:
        wait_for_page_load(driver, "https://serasa-judicial.serasaexperian.com.br/login")
        print(f"[EXECUTE] [serasa_2] waiting for certificate")
    except AssertionError:
        pass
    thresh = 30
    while not driver.current_url.startswith("https://serasa-judicial.serasaexperian.com.br/ordem"):
        time.sleep(.5)
        thresh -= .5
        if thresh < 0:
            raise AssertionError("Certificate not authenticated:", driver.current_url)
    print(f"[EXECUTE] [serasa_2] certificate authentication successful")
    wait_for_element(driver, "/html/body/app-root/app-ordem/div/div/div/div[1]/button").click()
    wait_for_page_load(driver, "https://serasa-judicial.serasaexperian.com.br/cadastrar-ordem")
    wait_for_element(driver, '//*[@id="mat-input-1"]').send_keys(data["executado_cpf_cnpj"])
    wait_for_element(driver, '/html/body/app-root/app-cadastrar-ordem/div/mat-toolbar').click()
    wait_for_element(driver, '//*[@id="mat-input-2"]').send_keys(data["numero_mandado"])
    wait_for_element(driver,
                     '/html/body/app-root/app-cadastrar-ordem/div/div/mat-tab-group/div/mat-tab-body[1]/div/app-inclusao-acao/div/div/form/div/div[3]/button').click()
    WebDriverWait(driver, 10).until(EC.alert_is_present())
    driver.switch_to.alert.accept()
    wait_for_element(driver,
                     '/html/body/app-root/app-cadastrar-ordem/div/div/mat-tab-group/div/mat-tab-body[1]/div/app-inclusao-acao/div/div/div/app-incluir-acao-form/form/div[1]/div[1]/mat-radio-group/mat-radio-button[4]/label/span[1]/span[1]').click()
    for exec in data["pesquisados"]:
        wait_for_element(driver, '//*[@id="mat-input-8"]').send_keys(exec["nome"])
        wait_for_element(driver, '//*[@id="mat-input-9"]').send_keys(exec["cpf_cnpj"])
        wait_for_element(driver,
                         '/html/body/app-root/app-cadastrar-ordem/div/div/mat-tab-group/div/mat-tab-body[1]/div/app-inclusao-acao/div/div/div/app-incluir-acao-form/form/div[1]/div[2]/div/div[3]/button').click()
    wait_for_element(driver,
                     '/html/body/app-root/app-cadastrar-ordem/div/div/mat-tab-group/div/mat-tab-body[1]/div/app-inclusao-acao/div/div/div/app-incluir-acao-form/form/div[1]/div[3]/div[1]/mat-form-field/div/div[1]/div[3]/mat-select/div/div[1]/span').click()
    wait_for_element(driver, '/html/body/div[2]/div[2]/div/div/div/mat-option[1]/span').click()
    time.sleep(.5)
    wait_for_element(driver,
                     '/html/body/app-root/app-cadastrar-ordem/div/div/mat-tab-group/div/mat-tab-body[1]/div/app-inclusao-acao/div/div/div/app-incluir-acao-form/form/div[1]/div[3]/div[2]/mat-form-field/div/div[1]/div[3]/mat-select/div/div[1]/span').click()
    wait_for_element(driver, '/html/body/div[2]/div[2]/div/div/div/mat-option[1]/span').click()
    time.sleep(.5)
    wait_for_element(driver,
                     '/html/body/app-root/app-cadastrar-ordem/div/div/mat-tab-group/div/mat-tab-body[1]/div/app-inclusao-acao/div/div/div/app-incluir-acao-form/form/div[1]/div[4]/div[1]/mat-form-field/div/div[1]/div[3]/mat-select/div/div[1]/span').click()
    wait_for_element(driver, '/html/body/div[2]/div[2]/div/div/div/mat-option[4]/span').click()
    time.sleep(.5)
    wait_for_element(driver, '//*[@id="mat-input-12"]').click()
    wait_for_element(driver, '/html/body/div[2]/div/div/div/mat-option[63]/span').click()
    wait_for_element(driver, '//*[@id="mat-input-14"]').send_keys(data["valor_pesquisa"])
    wait_for_element(driver, '//*[@id="mat-input-15"]').send_keys(data["autor"])
    wait_for_element(driver, '//*[@id="mat-input-16"]').send_keys(data["executado"])
    print(f"[EXECUTE] [serasa_2] finished successfully")


def cnib_incluir(data):
    driver.get("https://indisponibilidade.org.br/autenticacao/")
    wait_for_page_load(driver, "https://indisponibilidade.org.br/autenticacao/")
    time.sleep(3)
    driver.find_element(By.XPATH, "/html/body/div[1]/div[2]/div[1]/a").click()
    wait_for_element(driver, '/html/body/div[3]/div/div/button').click()
    print(f"[EXECUTE] [cnib_incluir] waiting for certificate")
    thresh = 30
    while not driver.current_url == "https://indisponibilidade.org.br/":
        time.sleep(.5)
        thresh -= .5
        if thresh < 0:
            raise AssertionError("Certificate not authenticated:", driver.current_url)
    print(f"[EXECUTE] [cnib_incluir] certificate authentication successful")
    wait_for_element(driver, '/html/body/div[1]/div[2]/div[3]/a').click()
    wait_for_page_load(driver, 'https://indisponibilidade.org.br/ordem/indisponibilidade/')
    wait_for_element(driver, '/html/body/div[1]/div[2]/div[4]/input[1]').send_keys(data["numero_mandado"])
    wait_for_element(driver, '/html/body/div[1]/div[2]/div[4]/input[2]').send_keys(data["executado"])
    wait_for_element(driver, '/html/body/div[1]/div[2]/div[4]/center/button[1]').click()
    for execs in data["pesquisados"]:
        cpf_cnpj = execs["cpf_cnpj"]
        if len(re.sub(r"\D", "", cpf_cnpj)) == 11:
            wait_for_element(driver, '/html/body/div[1]/div[2]/div[5]/div/input[1]').click()
        else:
            wait_for_element(driver, '/html/body/div[1]/div[2]/div[5]/div/input[2]').click()
        wait_for_element(driver, '/html/body/div[1]/div[2]/div[5]/div/input[3]').send_keys(cpf_cnpj)
        wait_for_element(driver, '/html/body/div[1]/div[2]/div[5]/div/button[1]').click()
        wait_for_element(driver, '/html/body/div[1]/div[2]/div[5]/div/button[2]').click()
        time.sleep(.5)
    print(f"[EXECUTE] [cnib_incluir] finished successfully")


def renajud(data):
    driver.get("https://renajud.denatran.serpro.gov.br/renajud/login.jsf")
    try:
        wait_for_page_load(driver, "https://renajud.denatran.serpro.gov.br/renajud/login.jsf")
        wait_for_element(driver, "/html/body/div[1]/div[3]/form/div/div/div[2]/div[1]/a").click()
        print(f"[EXECUTE] [renajud] waiting for certificate")
        thresh = 30
        while not driver.current_url.startswith("https://renajud.denatran.serpro.gov.br/renajud/restrito/index.jsf"):
            time.sleep(.5)
            thresh -= .5
            if thresh < 0:
                raise AssertionError("Certificate not authenticated:", driver.current_url)
    except AssertionError:
        pass
    wait_for_page_load(driver, "https://renajud.denatran.serpro.gov.br/renajud/restrito/index.jsf")
    print(f"[EXECUTE] [renajud] certificate authentication successful")
    total_execs = len(data["pesquisados"])
    for i, execs in enumerate(data["pesquisados"]):
        print(f"[EXECUTE] [renajud] starting search for exec {execs['cpf_cnpj']} [{i + 1}/{total_execs}]")
        driver.get("https://renajud.denatran.serpro.gov.br/renajud/restrito/restricoes-insercao.jsf")
        wait_for_page_load(driver, "https://renajud.denatran.serpro.gov.br/renajud/restrito/restricoes-insercao.jsf")
        cpf_cnpj_input = wait_for_element(driver, '//*[@id="form-incluir-restricao:campo-cpf-cnpj"]')
        cpf_cnpj_input.send_keys(re.sub(r"\D", "", execs["cpf_cnpj"]))
        wait_for_element(driver, '//*[@id="form-incluir-restricao:botao-pesquisar"]').click()
        wait_for_element_invisible(driver, '//*[@id="j_idt686_blocker"]')
        error = False
        try:
            wait_for_element(driver, '/html/body/div[1]/div[2]/div[3]/div', 1)
            print(f"[EXECUTE] [renajud] found 0 vehicles for {execs['cpf_cnpj']}")
            error = True
        except:
            pass
        vehicles = {}
        if not error:
            total_vehicles = int(
                wait_for_element(driver,
                                 '/html/body/div[1]/div[2]/div[4]/div/form/div/div/div[2]/div[1]/div[1]').text.split(
                    " ")[-1])
            print(f"[EXECUTE] [renajud] found {total_vehicles} vehicles for {execs['cpf_cnpj']}")
            tbody = wait_for_element(driver, '//*[@id="form-incluir-restricao:lista-veiculo_data"]')
            rows = tbody.find_elements(By.TAG_NAME, "tr")
            for j, row in enumerate(rows):
                row: WebElement
                if j >= 30:
                    print(f"[EXECUTE] [renajud] ending search at 30th vehicle")
                    break
                cells = row.find_elements(By.TAG_NAME, "td")
                plate = cells[1].text
                print(f"[EXECUTE] [renajud] vehicle {plate} [{j + 1}/{total_vehicles}]")
                ineligible_reason = None
                fab_year = int(cells[5].text)
                curr_year = datetime.now().year
                if fab_year + 10 < curr_year:
                    ineligible_reason = "over 10 years old"
                address = None
                if ineligible_reason is None:
                    car_btn = cells[9].find_element(By.XPATH, "./button[1]")
                    driver.execute_script("arguments[0].click();", car_btn)
                    wait_for_element_invisible(driver, '//*[@id="j_idt686_blocker"]')
                    time.sleep(1)
                    car_menu = cells[9].find_element(By.XPATH, "./div[1]")
                    wait_for_element(driver, car_menu)
                    sale_info = car_menu.find_elements(By.XPATH, "./div[2]/div/fieldset[2]/div/table/tbody/tr")
                    sold = len(sale_info) > 1
                    if sold:
                        ineligible_reason = f"sale info present ({len(sale_info)})"
                    else:
                        address = car_menu.find_element(By.XPATH,
                                                        "./div[2]/div/fieldset[3]/div/table/tbody/tr[2]/td[2]").text
                    driver.execute_script("arguments[0].click();", car_menu.find_element(By.XPATH, "./div/a"))
                    wait_for_element_invisible(driver, car_menu)
                if ineligible_reason is None:
                    # restricted = cells[8].text == "Sim"
                    # if restricted:
                    eye_btn = cells[9].find_element(By.XPATH, "./button[2]")
                    driver.execute_script("arguments[0].click();", eye_btn)
                    wait_for_element_invisible(driver, '//*[@id="j_idt686_blocker"]')
                    time.sleep(1)
                    eye_menu = cells[9].find_element(By.XPATH, "./div[2]")
                    wait_for_element(driver, eye_menu)
                    renavam_restr = eye_menu.find_elements(By.XPATH,
                                                           "./div[2]/span/span/fieldset[2]/div/table/tbody/tr/td/div/div/ul/li")
                    restr_filter = ["ALIENACAO_FIDUCIARIA", "ARRENDAMENTO", "RESERVA_DE_DOMINIO", "RESERVA_DOMINIO",
                                    "ROUBO", "VEICULO_ROUBADO", "FURTO", "VEICULO_FURTADO", "BAIXA", "VEICULO_BAIXADO"]
                    for restr in renavam_restr:
                        if restr.text in restr_filter:
                            ineligible_reason = f"renavam restriction: {restr.text}"
                            break
                    if ineligible_reason is None:
                        renajud_restr_count = len(
                            eye_menu.find_elements(By.XPATH, "./div[2]/span/span/span/fieldset/div/table"))
                        if renajud_restr_count > 20:
                            ineligible_reason = "more than 20 renajud restrictions"
                    driver.execute_script("arguments[0].click();", eye_menu.find_element(By.XPATH, "./div/a"))
                    wait_for_element_invisible(driver, eye_menu)
                vehicles[plate] = {"plate": plate, "address": address, "eligible": ineligible_reason is None,
                                   "index": j}
                if ineligible_reason is not None:
                    print(f"[EXECUTE] [renajud] vehicle {plate} ineligible: {ineligible_reason}")
                else:
                    print(f"[EXECUTE] [renajud] vehicle {plate} eligible")
        eligible_count = 0
        for vehicle in vehicles.values():
            if not vehicle["eligible"]:
                continue
            print(f"{vehicle['index'] + 1}. {vehicle['plate']}: {vehicle['address']}")
            eligible_count += 1
        print(f"[EXECUTE] [renajud] {execs['cpf_cnpj']} returned {eligible_count} eligible vehicles")
        if i + 1 < len(data["pesquisados"]):
            input("[EXECUTE] [renajud] press ENTER to continue...")
    print(f"[EXECUTE] [renajud] finished successfully")


if __name__ == "__main__":
    current_file_path = os.path.abspath(__file__)
    current_directory = os.path.dirname(current_file_path)
    os.chdir(current_directory)
    print(f"[DRIVER] [profile] using profile '{firefox_profile_path}'")
    profile = webdriver.FirefoxProfile(firefox_profile_path)
    options = webdriver.firefox.options.Options()
    options.profile = profile
    driver = webdriver.Firefox(options=options)
    webpki_path = os.path.abspath(webpki_path)
    print(f"[DRIVER] [extension] WebPKI path '{webpki_path}'")
    driver.install_addon(webpki_path, temporary=True)
    app.run(port=80)
