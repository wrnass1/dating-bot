# Нагрузочное тестирование (Apache JMeter)

## Подготовка

1. Подними стек: `docker compose up --build -d`
2. Создай 2+ пользователей и анкеты через бота (`/start`, `/profile`).
3. Установи [Apache JMeter](https://jmeter.apache.org/download_jmeter.cgi).

## Сценарий

Файл `feed-next.jmx` нагружает `POST /feed/next` и `POST /interactions`.

Переменные (User Defined Variables в плане):

| Переменная | Значение по умолчанию |
|------------|----------------------|
| `API_HOST` | `localhost` |
| `API_PORT` | `18000` |
| `VIEWER_TELEGRAM_ID` | `101` |
| `TARGET_PROFILE_ID` | UUID анкеты из БД |

Если задан `API_SERVICE_TOKEN`, добавь HTTP Header `X-API-Token`.

## Запуск

```bash
jmeter -n -t load-test/feed-next.jmx -l load-test/results.jtl -e -o load-test/report
```

Отчёт: `load-test/report/index.html`.

## Ожидаемый результат

- p95 latency для `/feed/next` < 500 ms при 10–20 потоках на локальной машине
- 0% ошибок при корректно заполненных тестовых данных
