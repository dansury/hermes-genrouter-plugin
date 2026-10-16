# GenRouter для [Hermes Agent](https://github.com/NousResearch/hermes-agent)

[English documentation](README.md) · [Описание API](docs/API.md) · [Документация Hermes по провайдерам](https://hermes-agent.nousresearch.com/docs/integrations/providers)

Репозиторий содержит независимый сторонний плагин провайдера **GenRouter** для [Hermes Agent](https://github.com/NousResearch/hermes-agent) и companion-плагин: регистрация, подтверждение почты, ключи, остатки и выбор моделей.

## Интеграция с Hermes Agent

Для установки Hermes, выбора провайдера и справочника встроенных провайдеров используйте официальную [документацию Hermes по LLM-провайдерам](https://hermes-agent.nousresearch.com/docs/integrations/providers). GenRouter не аффилирован с Nous Research.

## Установка

Нужен установленный Hermes Agent. Локально проверено с Hermes **0.21.6**, Python **3.11**, Windows. CI проверяет клиент на Windows/Linux с Python 3.11–3.13.

```shell
hermes plugins install dansury/hermes-genrouter-plugin --enable
hermes plugins install https://github.com/dansury/hermes-genrouter-plugin/tree/main/account --enable
```

Первая часть добавляет вендора `genrouter-ru`. Вторая — команды `hermes genrouter`, `/genrouter` и инструменты чтения. Для другого профиля используйте `hermes -p <профиль> ...`.

Ранее установленный вручную `plugins/model-providers/genrouter-ru` использует тот же адрес и переменную ключа. Запись `providers.genrouter` — отдельный custom endpoint; выбирайте вендора **GenRouter / genrouter-ru**.

## Существующий ключ

```shell
hermes auth add genrouter-ru --type api-key
hermes model
```

Введите ключ скрыто, выберите **GenRouter** и нужную модель. По умолчанию предлагается `anthropic/claude-opus-5`. Адрес плагина: `https://api.genrouter.ru/v1`. Для Anthropic SDK нужен `https://api.genrouter.ru` без `/v1`.

Можно добавить `GENROUTER_API_KEY=ваш-ключ` в `.env` профиля: обычно `%LOCALAPPDATA%\hermes\.env` на Windows, `~/.hermes/.env` на Linux/macOS. Не добавляйте файл в Git. Каталог и прямая диагностика companion-плагина без входа в кабинет читают эту переменную, а не пул ключей Hermes; используйте `.env`, если нужны эти команды с имеющимся ключом.

## Регистрация и первый ключ

В локальном интерактивном терминале:

```shell
hermes genrouter setup --register --nickname your_nickname --email you@example.com
```

Мастер попросит принять условия GenRouter, скрыто введёт пароль, отправит письмо, примет шестизначный код, создаст ключ `Hermes`, подключит его и выберет модель. Доступ к почтовому ящику не нужен — пользователь вводит код.

Текущая регистрация GenRouter требует **ник и пароль**, почта привязывается отдельным запросом. Пароль и код не сохраняются и не передаются аргументами команд.

Для существующего аккаунта:

```shell
hermes genrouter setup --nickname your_nickname --key-name Hermes
```

Если одноимённый ключ существует, но секрет неизвестен плагину, мастер не заменит его. Задайте другое имя или импортируйте ключ через `hermes auth add genrouter-ru`.

Если аккаунт создан, а письмо не пришло, не регистрируйтесь повторно:

```shell
hermes genrouter login --nickname your_nickname
hermes genrouter email-request --email you@example.com
hermes genrouter email-confirm
```

## Модели и ключи

```shell
hermes genrouter status
hermes genrouter keys list
hermes genrouter models
hermes genrouter select anthropic/claude-opus-5
hermes genrouter keys create --name Cursor --confirm
hermes genrouter keys show --name Cursor --reveal
```

Выбор проверяет модель по живому каталогу; image/video-модели не устанавливаются как чат-модель. Выданный ключ сначала сохраняется приватно. Полный секрет показывается только по `--reveal` в локальном интерактивном терминале. Создание ключа `Cursor` не меняет ключ Hermes; для этого есть `keys use --name Hermes`.

Новый ключ по умолчанию получает **нулевой баланс**. Перенести имеющиеся деньги из кошелька на ключ:

```shell
hermes genrouter keys fund --id KEY_ID --amount-usd 5 --confirm
```

Суммы задаются в USD, максимум шесть знаков после точки. API использует микродоллары: `1_000_000 = $1`. Отдельно показываются доступный баланс, резерв, расходы и число запросов. Лимиты RPM/TPM и сроки сброса API не раскрывает — они остаются неизвестными. Новые ключи не пополняют кошелёк и не обходят ограничения.

В чате: `/genrouter status`, `/genrouter keys`, `/genrouter models`, `/genrouter payments`. Инструменты: `genrouter_account_status`, `genrouter_key_balances`, `genrouter_models`. Они только читают данные. Запись выполняется локальными CLI-командами с подтверждением. Пароли, коды и полные ключи не передаются агенту как аргументы или ответы инструментов.

## Проверка подключения

```shell
hermes genrouter probe --model anthropic/claude-opus-5
```

Небольшой платный запрос отправляется напрямую в GenRouter, с `max_tokens: 16`, без резервных провайдеров. Успех — точный ответ `GENROUTER_OK`. Ошибка `HTTP 402` может прийти как от GenRouter, так и от поставщика. Плагин показывает очищенное сообщение и сохраняет `request_id`; пополнение не предлагается автоматически при каждом `402`. Обычный `hermes chat` может получить ответ от fallback и не доказывает работу GenRouter.

При разработке ключ видел 26 моделей, включая указанную Opus, но генерация вернула **HTTP 402**. Для проверки ответа нужен ключ с достаточным балансом. При расширении плагина реальные аккаунты, ключи и платежи не создавались.

## Будущая оплата

```shell
hermes genrouter payments
```

Флаг сервера отображается отдельно от готовности плагина; включённый `payments_enabled` не доказывает работу оплаты. Checkout отключён, пока явно не задано `GENROUTER_ENABLE_CHECKOUT=1` и не подтверждена сумма:

```shell
hermes genrouter checkout --amount-usd 5 --method card --confirm
```

Используйте после подтверждения контракта разработчиками. Плагин возвращает HTTPS-ссылку на платёжную страницу, оплату совершает пользователь. Данные карты он не принимает, создание ссылки не считает оплатой. Автосписаний, автопополнения и платёжных webhook нет.

## Подписка ChatGPT

```shell
hermes auth add openai-codex --type oauth --browser
```

После входа выберите доступную аккаунту Codex-модель через `hermes model` или добавьте её через `hermes fallback add`, оставив GenRouter основным. OAuth подписки не требует OpenAI API key и не пополняет GenRouter.

## Хранение и ограничения

Сессия кабинета и выданные ключи хранятся вне репозитория, в `plugin-data/genrouter-account/credentials.secrets` профиля. Windows использует **DPAPI** для текущего пользователя. Linux/macOS — приватный файл `0600`, директория `0700`, без шифрования содержимого. Inference-ключ в `.env` остаётся текстовым секретом Hermes.

HTTPS-запросы ограничены доменами GenRouter, имеют таймаут и запрет редиректов. Cookie кабинета не уходит в inference API, из ошибки сохраняются очищенное сообщение и отдельные поля диагностики, без сырого тела ответа. Запросы записи не повторяются автоматически: после обрыва соединения операция могла завершиться. Проверьте кабинет перед повтором. После таймаута перевода повторите тот же ключ и сумму: плагин использует сохранённый UUID. Создание ключа безопасно повторять нельзя: сначала проверьте список ключей и при необходимости явно перевыпустите секрет.

`hermes genrouter logout` завершает сессию кабинета, сохраняя выданные ключи и ключ inference. Ненужные ключи отзывайте в кабинете.

Интерфейсы аккаунта взяты из публичного кода кабинета, а не из стабильного документированного SDK. Регистрация и запись проверены с имитацией сервера, без создания живого аккаунта. Изменения GenRouter могут потребовать обновления — см. [API.md](docs/API.md).

## Разработка

```shell
python -m unittest discover -s tests -v
python -m account --help
hermes plugins validate .
hermes plugins validate ./account
hermes plugins doctor ./account --ci
```

Клиент использует стандартную библиотеку Python; загрузка плагинов требует Hermes. [Лицензия MIT](LICENSE). Проект независимый, не официальный продукт GenRouter или Nous Research.

## Обновления и сообщения об ошибках

Проверка обновлений обеих частей — **каждые 24 часа**, пока Hermes работает.
`hermes genrouter updates --force` проверяет сейчас. Установка обновлений:
`hermes plugins update genrouter-ru`, затем `hermes plugins update genrouter-account`.
`GENROUTER_UPDATE_CHECK_HOURS` меняет период в часах (24 по умолчанию, 0 отключает).
Автоматической установки нет.

Ошибки команд, инструментов и native inference сохраняются локально, с
дедубликацией; очередь ограничена 100 различными ошибками. `/genrouter report`
подсказывает, как поделиться диагностикой. В терминале:

```shell
hermes genrouter report list
hermes genrouter report preview
hermes genrouter report send
hermes genrouter report new --description "Что случилось и как повторить"
```

Перед отправкой показывается полный отчёт и запрашивается согласие.
`--confirm` — явное согласие через CLI. Если пользователь вошёл в GitHub CLI,
ему предлагают issue от своего имени. Иначе используется предоставленный
владельцем репозитория общий токен только для issues, без настройки.
Упаковка токена — обратимая маскировка, **не надёжное шифрование**.
Токен не должен иметь прав на код или администрирование; отзыв отключит общий
канал. `GENROUTER_ISSUE_TOKEN` позволяет заменить его локально.

В отчёте: версии плагина, Hermes, Python и ОС; время; команда; тип ошибки;
места в стеке; HTTP status/code, request_id, Retry-After и число повторов.
Ключи, cookies, пароли и email очищаются; переписка, полный config и сырые
HTTP payload не собираются. `--log-file путь` добавляет ограниченный фрагмент
выбранного текстового лога. Обязательно проверьте его: очистка произвольного
лога не гарантирует удаления всех личных данных.

Перед созданием issue проверяются открытые и закрытые issues по отпечатку.
POST не повторяется автоматически. Одновременные отправки с разных компьютеров
могут потребовать ручного объединения — GitHub не даёт атомарного создания по
отпечатку. При ошибке создаётся полный черновик `.eml` на
`dansury@gmail.com`: откройте, проверьте и отправьте в почтовом приложении.
Фоновой отправки писем нет.

Ник: 4–32 символа латиницы, цифры, underscore; пароль: 8–128 символов, буква и
цифра. Код почты действует 15 минут, пять попыток; повтор через минуту, пять
кодов в час. Проверка сессии: `hermes genrouter session`; сессия живёт 30 дней
без продления. Потерянный секрет:
`hermes genrouter keys rotate --id KEY_ID --confirm`; старый сразу перестаёт
работать. После таймаута ротации не повторяйте её вслепую.
