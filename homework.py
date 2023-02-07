import os
import time
import requests
import json

import sys
import telegram
import logging
from dotenv import load_dotenv
from http import HTTPStatus

from exceptions import ServerError, KeyNotFound, UnknownStatus, MissingVariable

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s - %(funcName)s - [%(levelname)s] - %(message)s'
)
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет наличие токенов."""
    flag = all([
        PRACTICUM_TOKEN is not None,
        TELEGRAM_TOKEN is not None,
        TELEGRAM_CHAT_ID is not None
    ])
    return flag


def send_message(bot, message) -> None:
    """
    Отправляет сообщение в Телеграмм.
    В случае неудачи, вызывает ошибку. Логирует события.
    """
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug('Сообщение успешно дошло до получателя.')
    except telegram.error.TelegramError:
        logger.error('Сообщение не отправилось')


def get_api_answer(timestamp):
    """Направляет запрос к API ЯндексПрактикума,возращает ответ."""
    params = {'from_date': timestamp}
    try:
        logging.info('Отправляю запрос к API ЯндексПрактикума')
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except requests.exceptions.ConnectionError as connect_error:
        raise logger.error('Ошибка подключения:', connect_error)
    except requests.exceptions.Timeout as timout_error:
        raise logger.error('Время запроса вышло', timout_error)
    except requests.exceptions.RequestException as request_error:
        raise logger.error(request_error)
    if response.status_code != HTTPStatus.OK:
        logger.error('Недоступность эндпоинта')
        raise ServerError()
    try:
        return response.json()
    except json.JSONDecodeError():
        raise logger.error('Полученный ответ не в ожидаемом JSON-формате')


def check_response(response: dict) -> list:
    """Проверка корректности ответа API."""
    if isinstance(response, dict):
        try:
            homework = response['homeworks']
        except KeyError as error:
            message = f'В ответе не обнаружен ключ {error}'
            logger.error(message)
            raise KeyNotFound(message)
        if not isinstance(homework, list):
            raise TypeError('Ответ не содержит список домашних работ')
        message = 'Получены сведения о последней домашней работе'
        logger.info(message) if len(homework) else None
        return homework
    else:
        raise TypeError('В ответе API не обнаружен словарь')


def parse_status(homework):
    """Извлекает статус работы из ответа ЯндексПракутикум."""
    try:
        homework_name = homework['homework_name']
        homework_status = homework['status']
    except KeyError as error:
        message = f'Ключ {error} не найден в информации о домашней работе'
        logger.error(message)
        raise KeyError(message)

    try:
        verdict = HOMEWORK_VERDICTS[homework_status]
        logger.info('Сообщение подготовлено для отправки')
    except KeyError as error:
        message = f'Неизвестный статус домашней работы: {error}'
        logger.error(message)
        raise UnknownStatus(message)

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def parse_date(homework):
    """Извлекает дату обновления работы из ответа ЯндексПракутикум."""
    date_updated = homework.get('date_updated')
    if date_updated is None:
        logging.error('В ответе API нет ключа date_updated')
        raise KeyError('В ответе API нет ключа date_updated')
    return date_updated


def main() -> None:
    """Основная логика работы бота."""
    logger.info('Бот запущен')

    if not check_tokens():
        message = 'Отсутствует одна из переменных окружения'
        logger.critical(message + '\nПрограмма остановлена.')
        raise MissingVariable(message)

    try:
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
    except telegram.error.InvalidToken as error:
        message = f'Ошибка при создании бота: {error}'
        logger.critical(message + '\nПрограмма остановлена.')
        raise telegram.error.InvalidToken

    timestamp = int(time.time())
    last_homework = None
    last_error = None

    while True:
        try:
            response = get_api_answer(timestamp - RETRY_PERIOD)
            homework = check_response(response)
            if homework and homework != last_homework:
                message = parse_status(homework[0])
                send_message(bot, message)
                last_homework = homework
            else:
                logger.debug('Статус домашней работы не изменился')
            timestamp = response.get('current_date')
            time.sleep(RETRY_PERIOD)

        except Exception as error:
            if str(error) != last_error:
                message = f'Сбой в работе программы: {error}'
                send_message(bot, message)
                last_error = str(error)
                time.sleep(RETRY_PERIOD)
            else:
                time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit()
