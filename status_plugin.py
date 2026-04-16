from __future__ import annotations
import json
from threading import Thread
from typing import TYPE_CHECKING
from Utils import cardinal_tools
from locales.localizer import Localizer

if TYPE_CHECKING:
    from cardinal import Cardinal
from FunPayAPI.updater.events import *
import tg_bot.static_keyboards
from os.path import exists
from tg_bot import CBT
from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B
import telebot
import logging

NAME = "Status Plugin"
VERSION = "0.0.11"
DESCRIPTION = "Добавляет возможность устанавливать статус, а пользователям FunPay по команде \"#status\" смотреть его " \
              "и время последнего действия (сообщение, отправленное человеком). "

CREDITS = "@sidor0912"
UUID = "03869c57-ddcc-49a6-8642-8319640323bd"
SETTINGS_PAGE = True
logger = logging.getLogger("FPC.status_plugin")
LOGGER_PREFIX = "[STATUS PLUGIN]"
CBT_TEXT_ADD_STATUS = "STATUS_PLUGIN_ADD_STATUS"
CBT_DELETE_STATUS = "STATUS_PLUGIN_DEL_STATUS"
CBT_GREETINGS = "STATUS_PLUGIN_GREETINGS_STATUS"
localizer = Localizer()
_ = localizer.translate


class StatusPlugin:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(StatusPlugin, cls).__new__(cls)
        return cls._instance

    def __init__(self, crd: Cardinal):
        if hasattr(self, "initialized"):
            return
        self.initialized = True
        self.cardinal = crd
        self.tg = None
        self.tgbot = None
        self.settings = {
            "statuses": list(),
            "status": "",
            "time": time.time(),
            "greetings": False
        }
        self.last_action_time = time.time()
        if self.cardinal.telegram:
            self.tg = self.cardinal.telegram
            self.tgbot = self.tg.bot
        setattr(StatusPlugin.greetings_handler, "plugin_uuid", UUID)
        setattr(StatusPlugin.message_hook, "plugin_uuid", UUID)

    def time_to_str(self, seconds):
        seconds = int(seconds)
        days = seconds // (24 * 3600)
        days = f"{days} дн. " if days else ""
        seconds = seconds % (24 * 3600)
        hours = seconds // (3600)
        hours = f"{hours} ч. " if hours else ""
        seconds = seconds % (3600)
        minutes = seconds // (60)
        minutes = f"{minutes} мин. " if minutes else ""
        seconds = seconds % (60)
        seconds = f"{seconds} сек. " if seconds else ""
        result = f"{days}{hours}{minutes}{seconds}".strip()
        return result if result else "0 сек."


    def generate_status_text(self):
        status_t = time.time() - self.settings["time"]
        last = time.time() - self.last_action_time
        msg_text = f"🚦 Статус: {self.settings['status']} (установлен {self.time_to_str(status_t)} назад)\n" if self.settings[
                                                                                                         'status'] is not None else ""
        last_action_text = f"⌛ Последнее действие: {self.time_to_str(last)} назад" if not self.cardinal.old_mode_enabled else ""
        return f"{msg_text}{last_action_text}".strip()


    def greetings_handler(self, c: Cardinal, e: NewMessageEvent | LastChatMessageChangedEvent):
        """
        Отправляет приветственное сообщение.
        """
        if not c.MAIN_CFG["Greetings"].getboolean("sendGreetings"):
            return
        if not c.old_mode_enabled:
            if isinstance(e, LastChatMessageChangedEvent):
                return
            obj = e.message
            chat_id, chat_name, mtype, its_me, badge = obj.chat_id, obj.chat_name, obj.type, obj.author_id == c.account.id, obj.badge
        else:
            obj = e.chat
            chat_id, chat_name, mtype, its_me, badge = obj.id, obj.name, obj.last_message_type, not obj.unread, None
        is_old_chat = (chat_id <= c.greeting_chat_id_threshold or chat_id in c.greeting_threshold_chat_ids)

        if any([c.MAIN_CFG["Greetings"].getboolean("onlyNewChats") and is_old_chat,
                time.time() - c.old_users.get(chat_id, 0) < float(
                    c.MAIN_CFG["Greetings"]["greetingsCooldown"]) * 24 * 60 * 60,
                its_me, mtype in (MessageTypes.DEAR_VENDORS, MessageTypes.ORDER_CONFIRMED_BY_ADMIN), badge is not None,
                (mtype is not MessageTypes.NON_SYSTEM and c.MAIN_CFG["Greetings"].getboolean("ignoreSystemMessages"))]):
            return
    
        logger.info(f"{LOGGER_PREFIX} " + _("log_sending_greetings", chat_name, chat_id))
        text = cardinal_tools.format_msg_text(c.MAIN_CFG["Greetings"]["greetingsText"], obj)
        Thread(target=c.send_message,
               args=(chat_id, f"{text}\n\n{self.generate_status_text()}", chat_name), daemon=True).start()


    def activate_plugin(self, c: Cardinal, *args):
        for i, f in enumerate(c.last_chat_message_changed_handlers):
            if f.__name__ == "greetings_handler":
                c.last_chat_message_changed_handlers[i] = self.greetings_handler
                break
        for i, f in enumerate(c.new_message_handlers):
            if f.__name__ == "greetings_handler":
                c.new_message_handlers[i] = self.greetings_handler
                break
    
    
    
    def load_config(self):
        if exists("storage/plugins/statuses_plugin_settings.json"):
            with open("storage/plugins/statuses_plugin_settings.json", "r", encoding="utf-8") as f:
                settings = json.loads(f.read())
                self.settings.update(settings)

    def save_config(self):
        with open("storage/plugins/statuses_plugin_settings.json", "w", encoding="utf-8") as f:
            f.write(json.dumps(self.settings, indent=4, ensure_ascii=False))

    def open_settings(self, call: telebot.types.CallbackQuery):
        keyboard = K()
        keyboard.add(B(f"{'🟢' if self.settings['greetings'] else '🔴'} Интегрировать в приветственное сообщении",
                       callback_data=CBT_GREETINGS))
        statuses = ""
        for i, el in enumerate(self.settings["statuses"]):
            statuses += f"/status{i + 1} - {el}\n"
            keyboard.add(B(f"🗑️ {i + 1}) {el}", callback_data=f"{CBT_DELETE_STATUS}:{i}"))
        keyboard.add(B("➕ Добавить статус", callback_data=f"{CBT_TEXT_ADD_STATUS}:"))
        keyboard.add(B("◀️ Назад", callback_data=f"{CBT.EDIT_PLUGIN}:{UUID}:0"))
        self.tgbot.edit_message_text(f"В данном разделе Вы можете настроить статус.\n\n{statuses}", call.message.chat.id,
                              call.message.id, reply_markup=keyboard)
        self.tgbot.answer_callback_query(call.id)

    def add_status(self, call: telebot.types.CallbackQuery):
        result = self.tgbot.send_message(call.message.chat.id,
                                  f"Введите статус для добавления.",
                                  reply_markup=tg_bot.static_keyboards.CLEAR_STATE_BTN())
        self.tg.set_state(call.message.chat.id, result.id, call.from_user.id, CBT_TEXT_ADD_STATUS, {})
        self.tgbot.answer_callback_query(call.id)

    def del_status(self, call: telebot.types.CallbackQuery):
        try:
            id_ = int(call.data.split(":")[-1])
            el = self.settings["statuses"].pop(id_)
            self.save_config()
            self.tgbot.send_message(
                text=f"🗑️ Статус удален: {el}\nИспользуй /restart для корректного отображения статусов в подсказках команд Telegram.",
                chat_id=call.message.chat.id)
        except:
            logger.debug(f"{LOGGER_PREFIX} Произошла ошибка при удалении статуса.")
            logger.debug(f"TRACEBACK", exc_info=True)
        self.open_settings(call)

    def edited(self, message: telebot.types.Message):
        text = message.text

        self.tg.clear_state(message.chat.id, message.from_user.id, True)
        keyboard = K() \
            .row(B("◀️ Назад", callback_data=f"{CBT.PLUGIN_SETTINGS}:{UUID}"))
        self.settings['statuses'].append(text)
        self.save_config()
        i = len(self.settings['statuses']) - 1
        self.tgbot.reply_to(message, f"✅ Добавлен статус:\n/status{i + 1} - {text}", reply_markup=keyboard)

    def edit_status(self, message: telebot.types.Message):
        self.last_action_time = time.time()
        text = message.text
        try:
            if len(text.split(" ")) == 1:
                num = int(text.split("@")[0].lower().replace("/status", ""))
                if num:
                    self.settings["status"] = self.settings["statuses"][num - 1]
                else:
                    self.settings["status"] = None

            else:
                status = text.split(" ", 1)[-1]
                self.settings["status"] = status
            self.settings["time"] = time.time()
            self.save_config()
            msg_txt = f"Статус изменен: {self.settings['status']}" if self.settings['status'] is not None else "Статус скрыт"
            self.tgbot.send_message(text=msg_txt, chat_id=message.chat.id)

        except:
            logger.debug(f"{LOGGER_PREFIX} Произошла ошибка при изменении статуса.")
            logger.debug(f"TRACEBACK", exc_info=True)
            self.tgbot.send_message(text="Статус не изменен. Команда введена неверно или элемент за границей списка",
                             chat_id=message.chat.id)

    def change_greetings(self, call: telebot.types.CallbackQuery):
        self.settings["greetings"] = not self.settings["greetings"]
        self.save_config()
        if self.settings["greetings"]:
            self.activate_plugin(self.cardinal)
        else:
            self.tgbot.answer_callback_query(call.id, "Успешно изменено. Перезапустите бота командой /restart",
                                      show_alert=True)
        self.open_settings(call)

    def reg_tg_handlers(self):
        self.tg.msg_handler(self.edited, func=lambda m: self.tg.check_state(m.chat.id, m.from_user.id, CBT_TEXT_ADD_STATUS))
        self.tg.cbq_handler(self.add_status, lambda c: f"{CBT_TEXT_ADD_STATUS}" in c.data)
        self.tg.cbq_handler(self.change_greetings, lambda c: f"{CBT_GREETINGS}" in c.data)
        self.tg.cbq_handler(self.del_status, lambda c: f"{CBT_DELETE_STATUS}:" in c.data)
        self.cardinal.add_telegram_commands(UUID, [
            (f"status0", "Скрыть статус", True),
        ])
        for i, el in enumerate(self.settings["statuses"]):
            self.cardinal.add_telegram_commands(UUID, [
                (f"status{i + 1}", el, True),
            ])
        self.cardinal.add_telegram_commands(UUID, [
            (f"status", "Произвольный статус", True),
        ])
        self.tg.msg_handler(self.edit_status, func=lambda m: m.text.startswith("/status"))
        self.tg.cbq_handler(self.open_settings, lambda c: f"{CBT.PLUGIN_SETTINGS}:{UUID}" in c.data)
        
    def reg_handlers(self, c: Cardinal):
        if self.settings["greetings"]:
            self.activate_plugin(c)
        self.cardinal.new_message_handlers.append(self.message_hook)
        self.cardinal.last_chat_message_changed_handlers.append(self.message_hook)
    
    
    def message_hook(self, c: Cardinal, e: NewMessageEvent | LastChatMessageChangedEvent):
        if not c.old_mode_enabled:
            if isinstance(e, LastChatMessageChangedEvent):
                return
            obj = e.message
            msg_text = obj.text
            author = obj.author
            chat_id = obj.chat_id
            if (not e.message.by_bot or hasattr(e,
                                                "sync_ignore")) and e.message.author_id == c.account.id and e.message.badge is None:
                self.last_action_time = time.time()
        else:
            obj = e.chat
            msg_text = obj.last_message_text
            chat_id = obj.id
            author = obj.name

        if msg_text is not None and msg_text.lower() == "#status":
            if author in c.blacklist and c.bl_response_enabled:
                return
            c.send_message(chat_id=chat_id, message_text=self.generate_status_text())

def pre_init(c: Cardinal):
    sp = StatusPlugin(c)
    sp.load_config()
    sp.reg_tg_handlers()
    sp.reg_handlers(c)

BIND_TO_PRE_INIT = [pre_init]
BIND_TO_DELETE = None
