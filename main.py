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
        parse_mode="HTML",
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
        "usuario": usuario,
    }

    partida["jogadores"].setdefault(
        usuario,
        0
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

    # Mostra a contagem somente para quem acabou de votar,
    # sem enviar mensagem no privado do jogador.
    await query.answer(
        parcial,
        show_alert=True
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
    jogadores = []

    for usuario, pontos in partida["jogadores"].items():
        nome = "Jogador"
        # O nome é recuperado dos votos feitos durante a partida.
        for voto in partida["votos"].values():
            if voto.get("nome") and voto.get("usuario") == usuario:
                nome = voto["nome"]
                break
        jogadores.append((usuario, nome, pontos))

    jogadores.sort(key=lambda item: item[2], reverse=True)

    ranking = carregar_ranking()

    for usuario, nome, pontos in jogadores:
        chave = str(usuario)
        registro = ranking["jogadores"].setdefault(
            chave,
            {"nome": nome, "pontos": 0}
        )
        if nome != "Jogador":
            registro["nome"] = nome
        registro["pontos"] += pontos

    salvar_ranking(ranking)

    texto = "🏆 <b>FIM DE JOGO!</b>\n\n"
    texto += "🔥 Foi uma batalha de conhecimento!\n\n"

    medalhas = ["🥇", "🥈", "🥉"]

    if not jogadores:
        texto += "😅 Ninguém marcou pontos desta vez!"
    else:
        for posicao, (_, nome, pontos) in enumerate(jogadores[:3]):
            texto += (
                f"{medalhas[posicao]} <b>{nome}</b> — "
                f"<b>{pontos} pontos</b>\n"
            )

    texto += "\n📈 <b>Ranking semanal atualizado!</b>\n"
    texto += "😈 Já prepara a revanche... o próximo desafio vem aí!"

    chat_id = partida["chat_id"]
    limpar_partida()

    await context.bot.send_message(
        chat_id=chat_id,
        text=texto,
        parse_mode="HTML"
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
    dados = carregar_ranking()
    jogadores = dados.get("jogadores", {})

    if not jogadores:
        await update.message.reply_text(
            "🏆 O ranking desta semana ainda está vazio!"
        )
        return

    lista = sorted(
        jogadores.items(),
        key=lambda item: item[1].get("pontos", 0),
        reverse=True
    )

    texto = (
        f"🏆 <b>RANKING SEMANAL</b>\n"
        f"📅 Semana {dados['semana']}\n\n"
    )

    medalhas = ["🥇", "🥈", "🥉"]

    for posicao, (_, info) in enumerate(lista[:10], 1):
        prefixo = medalhas[posicao - 1] if posicao <= 3 else f"{posicao}º"
        texto += (
            f"{prefixo} <b>{info.get('nome', 'Jogador')}</b> — "
            f"{info.get('pontos', 0)} pts\n"
        )

    await update.message.reply_text(
        texto,
        parse_mode="HTML"
    )





async def regras(update: Update, context):
    await update.message.reply_text(
        "📖 <b>COMO JOGAR</b>\n\n"
        "🎯 15 perguntas por partida.\n"
        "⏱️ 15 segundos para responder.\n"
        "☑️ Um voto por pergunta, sem volta.\n"
        "🚫 Não dá para votar depois do tempo.\n"
        "🏆 Cada acerto vale 10 pontos.\n"
        "🥇🥈🥉 Os três melhores vão para o pódio.\n"
        "📈 Os pontos entram no ranking semanal.\n\n"
        "😈 Nada de Google! 😂",
        parse_mode="HTML"
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
        CommandHandler(
            "regras",
            regras
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
