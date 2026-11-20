"""Format the eight verified arms, not an estimate of a population p95."""
import json
from pathlib import Path
from summarize import summary
base=Path(__file__).parent; ev=base/'evidence'
names=['indexed-A1','indexed-B1','indexed-B2','indexed-A2','absent-B','absent-A','wire-A','wire-B']
r=[summary(ev/n) for n in names]
def ms(n):return f'{n:.1f}'
lines=['# R20: результаты локального сравнения','',
       'Фиксированный синтетический набор. В каждом случае 4 из 100 пассивных архивов по 125 000 строк отображения и один активный turn A. Первая группа: четыре параллельных последних страницы по 50 строк. Обычный production-код Rust-клиента Desktop с настоящим 30-секундным лимитом, без графического окна. Сам /send и SSE наблюдает отдельный драйвер.','',
       '| Запуск | Окно 4 страниц, мс | Самый медленный вызов внутри Rust API, мс | PSS во время страниц, МиБ | TurnStarted ≤, мс | Первый текст, мс |',
       '|:---|---:|---:|---:|---:|---:|']
for d in r:
    meta=json.loads((ev/d['arm']/'summary.json').read_text())
    reqs=sorted(meta['desktop_api_requests'],key=lambda row:int(row['id']))[1:5]
    max_api=max(q['api_ms'] for q in reqs)
    lines.append('| '+' | '.join([d['arm'],ms(d['cold_window']['elapsed_ms']),ms(max_api),ms(d['cold_window']['peak_tree_kib']/1024),ms(d['durable_open_upper_ms']),ms(d['first_text_ms'])])+' |')
lines+=['','A = stock, B = candidate. Indexed: полный перезапуск после обычной HTTP-подготовки на тех же inode, оба штатных индекса сохранены. Absent: первый запрос к архивам без любых индексов приложения. Отдельные wire A/B добавляют перехватчик; для заявлений о скорости/памяти использовать uninstrumented строки выше. TurnStarted SSE не является сырым ACK.','']
for d in r[-2:]:
    counts=[v.get('open_snapshot',0) for v in d['restart_operations']]
    reads=[v.get('read_cache',0) for v in d['restart_operations']]
    pinned=[v.get('open_snapshot',0) for v in d['pinned_operations']]
    lines.append(f"* {d['arm']}: первый latest по архивам OpenSnapshot={counts}, ReadCache={reads}; pinned OpenSnapshot={pinned}. Реальный успешный wire ACK TurnOpened через {d['wire_turn_open_worker_ack_ms']:.1f} мс от отправки A; на эту границу ещё не вернулось {d['cold_outstanding_at_wire_ack']}/4 запросов.")
lines+=['','При готовой индексированной истории ускорение наблюдалось в обеих очередностях, но только на этом Linux-стенде; это не production percentile. Снижение памяти на готовом пути не доказано. При отсутствии индекса отдельный B/A не ускорил полный replay; ожидание активной сессии сохраняется. Здесь не тестируются аварийное питание, перенос каталогов или конкурентная порча диска.','',
'Доказательства: три проверенные страницы на архив (последние 50, первые 50 по pinned revision, последние 50 повторно), обе роли, ID и текст всех возвращённых строк, равенство исходного digest архивов, неизменность 96 невыбранных, четыре реальные загрузки HEAD при подготовленной истории, целостность turn A и канонического model prompt. Все исходные raw JSON, таймстемпы, идентификаторы бинарников, драйвер и стенд приложены. Готовая проекция уже работала в stock; результат двух разных приёмов (подготовка vs исправление чтения) не складывать.']
(base/'RESULTS-RU.md').write_text('\n'.join(lines)+'\n')
