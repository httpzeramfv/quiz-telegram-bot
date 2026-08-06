import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

TOKEN = os.getenv("BOT_TOKEN")

perguntas = [
    {
        "pergunta": "Qual é o maior planeta do Sistema Solar?",
        "opcoes": ["Terra", "Marte", "Júpiter", "Saturno"],
        "resposta": 2,
    },
    {
        "pergunta": "Quem pintou a Mona Lisa?",
        "opcoes": ["Van Gogh", "Leonardo da Vinci", "Picasso", "Michelangelo"],
        "resposta": 1,
    },
]

jogo = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎮 Bem-vindo ao Quiz!\n\nUse /quiz para começar."
    )


async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pergunta = perguntas[0]

    botoes = []
    for i, opcao in enumerate(pergunta["opcoes"]):
        botoes.append(
            [InlineKeyboardButton(
                f"{chr(65+i)}) {opcao}",
                callback_data=str(i)
            )]
        )

    mensagem = await update.message.reply_text(
        f"🧠 Pergunta:\n\n{pergunta['pergunta']}\n\n"
        "⏱ Você tem 20 segundos!",
        reply_markup=InlineKeyboardMarkup(botoes),
    )

    jogo["mensagem"] = mensagem.message_id
    jogo["respostas"] = {}
    jogo["chat"] = update.effective_chat.id

    await asyncio.sleep(20)

    resultado = "📊 Resultado:\n\n"

    for opcao, votos in enumerate(
        [list(jogo["respostas"].values()).count(i) for i in range(4)]
    ):
        resultado += f"{chr(65+opcao)}: {votos} votos\n"

    resultado += (
        f"\n✅ Resposta correta: "
        f"{chr(65+pergunta['resposta'])}) "
        f"{pergunta['opcoes'][pergunta['resposta']]}"
    )

    await context.bot.send_message(
        chat_id=jogo["chat"],
        text=resultado
    )


async def resposta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    usuario = query.from_user.id

    if usuario not in jogo["respostas"]:
        jogo["respostas"][usuario] = int(query.data)

    await query.answer("Resposta registrada!")


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(CallbackQueryHandler(resposta))

    app.run_polling()


if __name__ == "__main__":
    main()
