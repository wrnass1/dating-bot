# Отчет по сравнению стратегий кеширования

## Что сравнивается

Сравниваются три стратегии кеширования для одной и той же системы:

- `cache-aside`
- `write-through`
- `write-back`

Инфраструктура одинакова для всех прогонов:

- `PostgreSQL` - основная БД
- `Redis` - кеш
- одинаковый набор данных
- одинаковая длительность теста
- одинаковые профили нагрузки

## Профили нагрузки

- `read-heavy`: `80% read / 20% write`
- `balanced`: `50% read / 50% write`
- `write-heavy`: `20% read / 80% write`

## Команды запуска

```bash
./.venv/bin/python -m src.cli init-db --dataset-size 1000
./.venv/bin/python -m src.cli matrix --duration-s 20
```

## Таблица результатов

После запуска `matrix` перенеси сюда строки из `results/matrix_*.csv`.

| strategy | profile | throughput_req_s | latency_ms_mean | latency_ms_p95 | db_total_ops | cache_hit_rate | write_back_pending_max |
|----------|---------|------------------|-----------------|----------------|--------------|----------------|------------------------|
| cache-aside | read-heavy | pending | pending | pending | pending | pending | n/a |
| cache-aside | balanced | pending | pending | pending | pending | pending | n/a |
| cache-aside | write-heavy | pending | pending | pending | pending | pending | n/a |
| write-through | read-heavy | pending | pending | pending | pending | pending | n/a |
| write-through | balanced | pending | pending | pending | pending | pending | n/a |
| write-through | write-heavy | pending | pending | pending | pending | pending | n/a |
| write-back | read-heavy | pending | pending | pending | pending | pending | pending |
| write-back | balanced | pending | pending | pending | pending | pending | pending |
| write-back | write-heavy | pending | pending | pending | pending | pending | pending |

## Описание тестов

Используется единый генератор нагрузки, который:

- работает заданное количество секунд
- случайно выбирает ключи в одном и том же диапазоне
- выполняет операции чтения и записи по заданной доле
- считает `throughput`, `latency`, обращения к БД и `cache hit rate`

## Выводы

### Для чтения

Заполнить после прогонов.

### Для записи

Заполнить после прогонов.

### Для смешанной нагрузки

Заполнить после прогонов.

## Логи и скрины

Во время `run` и `matrix` команды печатают строки прогресса в консоль. По этим логам можно сделать скрины для сдачи.
