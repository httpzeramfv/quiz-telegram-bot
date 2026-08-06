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
    "perguntas": [],
    "numero": 0,
    "votos": {},
    "jogadores": {},
    "chat_id": None,
}


def carregar_json(arquivo, padrao):
    try:
        with open(arquivo, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return padrao


def salvar_json(arquivo, dados):
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(
            dados,
            f,
            indent=4,
            ensure_ascii=False
        )


def carregar_perguntas():
    banco = carregar_json(
        ARQUIVO_PERGUNTAS,
        []
    )

    todas = []

    for categoria in banco:
        for pergunta in categoria["perguntas"]:
            pergunta["categoria"] = categoria["categoria"]
            todas.append(pergunta)

    return todas


def carregar_ranking():
    return carregar_json(
        ARQUIVO_RANKING,
        {}
    )


def salvar_ranking(ranking):
    salvar_json(
        ARQUIVO_RANKING,
        ranking
    )
    def iniciar_pergunta(context):
    pergunta = partida["perguntas"][partida["numero"]]

    botoes = []

    for i, opcao in enumerate(pergunta["opcoes"]):
        botoes.append(
            [
                InlineKeyboardButton(
                    f"{chr(65+i)}) {opcao}",
                    callback_data=f"voto_{i}"
                )
            ]
        )

    texto = (
        f"🧠 Pergunta {partida['numero'] + 1}/{TOTAL_PERGUNTAS}\n\n"
        f"{pergunta['pergunta']}\n\n"
        f"⏱ Tempo: {TEMPO_RESPOSTA} segundos"
    )

    asyncio.create_task(
        enviar_pergunta(
            context,
            texto,
            botoes
        )
    )


async def enviar_pergunta(context, texto, botoes):

    mensagem = await context.bot.send_message(
        chat_id=partida["chat_id"],
        text=texto,
        reply_markup=InlineKeyboardMarkup(botoes)
    )

    partida["mensagem_id"] = mensagem.message_id
    partida["votos"] = {}

    await asyncio.sleep(TEMPO_RESPOSTA)

    await finalizar_pergunta(context)


async def finalizar_pergunta(context):

    pergunta = partida["perguntas"][partida["numero"]]

    contagem = [0, 0, 0, 0]

    for voto in partida["votos"].values():
        contagem[voto] += 1

    resultado = "⏰ Tempo encerrado!\n\n📊 Votos:\n\n"

    for i, total in enumerate(contagem):
        resultado += (
            f"{chr(65+i)}) "
            f"{pergunta['opcoes'][i]} "
            f"- {total} votos\n"
        )

    correta = pergunta["correta"]

    resultado += (
        f"\n✅ Resposta correta:\n"
        f"{chr(65+correta)}) "
        f"{pergunta['opcoes'][correta]}"
    )

    await context.bot.send_message(
        chat_id=partida["chat_id"],
        text=resultado
    )


    for usuario, resposta in partida["votos"].items():

        if resposta == correta:

            if usuario not in partida["jogadores"]:
                partida["jogadores"][usuario] = 0

            partida["jogadores"][usuario] += 10


    partida["numero"] += 1


    if partida["numero"] < TOTAL_PERGUNTAS:
        iniciar_pergunta(context)

    else:
        await finalizar_quiz(context)


async def receber_voto(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    usuario = query.from_user.id

    if usuario in partida["votos"]:
        await query.answer(
            "Você já votou!",
            show_alert=True
        )
        return


    escolha = int(
        query.data.replace(
            "voto_",
            ""
        )
    )


    partida["votos"][usuario] = escolha


    await query.answer(
        "✅ Voto registrado!"
    )


    contagem = [0,0,0,0]

    for voto in partida["votos"].values():
        contagem[voto] += 1


    parcial = "📊 Votos atuais:\n\n"

    for i, total in enumerate(contagem):
        parcial += (
            f"{chr(65+i)} - {total} votos\n"
        )


    await context.bot.send_message(
        chat_id=query.message.chat.id,
        text=parcial
    )
    async def finalizar_quiz(context):

    ranking = carregar_ranking()

    resultado = "🏆 PÓDIO DO QUIZ\n\n"

    jogadores_ordenados = sorted(
        partida["jogadores"].items(),
        key=lambda x: x[1],
        reverse=True
    )

    medalhas = ["🥇", "🥈", "🥉"]

    for posicao, (usuario, pontos) in enumerate(
        jogadores_ordenados[:3]
    ):

        nome = f"Jogador {usuario}"

        resultado += (
            f"{medalhas[posicao]} "
            f"{nome} - {pontos} pontos\n"
        )


        if str(usuario) not in ranking:
            ranking[str(usuario)] = {
                "pontos": 0,
                "ultima_atualizacao": ""
            }


        ranking[str(usuario)]["pontos"] += pontos
        ranking[str(usuario)]["ultima_atualizacao"] = (
            datetime.now().strftime("%Y-%m-%d")
        )


    salvar_ranking(ranking)


    resultado += "\n📅 Ranking semanal atualizado!"


    await context.bot.send_message(
        chat_id=partida["chat_id"],
        text=resultado
    )


    partida["ativa"] = False



async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if partida["ativa"]:
        await update.message.reply_text(
            "⚠️ Já existe um quiz em andamento!"
        )
        return


    perguntas = carregar_perguntas()


    if len(perguntas) < TOTAL_PERGUNTAS:
        await update.message.reply_text(
            "❌ Banco de perguntas insuficiente."
        )
        return


    partida["ativa"] = True
    partida["chat_id"] = update.message.chat.id
    partida["perguntas"] = random.sample(
        perguntas,
        TOTAL_PERGUNTAS
    )
    partida["numero"] = 0
    partida["votos"] = {}
    partida["jogadores"] = {}


    await update.message.reply_text(
        "🎮 Quiz iniciado!\n\n"
        f"Serão {TOTAL_PERGUNTAS} perguntas.\n"
        f"Você tem {TEMPO_RESPOSTA}s para cada uma!"
    )


    iniciar_pergunta(context)
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🎮 Bem-vindo ao Quiz!\n\n"
        "Use /quiz para iniciar uma partida."
    )



async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):

    dados = carregar_ranking()


    if not dados:
        await update.message.reply_text(
            "📅 Ranking semanal vazio."
        )
        return


    lista = sorted(
        dados.items(),
        key=lambda x: x[1]["pontos"],
        reverse=True
    )


    texto = "🏆 RANKING SEMANAL\n\n"


    for posicao, (usuario, dados_usuario) in enumerate(lista[:10], 1):

        texto += (
            f"{posicao}º - "
            f"Jogador {usuario} "
            f"{dados_usuario['pontos']} pts\n"
        )


    await update.message.reply_text(texto)



def main():

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
            "ranking",
            ranking
        )
    )


    app.add_handler(
        CallbackQueryHandler(
            receber_voto
        )
    )


    print("Bot de quiz iniciado!")


    app.run_polling()



if __name__ == "__main__":
    main()
