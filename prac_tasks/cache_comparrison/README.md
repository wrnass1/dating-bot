# Cache comparison practice

Практика из `cache-comparison-practice.md`: одна и та же система чтения/записи данных реализована с тремя стратегиями кеширования:

- `cache-aside`
- `write-through`
- `write-back`

Во всех случаях используются одни и те же:

- PostgreSQL как БД
- Redis как кеш
- набор данных
- генератор нагрузки
- профили нагрузки

## Структура решения

- `src/cli.py` - команды запуска
- `src/bench.py` - общий бенчмарк
- `src/strategies.py` - три стратегии кеширования
- `src/db.py` - работа с PostgreSQL и подсчет обращений в БД
- `src/metrics.py` - измерение latency и hit rate
- `results/` - результаты прогонов
- `report/report.md` - итоговый отчет

## Шаги выполнения

1. Поднять инфраструктуру:

```bash
cd prac_tasks/cache_comparrison
docker compose up -d
```

2. Установить зависимости:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

3. Инициализировать таблицу и базовый набор данных:

```bash
./.venv/bin/python -m src.cli init-db --dataset-size 1000
```

4. Прогнать одну стратегию на одном профиле:

```bash
./.venv/bin/python -m src.cli run --strategy cache-aside --profile read-heavy --duration-s 20
```

5. Прогнать все стратегии на всех профилях и сохранить общую таблицу:

```bash
./.venv/bin/python -m src.cli matrix --duration-s 20
```

6. Перенести результаты из `results/` в `report/report.md` и добавить скрины консоли.

## Профили нагрузки

- `read-heavy` = `80% read / 20% write`
- `balanced` = `50% read / 50% write`
- `write-heavy` = `20% read / 80% write`

## Что измеряется

- `throughput_req_s`
- `latency_ms_mean`
- `latency_ms_p95`
- `db_reads`
- `db_writes`
- `db_total_ops`
- `cache_hit_rate`
- `cache_hits`
- `cache_misses`

Для `write-back` дополнительно:

- `write_back_flushes`
- `write_back_items_flushed`
- `write_back_pending_max`
- `write_back_pending_final`

## Быстрые команды

Один прогон:

```bash
./.venv/bin/python -m src.cli run --strategy write-through --profile balanced --duration-s 15
```

Полная матрица:

```bash
./.venv/bin/python -m src.cli matrix --duration-s 20 --dataset-size 1000 --key-space 200
```

## Где результаты

- `results/matrix_*.csv` - сводная таблица
- `results/matrix_*.jsonl` - сырые результаты
- `report/report.md` - отчет
