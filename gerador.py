import requests
import random
import string
import time
from colorama import Fore

def salvar_codigo_diferente_region(serialno):
    try:
        with open("codigos_regiao_diferente.txt", "a") as arquivo:
            arquivo.write(serialno + "\n")
        print(Fore.GREEN + f"Código {serialno} salvo por erro de região.")
    except Exception as e:
        print(Fore.RED + f'Erro ao salvar código: {str(e)}')

def send_telegram_message(message):
    bot_token = "7495344523:AAGo0ytykmgs4-gL8oQ4Efw66VPBjM3p2tI"
    chat_id = "7591480694"
    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"  # Opcional: permite formatação básica em HTML
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()  # Levanta uma exceção se a requisição falhar
        return response.json()
    except requests.exceptions.RequestException as ex:
        print(Fore.RED + f'Erro ao enviar mensagem: {str(ex)}')
        return None

def redimir_codigo(access_token, serialno):
    url = "https://prod-api.reward.ff.garena.com/redemption/api/game/ff/redeem/"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain",
        "Access-Token": access_token,
        "Origin": "https://reward.ff.garena.com",
        "Referer": "https://reward.ff.garena.com/"
    }
    payload = {"serialno": serialno}

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            return {"msg": "Erro desconhecido"}
    except Exception as e:
        return {"msg": f'Erro na requisição: {str(e)}'}

def gerar_combinacoes(base_code, choice, access_tokens):
    character_sets = {
        1: string.ascii_uppercase + string.digits,  # Letras e números
        2: string.digits,  # Apenas números
        3: string.ascii_uppercase  # Apenas letras
    }

    if choice not in character_sets:
        print(Fore.RED + "Escolha inválida de combinação.")
        return

    characters = character_sets[choice]
    remaining_length = 12 - len(base_code)
    gerados = set()
    print(f"Gerando códigos baseados em {base_code} com {remaining_length} caracteres aleatórios...")

    current_token_index = 0

    while current_token_index < len(access_tokens):
        access_token = access_tokens[current_token_index]
        attempt_count = 0

        while True:
            random_suffix = ''.join(random.choices(characters, k=remaining_length))
            generated_code = base_code + random_suffix

            if generated_code not in gerados:
                gerados.add(generated_code)
                break

        resposta = redimir_codigo(access_token, generated_code)
        status = resposta.get("msg", "Resposta sem mensagem")

        if status == "error_too_many_requests":
            print(Fore.YELLOW + "Limite de requisições atingido para este token. Trocando para o próximo...")
            current_token_index += 1
            continue

        if status == "error_invalid_token":
            print(Fore.YELLOW + "Token inválido. Trocando para o próximo...")
            current_token_index += 1
            continue

        if status == "error_different_region":
            print(Fore.BLUE + f"Código {generated_code} está em outra região. Salvando...")
            send_telegram_message(f"Código {generated_code} detectado")
            salvar_codigo_diferente_region(generated_code)
            continue

        if "inválido" in status.lower() or "erro" in status.lower():
            print(Fore.LIGHTCYAN_EX + f"{attempt_count + 1} - {generated_code} - ({status})")
        else:
            print(Fore.GREEN + f"{attempt_count + 1} - {generated_code} - ({status})")

        attempt_count += 1

        if attempt_count >= 100:
            print(Fore.YELLOW + "Token atingiu 100 tentativas. Trocando para o próximo token...")
            current_token_index += 1
            attempt_count = 0
        

    print(Fore.RED + "Todos os tokens foram utilizados.")
    print(Fore.CYAN + "Aguardando 2 minutos antes de reiniciar...")
    send_telegram_message("Tokens offlines, voltando em alguns segundos...")
    time.sleep(3600)  # Espera 2 minutos
    send_telegram_message("Retornando...")
    gerar_combinacoes(base_code, choice, access_tokens)

if __name__ == "__main__":
    print(Fore.MAGENTA + "Digite Access Tokens separados por vírgula (quantidade ilimitada):")
    tokens_input = input("Access Tokens: ").strip()
    access_tokens = [token.strip() for token in tokens_input.split(",") if token.strip()]

    if len(access_tokens) == 0:
        print(Fore.RED + "Você deve fornecer pelo menos 1 token.")
        exit()

    print(Fore.MAGENTA + "Digite o código inicial (menos de 12 caracteres):")
    base_code = input("Código Inicial: ").strip()

    if len(base_code) >= 12:
        print(Fore.RED + "O código inicial deve ter menos de 12 caracteres.")
        exit()

    print("Escolha o tipo de combinação:")
    print("1 - Letras e números")
    print("2 - Somente números")
    print("3 - Somente letras")

    try:
        choice = int(input("Digite o número da sua escolha: "))
        gerar_combinacoes(base_code, choice, access_tokens)
    except ValueError:
        print(Fore.RED + "Por favor, insira um número válido.")