import os
import logging
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
import fitz

# Configuration - Environment Variables only (no defaults with real values)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
PORT = int(os.environ.get("PORT", 8080))

logger.info(f"Boot config: TELEGRAM_TOKEN={'set' if TELEGRAM_TOKEN else 'MISSING'}, "
            f"GROQ_API_KEY={'set' if GROQ_API_KEY else 'MISSING'}, PORT={PORT}")

if not TELEGRAM_TOKEN or not GROQ_API_KEY:
    logger.error("FATAL: TELEGRAM_TOKEN and GROQ_API_KEY environment variables must be set")

# Initialize Groq Client
groq_client = Groq(api_key=GROQ_API_KEY)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Fake Health Check Server - يحافظ على نشاط الـ Worker على Render
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive")

    def log_message(self, format, *args):
        pass  # Silent logs

def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logger.info(f"Health server running on port {PORT}")
    server.serve_forever()

# Knowledge Base
KNOWLEDGE_BASE = """
معلومات متجر التك للابتوبات (Tech Laptop Store):
- اسم المتجر: متجر التك للابتوبات
- الموقع: بورتسودان (معرض رئيسي) + خدمة التوصيل والشحن لجميع الولايات.
- ساعات العمل: يومياً من 9:00 صباحاً حتى 9:00 مساءً.

الأجهزة المتاحة حالياً:
1. Lenovo ThinkPad X1 Carbon Gen 10:
   - المعالج: Intel Core i7 (الجيل 12)
   - الذاكرة: 16GB RAM
   - التخزين: 512GB NVMe SSD
   - السعر: 750,000 جنيه سوداني (أو 650 دولار)
   - الاستخدام: ممتاز للبرمجة والدراسة.

2. Dell XPS 13:
   - المعالج: Intel Core i7 (الجيل 11)
   - الذاكرة: 16GB RAM
   - التخزين: 512GB SSD
   - الشاشة: 13.3 بوصة 4K Touchscreen
   - السعر: 680,000 جنيه سوداني (أو 590 دولار)
   - الاستخدام: تصاميم، خفيف الوزن.

3. HP Spectre x360:
   - المعالج: Intel Core i7 (الجيل 12)
   - الذاكرة: 16GB RAM
   - التخزين: 1TB SSD
   - السعر: 820,000 جنيه سوداني (أو 710 دولار)
   - الاستخدام: المونتاج، الجرافيكس.

4. MacBook Pro 14 (M1 Pro):
   - المعالج: M1 Pro
   - الذاكرة: 16GB Unified Memory
   - التخزين: 512GB SSD
   - السعر: 1,100,000 جنيه سوداني (أو 950 دولار)
   - الاستخدام: البرمجة والمونتاج الثقيل.

5. ASUS ROG Zephyrus G14:
   - المعالج: AMD Ryzen 7 5800HS
   - كرت الشاشة: Nvidia RTX 3060 6GB
   - الذاكرة: 16GB RAM
   - التخزين: 512GB SSD
   - السعر: 900,000 جنيه سوداني (أو 780 دولار)
   - الاستخدام: الألعاب الثقيلة والـ 3D Rendering.

سياسات المتجر:
- الضمان: فحص مجاني + ضمان صيانة 6 أشهر.
- الاسترجاع: خلال 3 أيام عمل.
- وسائل الدفع: بنكك، كاش، تحويل بنكي.
- التوصيل: بورتسودان فوري، باقي الولايات خلال 24-48 ساعة.
"""

SYSTEM_PROMPT = f"""
أنت موظف خدمة عملاء ذكي لـ "متجر التك للابتوبات" في السودان.
اسمك "مساعد التك".

قواعد الرد:
1. تحدث دائماً بـ "اللهجة السودانية" مثل: "مرحب بيك يا حبيبنا"، "حبابك عشرة"، "أبشر بالخير"، "تأمر أمر".
2. اعتمد فقط على معلومات المتجر أدناه، وإذا سألك عن شيء غير موجود قل له بلطف إنك ستتأكد من الإدارة.
3. كن موجزاً ومباشراً.
4. تعامل بنفس الأسلوب السوداني اللطيف مع الفويسات والصور والملفات.

معلومات المتجر:
{KNOWLEDGE_BASE}
"""

# User Conversation Memory
user_chat_history = {}

def get_history(user_id):
    if user_id not in user_chat_history:
        user_chat_history[user_id] = []
    return user_chat_history[user_id]

def add_to_history(user_id, role, content):
    history = get_history(user_id)
    history.append({"role": role, "content": content})
    if len(history) > 10:
        user_chat_history[user_id] = history[-10:]

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    greeting = f"مرحب بيك يا {user.first_name}! 👋\n\nأنا مساعد متجر التك للابتوبات 💻. أهلاً وسهلاً بيك، أقدر أساعدك في اختيار اللابتوب المناسب، معرفة الأسعار، المواصفات، أو أي استفسار عن الضمان والتوصيل.\n\nممكن تراسلني بنص، تسجل لي فويسات، أو ترسل صور وملفات PDF! أبشر بالخير."
    await update.message.reply_text(greeting)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text

    add_to_history(user_id, "user", user_text)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(get_history(user_id))

    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.6,
            max_tokens=800
        )
        bot_reply = completion.choices[0].message.content
        add_to_history(user_id, "assistant", bot_reply)
        await update.message.reply_text(bot_reply)
    except Exception as e:
        logger.error(f"Error handling text: {e}")
        await update.message.reply_text("معليش يا حبيبنا حصلت مشكلة بسيطة في الشبكة، جرب راسلني تاني بركة.")

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("🎧 جاري استماع الصوت وتحويله لنص...")

    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        voice_bytes = await voice_file.download_as_bytearray()

        audio_file_obj = ("voice.ogg", bytes(voice_bytes), "audio/ogg")
        transcription = groq_client.audio.transcriptions.create(
            file=audio_file_obj,
            model="whisper-large-v3-turbo",
            language="ar",
            response_format="text"
        )

        transcribed_text = str(transcription).strip()
        logger.info(f"Transcribed Voice: {transcribed_text}")

        reply_intro = f"🎙️ *سمعتك بتقول:* \"{transcribed_text}\"\n\n"

        add_to_history(user_id, "user", f"[رسالة صوتية من الزبون]: {transcribed_text}")

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(get_history(user_id))

        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.6,
            max_tokens=800
        )

        bot_reply = completion.choices[0].message.content
        add_to_history(user_id, "assistant", bot_reply)

        await update.message.reply_text(reply_intro + bot_reply, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error handling voice: {e}")
        await update.message.reply_text("يا حبيبنا معليش ما قدرت أسمع الفويس كويس، جرب سجل تاني أو اكتب لي نص.")

async def handle_document_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    doc = update.message.document

    if not doc.file_name.lower().endswith('.pdf'):
        await update.message.reply_text("أهلاً يا حبيبنا! ياريت ترسل الملف بصيغة PDF.")
        return

    await update.message.reply_text("📄 جاري قراءة وتحليل ملف الـ PDF...")

    try:
        pdf_file = await context.bot.get_file(doc.file_id)
        pdf_bytes = await pdf_file.download_as_bytearray()

        doc_fitz = fitz.open(stream=pdf_bytes, filetype="pdf")
        extracted_text = ""
        for page in doc_fitz:
            extracted_text += page.get_text()

        extracted_text = extracted_text.strip()[:3000]

        if not extracted_text:
            await update.message.reply_text("الملف ده ما فيه نصوص واضحة، جرب ارسل ملف تاني.")
            return

        prompt = f"الزبون أرسل ملف PDF اسمه '{doc.file_name}'. محتوى الملف:\n{extracted_text}\n\nيرجى قراءته والرد على الزبون باللهجة السودانية."

        add_to_history(user_id, "user", prompt)

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(get_history(user_id))

        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.6,
            max_tokens=900
        )

        bot_reply = completion.choices[0].message.content
        add_to_history(user_id, "assistant", bot_reply)

        await update.message.reply_text(f"📊 *نتيجة قراءة الملف ({doc.file_name}):*\n\n{bot_reply}", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error handling PDF: {e}")
        await update.message.reply_text("معليش حصلت مشكلة أثناء قراءة ملف الـ PDF.")

async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    caption = update.message.caption or ""

    prompt = f"الزبون أرسل صورة لابتوب/منتج مع تعليق: '{caption}'. رد عليه بلطف باللهجة السودانية واسأله عن التفاصيل."

    add_to_history(user_id, "user", prompt)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(get_history(user_id))

    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.6,
            max_tokens=600
        )

        bot_reply = completion.choices[0].message.content
        add_to_history(user_id, "assistant", bot_reply)

        await update.message.reply_text(f"🖼️ أهلاً بيك! استلمت الصورة 👍\n\n{bot_reply}")
    except Exception as e:
        logger.error(f"Error handling photo: {e}")
        await update.message.reply_text("استلمت الصورة يا حبيبنا! أقدر أساعدك كيف بخصوصها؟")

def main():
    print("🚀 جاري تشغيل بوت متجر التك للابتوبات...")

    # تشغيل Health Server في Thread منفصل عشان Render ما يقفل الـ Worker
    health_thread = Thread(target=run_health_server, daemon=True)
    health_thread.start()

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))

    print("✅ البوت شغال ومستعد لاستقبال الرسائل في تليجرام!")
    app.run_polling()

if __name__ == "__main__":
    main()