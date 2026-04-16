from __future__ import annotations
from typing import TYPE_CHECKING
from locales.localizer import Localizer

if TYPE_CHECKING:
    from cardinal import Cardinal
import tg_bot.static_keyboards
import telebot
import logging
import requests

NAME = "TG Proxy Plugin"
VERSION = "0.0.1"
DESCRIPTION = "Возможность добавить прокси Telegram до установки Cardinal 0.1.17.4+, чтобы не нужно было повторно вручную редактировать файлы."

CREDITS = "@sidor0912"
UUID = "d1fc5c71-911f-4ecd-bf21-2e81aed678c5"
SETTINGS_PAGE = False
localizer = Localizer()
_ = localizer.translate
logger = logging.getLogger("FPC.tg_proxy_plugin")
PROXY_STATE = UUID

class ProxyTG:

    def __init__(self, crd: Cardinal):
        self.cardinal = crd
        self.tg = None
        self.tgbot = None
        if self.cardinal.telegram:
            self.tg = self.cardinal.telegram
            self.tgbot = self.tg.bot

    def check_proxy(self, proxy: dict) -> bool:
        """
        Проверяет работоспособность прокси.

        :param proxy: словарь с данными прокси.

        :return: True, если прокси работает, иначе - False.
        """
        logger.info(_("crd_checking_proxy"))
        try:
            response = requests.get("https://api.ipify.org/", proxies=proxy, timeout=10)
        except:
            logger.error(_("crd_proxy_err"))
            logger.debug("TRACEBACK", exc_info=True)
            return False
        logger.info(_("crd_proxy_success", response.content.decode()))
        return True

    def validate_proxy(self, proxy: str):
        """
        Проверяет прокси на соответствие формату IPv4 и выбрасывает исключение или возвращает логин, пароль, IP и порт.

        :param proxy: прокси
        :return: логин, пароль, IP и порт
        """
        try:
            if "://" in proxy:
                scheme, rest = proxy.split("://", 1)
            else:
                scheme = "http"
                rest = proxy

            if "@" in rest:
                login_password, ip_port = rest.split("@")
                login, password = login_password.split(":")
            else:
                login, password = "", ""
                ip_port = rest

            ip, port = ip_port.split(":")

            ip_parts = ip.split(".")
            if len(ip_parts) != 4 or not all(part.isdigit() and 0 <= int(part) < 256 for part in ip_parts):
                raise ValueError("Неправильный IP")

            if not port.isdigit() or not 0 < int(port) <= 65535:
                raise ValueError("Неправильный порт")

            if scheme not in ("http", "https", "socks5"):
                raise ValueError("Схема прокси должна быть http, https или socks5")

        except Exception:
            raise ValueError("Прокси должен иметь формат:\n"
                             "ip:port\nlogin:password@ip:port\n"
                             "или socks5://ip:port\nsocks5://login:password@ip:port")

        return scheme, login, password, ip, port

    def build_proxy(self, scheme: str | None, login: str, password: str, ip: str, port: str) -> str:
        if not scheme:
            scheme = "http"
        if login and password:
            return f"{scheme}://{login}:{password}@{ip}:{port}"
        else:
            return f"{scheme}://{ip}:{port}"

    def edited(self, message: telebot.types.Message):
        text = message.text

        self.tg.clear_state(message.chat.id, message.from_user.id, True)
        try:
            try:
                p = self.validate_proxy(text)
            except Exception as ex:
                self.tgbot.reply_to(message, f"❌ Некорректный формат!\n\n"
                                             f"Правильные форматы:\n"
                                             f"<code>scheme://login:password@ip:port</code> (Например: <code>socks5://loginchik:passwordik@124.123.122.11:8000</code>)\n"
                                             f"<code>login:password@ip:port</code>\n"
                                             f"<code>ip:port</code>\n")
                return
            proxy_str = self.build_proxy(*p)
            proxy_dict = {"http": proxy_str, "https": proxy_str}
            if not self.check_proxy(proxy_dict):
                self.tgbot.reply_to(message, f"❌ Возникла ошибка при проверке валидности прокси!")
                return
            self.cardinal.MAIN_CFG["Telegram"]["proxy"] = proxy_str
            self.cardinal.save_config(self.cardinal.MAIN_CFG, "configs/_main.cfg")

            self.tgbot.reply_to(message, f"✅ Telegram прокси добавлены!")
        except:
            self.tgbot.reply_to(message, f"❌ Возникла ошибка при добавлении прокси!")

    def edit(self, message: telebot.types.Message):
        result = self.tgbot.send_message(message.chat.id,
                                  f"Введите прокси для подключения к Telegram в одном из следующих форматов:\n"
                                  f"<code>scheme://login:password@ip:port</code> (Например: <code>socks5://loginchik:passwordik@124.123.122.11:8000</code>)\n"
                                  f"<code>login:password@ip:port</code>\n"
                                  f"<code>ip:port</code>\n",
                                  reply_markup=tg_bot.static_keyboards.CLEAR_STATE_BTN())
        self.tg.set_state(message.chat.id, result.id, message.from_user.id, PROXY_STATE, {})

    def reg_tg_handlers(self):
        self.tg.msg_handler(self.edited, func=lambda m: self.tg.check_state(m.chat.id, m.from_user.id, PROXY_STATE))
        self.tg.msg_handler(self.edit, func=lambda m: m.text.startswith("/proxy_tg"))
        self.cardinal.add_telegram_commands(UUID, [
            (f"proxy_tg", "Добавить прокси Telegram", True),
        ])

def pre_init(c: Cardinal):
    sp = ProxyTG(c)
    sp.reg_tg_handlers()

BIND_TO_PRE_INIT = [pre_init]
BIND_TO_DELETE = None
