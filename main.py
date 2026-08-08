# QUIZ TELEGRAM BOT - V5
# Arquivo revisado: votação, /parar, temporizador e visual das perguntas.

import os
import json
import random
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

TOKEN = os.getenv("BOT_TOKEN")

TEMPO_RESPOSTA = 15
TOTAL_PERGUNTAS = 15

ARQUIVO_PERGUNTAS = "perguntas.json"
ARQUIVO_RANKING = "ranking.json"

partida = {
    "ativa": False,
    "chat_id": None,
    "perguntas": [],
    "numero": 0,
    "votos": {},
    "jogadores": {},
    "task": None,
}


def carregar_json(nome, padrao):
    try:
        with open(nome, "r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except Exception:
        return padrao


def salvar_json(nome, dados):
    with open(nome, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, indent=4, ensure_ascii=False)


def carregar_perguntas():
    banco = carregar_json(ARQUIVO_PERGUNTAS, [])
    perguntas = []

    for categoria in banco:
        nome_categoria = categoria.get("categoria", "🤯 Curiosidades")

        for item in categoria.get("perguntas", []):
            pergunta = dict(item)
            pergunta["categoria"] = nome_categoria
            pergunta.setdefault("emoji", "🧠")
            perguntas.append(pergunta)

    return perguntas


def carregar_ranking():
    dados = carregar_json(
        ARQUIVO_RANKING,
        {"jogadores": {}},
    )

    # Compatibilidade com o ranking antigo.
    if "jogadores" not in dados:
        antigo = dados
        dados = {"jogadores": {}}

        for usuario, info in antigo.items():
            if isinstance(info, dict):
                dados["jogadores"][str(usuario)] = {
                    "nome": f"Jogador {usuario}",
                    "pontos": info.get("pontos", 0),
                }

    return dados


def nome_usuario(user):
    nome = user.first_name or ""

    if user.last_name:
        nome += f" {user.last_name}"

    if not nome:
        nome = user.username or f"Jogador {user.id}"

    return nome


def limpar_partida():
    partida["ativa"] = False
    partida["chat_id"] = None
    partida["perguntas"] = []
    partida["numero"] = 0
    partida["votos"] = {}
    partida["jogadores"] = {}
    partida["task"] = None


async def enviar_pergunta(context):
    if not partida["ativa"]:
        return

    if partida["numero"] >= len(partida["perguntas"]):
        return

    pergunta = partida["perguntas"][partida["numero"]]

    # Zera os votos somente quando uma nova pergunta começa.
    partida["votos"] = {}

    botoes = []

    for i, opcao in enumerate(pergunta["opcoes"]):
        botoes.append([
            InlineKeyboardButton(
                f"{chr(65 + i)}) {opcao}",
                callback_data=f"VOTO:{partida['numero']}:{i}",
            )
        ])

    frases = [
        "👀 Cuidado... essa parece fácil demais!",
        "😂 Sem Google! O grupo está de olho!",
        "🔥 Hora de separar os especialistas dos comentaristas de sofá!",
        "🧠 Puxe tudo o que você sabe da memória!",
        "😈 Essa foi escolhida para pegar quem está distraído!",
        "⚡ Responda rápido antes que o cérebro entre em modo economia!",
        "🎯 Mire na resposta certa!",
        "🤔 Pense bem... mas não pense 15 segundos inteiros!",
    ]

    categoria = pergunta.get("categoria", "🤯 Curiosidades")
    emoji = pergunta.get("emoji", "🧠")
    frase = random.choice(frases)

    texto = (
        f"🧠 <b>DESAFIO {partida['numero'] + 1}/{TOTAL_PERGUNTAS}</b>\n\n"
        f"{emoji} <b>{categoria}</b>\n\n"
        f"❓ <b>{pergunta['pergunta']}</b>\n\n"
        f"{frase}\n\n"
        f"⏱️ <b>{TEMPO_RESPOSTA} segundos!</b> CORRE! 🏃💨"
    )

    await context.bot.send_message(
        chat_id=partida["chat_id"],
        text=texto,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(botoes),
    )


async def finalizar_pergunta(context):
    if not partida["ativa"]:
        return

    if partida["numero"] >= len(partida["perguntas"]):
        return

    pergunta = partida["perguntas"][partida["numero"]]
    contagem = [0] * len(pergunta["opcoes"])

    for escolha in partida["votos"].values():
        if 0 <= escolha < len(contagem):
            contagem[escolha] += 1

    texto = "⏰ <b>TEMPO ENCERRADO!</b>\n\n"
    texto += "📊 <b>VOTOS:</b>\n\n"

    for i, opcao in enumerate(pergunta["opcoes"]):
        texto += (
            f"{chr(65 + i)}) {opcao} — "
            f"<b>{contagem[i]} voto(s)</b>\n"
        )

    correta = pergunta["correta"]

    texto += (
        f"\n✅ <b>Resposta correta:</b>\n"
        f"{chr(65 + correta)}) {pergunta['opcoes'][correta]}"
    )

    await context.bot.send_message(
        chat_id=partida["chat_id"],
        text=texto,
        parse_mode="HTML",
    )

    for usuario, escolha in partida["votos"].items():
        if usuario in partida["jogadores"] and escolha == correta:
            partida["jogadores"][usuario]["pontos"] += 10

    partida["numero"] += 1

    if partida["numero"] < TOTAL_PERGUNTAS and partida["ativa"]:
        await enviar_pergunta(context)

        partida["task"] = asyncio.create_task(
            temporizador_pergunta(context)
        )
    else:
        await finalizar_quiz(context)


async def temporizador_pergunta(context):
    numero = partida["numero"]

    try:
        await asyncio.sleep(TEMPO_RESPOSTA)
    except asyncio.CancelledError:
        return

    if not partida["ativa"]:
        return

    if partida["numero"] != numero:
        return

    await finalizar_pergunta(context)


async def receber_voto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if not partida["ativa"]:
        await query.answer(
            "🛑 O quiz já foi encerrado.",
            show_alert=True,
        )
        return

    try:
        dados = query.data.split(":")

        if len(dados) != 3 or dados[0] != "VOTO":
            await query.answer()
            return

        numero = int(dados[1])
        escolha = int(dados[2])
        usuario = query.from_user.id

        if numero != partida["numero"]:
            await query.answer(
                "⏰ Essa pergunta já terminou!",
                show_alert=True,
            )
            return

        if usuario in partida["votos"]:
            await query.answer(
                "☑️ Você já votou!",
                show_alert=True,
            )
            return

        pergunta = partida["perguntas"][partida["numero"]]

        if escolha < 0 or escolha >= len(pergunta["opcoes"]):
            await query.answer("Opção inválida.", show_alert=True)
            return

        partida["votos"][usuario] = escolha

        if usuario not in partida["jogadores"]:
            partida["jogadores"][usuario] = {
                "nome": nome_usuario(query.from_user),
                "pontos": 0,
            }

        # NÃO envia mensagem para o privado nem para o grupo.
        # A confirmação aparece apenas no próprio botão.
        await query.answer("✅ Voto registrado!")

    except Exception as erro:
        print("ERRO NO VOTO:", erro)

        try:
            await query.answer(
                "❌ Não foi possível registrar o voto.",
                show_alert=True,
            )
        except Exception:
            pass


async def finalizar_quiz(context):
    chat_id = partida["chat_id"]

    if not chat_id:
        limpar_partida()
        return

    jogadores = sorted(
        partida["jogadores"].items(),
        key=lambda item: item[1]["pontos"],
        reverse=True,
    )

    ranking = carregar_ranking()

    for usuario, info in partida["jogadores"].items():
        chave = str(usuario)

        if chave not in ranking["jogadores"]:
            ranking["jogadores"][chave] = {
                "nome": info["nome"],
                "pontos": 0,
            }

        ranking["jogadores"][chave]["nome"] = info["nome"]
        ranking["jogadores"][chave]["pontos"] += info["pontos"]

    salvar_json(ARQUIVO_RANKING, ranking)

    texto = "🏆 <b>FIM DE JOGO!</b>\n\n"
    texto += "🔥 Foi uma batalha de conhecimento!\n\n"

    medalhas = ["🥇", "🥈", "🥉"]

    if not jogadores:
        texto += "😅 Ninguém marcou pontos desta vez!"
    else:
        for posicao, (_, info) in enumerate(jogadores[:3]):
            texto += (
                f"{medalhas[posicao]} <b>{info['nome']}</b> — "
                f"<b>{info['pontos']} pontos</b>\n"
            )

    texto += "\n📈 <b>Ranking atualizado!</b>"
    texto += "\n😈 Já prepara a revanche!"

    limpar_partida()

    await context.bot.send_message(
        chat_id=chat_id,
        text=texto,
        parse_mode="HTML",
    )


async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if partida["ativa"]:
        await update.message.reply_text(
            "⚠️ Já existe um quiz em andamento."
        )
        return

    perguntas = carregar_perguntas()

    if len(perguntas) < TOTAL_PERGUNTAS:
        await update.message.reply_text(
            f"❌ Preciso de pelo menos {TOTAL_PERGUNTAS} perguntas."
        )
        return

    partida["ativa"] = True
    partida["chat_id"] = update.effective_chat.id
    partida["perguntas"] = random.sample(
        perguntas,
        TOTAL_PERGUNTAS,
    )
    partida["numero"] = 0
    partida["votos"] = {}
    partida["jogadores"] = {}

    await update.message.reply_text(
        "🎮 <b>QUIZ INICIADO!</b>\n\n"
        "🧠 15 perguntas\n"
        "⏱️ 15 segundos por pergunta\n"
        "🏆 Cada acerto vale 10 pontos\n\n"
        "🔥 Boa sorte!",
        parse_mode="HTML",
    )

    await enviar_pergunta(context)

    partida["task"] = asyncio.create_task(
        temporizador_pergunta(context)
    )


async def parar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not partida["ativa"]:
        await update.message.reply_text(
            "ℹ️ Não existe quiz em andamento."
        )
        return

    chat_id = partida["chat_id"]

    # Desativa antes de cancelar o temporizador.
    partida["ativa"] = False

    task = partida.get("task")

    if task and not task.done():
        task.cancel()

    limpar_partida()

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🛑 <b>QUIZ ENCERRADO!</b>\n\n"
            "A partida foi interrompida manualmente. 😎"
        ),
        parse_mode="HTML",
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎮 <b>BEM-VINDO AO QUIZ!</b>\n\n"
        "/quiz — iniciar quiz\n"
        "/ranking — ver ranking\n"
        "/regras — como jogar\n"
        "/parar — encerrar quiz",
        parse_mode="HTML",
    )


async def regras(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>COMO JOGAR</b>\n\n"
        "🎯 15 perguntas por partida.\n"
        "⏱️ 15 segundos para responder.\n"
        "☑️ Um voto por pergunta.\n"
        "🚫 Não dá para votar depois do tempo.\n"
        "🏆 Cada acerto vale 10 pontos.\n"
        "🥇🥈🥉 Os três melhores vão para o pódio.\n"
        "📈 Os pontos entram no ranking.\n\n"
        "😈 Nada de Google! 😂",
        parse_mode="HTML",
    )


async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dados = carregar_ranking()
    jogadores = dados.get("jogadores", {})

    if not jogadores:
        await update.message.reply_text(
            "🏆 O ranking ainda está vazio."
        )
        return

    lista = sorted(
        jogadores.items(),
        key=lambda item: item[1].get("pontos", 0),
        reverse=True,
    )

    texto = "🏆 <b>RANKING</b>\n\n"
    medalhas = ["🥇", "🥈", "🥉"]

    for posicao, (_, info) in enumerate(lista[:10], 1):
        prefixo = (
            medalhas[posicao - 1]
            if posicao <= 3
            else f"{posicao}º"
        )

        texto += (
            f"{prefixo} <b>{info.get('nome', 'Jogador')}</b> — "
            f"{info.get('pontos', 0)} pts\n"
        )

    await update.message.reply_text(
        texto,
        parse_mode="HTML",
    )


def main():
    if not TOKEN:
        raise RuntimeError(
            "A variável BOT_TOKEN não foi configurada."
        )

    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(CommandHandler("parar", parar))
    app.add_handler(CommandHandler("ranking", ranking))
    app.add_handler(CommandHandler("regras", regras))

    app.add_handler(
        CallbackQueryHandler(
            receber_voto,
            pattern=r"^VOTO:",
        )
    )

    print("BOT QUIZ V5 INICIADO!")

    app.run_polling()


if __name__ == "__main__":
    main()
