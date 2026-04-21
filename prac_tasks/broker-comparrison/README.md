# Broker comparison (RabbitMQ vs Redis Streams)

Практика из `broker-comparrison-practice.md`: один и тот же producer/consumer, одинаковый формат сообщения и одинаковые параметры нагрузки, по очереди прогоняем через RabbitMQ и Redis и собираем измеримые метрики.

## Что измеряем

- `throughput_msg_s` (сообщений/сек обработано consumer-ами)
- `latency_ms_mean`
- `latency_ms_p95`
- `sent/processed` + ошибки

Метрики считаются на стороне consumer-а по timestamp внутри сообщения (одна машина → можно сравнивать напрямую).

## Быстрый старт

Поднять брокеры (одинаковые лимиты по CPU/RAM заданы в `docker-compose.yml`):

```bash
cd prac_tasks/broker-comparrison
docker compose up -d
```

Установить зависимости:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

Один прогон:

```bash
./.venv/bin/python -m src.cli run --broker rabbitmq --duration-s 20 --producers 1 --consumers 1 --rps 1000 --payload-bytes 128
./.venv/bin/python -m src.cli run --broker redis    --duration-s 20 --producers 1 --consumers 1 --rps 1000 --payload-bytes 128
```

Прогон матрицы (размер × rps) для обоих брокеров, вывод в `results/`:

```bash
./.venv/bin/python -m src.cli matrix --duration-s 20 --producers 1 --consumers 1 \
  --payload-bytes 128,1024,10240,102400 \
  --rps 1000,5000,10000
```

## Про формат сообщения (важно для честности)

Один и тот же бинарный формат для обоих брокеров:

- 8 байт: `sent_time_ns` (monotonic)
- 8 байт: `seq`
- N байт: случайный payload (`payload_bytes`)

## Где результаты

- `results/matrix_*.csv` — таблица результатов
- `results/matrix_*.jsonl` — построчный JSON
- черновик отчёта: `report/report.md`

