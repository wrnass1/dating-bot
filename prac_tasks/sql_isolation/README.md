# SQL isolation practice

Практика по аномалиям изоляции транзакций в SQL.

Используется `MySQL 8.4` с движком `InnoDB`, потому что он позволяет наглядно показать все четыре аномалии из задания:

- `dirty read`
- `non-repeatable read`
- `phantom read`
- `lost update`

## Запуск БД

```bash
cd prac_tasks/sql_isolation
docker compose up -d
```

Подключение:

```bash
docker exec -it sql-isolation-mysql mysql -uroot -proot isolation_lab
```

## Инициализация таблиц

```bash
docker exec -i sql-isolation-mysql mysql -uroot -proot isolation_lab < sql/00_schema.sql
```

## Как запускать сценарии

Для каждой аномалии открой два терминала MySQL:

```bash
docker exec -it sql-isolation-mysql mysql -uroot -proot isolation_lab
```

В терминале `A` выполняй файл `*_session_a.sql` по шагам.
В терминале `B` выполняй файл `*_session_b.sql` по шагам.

Порядок шагов указан комментариями внутри каждого файла.

## Структура

- `sql/00_schema.sql` - создание таблиц и начальных данных.
- `scenarios/` - сценарии для двух параллельных транзакций.
- `results/expected-results.md` - ожидаемые результаты выполнения.
- `report/report.md` - итоговый отчет.
