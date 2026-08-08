import os
import json
import random
import asyncio
from datetime import datetime, timedelta

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
    "rodada": 0,
    "task": None,
}


def carregar_json(nome, padrao):
    try:
        with open(nome, "r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except (FileNotFoundError, json.JSONDecodeError):
        return padrao


def salvar_json(nome, dados):
    with open(nome, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, indent=4, ensure_ascii=False)


def carregar_perguntas():
    banco = carregar_json(ARQUIVO_PERGUNTAS, [])
    lista = []

    for categoria in banco:
        for pergunta in categoria.get("perguntas", []):
            lista.append(pergunta)

    return lista


def nome_usuario(user):
    nome = user.full_name or user.first_name or "Jogador"
    return nome.replace("\n", " ")[:40]


async def enviar_pergunta(context):
    if not partida["ativa"]:
        return

    numero = partida["numero"]
    pergunta = partida["perguntas"][numero]

    partida["votos"] = {}
    partida["rodada"] += 1
    rodada_atual = partida["rodada"]

    botoes = []

    for i, opcao in enumerate(pergunta["opcoes"]):
        botoes.append([
            InlineKeyboardButton(
                f"{chr(65 + i)}) {opcao}",
                callback_data=f"voto:{rodada_atual}:{i}"
            )
        ])

    texto = (
        f"🧠 PERGUNTA {numero + 1}/{TOTAL_PERGUNTAS}\n\n"
        f"{pergunta['pergunta']}\n\n"
        f"⏱️ Você tem {TEMPO_RESPOSTA} segundos."
    )

    await context.bot.send_message(
        chat_id=partida["chat_id"],
        text=texto,
        reply_markup=InlineKeyboardMarkup(botoes)
    )

    await asyncio.sleep(TEMPO_RESPOSTA)

    if partida["ativa"] and partida["rodada"] == rodada_atual:
        await finalizar_pergunta(context)


async def finalizar_pergunta(context):
    if not partida["ativa"]:
        return

    pergunta = partida["perguntas"][partida["numero"]]

    contagem = [0] * len(pergunta["opcoes"])

    for voto in partida["votos"].values():
        if 0 <= voto["resposta"] < len(contagem):
            contagem[voto["resposta"]] += 1

    resultado = "⏰ TEMPO ENCERRADO!\n\n📊 VOTOS:\n\n"

    for i, total in enumerate(contagem):
        resultado += (
            f"{chr(65 + i)}) "
            f"{pergunta['opcoes'][i]} "
            f"- {total} voto(s)\n"
        )

    correta = pergunta["correta"]

    resultado += (
        f"\n✅ Resposta correta:\n"
        f"{chr(65 + correta)}) "
        f"{pergunta['opcoes'][correta]}"
    )

    await context.bot.send_message(
        chat_id=partida["chat_id"],
        text=resultado
    )

    for usuario, voto in partida["votos"].items():
        if voto["resposta"] == correta:
            partida["jogadores"][usuario] = (
                partida["jogadores"].get(usuario, 0) + 10
            )

    partida["numero"] += 1

    if partida["numero"] < TOTAL_PERGUNTAS:
        partida["task"] = context.application.create_task(
            enviar_pergunta(context)
        )
    else:
        await finalizar_quiz(context)


async def receber_voto(update: Update, context):
    query = update.callback_query

    if not partida["ativa"]:
        await query.answer(
            "🛑 Este quiz não está mais em andamento.",
            show_alert=True
        )
        return

    try:
        partes = query.data.split(":")
        rodada = int(partes[1])
        escolha = int(partes[2])
    except (ValueError, IndexError):
        await query.answer(
            "Voto inválido.",
            show_alert=True
        )
        return

    if rodada != partida["rodada"]:
        await query.answer(
            "⏰ Essa pergunta já terminou.",
            show_alert=True
        )
        return

    usuario = query.from_user.id

    if usuario in partida["votos"]:
        await query.answer(
            "Você já votou nesta pergunta!",
            show_alert=True
        )
        return

    pergunta = partida["perguntas"][partida["numero"]]

    if escolha < 0 or escolha >= len(pergunta["opcoes"]):
        await query.answer(
            "Opção inválida.",
            show_alert=True
        )
        return

    partida["votos"][usuario] = {
        "resposta": escolha,
        "nome": nome_usuario(query.from_user),
    }

    partida["jogadores"].setdefault(
        usuario,
        0
    )

    await query.answer(
        "✅ Voto registrado!"
    )

    contagem = [0] * len(pergunta["opcoes"])

    for voto in partida["votos"].values():
        contagem[voto["resposta"]] += 1

    parcial = "📊 VOTOS ATUAIS\n\n"

    for i, total in enumerate(contagem):
        parcial += (
            f"{chr(65 + i)}) "
            f"{total} voto(s)\n"
        )

    # O resultado parcial é enviado somente para quem votou.
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=parcial
    )


def limpar_partida():
    partida["ativa"] = False
    partida["chat_id"] = None
    partida["perguntas"] = []
    partida["numero"] = 0
    partida["votos"] = {}
    partida["jogadores"] = {}
    partida["rodada"] = 0
    partida["task"] = None


async def finalizar_quiz(context):
    jogadores = sorted(
        partida["jogadores"].items(),
        key=lambda item: item[1],
        reverse=True
    )

    texto = "🏆 PÓDIO FINAL\n\n"

    if not jogadores:
        texto += "Ninguém marcou pontos nesta partida."
    else:
        medalhas = ["🥇", "🥈", "🥉"]

        for posicao, (usuario, pontos) in enumerate(
            jogadores[:3]
        ):
            # Nome salvo durante os votos.
            nome = "Jogador"

            for voto in partida["votos"].values():
                if voto.get("nome") and False:
                    nome = voto["nome"]

            texto += (
                f"{medalhas[posicao]} "
                f"Jogador {usuario} — "
                f"{pontos} pontos\n"
            )

    ranking = carregar_json(
        ARQUIVO_RANKING,
        {}
    )

    for usuario, pontos in partida["jogadores"].items():
        chave = str(usuario)

        if chave not in ranking:
            ranking[chave] = {
                "pontos": 0,
                "ultima_atualizacao": ""
            }

        ranking[chave]["pontos"] += pontos
        ranking[chave]["ultima_atualizacao"] = (
            datetime.now().strftime("%Y-%m-%d")
        )

    salvar_json(
        ARQUIVO_RANKING,
        ranking
    )

    chat_id = partida["chat_id"]

    limpar_partida()

    await context.bot.send_message(
        chat_id=chat_id,
        text=texto
    )


async def iniciar_quiz_em_background(context, chat_id):
    try:
        await enviar_pergunta(context)
    except asyncio.CancelledError:
        return
    except Exception as erro:
        print("ERRO NO QUIZ:", erro)

        if partida["ativa"]:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Ocorreu um erro durante o quiz."
            )

            limpar_partida()


async def quiz(update: Update, context):
    if partida["ativa"]:
        await update.message.reply_text(
            "⚠️ Já existe um quiz em andamento."
        )
        return

    banco = carregar_perguntas()

    if len(banco) < TOTAL_PERGUNTAS:
        await update.message.reply_text(
            f"❌ O banco possui apenas {len(banco)} perguntas.\n\n"
            f"São necessárias pelo menos {TOTAL_PERGUNTAS}."
        )
        return

    partida["ativa"] = True
    partida["chat_id"] = update.effective_chat.id
    partida["perguntas"] = random.sample(
        banco,
        TOTAL_PERGUNTAS
    )
    partida["numero"] = 0
    partida["votos"] = {}
    partida["jogadores"] = {}
    partida["rodada"] = 0

    await update.message.reply_text(
        "🎮 QUIZ INICIADO!\n\n"
        f"🧠 {TOTAL_PERGUNTAS} perguntas\n"
        f"⏱️ {TEMPO_RESPOSTA} segundos por pergunta"
    )

    # Importante: não esperamos as 15 perguntas aqui.
    # O quiz roda em segundo plano para que votos e /parar
    # possam ser recebidos durante a partida.
    partida["task"] = context.application.create_task(
        iniciar_quiz_em_background(
            context,
            partida["chat_id"]
        )
    )


async def parar(update: Update, context):
    if not partida["ativa"]:
        await update.message.reply_text(
            "ℹ️ Não existe quiz em andamento."
        )
        return

    task = partida.get("task")

    limpar_partida()

    if task and not task.done():
        task.cancel()

    await update.message.reply_text(
        "🛑 QUIZ ENCERRADO MANUALMENTE."
    )


def semana_atual():
    hoje = datetime.now()
    inicio = hoje - timedelta(days=hoje.weekday())
    return inicio.strftime("%Y-%m-%d")


async def ranking(update: Update, context):
    dados = carregar_json(
        ARQUIVO_RANKING,
        {}
    )

    if not dados:
        await update.message.reply_text(
            "🏆 Ranking vazio."
        )
        return

    lista = []

    for usuario, info in dados.items():
        if isinstance(info, dict):
            pontos = info.get("pontos", 0)
        else:
            pontos = info

        lista.append(
            (usuario, pontos)
        )

    lista.sort(
        key=lambda item: item[1],
        reverse=True
    )

    texto = "🏆 RANKING SEMANAL\n\n"

    for posicao, (usuario, pontos) in enumerate(
        lista[:10],
        1
    ):
        texto += (
            f"{posicao}º — "
            f"Jogador {usuario}: "
            f"{pontos} pts\n"
        )

    await update.message.reply_text(
        texto
    )


async def start(update: Update, context):
    await update.message.reply_text(
        "🎮 BEM-VINDO AO QUIZ!\n\n"
        "/quiz — iniciar uma partida\n"
        "/parar — encerrar a partida\n"
        "/ranking — ver o ranking"
    )


def main():
    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN não foi configurado nas variables."
        )

    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "quiz",
            quiz
        )
    )

    app.add_handler(
        CommandHandler(
            "parar",
            parar
        )
    )

    app.add_handler(
        CommandHandler(
            "ranking",
            ranking
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            receber_voto,
            pattern=r"^voto:[0-9]+:[0-9]+$"
        )
    )

    print("Bot de quiz iniciado!")

    app.run_polling()


if __name__ == "__main__":
    main()
