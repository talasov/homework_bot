import os
import time
import requests
import json

import sys
import telegram
import logging
from dotenv import load_dotenv
from http import HTTPStatus

from exceptions import ServerError, KeyNotFound, UnknownStatus, MissingVariable, EmptyDictionaryOrListError, \
    UndocumentedStatusError

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
    """Проверяет доступ к переменным окружения, необходимых для работы бота."""
    return PRACTICUM_TOKEN and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID


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
    except Exception as connect_error:
        raise logger.error('Ошибка подключения:', connect_error)
    if response.status_code != HTTPStatus.OK:
        logger.error('Недоступность эндпоинта')
        raise ServerError()
    try:
        return response.json()
    except json.JSONDecodeError():
        raise logger.error('Полученный ответ не в ожидаемом JSON-формате')


def check_response(response: dict) -> list:
    """Проверка корректности ответа API."""
    if not isinstance(response, dict):
        raise TypeError(
            f'Ответ сервиса не является словарем. Ответ сервиса {response}.'
        )

    if not response.get('current_date'):
        raise KeyError('В полученном ответе отсутствует ключ `current_date`.')

    if not response.get('homeworks'):
        raise KeyError('В полученном ответе отсутствует ключ `homeworks`.')

    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError(
            f'Значение по ключу `homeworks` не является списком.'
            f'Ответ сервиса: {homeworks}'
        )

    if not homeworks:
        raise IndexError('Значение по ключу `homeworks` - пустой список.')

    return homeworks


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

        except Exception as error:
            if str(error) != last_error:
                message = f'Сбой в работе программы: {error}'
                send_message(bot, message)
                last_error = str(error)

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit()
