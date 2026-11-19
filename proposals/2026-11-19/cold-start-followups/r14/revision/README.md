# История A не должна получать строки B

Патч `validated-display-revision-on-packs.patch` — совместимый с #222 перенос уже существующего R9. **Не применяйте оба.** Производственная логика и тест R9 сохранены; тест перемещён из конца файла, куда #222 добавил собственные тесты. Это не перенос записи в фон. Проект следующего шага и ограничения описаны в [READY-DESIGN.md](READY-DESIGN.md).

Локальная база #222: `68eaace25670935f5a87274337c6977df6a961a4` поверх `2aad0ba29311f0dbf7c107efc281abc1202ce4c4`. Проверен `git apply --check` на #222 и после двух изменений Core R13 (компактный PrefixIdentities и потоковый рендер history-only). Остальные изменения для этого не нужны. В своём checkout:

```sh
git apply --check /path/to/validated-display-revision-on-packs.patch
git apply /path/to/validated-display-revision-on-packs.patch
python3 scripts/test.py -p proteus-core --lib prepared_view_never_mixes_an_older_summary_with_a_newer_transcript
```

Детерминированный тест останавливает логический порядок между подготовкой проверенного A и рендером: другой читатель успевает записать и опубликовать B. На #222 результат без исправления — новый последний текст `message-1-0` при старой статистике A (ожидался `message-0-50`). После исправления проверяются оба случая: именованная страница A сохранилась или отсутствует. Во втором случае Core возвращает проверенную историю A без ложного курсора.

Повторная сборка включала настоящие модули Core remote storage и transcript с контролируемым storage fixture, а не сборку полного приложения. В [native-after.log](native-after.log) 59/59 тестов прошли на #222 + перенос, в [native-combo.log](native-combo.log) 63/63 на #222 + два изменения Core R13 + перенос; [native-before.log](native-before.log) воспроизводит отказ без переноса. Новые native AppServer/GUI/backend-process тесты именно этого стека в этих результатах не заявляются. `interleavings.py` и [model-results.txt](model-results.txt) относятся **только к дизайну следующего шага**, отдельно от этих тестов Rust.
