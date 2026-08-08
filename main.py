import os
import json
import random
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

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
    "jogadores": {}
}


def carregar(nome, padrao):
    try:
        with open(nome, "r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except (FileNotFoundError, json.JSONDecodeError):
        return padrao


def salvar(nome, dados):
    with open(nome, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, indent=4, ensure_ascii=False)


def carregar_perguntas():
    banco = carregar(ARQUIVO_PERGUNTAS, [])
    lista = []
    for categoria in banco:
        lista.extend(categoria.get("perguntas", []))
    return lista


async def enviar_pergunta(context: ContextTypes.DEFAULT_TYPE):
    if not partida["ativa"]:
        return

    pergunta = partida["perguntas"][partida["numero"]]
    partida["votos"] = {}

    botoes = []
    for i, opcao in enumerate(pergunta["opcoes"]):
        botoes.append([
            InlineKeyboardButton(
                f"{chr(65 + i)}) {opcao}",
                callback_data=f"voto_{i}"
            )
        ])

    texto = (
        f"🧠 PERGUNTA {partida['numero'] + 1}/{TOTAL_PERGUNTAS}\n\n"
        f"{pergunta['pergunta']}\n\n"
        f"⏱️ Você tem {TEMPO_RESPOSTA} segundos."
    )

    await context.bot.send_message(
        chat_id=partida["chat_id"],
        text=texto,
        reply_markup=InlineKeyboardMarkup(botoes)
    )

    await asyncio.sleep(TEMPO_RESPOSTA)

    if partida["ativa"]:
        await finalizar_pergunta(context)


async def finalizar_pergunta(context: ContextTypes.DEFAULT_TYPE):
    if not partida["ativa"]:
        return

    pergunta = partida["perguntas"][partida["numero"]]
    contagem = [0] * len(pergunta["opcoes"])

    for voto in partida["votos"].values():
        if 0 <= voto < len(contagem):
            contagem[voto] += 1

    resultado = "⏰ TEMPO ENCERRADO!\n\n📊 VOTOS:\n"
    for i, total in enumerate(contagem):
        resultado += f"{chr(65 + i)}) {total} voto(s)\n"

    correta = pergunta["correta"]
    resultado += (
        f"\n✅ Resposta correta: "
        f"{chr(65 + correta)}) {pergunta['opcoes'][correta]}"
    )

    await context.bot.send_message(
        chat_id=partida["chat_id"],
        text=resultado
    )

    for usuario, resposta in partida["votos"].items():
        if resposta == correta:
            partida["jogadores"][usuario] = partida["jogadores"].get(usuario, 0) + 10

    partida["numero"] += 1

    if partida["numero"] < TOTAL_PERGUNTAS:
        await enviar_pergunta(context)
    else:
        await finalizar_quiz(context)


async def receber_voto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if not partida["ativa"]:
        await query.answer("Este quiz já terminou.", show_alert=True)
        return

    usuario = query.from_user.id

    if usuario in partida["votos"]:
        await query.answer("Você já votou nesta pergunta!", show_alert=True)
        return

    try:
        escolha = int(query.data.split("_")[1])
    except (ValueError, IndexError):
        await query.answer("Voto inválido.", show_alert=True)
        return

    partida["votos"][usuario] = escolha
    partida["jogadores"].setdefault(usuario, 0)

    await query.answer("✅ Voto registrado!")

    pergunta = partida["perguntas"][partida["numero"]]
    contagem = [0] * len(pergunta["opcoes"])

    for voto in partida["votos"].values():
        if 0 <= voto < len(contagem):
            contagem[voto] += 1

    texto = "📊 VOTOS ATUAIS:\n\n"
    for i, total in enumerate(contagem):
        texto += f"{chr(65 + i)}) {total} voto(s)\n"

    await context.bot.send_message(
        chat_id=query.message.chat.id,
        text=texto
    )


async def finalizar_quiz(context: ContextTypes.DEFAULT_TYPE):
    jogadores = sorted(
        partida["jogadores"].items(),
        key=lambda item: item[1],
        reverse=True
    )

    texto = "🏆 PÓDIO FINAL\n\n"
    medalhas = ["🥇", "🥈", "🥉"]

    if not jogadores:
        texto += "Ninguém marcou pontos nesta partida."
    else:
        for posicao, (usuario, pontos) in enumerate(jogadores[:3]):
            texto += f"{medalhas[posicao]} Jogador {usuario} — {pontos} pontos\n"

    ranking = carregar(ARQUIVO_RANKING, {})
    for usuario, pontos in partida["jogadores"].items():
        chave = str(usuario)
        ranking[chave] = ranking.get(chave, 0) + pontos

    salvar(ARQUIVO_RANKING, ranking)

    await context.bot.send_message(
        chat_id=partida["chat_id"],
        text=texto
    )

    partida["ativa"] = False
    partida["perguntas"] = []
    partida["votos"] = {}
    partida["jogadores"] = {}
    partida["numero"] = 0


async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if partida["ativa"]:
        await update.message.reply_text("⚠️ Já existe um quiz em andamento.")
        return

    perguntas = carregar_perguntas()

    if len(perguntas) < TOTAL_PERGUNTAS:
        await update.message.reply_text(
            f"❌ O banco possui apenas {len(perguntas)} perguntas. "
            f"São necessárias pelo menos {TOTAL_PERGUNTAS}."
        )
        return

    partida["ativa"] = True
    partida["chat_id"] = update.message.chat.id
    partida["perguntas"] = random.sample(perguntas, TOTAL_PERGUNTAS)
    partida["numero"] = 0
    partida["votos"] = {}
    partida["jogadores"] = {}

    await update.message.reply_text(
        "🎮 QUIZ INICIADO!\n\n"
        f"🧠 {TOTAL_PERGUNTAS} perguntas\n"
        f"⏱️ {TEMPO_RESPOSTA} segundos por pergunta"
    )

    await enviar_pergunta(context)


async def parar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not partida["ativa"]:
        await update.message.reply_text("ℹ️ Não existe quiz em andamento.")
        return

    partida["ativa"] = False
    partida["perguntas"] = []
    partida["votos"] = {}
    partida["jogadores"] = {}
    partida["numero"] = 0

    await update.message.reply_text("🛑 Quiz encerrado manualmente.")


async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dados = carregar(ARQUIVO_RANKING, {})

    if not dados:
        await update.message.reply_text("🏆 Ranking vazio.")
        return

    lista = sorted(dados.items(), key=lambda item: item[1], reverse=True)
    texto = "🏆 RANKING\n\n"

    for posicao, (usuario, pontos) in enumerate(lista[:10], 1):
        texto += f"{posicao}º — Jogador {usuario}: {pontos} pts\n"

    await update.message.reply_text(texto)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎮 Bem-vindo ao Quiz!\n\n"
        "/quiz — iniciar uma partida\n"
        "/parar — parar a partida\n"
        "/ranking — ver o ranking"
    )


def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN não foi configurado nas variáveis do serviço.")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(CommandHandler("parar", parar))
    app.add_handler(CommandHandler("ranking", ranking))
    app.add_handler(CallbackQueryHandler(receber_voto, pattern=r"^voto_[0-9]+$"))

    print("Bot de quiz iniciado!")
    app.run_polling()


if __name__ == "__main__":
    main()
